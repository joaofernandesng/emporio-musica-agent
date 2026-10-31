"""Deterministic payment calculation (PIX discount, installments, combinations)."""

from __future__ import annotations

import sqlite3
from typing import Any

from emporio.tools.common import brl, brl_text, open_db, percent_of, to_cents
from emporio.tools.products import active_promotion

PIX_DISCOUNT_PERCENT = 5
MAX_INSTALLMENTS = 12
COMBINATION_MIN_CENTS = 200_000  # "acima de R$ 2.000,00": strictly greater

METHODS = ("pix", "debit", "credit", "boleto")


def min_installment_cents(installments: int) -> int:
    """Minimum installment value (manual 3.1; SUPOSIÇÃO: 2-3x means >= R$ 50)."""
    if installments <= 1:
        return 0
    if installments <= 3:
        return 5_000
    if installments <= 6:
        return 8_000
    return 10_000


def max_installments_for(total_cents: int) -> int:
    """Largest installment count (1-12) whose installment respects the minimum."""
    best = 1
    for n in range(2, MAX_INSTALLMENTS + 1):
        if total_cents >= min_installment_cents(n) * n:
            best = n
    return best


def _split(total_cents: int, n: int) -> list[int]:
    base, extra = divmod(total_cents, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def _denied(reason: str) -> dict[str, Any]:
    return {"allowed": False, "reason": reason}


def calculate_payment(
    method: str,
    installments: int = 1,
    items: list[dict[str, int]] | None = None,
    amount_brl: float | None = None,
    amount_has_promotion: bool = False,
    combine_methods: bool = False,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Compute what a purchase costs with a payment method, and whether it is allowed.

    All arithmetic happens here, never in the model. Rules (manual sections 3, 6.2):
    PIX gives 5% off items WITHOUT an active promotion (not cumulative); debit and
    boleto are single payments; credit is interest-free up to 12x with a minimum
    installment (2-3x: R$ 50, 4-6x: R$ 80, 7-12x: R$ 100); combining payment methods
    is allowed only when the purchase is strictly above R$ 2.000,00.

    Args:
        method: "pix", "debit", "credit" or "boleto".
        installments: Number of credit installments (1 for any other method).
        items: ``[{"product_id": 95, "quantity": 1}, ...]`` priced from the catalog.
        amount_brl: Alternative to ``items``: a plain amount in BRL.
        amount_has_promotion: With ``amount_brl``, whether it is already a
            promotional price (then PIX gives no extra discount).
        combine_methods: Ask whether splitting the payment between methods is allowed.

    Returns:
        A dict with ``allowed``, ``reason`` (Portuguese, when not allowed),
        subtotal/discount/total, installment values, ``max_installments`` and
        ``combination_allowed``.
    """
    method = (method or "").strip().lower()
    if method not in METHODS:
        return _denied(f"Forma de pagamento desconhecida: '{method}'.")
    installments = int(installments)
    if installments < 1:
        return _denied("O número de parcelas deve ser pelo menos 1.")
    if method == "credit" and installments > MAX_INSTALLMENTS:
        return _denied(f"O parcelamento vai até {MAX_INSTALLMENTS}x sem juros.")

    lines: list[dict[str, Any]] = []
    pix_eligible_cents = 0
    if items:
        with open_db(conn) as db:
            for item in items:
                pid, qty = int(item["product_id"]), int(item.get("quantity", 1))
                row = db.execute(
                    "SELECT product_id, name, price_cents, availability FROM products WHERE product_id = ?",
                    (pid,),
                ).fetchone()
                if row is None or qty < 1:
                    return _denied(f"Produto {pid} não encontrado ou quantidade inválida.")
                if row["availability"] != "available":
                    return _denied(f"'{row['name']}' não está disponível para compra no momento.")
                promo = active_promotion(db, pid, row["price_cents"])
                unit = to_cents(promo["promo_price_brl"]) if promo else row["price_cents"]
                line_total = unit * qty
                if not promo:
                    pix_eligible_cents += line_total
                lines.append({
                    "product_id": pid, "name": row["name"], "quantity": qty,
                    "unit_price_brl": brl(unit), "line_total_brl": brl(line_total),
                    "promotion_applied": bool(promo),
                    "_cents": line_total,
                })
        subtotal = sum(line["_cents"] for line in lines)
    elif amount_brl is not None and amount_brl > 0:
        subtotal = to_cents(amount_brl)
        pix_eligible_cents = 0 if amount_has_promotion else subtotal
    else:
        return _denied("Informe os produtos (items) ou um valor (amount_brl).")
    for line in lines:
        line.pop("_cents")

    pix_discount = percent_of(pix_eligible_cents, PIX_DISCOUNT_PERCENT) if method == "pix" else 0
    total = subtotal - pix_discount
    out: dict[str, Any] = {
        "method": method,
        "lines": lines,
        "subtotal_brl": brl(subtotal),
        "subtotal_text": brl_text(subtotal),
        "pix_discount_brl": brl(pix_discount),
        "pix_discount_text": brl_text(pix_discount),
        "total_brl": brl(total),
        "total_text": brl_text(total),
        "combination_allowed": subtotal > COMBINATION_MIN_CENTS,
    }
    if method == "pix" and not pix_discount:
        out["pix_note"] = "Sem desconto de PIX: os itens já estão com preço promocional (promoções não são cumulativas)."

    n = installments if method == "credit" else 1
    schedule = _split(total, n)
    reason = None
    if method != "credit" and installments != 1:
        reason = "Só o cartão de crédito pode ser parcelado; as demais formas são à vista."
    elif method == "credit":
        out["max_installments"] = max_installments_for(total)
        out["max_installment_value_brl"] = brl(_split(total, out["max_installments"])[0])
        if total < min_installment_cents(n) * n:
            reason = (
                f"Em {n}x a parcela ficaria em {brl_text(schedule[0])}, abaixo do mínimo de "
                f"{brl_text(min_installment_cents(n))} por parcela nessa faixa."
            )
    if combine_methods and not out["combination_allowed"] and reason is None:
        reason = "Combinar formas de pagamento só é possível em compras acima de R$ 2.000,00."
    out.update(
        installments=n,
        installment_brl=brl(schedule[0]),
        installment_text=brl_text(schedule[0]),
        schedule_brl=[brl(v) for v in schedule],
        allowed=reason is None,
        reason=reason,
    )
    return out
