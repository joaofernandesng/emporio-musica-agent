"""Human hand-off tickets stored as JSON lines."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from emporio.paths import TICKETS_PATH
from emporio.tools.common import now_in_store_tz

TICKET_TYPES = ("reclamacao", "troca_devolucao", "garantia_defeito", "atraso_pedido", "outro")
RESPONSE_TIME = "24 horas úteis"


def create_ticket(
    tipo: str,
    resumo: str,
    contato: str,
    *,
    path: Path = TICKETS_PATH,
) -> dict[str, Any]:
    """Register a ticket so a human attendant follows up (complaint or hand-off).

    Appends one JSON line to ``data/runtime/tickets.jsonl``. The manual (7.3)
    promises a reply within 24 business hours.

    Args:
        tipo: One of reclamacao, troca_devolucao, garantia_defeito, atraso_pedido, outro.
        resumo: Short description of the problem in the customer's words.
        contato: E-mail or phone where the team should answer.

    Returns:
        ``{"created": True, "ticket_id", "expected_response"}`` or
        ``{"created": False, "error"}`` when an argument is invalid.
    """
    tipo = (tipo or "").strip().lower()
    resumo = (resumo or "").strip()
    contato = (contato or "").strip()
    if tipo not in TICKET_TYPES:
        return {"created": False, "error": f"tipo must be one of {list(TICKET_TYPES)}"}
    if not resumo:
        return {"created": False, "error": "resumo is required"}
    if "@" not in contato and len(re.sub(r"\D", "", contato)) < 10:
        return {"created": False, "error": "contato must be an e-mail or a phone with area code"}

    moment = now_in_store_tz()
    ticket = {
        "ticket_id": f"T-{moment:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}",
        "created_at": moment.isoformat(timespec="seconds"),
        "tipo": tipo,
        "resumo": resumo,
        "contato": contato,
        "status": "open",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ticket, ensure_ascii=False) + "\n")
    return {
        "created": True,
        "ticket_id": ticket["ticket_id"],
        "expected_response": RESPONSE_TIME,
    }
