"""Data layer: SQLite build, derived columns and flags."""

import json


def test_row_counts(conn):
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("categories", "customers", "products", "promotions", "orders", "order_items")
    }
    assert counts == {"categories": 9, "customers": 50, "products": 65,
                      "promotions": 25, "orders": 20, "order_items": 22}


def test_prices_are_integer_cents(conn):
    row = conn.execute("SELECT price_cents FROM products WHERE product_id = 96").fetchone()
    assert row["price_cents"] == 79990


def test_specs_are_valid_json(conn):
    for row in conn.execute("SELECT specs_json FROM products"):
        assert isinstance(json.loads(row["specs_json"]), dict)


def test_availability_states(conn):
    states = dict(conn.execute("SELECT product_id, availability FROM products").fetchall())
    assert states[96] == "out_of_stock"      # active with stock 0
    assert states[113] == "discontinued"
    assert states[136] == "discontinued"      # discontinued even with stock 13
    assert states[130] == "coming_soon"       # coming soon even with stock 2
    assert states[95] == "available"


def test_unreliable_descriptions_are_flagged(conn):
    flagged = {r[0] for r in conn.execute(
        "SELECT product_id FROM products WHERE description_reliable = 0")}
    assert flagged == {135, 136, 137, 139, 140, 142, 144}
    assert conn.execute("SELECT COUNT(*) FROM products WHERE product_id = 95 "
                        "AND description_reliable = 1").fetchone()[0] == 1


def test_order_total_mismatches_are_exactly_orders_3_and_20(conn):
    bad = {r[0] for r in conn.execute("SELECT order_id FROM orders WHERE total_matches_list = 0")}
    assert bad == {3, 20}


def test_empty_categories(conn):
    empty = {r[0] for r in conn.execute(
        """SELECT category_id FROM categories WHERE category_id NOT IN
           (SELECT category_id FROM products)""")}
    assert empty == {6, 7, 8}


def test_derived_contact_columns(conn):
    row = conn.execute("SELECT phone_digits, email_norm FROM customers WHERE customer_id = 2").fetchone()
    assert row["phone_digits"] == "67996547821"
    assert row["email_norm"] == "anacarol.ferreira@coldmail.com"
