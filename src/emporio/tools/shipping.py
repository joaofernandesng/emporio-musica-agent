"""Shipping estimate (manual section 5)."""

from __future__ import annotations

import sqlite3
from typing import Any

from emporio.build_db import strip_accents
from emporio.tools.common import brl_text, open_db, to_cents

FREE_ABOVE_CENTS = 50_000  # "acima de R$ 500,00": strictly greater
FLAT_FEE_CENTS = 3_500
METRO_CITIES = {"campo grande"}  # SUPOSIÇÃO: the manual does not define the metro area
# Large items that may need a quoted ("especial") freight: drums, keyboards/pianos,
# basses (the manual says "contrabaixos").
BULKY_CATEGORY_IDS = {2, 3, 4}

CARRIERS = [
    {"service": "PAC (Correios)", "delivery_time": "5 a 12 dias úteis", "tracking": True, "insurance": True},
    {"service": "SEDEX (Correios)", "delivery_time": "2 a 5 dias úteis", "tracking": True, "insurance": True},
    {"service": "Jadlog (.package)", "delivery_time": "3 a 8 dias úteis", "tracking": True, "insurance": True},
]


def estimate_shipping(
    subtotal_brl: float,
    city: str,
    product_ids: list[int] | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Estimate shipping for a purchase delivered to ``city``.

    Campo Grande (metropolitan region, SUPOSIÇÃO: only the capital): free above
    R$ 500,00, otherwise a flat R$ 35,00, delivered in 1 to 3 business days by the
    store's own motorcycle courier. Other cities: the manual gives no price (it is
    computed by ZIP code, weight and size), so only the carriers and their delivery
    times are returned. Drums, keyboards/pianos and basses are flagged as
    "special freight" (individual quote).

    Args:
        subtotal_brl: Merchandise value in BRL, after discounts.
        city: Destination city.
        product_ids: Optional products, used to flag large items.

    Returns:
        A dict with ``region``, ``shipping_brl`` (``None`` when it cannot be
        computed), delivery time, carriers and ``special_shipping_items``.
    """
    subtotal = to_cents(subtotal_brl)
    flagged: list[dict[str, Any]] = []
    if product_ids:
        with open_db(conn) as db:
            marks = ",".join("?" * len(product_ids))
            flagged = [
                {"product_id": r["product_id"], "name": r["name"]}
                for r in db.execute(
                    f"SELECT product_id, name, category_id FROM products WHERE product_id IN ({marks})",
                    product_ids,
                )
                if r["category_id"] in BULKY_CATEGORY_IDS
            ]

    normalized = strip_accents(city or "").strip()
    if normalized in METRO_CITIES:
        free = subtotal > FREE_ABOVE_CENTS
        fee = 0 if free else FLAT_FEE_CENTS
        result: dict[str, Any] = {
            "region": "metropolitan_campo_grande",
            "shipping_brl": fee / 100,
            "shipping_text": "Grátis" if free else brl_text(fee),
            "free_shipping": free,
            "delivery_time": "1 a 3 dias úteis",
            "delivery_method": "motoboy próprio da loja (o cliente é avisado por telefone antes)",
            "rule": "Frete grátis acima de R$ 500,00; abaixo disso, taxa fixa de R$ 35,00.",
        }
        if not free:
            missing = FREE_ABOVE_CENTS - subtotal + 1
            result["missing_for_free_shipping_brl"] = missing / 100
    else:
        result = {
            "region": "other_cities",
            "shipping_brl": None,
            "shipping_text": "Calculado pelo CEP, peso e dimensões do produto",
            "free_shipping": False,
            "carriers": CARRIERS,
            "rule": "O valor do frete é calculado com base no CEP de destino, peso e dimensões; "
                    "todos os envios incluem seguro e código de rastreamento.",
        }
    result["special_shipping_items"] = flagged
    if flagged:
        result["special_shipping_note"] = (
            "Instrumento de grande porte: pode exigir frete especial com cotação individual; "
            "confirmar com a equipe."
        )
    return result
