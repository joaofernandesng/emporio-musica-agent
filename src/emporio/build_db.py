"""Build ``data/runtime/store.db`` (SQLite) from the raw CSV files.

Raw files are never modified. Every correction is expressed as a derived column
or flag (``availability``, ``description_reliable``, ``items_list_total_cents``,
...), so the original values stay available next to the interpreted ones.

Run with: ``python -m emporio.build_db``
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from emporio.paths import DB_PATH, RAW_DIR

# Logical table name -> real file name inside data/raw (names have spaces).
RAW_FILES = {
    "categories": "desafio_tecnico_ai_eng - categories.csv",
    "customers": "desafio_tecnico_ai_eng - customers.csv",
    "order_items": "desafio_tecnico_ai_eng - order_items.csv",
    "orders": "desafio_tecnico_ai_eng - orders.csv",
    "products": "desafio_tecnico_ai_eng - products.csv",
    "promotions": "desafio_tecnico_ai_eng - promotions.csv",
}

# Raw status + stock -> what the agent may tell the customer.
AVAILABLE = "available"
OUT_OF_STOCK = "out_of_stock"
DISCONTINUED = "discontinued"
COMING_SOON = "coming_soon"

# Brands appearing in product names; used to detect descriptions that talk
# about another brand than the product name.
BRANDS = [
    "yamaha", "tagima", "giannini", "rozini", "shelby", "crafter", "martin",
    "taylor", "takamine", "kala", "ohana", "kalani", "fender", "gibson",
    "ibanez", "prs", "music man", "korg", "nord", "roland", "pearl", "tama",
]
# Model names that identify a brand without naming it.
MODEL_ALIASES = {"jazz bass": "fender", "precision": "fender", "stingray": "music man"}

SCHEMA = """
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);
CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT,
    phone_digits TEXT,      -- derived: digits only
    email        TEXT,
    email_norm   TEXT,      -- derived: trimmed + lowercase
    city         TEXT
);
CREATE TABLE products (
    product_id           INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL,
    category_id          INTEGER NOT NULL REFERENCES categories(category_id),
    description          TEXT,
    price_cents          INTEGER NOT NULL,
    stock_quantity       INTEGER NOT NULL,
    status_raw           TEXT NOT NULL,
    availability         TEXT NOT NULL,   -- derived: available/out_of_stock/discontinued/coming_soon
    specs_json           TEXT NOT NULL,   -- parsed + re-serialised JSON
    string_type          TEXT,            -- derived from specs.strings (steel/nylon)
    has_electronics      INTEGER,         -- derived from specs.electronics (1/0/NULL)
    description_reliable INTEGER NOT NULL,-- derived: 0 when description contradicts name/specs
    description_issues   TEXT,            -- derived: why description_reliable = 0
    created_at           TEXT
);
CREATE TABLE promotions (
    promotion_id     INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent INTEGER NOT NULL,
    description      TEXT,
    is_active        INTEGER NOT NULL
);
CREATE TABLE orders (
    order_id                INTEGER PRIMARY KEY,
    customer_id             INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date              TEXT NOT NULL,
    status                  TEXT NOT NULL,
    total_cents             INTEGER NOT NULL,
    payment_method          TEXT,
    tracking_code           TEXT,
    estimated_delivery      TEXT,
    notes                   TEXT,
    items_list_total_cents  INTEGER,   -- derived: sum(current list price x qty)
    total_matches_list      INTEGER    -- derived: total_cents == items_list_total_cents
);
CREATE TABLE order_items (
    item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL
);
"""


def to_cents(value: str) -> int:
    """Convert a decimal string such as ``"799.9"`` to integer cents."""
    return int((Decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def strip_accents(text: str) -> str:
    """Lowercase ``text`` and remove accents."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def read_csv(table: str, raw_dir: Path = RAW_DIR) -> list[dict[str, str]]:
    """Read one raw CSV as a list of dicts (UTF-8)."""
    with open(raw_dir / RAW_FILES[table], newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _brands_in(text: str) -> set[str]:
    norm = strip_accents(text)
    found = {b for b in BRANDS if re.search(rf"\b{re.escape(b)}\b", norm)}
    found |= {brand for model, brand in MODEL_ALIASES.items() if model in norm}
    return found


def description_issues(name: str, description: str, specs: dict) -> list[str]:
    """Return reasons why a description contradicts the product name or specs.

    Two deterministic checks: (1) the description names a brand that is not in
    the product name; (2) a count in the description ("88 teclas",
    "5 cordas") differs from the numeric spec of the same attribute.
    """
    issues = []
    name_brands = _brands_in(name)
    extra = _brands_in(description) - name_brands
    if extra:
        issues.append(
            f"description mentions brand(s) {sorted(extra)} but the name says {sorted(name_brands)}"
        )
    for pattern, key, label in (
        (r"(\d+)\s+teclas", "keys", "keys"),
        (r"(\d+)\s+cordas", "strings", "strings"),
    ):
        match = re.search(pattern, description)
        spec = str(specs.get(key, ""))
        if match and spec.isdigit() and match.group(1) != spec:
            issues.append(f"description says {match.group(1)} {label} but specs say {spec}")
    return issues


def availability(status: str, stock: int) -> str:
    """Normalise raw status + stock into one customer-facing availability."""
    if status == "discontinued":
        return DISCONTINUED
    if status == "coming_soon":
        return COMING_SOON
    return AVAILABLE if stock > 0 else OUT_OF_STOCK


def _load_products(conn: sqlite3.Connection, raw_dir: Path) -> None:
    for row in read_csv("products", raw_dir):
        specs = json.loads(row["specs"])
        issues = description_issues(row["name"], row["description"], specs)
        electronics = specs.get("electronics")
        strings = specs.get("strings")
        conn.execute(
            "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                int(row["product_id"]),
                row["name"],
                int(row["category_id"]),
                row["description"],
                to_cents(row["price_brl"]),
                int(row["stock_quantity"]),
                row["status"],
                availability(row["status"], int(row["stock_quantity"])),
                json.dumps(specs, ensure_ascii=False, sort_keys=True),
                strings if strings in ("steel", "nylon") else None,
                None if electronics is None else int(electronics == "yes"),
                0 if issues else 1,
                "; ".join(issues) or None,
                row["created_at"],
            ),
        )


def build(db_path: Path = DB_PATH, raw_dir: Path = RAW_DIR) -> Path:
    """(Re)create the SQLite database from the raw CSVs and return its path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for r in read_csv("categories", raw_dir):
            conn.execute(
                "INSERT INTO categories VALUES (?,?,?)",
                (int(r["category_id"]), r["name"], r["description"]),
            )
        for r in read_csv("customers", raw_dir):
            conn.execute(
                "INSERT INTO customers VALUES (?,?,?,?,?,?,?)",
                (
                    int(r["customer_id"]), r["name"], r["phone"],
                    re.sub(r"\D", "", r["phone"]), r["email"],
                    r["email"].strip().lower(), r["city"],
                ),
            )
        _load_products(conn, raw_dir)
        for r in read_csv("promotions", raw_dir):
            conn.execute(
                "INSERT INTO promotions VALUES (?,?,?,?,?)",
                (
                    int(r["promotion_id"]), int(r["product_id"]),
                    int(r["discount_percent"]), r["description"], int(r["is_active"]),
                ),
            )
        for r in read_csv("orders", raw_dir):
            conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)",
                (
                    int(r["order_id"]), int(r["customer_id"]), r["order_date"],
                    r["status"], to_cents(r["total_brl"]), r["payment_method"] or None,
                    r["tracking_code"] or None, r["estimated_delivery"] or None,
                    r["notes"] or None,
                ),
            )
        for r in read_csv("order_items", raw_dir):
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?,?,?)",
                (int(r["order_id"]), int(r["product_id"]), int(r["quantity"])),
            )
        conn.execute(
            """UPDATE orders SET items_list_total_cents = (
                   SELECT SUM(p.price_cents * i.quantity)
                   FROM order_items i JOIN products p USING (product_id)
                   WHERE i.order_id = orders.order_id)"""
        )
        conn.execute(
            "UPDATE orders SET total_matches_list = (total_cents = items_list_total_cents)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the store database, building it first if it does not exist."""
    if not db_path.exists():
        build(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    path = build()
    with sqlite3.connect(path) as c:
        for table in RAW_FILES:
            count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count} rows")
    print(f"database written to {path}")
