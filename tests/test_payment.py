import pytest

from emporio.tools.payment import calculate_payment, max_installments_for, min_installment_cents


def pay(conn, **kwargs):
    return calculate_payment(conn=conn, **kwargs)


def test_pix_applies_5_percent_without_promotion(conn):
    r = pay(conn, method="pix", items=[{"product_id": 95}])      # Takamine GD20, R$ 2.199,00
    assert r["subtotal_brl"] == 2199.0
    assert r["pix_discount_brl"] == 109.95
    assert r["total_brl"] == 2089.05
    assert r["allowed"] is True


def test_pix_does_not_stack_on_promotional_price(conn):
    r = pay(conn, method="pix", items=[{"product_id": 90}])      # 18% promotion
    assert r["pix_discount_brl"] == 0.0
    assert r["total_brl"] == 1967.18
    assert "promocional" in r["pix_note"]


def test_pix_discount_is_per_line_in_mixed_cart(conn):
    r = pay(conn, method="pix", items=[{"product_id": 90}, {"product_id": 83}])   # promo + no promo
    assert r["subtotal_brl"] == round(1967.18 + 429.9, 2)
    assert r["pix_discount_brl"] == 21.5                          # 5% of 429.90 only
    assert [ln["promotion_applied"] for ln in r["lines"]] == [True, False]


def test_quantities_multiply(conn):
    assert pay(conn, method="debit", items=[{"product_id": 83, "quantity": 3}])["total_brl"] == 1289.7


def test_installment_below_minimum_is_refused(conn):
    r = pay(conn, method="credit", installments=6, amount_brl=349.90)   # R$ 58,32 < R$ 80
    assert r["allowed"] is False
    assert "80,00" in r["reason"]
    assert r["max_installments"] == 4                                    # 349.90 / 4 = 87.48 >= 80; /5 = 69.98 < 80
    assert r["installment_brl"] == 58.32


def test_three_installments_need_at_least_50_per_installment(conn):
    assert pay(conn, method="credit", installments=3, amount_brl=120)["allowed"] is False   # 40 < 50
    assert pay(conn, method="credit", installments=2, amount_brl=120)["allowed"] is True    # 60
    assert pay(conn, method="credit", installments=3, amount_brl=150)["allowed"] is True    # exactly 50


def test_twelve_installments_need_100_each(conn):
    ok = pay(conn, method="credit", installments=12, items=[{"product_id": 95}])   # 183.25
    assert ok["allowed"] and ok["installment_brl"] == 183.25
    assert pay(conn, method="credit", installments=12, amount_brl=1199.99)["allowed"] is False
    assert pay(conn, method="credit", installments=12, amount_brl=1200)["allowed"] is True


def test_more_than_12_installments_refused(conn):
    assert pay(conn, method="credit", installments=13, amount_brl=50000)["allowed"] is False


def test_installments_split_exactly(conn):
    r = pay(conn, method="credit", installments=3, amount_brl=100.00)
    assert sum(r["schedule_brl"]) == pytest.approx(100.0)
    r = pay(conn, method="credit", installments=3, amount_brl=200.00)
    assert r["schedule_brl"] == [66.67, 66.67, 66.66]


def test_only_credit_can_be_split(conn):
    r = pay(conn, method="debit", installments=2, amount_brl=500)
    assert r["allowed"] is False and r["installments"] == 1


def test_combination_only_above_2000(conn):
    assert pay(conn, method="credit", amount_brl=2000.00, combine_methods=True)["allowed"] is False
    assert pay(conn, method="credit", amount_brl=2000.01, combine_methods=True)["allowed"] is True
    assert pay(conn, method="credit", amount_brl=1500, combine_methods=True)["allowed"] is False


def test_unavailable_product_cannot_be_priced(conn):
    for pid in (96, 113, 130):
        r = pay(conn, method="pix", items=[{"product_id": pid}])
        assert r["allowed"] is False and "disponível" in r["reason"]


def test_amount_mode_pix_and_promotional_amount(conn):
    assert pay(conn, method="pix", amount_brl=1000)["total_brl"] == 950.0
    assert pay(conn, method="pix", amount_brl=1000, amount_has_promotion=True)["total_brl"] == 1000.0


def test_invalid_input(conn):
    assert pay(conn, method="cheque", amount_brl=10)["allowed"] is False
    assert pay(conn, method="pix")["allowed"] is False
    assert pay(conn, method="pix", items=[{"product_id": 99999}])["allowed"] is False
    assert pay(conn, method="credit", installments=0, amount_brl=10)["allowed"] is False


def test_min_installment_tiers():
    assert [min_installment_cents(n) for n in (1, 2, 3, 4, 6, 7, 12)] == [0, 5000, 5000, 8000, 8000, 10000, 10000]
    assert max_installments_for(100_000) == 10      # R$ 1.000 / 10 = 100
