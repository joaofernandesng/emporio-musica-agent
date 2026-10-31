"""System prompt loader: the text lives in ``system_prompt.md``."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from emporio.tools.common import now_in_store_tz

PROMPT_PATH = Path(__file__).with_name("system_prompt.md")
WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def build_system_prompt(now: datetime | None = None) -> str:
    """Return the prompt with the current Campo Grande date and time injected."""
    moment = now_in_store_tz(now)
    stamp = f"{WEEKDAYS[moment.weekday()]}, {moment:%d/%m/%Y}, {moment:%H:%M}"
    return PROMPT_PATH.read_text(encoding="utf-8").replace("{{AGORA}}", stamp)
