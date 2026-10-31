"""Helpers shared by the tools: money, text normalisation, DB access, time."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator
from zoneinfo import ZoneInfo

from emporio.build_db import connect, strip_accents

STORE_TZ = ZoneInfo("America/Campo_Grande")

AVAILABILITY_LABELS = {
    "available": "disponível",
    "out_of_stock": "esgotado",
    "discontinued": "descontinuado",
    "coming_soon": "em breve",
}


@contextmanager
def open_db(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    """Yield ``conn`` if given, otherwise a fresh connection to the store DB."""
    if conn is not None:
        yield conn
        return
    own = connect()
    try:
        yield own
    finally:
        own.close()


def brl(cents: int) -> float:
    """Convert integer cents to a BRL float with 2 decimals."""
    return round(cents / 100, 2)


def brl_text(cents: int) -> str:
    """Format integer cents as Brazilian currency, e.g. ``R$ 2.199,00``."""
    reais, rest = divmod(abs(cents), 100)
    text = f"{reais:,}".replace(",", ".")
    return f"{'-' if cents < 0 else ''}R$ {text},{rest:02d}"


def to_cents(value: float | int | str) -> int:
    """Convert a BRL amount (float/str) to integer cents, rounding half up."""
    from decimal import ROUND_HALF_UP, Decimal

    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def percent_of(cents: int, percent: int) -> int:
    """``percent``% of ``cents``, rounded half up, using integer arithmetic."""
    return (cents * percent * 2 + 100) // 200


def stem(word: str) -> str:
    """Light Portuguese normalisation: no accents, lowercase, plural folded."""
    w = strip_accents(word)
    if w.endswith(("oes", "aes")) and len(w) > 4:
        return w[:-3] + "ao"
    if w.endswith("s") and len(w) > 3:
        return w[:-1]
    return w


def tokens(text: str) -> list[str]:
    """Split ``text`` into normalised word tokens."""
    return [stem(t) for t in re.findall(r"[0-9a-zA-ZÀ-ÿ]+", text)]


def now_in_store_tz(now: datetime | str | None = None) -> datetime:
    """Return ``now`` (or the current time) as an aware datetime in the store TZ.

    Naive datetimes/strings are interpreted as already being store-local time.
    """
    if now is None:
        return datetime.now(STORE_TZ)
    if isinstance(now, str):
        now = datetime.fromisoformat(now)
    if now.tzinfo is None:
        return now.replace(tzinfo=STORE_TZ)
    return now.astimezone(STORE_TZ)
