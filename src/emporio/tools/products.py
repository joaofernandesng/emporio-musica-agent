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


# ---- accessories: the store sells instruments only (manual 1 and 7.1) ----------------
# Normalised (no accents, plural folded) query words that mean an accessory.
ACCESSORY_TERMS = {
    "corda", "encordoamento", "cabo", "palheta", "pedal", "amplificador", "case", "capa",
    "bag", "afinador", "estante", "baqueta", "correia",
}
NUMBER_WORDS = {"seis", "sete", "oito", "nove", "dez", "onze", "doze"}
# "violao com afinador integrado" asks for an instrument feature, not the accessory.
QUALIFIER_BEFORE = {"com", "c"}
QUALIFIER_AFTER = {"integrado", "embutido", "interno", "incluso"}
ACCESSORY_MESSAGE = (
    "A Empório da Música trabalha exclusivamente com instrumentos musicais: não vende "
    "acessórios como cordas, cabos, palhetas, pedais, amplificadores, cases, capas, "
    "afinadores, estantes, baquetas ou correias."
)


def _singular(word: str) -> str:
    """Fold the Portuguese plurals that ``tokens`` leaves behind: pedai(s) -> pedal,
    amplificadore(s) -> amplificador."""
    if word.endswith("ai") and len(word) > 3:
        return word[:-1] + "l"
    if word.endswith("ore") and len(word) > 4:
        return word[:-1]
    return word


def accessory_terms(query: str | None) -> list[str]:
    """Accessory words in ``query`` (empty when it asks for an instrument).

    Plurals are recognised ("pedais", "amplificadores", "cabos"). Ignored: "cordas"
    after a number ("7 cordas", "sete cordas": a string count), and a term used as
    a feature of an instrument ("com afinador integrado").
    "caixa amplificada" counts as an amplifier; "caixa" alone (snare drum) does not.
    """
    words = [_singular(w) for w in tokens(query or "")]
    found: list[str] = []
    for i, word in enumerate(words):
        is_term = word in ACCESSORY_TERMS or (word == "amplificada" and "caixa" in words)
        if not is_term:
            continue
        before = words[i - 1] if i else ""
        after = words[i + 1] if i + 1 < len(words) else ""
        if word == "corda" and (before.isdigit() or before in NUMBER_WORDS):
            continue
        if before in QUALIFIER_BEFORE or (i > 1 and words[i - 2] in QUALIFIER_BEFORE) or after in QUALIFIER_AFTER:
            continue
        found.append(word)
    return found


def alternatives_for(db: sqlite3.Connection, row: sqlite3.Row, limit: int = 3) -> list[dict[str, Any]]:
    """Up to ``limit`` AVAILABLE products to suggest instead of an unavailable one.

    Same category, same ``string_type`` when the product has one, and the same
    string-count marker in the name ("7 Cordas"; the count is not a structured
    spec, so the name is the source of truth), closest current price first.
    """
    def marker(name: str) -> str | None:
        m = re.search(r"\b(\d+) cordas\b", strip_accents(name).lower())
        return m.group(1) if m else None

    wanted = marker(row["name"])
    pool = [
        r for r in db.execute(_BASE_SQL + " WHERE p.category_id = ? AND p.availability = 'available'",
                              (row["category_id"],)).fetchall()
        if r["product_id"] != row["product_id"]
        and r["string_type"] == row["string_type"]
        and marker(r["name"]) == wanted
    ]
    items = [summarize(db, r) for r in pool]
    items.sort(key=lambda a: (abs(a["current_price_brl"] - brl(row["price_cents"])), a["product_id"]))
    return items[:limit]


def _attach_alternatives(db: sqlite3.Connection, row: sqlite3.Row, target: dict[str, Any]) -> None:
    if row["availability"] == "available":
        return
    target["alternatives"] = alternatives_for(db, row)
    if not target["alternatives"]:
        target["alternatives_note"] = "Não há produto disponível equivalente no catálogo agora."


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
        "discount_brl": brl(price_cents - promo_cents),
        "discount_text": brl_text(price_cents - promo_cents),
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
    on_promotion: bool | None = None,
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
        on_promotion: True keeps only products with an active promotion
            (False/None: no filter).

    Returns:
        ``{"count", "total_count", "returned_count", "results", "truncated",
        "notes"}``. ``total_count`` is the number of matches before ``limit``;
        when ``truncated`` the list is incomplete and a note says so.
    """
    notes: list[str] = []
    matched_terms = accessory_terms(query)
    if matched_terms:
        return {"count": 0, "results": [], "truncated": False, "notes": [],
                "not_sold_accessory": True, "matched_terms": matched_terms,
                "message": ACCESSORY_MESSAGE}
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

        results = []
        for r in rows:
            item = summarize(db, r)
            _attach_alternatives(db, r, item)
            results.append(item)

    if on_promotion:
        results = [r for r in results if r["promotion"]]
    if min_price is not None:
        results = [r for r in results if r["current_price_brl"] >= min_price]
    if max_price is not None:
        results = [r for r in results if r["current_price_brl"] <= max_price]
    results.sort(key=lambda r: (r["current_price_brl"], r["product_id"]))
    shown = results[:limit]
    truncated = len(results) > limit
    if truncated:
        notes.append(
            f"Lista incompleta: {len(results)} produtos correspondem, só {len(shown)} foram "
            "devolvidos (ordenados por preço). Não conclua que algo não existe nem fale em "
            "'todos' ou 'nenhum' com base nesta lista: refine a busca (on_promotion=true, "
            "faixa de preço, tipo de corda) ou diga quantos há e ofereça um filtro."
        )
    return {
        "count": len(results),
        "total_count": len(results),
        "returned_count": len(shown),
        "results": shown,
        "truncated": truncated,
        "notes": notes,
    }


# Words a customer puts around a product name: articles and generic nouns.
NAME_FILLERS = {"o", "a", "os", "as", "um", "uma", "do", "da", "de", "modelo", "instrumento"}
# Everyday names of the categories, folded like ``tokens`` does.
CATEGORY_SYNONYMS = {
    1: {"guitarra"}, 2: {"baixo", "contrabaixo"}, 3: {"bateria", "percussao"},
    4: {"teclado", "piano", "sintetizador"}, 5: {"violao"}, 9: {"ukulele", "uke"},
}


def _category_words(db: sqlite3.Connection) -> set[str]:
    words = {w for s in CATEGORY_SYNONYMS.values() for w in s}
    for (name,) in db.execute("SELECT name FROM categories"):
        words |= set(tokens(name))
    return words - NAME_FILLERS


def _category_words_of(row: sqlite3.Row) -> set[str]:
    return set(tokens(row["category_name"])) | CATEGORY_SYNONYMS.get(row["category_id"], set())


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
        if not hits:  # "o violão Takamine GD20": drop articles and category words
            category_words = wanted & _category_words(db)
            core = wanted - category_words - NAME_FILLERS
            if core and core != wanted:
                hits = [r for r in rows if core <= set(tokens(r["name"]))]
                in_category = [r for r in hits if category_words <= _category_words_of(r)]
                if hits and not in_category:  # "guitarra Takamine": no such guitar
                    return {"status": "not_found",
                            "candidates": [summarize(db, r) for r in hits[:3]]}
                hits, wanted = in_category, core
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
    _attach_alternatives(db, row, product)
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

