from datetime import datetime, timezone

from emporio.tools.hours import get_store_hours
from emporio.tools.shipping import estimate_shipping


# ---- shipping ---------------------------------------------------------------
def test_metro_shipping_free_above_500(conn):
    r = estimate_shipping(500.01, "Campo Grande", conn=conn)
    assert r["free_shipping"] is True and r["shipping_brl"] == 0
    assert r["delivery_time"] == "1 a 3 dias úteis"


def test_metro_shipping_flat_fee_below_500(conn):
    r = estimate_shipping(499.99, "Campo Grande", conn=conn)
    assert r["free_shipping"] is False and r["shipping_brl"] == 35.0
    assert r["missing_for_free_shipping_brl"] == 0.02


def test_metro_shipping_at_exactly_500_charges_the_fee(conn):
    # "acima de R$ 500" is read as strictly greater (documented assumption)
    assert estimate_shipping(500.00, "Campo Grande", conn=conn)["shipping_brl"] == 35.0


def test_city_matching_ignores_case_and_accents(conn):
    assert estimate_shipping(100, "  campo GRANDE ", conn=conn)["region"] == "metropolitan_campo_grande"


def test_other_cities_have_no_price_but_carriers(conn):
    r = estimate_shipping(3000, "Dourados", conn=conn)
    assert r["region"] == "other_cities" and r["shipping_brl"] is None
    assert {c["service"] for c in r["carriers"]} == {"PAC (Correios)", "SEDEX (Correios)", "Jadlog (.package)"}
    assert [c["delivery_time"] for c in r["carriers"]] == ["5 a 12 dias úteis", "2 a 5 dias úteis", "3 a 8 dias úteis"]


def test_bulky_items_are_flagged_special_freight(conn):
    r = estimate_shipping(5000, "Corumbá", product_ids=[139, 135, 142, 95], conn=conn)
    assert {i["product_id"] for i in r["special_shipping_items"]} == {139, 135, 142}   # drums, bass, keys
    assert "special_shipping_note" in r
    assert estimate_shipping(5000, "Corumbá", product_ids=[95], conn=conn)["special_shipping_items"] == []


# ---- opening hours (now injected; 2026-10-31 is a Saturday) ------------------
def test_saturday_noon_is_open():
    r = get_store_hours("2026-10-31T12:00")
    assert r["is_open"] is True and r["closes_at"] == "13:00"


def test_saturday_2pm_is_closed_and_opens_tuesday():
    r = get_store_hours("2026-10-31T14:00")
    assert r["is_open"] is False
    # Monday 2026-11-02 is Finados (holiday), so the next opening is Tuesday
    assert r["next_open"] == "2026-11-03T09:00-04:00"


def test_sunday_is_closed():
    r = get_store_hours("2026-11-01T10:00")
    assert r["is_open"] is False and r["today_hours"] is None


def test_national_holiday_is_closed_even_on_a_weekday():
    r = get_store_hours("2026-12-25T10:00")          # Friday, Natal
    assert r["is_open"] is False and r["holiday"] == "Natal"
    assert get_store_hours("2025-09-07T10:00")["holiday"] == "Independência do Brasil"


def test_weekday_boundaries():
    assert get_store_hours("2026-10-30T09:00")["is_open"] is True       # Friday opening
    assert get_store_hours("2026-10-30T08:59")["is_open"] is False
    assert get_store_hours("2026-10-30T17:59")["is_open"] is True
    assert get_store_hours("2026-10-30T18:00")["is_open"] is False


def test_next_open_after_friday_closing_is_saturday_morning():
    assert get_store_hours("2026-10-30T18:30")["next_open"] == "2026-10-31T09:00-04:00"


def test_aware_datetimes_are_converted_to_campo_grande_time():
    utc_noon = datetime(2026, 10, 30, 13, 0, tzinfo=timezone.utc)      # 09:00 in UTC-4
    r = get_store_hours(utc_noon)
    assert r["is_open"] is True and r["now"] == "2026-10-30T09:00-04:00"
    assert get_store_hours(datetime(2026, 10, 30, 12, 59, tzinfo=timezone.utc))["is_open"] is False


def test_limitation_is_reported():
    assert "municipais" in get_store_hours("2026-10-30T10:00")["limitation"]
