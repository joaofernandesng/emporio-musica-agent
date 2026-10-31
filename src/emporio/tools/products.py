"""Catalog tools: ``search_products`` and ``get_product``."""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from typing import Any

from emporio.build_db import strip_accents
from emporio.tools.common import (
    AVAILABILITY_LABELS,
    brl,
    brl_text,
    open_db,
    percent_of,
    to_cents,
    tokens,
)

STRING_ALIASES = {"aco": "steel", "aço": "steel", "steel": "steel", "nylon": "nylon", "nailon": "nylon"}


def active_promotion(conn: sqlite3.Connection, product_id: int, price_cents: int) -> dict | None:
    """Return the active promotion of a product, or ``None``.

    Only ``is_active = 1`` counts (the table has no dates). If several active
    rows existed, the largest discount would win.
    """
    row = conn.execute(
        """SELECT promotion_id, discount_percent, description FROM promotions
           WHERE product_id = ? AND is_active = 1
           ORDER BY discount_percent DESC LIMIT 1""",
        (product_id,),
    ).fetchone()
    if row is None:
        return None
    promo_cents = price_cents - percent_of(price_cents, row["discount_percent"])
    return {
        "discount_percent": row["discount_percent"],
        "label": row["description"],
        "original_price_brl": brl(price_cents),
        "original_price_text": brl_text(price_cents),
        "promo_price_brl": brl(promo_cents),
        "promo_price_text": brl_text(promo_cents),
    }


def effective_price_cents(price_cents: int, promotion: dict | None) -> int:
    """Price the customer pays before payment-method discounts."""
    return to_cents(promotion["promo_price_brl"]) if promotion else price_cents


def summarize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """Compact product dict used by search results and candidate lists."""
    promo = active_promotion(conn, row["product_id"], row["price_cents"])
    shown = effective_price_cents(row["price_cents"], promo)
    available = row["availability"] == "available"
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category_name"],
        "price_brl": brl(row["price_cents"]),
        "price_text": brl_text(row["price_cents"]),
        "current_price_brl": brl(shown),
        "current_price_text": brl_text(shown),
        "availability": row["availability"],
        "availability_label": AVAILABILITY_LABELS[row["availability"]],
        "stock_quantity": row["stock_quantity"] if available else None,
        "promotion": promo,
    }


_BASE_SQL = """SELECT p.*, c.name AS category_name FROM products p
               JOIN categories c USING (category_id)"""


def search_products(
    query: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    string_type: str | None = None,
    has_electronics: bool | None = None,
    include_unavailable: bool = False,
    limit: int = 20,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Search the catalog by free text and filters.

    Text matching ignores accents/case and simple plurals; every query word must
    appear in the product name, category or specs. Price filters use the price the
    customer would pay today (promotional price when a promotion is active).
    Products that are out of stock, discontinued or coming soon are hidden unless
    ``include_unavailable`` is true.

    Args:
        query: Free text such as "takamine" or "ukulele tenor".
        category: Category name or part of it ("violões", "baterias").
        min_price: Minimum current price in BRL.
        max_price: Maximum current price in BRL.
        string_type: "steel" (aço) or "nylon" (acoustic guitars/ukuleles only).
        has_electronics: True for electro-acoustic, False for purely acoustic.
        include_unavailable: Also list non-available products.
        limit: Maximum number of results (default 20).

    Returns:
        ``{"count", "results", "truncated", "notes"}`` with JSON-safe values.
    """
    notes: list[str] = []
    with open_db(conn) as db:
        rows = db.execute(_BASE_SQL + " ORDER BY p.product_id").fetchall()
        categories = db.execute("SELECT category_id, name FROM categories").fetchall()

        if category:
            wanted = set(tokens(category))
            matched = {c["category_id"] for c in categories if wanted <= set(tokens(c["name"]))}
            if not matched and category.strip().isdigit():
                matched = {int(category)}
            if not matched:
                return {"count": 0, "results": [], "truncated": False,
                        "notes": [f"No category matches '{category}'."]}
            in_category = [r for r in rows if r["category_id"] in matched]
            if not in_category:
                names = [c["name"] for c in categories if c["category_id"] in matched]
                notes.append(
                    f"Category {names} exists but the catalog has no products in it right now."
                )
            rows = in_category

        if string_type:
            wanted_type = STRING_ALIASES.get(strip_accents(string_type).strip(), string_type)
            rows = [r for r in rows if r["string_type"] == wanted_type]
        if has_electronics is not None:
            rows = [r for r in rows if r["has_electronics"] == int(bool(has_electronics))]
        if not include_unavailable:
            rows = [r for r in rows if r["availability"] == "available"]
        if query:
            wanted = set(tokens(query))
            rows = [
                r for r in rows
                if wanted <= set(tokens(r["name"] + " " + r["category_name"] + " " + _spec_text(r)))
            ]

        results = [summarize(db, r) for r in rows]

    if min_price is not None:
        results = [r for r in results if r["current_price_brl"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["current_price_brl"] <= max_price]
    results.sort(key=lambda r: (r["current_price_brl"], r["product_id"]))
    return {
        "count": len(results),
        "results": results[:limit],
        "truncated": len(results) > limit,
        "notes": notes,
    }


def _spec_text(row: sqlite3.Row) -> str:
    return " ".join(str(v) for v in json.loads(row["specs_json"]).values())


def _compact(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", strip_accents(text))


def get_product(
    product_id: int | None = None,
    name: str | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Get full details of one product by id or by (approximate) name.

    Name lookup tolerates case, accents, plurals and spacing ("takamine gd 20").
    If several products match, ``status`` is ``"ambiguous"`` and ``candidates``
    lists them. The free-text description is returned only when it does not
    contradict the product name/specs.

    Args:
        product_id: Exact product id.
        name: Product name or part of it.

    Returns:
        ``{"status": "found"|"ambiguous"|"not_found", "product"?, "candidates"?}``.
    """
    with open_db(conn) as db:
        if product_id is not None:
            row = db.execute(_BASE_SQL + " WHERE p.product_id = ?", (product_id,)).fetchone()
            return _found(db, row) if row else {"status": "not_found", "candidates": []}
        if not name or not name.strip():
            return {"status": "not_found", "candidates": [],
                    "notes": ["Provide product_id or name."]}

        rows = db.execute(_BASE_SQL + " ORDER BY p.product_id").fetchall()
        wanted = set(tokens(name))
        hits = [r for r in rows if wanted <= set(tokens(r["name"]))]
        if not hits:  # "gd 20" vs "gd20": compare without separators
            compact = _compact(name)
            hits = [r for r in rows if compact and compact in _compact(r["name"])]
        if not hits:  # typo tolerance
            scored = sorted(
                ((difflib.SequenceMatcher(None, _compact(name), _compact(r["name"])).ratio(), r)
                 for r in rows),
                key=lambda x: -x[0],
            )
            close = [r for score, r in scored[:3] if score >= 0.5]
            return {"status": "not_found",
                    "candidates": [summarize(db, r) for r in close]}
        if len(hits) > 1:
            exact = [r for r in hits if set(tokens(r["name"])) == wanted]
            if len(exact) == 1:
                hits = exact
        if len(hits) == 1:
            return _found(db, hits[0])
        return {"status": "ambiguous", "candidates": [summarize(db, r) for r in hits[:8]]}


def _found(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    product = summarize(db, row)
    product["specs"] = json.loads(row["specs_json"])
    product["description_reliable"] = bool(row["description_reliable"])
    if row["description_reliable"]:
        product["description"] = row["description"]
    else:
        product["description_note"] = (
            "Catalog description contradicts the product name/specs and was withheld; "
            "use only the name, price, availability and specs."
        )
    return {"status": "found", "product": product}

