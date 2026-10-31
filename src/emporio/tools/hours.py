"""Opening hours (manual section 2) with a fixed list of national holidays.

Limitation: only the national holidays listed below (2025-2026) are known. State
and municipal holidays (e.g. Campo Grande's anniversary on 26 August, MS state day
on 11 October), optional holidays (Carnaval, Corpus Christi) and the extended
hours the store may run on special dates (Black Friday, Natal) are NOT covered.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from emporio.tools.common import now_in_store_tz

HOLIDAYS: dict[date, str] = {
    date(2025, 1, 1): "Confraternização Universal",
    date(2025, 4, 18): "Sexta-feira Santa",
    date(2025, 4, 21): "Tiradentes",
    date(2025, 5, 1): "Dia do Trabalho",
    date(2025, 9, 7): "Independência do Brasil",
    date(2025, 10, 12): "Nossa Senhora Aparecida",
    date(2025, 11, 2): "Finados",
    date(2025, 11, 15): "Proclamação da República",
    date(2025, 11, 20): "Consciência Negra",
    date(2025, 12, 25): "Natal",
    date(2026, 1, 1): "Confraternização Universal",
    date(2026, 4, 3): "Sexta-feira Santa",
    date(2026, 4, 21): "Tiradentes",
    date(2026, 5, 1): "Dia do Trabalho",
    date(2026, 9, 7): "Independência do Brasil",
    date(2026, 10, 12): "Nossa Senhora Aparecida",
    date(2026, 11, 2): "Finados",
    date(2026, 11, 15): "Proclamação da República",
    date(2026, 11, 20): "Consciência Negra",
    date(2026, 12, 25): "Natal",
}

# weekday() -> (opens, closes); Monday is 0. Missing = closed.
SCHEDULE: dict[int, tuple[time, time]] = {
    **{d: (time(9, 0), time(18, 0)) for d in range(5)},
    5: (time(9, 0), time(13, 0)),
}
WEEKDAYS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]

LIMITATION = (
    "Feriados municipais/estaduais e horários especiais (Black Friday, Natal etc.) "
    "não são considerados."
)


def _hours_for(day: date) -> tuple[time, time] | None:
    if day in HOLIDAYS:
        return None
    return SCHEDULE.get(day.weekday())


def _fmt(t: time) -> str:
    return t.strftime("%H:%M")


def get_store_hours(now: datetime | str | None = None) -> dict[str, Any]:
    """Tell whether the store is open at ``now`` and when it opens next.

    Time zone is America/Campo_Grande (UTC-4). Regular hours: Monday-Friday
    09:00-18:00, Saturday 09:00-13:00, closed on Sunday and national holidays
    (fixed 2025-2026 list). The store opens at the start minute and closes at the
    closing time (18:00:00 is already closed). See the module docstring for the
    limitations.

    Args:
        now: Moment to evaluate (ISO string or datetime; naive means store local
            time). Defaults to the current time.

    Returns:
        ``is_open``, today's hours, holiday name if any, ``next_open`` and notes.
    """
    moment = now_in_store_tz(now)
    today = moment.date()
    hours = _hours_for(today)
    is_open = bool(hours and hours[0] <= moment.time() < hours[1])

    next_open = None
    for offset in range(0, 15):
        day = today + timedelta(days=offset)
        slot = _hours_for(day)
        if slot is None:
            continue
        opening = datetime.combine(day, slot[0], tzinfo=moment.tzinfo)
        if opening > moment:
            next_open = opening
            break

    result: dict[str, Any] = {
        "now": moment.isoformat(timespec="minutes"),
        "weekday": WEEKDAYS_PT[today.weekday()],
        "timezone": "America/Campo_Grande",
        "is_open": is_open,
        "holiday": HOLIDAYS.get(today),
        "today_hours": f"{_fmt(hours[0])} às {_fmt(hours[1])}" if hours else None,
        "closes_at": _fmt(hours[1]) if is_open and hours else None,
        "next_open": next_open.isoformat(timespec="minutes") if next_open else None,
        "next_open_text": (
            f"{WEEKDAYS_PT[next_open.weekday()]}, {next_open.strftime('%d/%m')} às {_fmt(next_open.time())}"
            if next_open else None
        ),
        "regular_hours": "Segunda a sexta 09:00 às 18:00; sábado 09:00 às 13:00; domingo e feriados fechado.",
        "limitation": LIMITATION,
    }
    return result
