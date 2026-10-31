from emporio.tools.orders import NOT_VERIFIED, get_order_status

ANA_EMAIL = "anacarol.ferreira@coldmail.com"   # customer 2, owner of order 8
ANA_PHONE = "(67) 99654-7821"


def test_correct_email_verifies(conn):
    result = get_order_status(8, ANA_EMAIL, today="2026-10-31", conn=conn)
    assert result["verified"] is True
    order = result["order"]
    assert order["status"] == "shipped" and order["tracking_code"] == "BRJL5544332BR"
    assert order["items"] == [{"product_id": 120, "name": "Kala KA-C Concert Mogno", "quantity": 1}]
    assert order["total_brl"] == 349.9
    assert order["customer_first_name"] == "Ana"


def test_email_is_case_and_space_insensitive(conn):
    assert get_order_status(8, f"  {ANA_EMAIL.upper()} ", today="2026-10-31", conn=conn)["verified"]


def test_phone_in_any_format_verifies(conn):
    for phone in (ANA_PHONE, "67996547821", "+55 67 99654-7821", "5567996547821"):
        assert get_order_status(8, phone, today="2026-10-31", conn=conn)["verified"], phone


def test_wrong_contact_and_unknown_order_are_indistinguishable(conn):
    wrong_contact = get_order_status(8, "someone@else.com", conn=conn)
    unknown_order = get_order_status(9999, ANA_EMAIL, conn=conn)
    no_contact = get_order_status(8, None, conn=conn)
    blank_contact = get_order_status(8, "  ", conn=conn)
    assert wrong_contact == unknown_order == no_contact == blank_contact == NOT_VERIFIED
    assert wrong_contact["verified"] is False and "order" not in wrong_contact


def test_other_customers_contact_does_not_unlock_the_order(conn):
    # customer 7 owns order 2; Ana's valid e-mail must not open it
    assert get_order_status(2, ANA_EMAIL, conn=conn) == NOT_VERIFIED


def test_duplicate_email_does_not_leak_orders(conn):
    # bruno.martins@jmail.com is on customers 11 and 43; order 10 belongs to 11 and
    # order 1 to customer 3: the e-mail only works for the order's own customer.
    assert get_order_status(10, "bruno.martins@jmail.com", conn=conn)["verified"]
    assert get_order_status(1, "bruno.martins@jmail.com", conn=conn) == NOT_VERIFIED


def test_short_phone_is_rejected(conn):
    assert get_order_status(8, "7821", conn=conn) == NOT_VERIFIED
    assert get_order_status(8, "99654-7821", conn=conn) == NOT_VERIFIED  # no area code


def test_order_8_is_delayed(conn):
    order = get_order_status(8, ANA_EMAIL, today="2026-10-31", conn=conn)["order"]
    assert order["delayed"] is True
    assert order["days_overdue"] == 245


def test_shipped_order_is_not_delayed_before_estimate(conn):
    order = get_order_status(8, ANA_EMAIL, today="2026-02-28", conn=conn)["order"]
    assert order["delayed"] is False and order["days_overdue"] == 0


def test_delivered_order_is_never_delayed(conn):
    order = get_order_status(1, "(67) 98432-1098", today="2026-10-31", conn=conn)["order"]
    assert order["status"] == "delivered" and order["delayed"] is False


def test_cancelled_order_reports_reason(conn):
    order = get_order_status(18, "gustavo.nunes@inlook.com", conn=conn)["order"]
    assert order["status"] == "cancelled"
    assert "fora de estoque" in order["notes"]


def test_items_carry_no_unit_prices(conn):
    # order 20 belongs to customer 7 (thiago.barbosa)
    own = get_order_status(20, "thiago.barbosa@jmail.com", conn=conn)["order"]
    assert own["total_brl"] == 1400.0
    assert all(set(item) == {"product_id", "name", "quantity"} for item in own["items"])


def test_open_orders_report_age_but_are_never_delayed(conn):
    # Order 9 is pending/confirmed and months old: no processing deadline exists.
    row = conn.execute("SELECT status, order_date, customer_id FROM orders WHERE order_id = 9").fetchone()
    email = conn.execute("SELECT email_norm FROM customers WHERE customer_id = ?", (row["customer_id"],)).fetchone()[0]
    order = get_order_status(9, email, today="2026-10-31", conn=conn)["order"]
    assert order["status"] in ("pending", "confirmed")
    assert order["delayed"] is False and order["days_overdue"] == 0
    assert order["days_since_order"] > 200
