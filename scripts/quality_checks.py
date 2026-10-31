"""Compute the evidence quoted in docs/data_quality.md.

Run with: ``python scripts/quality_checks.py [YYYY-MM-DD]`` (reference date for
the "overdue" check; defaults to today in America/Campo_Grande).
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from emporio.build_db import build, connect, read_csv  # noqa: E402


def show(title: str, rows) -> None:
    """Print a titled result set."""
    rows = [tuple(r) for r in rows]
    print(f"\n## {title} ({len(rows)} rows)")
    for r in rows:
        print("  ", r)


def main() -> None:
    today = (
        date.fromisoformat(sys.argv[1])
        if len(sys.argv) > 1
        else datetime.now(ZoneInfo("America/Campo_Grande")).date()
    )
    build()
    db = connect()
    q = lambda sql, *a: db.execute(sql, a).fetchall()  # noqa: E731
    print(f"reference date: {today}")

    # ---- catalog -------------------------------------------------------
    show("products per category (all categories)", q(
        """SELECT c.category_id, c.name, COUNT(p.product_id) FROM categories c
           LEFT JOIN products p USING (category_id) GROUP BY 1 ORDER BY 1"""))
    print("\ntotal products:", q("SELECT COUNT(*) FROM products")[0][0])
    ids = [int(r["product_id"]) for r in read_csv("products")]
    print("CSV product_id order out of sequence:",
          [(a, b) for a, b in zip(ids, ids[1:]) if b != a + 1])
    show("availability counts", q("SELECT availability, COUNT(*) FROM products GROUP BY 1"))
    show("non-available products", q(
        """SELECT product_id, name, status_raw, stock_quantity, availability
           FROM products WHERE availability != 'available'"""))
    show("sellable-looking stock on non-available products (stock>0)", q(
        "SELECT product_id, status_raw, stock_quantity FROM products "
        "WHERE availability IN ('discontinued','coming_soon') AND stock_quantity > 0"))
    show("description contradicts name/specs", q(
        "SELECT product_id, name, description_issues FROM products WHERE description_reliable=0"))
    show("products 135-144 with NO detectable description conflict", q(
        "SELECT product_id, name FROM products WHERE product_id BETWEEN 135 AND 144 "
        "AND description_reliable=1"))
    show("name says Aço/Nylon but specs.strings differs", q(
        """SELECT product_id, name, string_type FROM products WHERE category_id IN (5,9) AND
           ((name LIKE '%Aço%' AND string_type!='steel') OR (name LIKE '%Nylon%' AND string_type!='nylon'))"""))
    show("name says Elétrico but specs.electronics != yes", q(
        "SELECT product_id, name, has_electronics FROM products "
        "WHERE name LIKE '%Elétrico%' AND COALESCE(has_electronics,0)!=1"))
    show("duplicate specs among products 135-138 / 142-144 (excluding color)", q(
        """SELECT specs_json, GROUP_CONCAT(product_id) FROM
           (SELECT product_id, REPLACE(REPLACE(specs_json,'"Black"','"X"'),'"Red"','"X"') AS specs_json
            FROM products WHERE product_id BETWEEN 135 AND 144)
           GROUP BY 1 HAVING COUNT(*)>1"""))
    show("price range per category (cents)", q(
        "SELECT category_id, MIN(price_cents), MAX(price_cents) FROM products GROUP BY 1"))

    # ---- promotions ----------------------------------------------------
    show("promotions: active", q(
        """SELECT pr.promotion_id, pr.product_id, p.name, pr.discount_percent, p.availability
           FROM promotions pr JOIN products p USING (product_id) WHERE is_active=1"""))
    show("promotions: products with >1 promotion row", q(
        """SELECT product_id, GROUP_CONCAT(promotion_id||':'||discount_percent||'%/'||is_active)
           FROM promotions GROUP BY 1 HAVING COUNT(*)>1"""))
    show("promotions: products with >1 ACTIVE row", q(
        "SELECT product_id, COUNT(*) FROM promotions WHERE is_active=1 GROUP BY 1 HAVING COUNT(*)>1"))
    show("promotions: inactive on out-of-stock/discontinued/coming_soon", q(
        """SELECT pr.promotion_id, pr.product_id, p.availability, pr.is_active FROM promotions pr
           JOIN products p USING (product_id) WHERE p.availability!='available'"""))
    print("\npromotions table columns:", [r[1] for r in q("PRAGMA table_info(promotions)")],
          "-> no start/end date column")
    show("manual ranges violated (Black Friday 15-30, Aniversario 10-25)", q(
        """SELECT promotion_id, product_id, description, discount_percent FROM promotions
           WHERE (description='Black Friday' AND discount_percent NOT BETWEEN 15 AND 30)
              OR (description='Aniversário da Loja' AND discount_percent NOT BETWEEN 10 AND 25)"""))

    # ---- orders --------------------------------------------------------
    show("orders whose total != sum(list price x qty)", q(
        """SELECT order_id, total_cents, items_list_total_cents,
                  items_list_total_cents - total_cents AS diff_cents,
                  ROUND(100.0*(items_list_total_cents-total_cents)/items_list_total_cents,2) AS pct
           FROM orders WHERE total_matches_list=0"""))
    show("PIX orders: total vs list (5% discount visible?)", q(
        "SELECT order_id, total_cents, items_list_total_cents FROM orders WHERE payment_method='pix'"))
    show("shipped orders vs reference date", [
        (r["order_id"], r["estimated_delivery"], (today - date.fromisoformat(r["estimated_delivery"])).days)
        for r in q("SELECT order_id, estimated_delivery FROM orders WHERE status='shipped'")])
    show("open orders (pending/confirmed) older than 30 days at reference date", [
        (r["order_id"], r["status"], r["order_date"], (today - date.fromisoformat(r["order_date"])).days)
        for r in q("SELECT * FROM orders WHERE status IN ('pending','confirmed')")
        if (today - date.fromisoformat(r["order_date"])).days > 30])
    show("orders containing coming_soon/discontinued/out_of_stock products", q(
        """SELECT o.order_id, o.status, i.product_id, p.availability, i.quantity FROM orders o
           JOIN order_items i USING (order_id) JOIN products p USING (product_id)
           WHERE p.availability!='available'"""))
    show("cancelled 'out of stock' order vs current stock", q(
        """SELECT o.order_id, o.notes, i.product_id, p.stock_quantity FROM orders o
           JOIN order_items i USING (order_id) JOIN products p USING (product_id)
           WHERE o.status='cancelled' AND o.notes LIKE '%estoque%'"""))
    show("tracking code format (BR + 9 alnum + BR) violations", [
        (r["order_id"], r["tracking_code"]) for r in q(
            "SELECT order_id, tracking_code FROM orders WHERE tracking_code IS NOT NULL")
        if not re.fullmatch(r"BR[A-Z0-9]{9}BR", r["tracking_code"])])
    show("status vs tracking/estimate presence", q(
        """SELECT status, COUNT(*), SUM(tracking_code IS NOT NULL), SUM(estimated_delivery IS NOT NULL)
           FROM orders GROUP BY 1"""))
    show("days between order and estimated delivery (customer city)", [
        (r["order_id"], r["city"], (date.fromisoformat(r["estimated_delivery"]) - date.fromisoformat(r["order_date"])).days)
        for r in q("""SELECT o.order_id, c.city, o.order_date, o.estimated_delivery FROM orders o
                      JOIN customers c USING (customer_id) WHERE o.estimated_delivery IS NOT NULL""")])
    show("credit installments below the minimum parcel (3.1)", [
        (r["order_id"], r["payment_method"], r["total_cents"], round(r["total_cents"] / int(r["payment_method"][7:-1])),
         r["status"])
        for r in q("SELECT * FROM orders WHERE payment_method LIKE 'credit_%'")
        if round(r["total_cents"] / int(r["payment_method"][7:-1])) < {3: 5000, 6: 8000, 12: 10000}[int(r["payment_method"][7:-1])]])
    show("orders with orphan customer/product", q(
        """SELECT order_id FROM orders WHERE customer_id NOT IN (SELECT customer_id FROM customers)
           UNION SELECT order_id FROM order_items WHERE product_id NOT IN (SELECT product_id FROM products)"""))
    print("\norder_items columns:", [r[1] for r in q("PRAGMA table_info(order_items)")],
          "-> no unit price")

    # ---- customers -----------------------------------------------------
    show("duplicate e-mail across customers", q(
        """SELECT email_norm, GROUP_CONCAT(customer_id||':'||name||'/'||phone||'/'||city, ' | ')
           FROM customers GROUP BY 1 HAVING COUNT(*)>1"""))
    show("duplicate phone across customers", q(
        "SELECT phone_digits, GROUP_CONCAT(customer_id) FROM customers GROUP BY 1 HAVING COUNT(*)>1"))
    show("customers by city", q("SELECT city, COUNT(*) FROM customers GROUP BY 1 ORDER BY 2 DESC"))
    show("customers with orders per customer (>1)", q(
        "SELECT customer_id, COUNT(*) FROM orders GROUP BY 1 HAVING COUNT(*)>1"))


if __name__ == "__main__":
    main()
