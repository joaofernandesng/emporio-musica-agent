import pytest

from emporio.tools import SCHEMAS
from emporio.tools.common import now_in_store_tz
from emporio.tools.hours import get_store_hours
from emporio.tools.orders import get_order_status


def test_emporio_now_overrides_real_clock(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")
    moment = now_in_store_tz()
    assert moment.isoformat() == "2026-03-25T10:00:00-04:00"


def test_empty_emporio_now_uses_real_clock(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "")
    assert now_in_store_tz().year >= 2026


def test_invalid_emporio_now_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "ontem")
    with pytest.raises(ValueError, match="EMPORIO_NOW"):
        now_in_store_tz()


def test_explicit_argument_beats_env(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")
    assert now_in_store_tz("2026-01-02T08:00").day == 2


def test_store_hours_follow_env_clock(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")  # Wednesday, open
    assert get_store_hours()["is_open"] is True
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T20:00")
    assert get_store_hours()["is_open"] is False


def test_order_8_is_25_days_late_on_demo_date(conn, monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")
    email = conn.execute(
        "SELECT c.email_norm FROM orders o JOIN customers c USING (customer_id) WHERE o.order_id = 8"
    ).fetchone()[0]
    order = get_order_status(8, email, conn=conn)["order"]
    assert order["delayed"] is True and order["days_overdue"] == 25


def test_model_cannot_set_the_clock():
    schema = next(t for t in SCHEMAS if t["function"]["name"] == "get_store_hours")
    assert schema["function"]["parameters"]["properties"] == {}
