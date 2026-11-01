"""Order lookup with customer verification (LGPD-safe)."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from emporio.tools.common import brl, brl_text, now_in_store_tz, open_db

STATUS_LABELS = {
    "pending": "pendente (aguardando confirmação de pagamento)",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

PAYMENT_LABELS = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
}

# Same answer for "order does not exist", "wrong contact" and "no contact given",
# so the reply never reveals whether an order exists or who it belongs to.
NOT_VERIFIED = {
    "verified": False,
    "message": (
        "Não consegui confirmar um pedido com esses dados. Confira o número do pedido e "
        "informe o e-mail ou o telefone cadastrados na compra."
    ),
}


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    return digits


def _matches(contact: str | None, customer: sqlite3.Row) -> bool:
    if not contact or not contact.strip():
        return False
    contact = contact.strip()
    if "@" in contact:
        return contact.lower() == customer["email_norm"]
    phone = _normalize_phone(contact)
    return len(phone) >= 10 and phone == customer["phone_digits"]


def _normalized_contact(contact: str) -> str:
    """The contact exactly as the customer gave it, normalised (never read from the database)."""
    contact = contact.strip()
    return contact.lower() if "@" in contact else _normalize_phone(contact)


def _payment_label(method: str | None) -> str | None:
    if method is None:
        return None
    if method.startswith("credit_"):
        return f"cartão de crédito em {method.split('_')[1]}"
    return PAYMENT_LABELS.get(method, method)


# (key, policy, days, counted from) -- manual 4.1, 4.3, 4.2 and 8.1.
RETURN_WINDOWS = (
    ("arrependimento", "4.1", 7, "receipt"),
    ("troca_por_preferencia", "4.3", 7, "receipt"),
    ("troca_por_defeito", "4.2", 30, "purchase"),
    ("garantia_legal", "8.1", 90, "receipt"),
)
RETURN_WINDOWS_BASIS = (
    "O dataset não tem a data real de recebimento: usa-se a previsão de entrega como "
    "aproximação. Pedidos do sistema são tratados como compras à distância (online)."
)


def return_windows(order_date: str, received: str, today: date) -> dict[str, Any]:
    """Deadlines for withdrawal, exchange and warranty, computed from the single clock."""
    start = {"receipt": date.fromisoformat(received), "purchase": date.fromisoformat(order_date[:10])}
    windows: dict[str, Any] = {}
    for key, policy, days, origin in RETURN_WINDOWS:
        deadline = start[origin] + timedelta(days=days)
        delta = (deadline - today).days
        windows[key] = {
            "policy": policy,
            "counted_from": "recebimento (aproximado)" if origin == "receipt" else "data da compra",
            "deadline": deadline.isoformat(),
            "within_deadline": delta >= 0,
            "days_remaining": max(delta, 0),
            "days_expired": max(-delta, 0),
        }
    return windows


def get_order_status(
    order_id: int,
    email_or_phone: str | None = None,
    today: date | datetime | str | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Return the status of an order, only after verifying the customer.

    The e-mail (case-insensitive) or phone (any format, optional +55) must belong
    to the customer who owns the order. If the order does not exist, the contact is
    missing, or the contact does not match, the SAME generic answer is returned, so
    nothing about the order or other customers is disclosed.

    When verified, ``delayed`` is true only if the order is ``shipped`` and its
    estimated delivery date is before today (America/Campo_Grande). The manual sets
    no processing deadline, so ``pending``/``confirmed`` orders are never flagged;
    ``days_since_order`` lets the agent describe their age. Item lines carry
    product and quantity only: the data has no per-item unit price.

    Args:
        order_id: Order number given by the customer.
        email_or_phone: E-mail or phone registered on the purchase.
        today: Reference date (injectable for tests); defaults to today in
            America/Campo_Grande.

    When verified, ``verified_contact`` is the e-mail or phone the customer gave in
    this query (normalised), so a ticket can reuse it without asking again. It is
    never a contact from the customer record that the customer did not give.

    Returns:
        ``{"verified": False, "message"}`` or
        ``{"verified": True, "verified_contact", "order": {...}}``.
    """
    if isinstance(today, str):
        today = date.fromisoformat(today)
    elif isinstance(today, datetime):
        today = today.date()
    elif today is None:
        today = now_in_store_tz().date()

    with open_db(conn) as db:
        order = db.execute(
            """SELECT o.*, c.name AS customer_name, c.email_norm, c.phone_digits
               FROM orders o JOIN customers c USING (customer_id) WHERE o.order_id = ?""",
            (order_id,),
        ).fetchone()
        if order is None or not _matches(email_or_phone, order):
            return dict(NOT_VERIFIED)
        items = db.execute(
            """SELECT i.product_id, p.name, i.quantity FROM order_items i
               JOIN products p USING (product_id) WHERE i.order_id = ? ORDER BY i.item_id""",
            (order_id,),
        ).fetchall()

    estimated = order["estimated_delivery"]
    windows = None
    windows_note = RETURN_WINDOWS_BASIS
    if order["status"] == "delivered" and estimated:
        windows = return_windows(order["order_date"], estimated, today)
    else:
        windows_note = (
            "Sem janelas de troca/devolução: só pedidos entregues têm prazo contado a partir "
            f"do recebimento (status atual: {STATUS_LABELS.get(order['status'], order['status'])})."
        )
    days_since_order = max((today - date.fromisoformat(order["order_date"][:10])).days, 0)
    days_overdue = 0
    if order["status"] == "shipped" and estimated:
        days_overdue = max((today - date.fromisoformat(estimated)).days, 0)
    return {
        "verified": True,
        "verified_contact": _normalized_contact(email_or_phone),
        "order": {
            "order_id": order["order_id"],
            "customer_first_name": order["customer_name"].split()[0],
            "status": order["status"],
            "status_label": STATUS_LABELS.get(order["status"], order["status"]),
            "order_date": order["order_date"],
            "days_since_order": days_since_order,
            "items": [
                {"product_id": i["product_id"], "name": i["name"], "quantity": i["quantity"]}
                for i in items
            ],
            "total_brl": brl(order["total_cents"]),
            "total_text": brl_text(order["total_cents"]),
            "payment": _payment_label(order["payment_method"]),
            "tracking_code": order["tracking_code"],
            "estimated_delivery": estimated,
            "delayed": days_overdue > 0,
            "days_overdue": days_overdue,
            "notes": order["notes"],
            "return_windows": windows,
            "return_windows_note": windows_note,
        },
    }
