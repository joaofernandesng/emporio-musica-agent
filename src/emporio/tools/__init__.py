"""Tool registry: Python functions plus their OpenAI tool-calling schemas."""

from __future__ import annotations

import json
from typing import Any, Callable

from emporio.tools.hours import get_store_hours
from emporio.tools.orders import get_order_status
from emporio.tools.payment import calculate_payment
from emporio.tools.policies import search_policies
from emporio.tools.products import get_product, search_products
from emporio.tools.shipping import estimate_shipping
from emporio.tools.tickets import TICKET_TYPES, create_ticket

FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_products": search_products,
    "get_product": get_product,
    "get_order_status": get_order_status,
    "calculate_payment": calculate_payment,
    "estimate_shipping": estimate_shipping,
    "get_store_hours": get_store_hours,
    "search_policies": search_policies,
    "create_ticket": create_ticket,
}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


SCHEMAS: list[dict] = [
    _tool(
        "search_products",
        "Search the catalog by text and filters. Use for any question about which products "
        "exist, prices or availability. Hides unavailable products unless include_unavailable; "
        "unavailable items come with ready-made `alternatives`. If not_sold_accessory is true, the "
        "customer asked for an accessory, which the store does not sell.",
        {
            "query": {"type": "string", "description": "Free text, e.g. 'takamine' or 'ukulele tenor'."},
            "category": {"type": "string", "description": "Category name, e.g. 'violões', 'baterias'."},
            "min_price": {"type": "number", "description": "Minimum current price in BRL."},
            "max_price": {"type": "number", "description": "Maximum current price in BRL."},
            "string_type": {"type": "string", "enum": ["steel", "nylon"],
                            "description": "Strings of acoustic guitars/ukuleles (steel = aço)."},
            "has_electronics": {"type": "boolean", "description": "True for electro-acoustic models."},
            "on_promotion": {"type": "boolean",
                            "description": "True to list only products with an active promotion "
                                           "(use it for 'what is on sale?')."},
            "include_unavailable": {"type": "boolean",
                                    "description": "Also list out-of-stock, discontinued and coming-soon items."},
        },
        [],
    ),
    _tool(
        "get_product",
        "Get details, specs, availability and active promotion of one product, by id or "
        "approximate name. Returns candidates when the name is ambiguous.",
        {
            "product_id": {"type": "integer"},
            "name": {"type": "string", "description": "Product name or part of it, e.g. 'Takamine GD20'."},
        },
        [],
    ),
    _tool(
        "get_order_status",
        "Look up an order. Requires the order number AND the e-mail or phone registered on "
        "the purchase; without a matching contact it reveals nothing about the order.",
        {
            "order_id": {"type": "integer", "description": "Order number."},
            "email_or_phone": {"type": "string", "description": "E-mail or phone used on the purchase."},
        },
        ["order_id"],
    ),
    _tool(
        "calculate_payment",
        "Compute the final price and installments for a payment method and check whether the "
        "condition is allowed (PIX 5% only without promotion, minimum installment, combined "
        "methods only above R$ 2.000). ALWAYS use this instead of doing the math yourself.",
        {
            "method": {"type": "string", "enum": ["pix", "debit", "credit", "boleto"]},
            "installments": {"type": "integer", "minimum": 1, "maximum": 12,
                             "description": "Credit installments (1-12).", "default": 1},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"product_id": {"type": "integer"}, "quantity": {"type": "integer"}},
                    "required": ["product_id"],
                },
                "description": "Products to buy. Alternative to amount_brl.",
            },
            "amount_brl": {"type": "number", "description": "Plain amount in BRL, if no items."},
            "amount_has_promotion": {"type": "boolean",
                                     "description": "With amount_brl: true if it is already a promotional price."},
            "combine_methods": {"type": "boolean",
                                "description": "True to ask if splitting payment across methods is allowed."},
        },
        ["method"],
    ),
    _tool(
        "estimate_shipping",
        "Estimate shipping cost and delivery time for a destination city (Campo Grande vs "
        "other cities) and flag large items that need special freight.",
        {
            "subtotal_brl": {"type": "number", "description": "Merchandise value in BRL after discounts."},
            "city": {"type": "string", "description": "Destination city."},
            "product_ids": {"type": "array", "items": {"type": "integer"},
                            "description": "Products in the purchase (to flag large items)."},
        },
        ["subtotal_brl", "city"],
    ),
    _tool(
        "get_store_hours",
        "Say whether the store is open right now (Campo Grande time, holidays included) and "
        "when it opens next. Takes no arguments: the clock is handled by the program.",
        {},
        [],
    ),
    _tool(
        "search_policies",
        "Search the store manual for rules: exchanges, returns, warranty, payment, shipping, "
        "promotions, hours, privacy, store contact data. Returns the most relevant sections.",
        {"query": {"type": "string", "description": "The customer's question, in Portuguese."}},
        ["query"],
    ),
    _tool(
        "create_ticket",
        "Register a ticket for a human attendant (complaint, defect claim, return request, "
        "delayed order, anything the agent cannot resolve). The team answers in 24 business hours.",
        {
            "tipo": {"type": "string", "enum": list(TICKET_TYPES)},
            "resumo": {"type": "string", "description": "Short summary of the problem."},
            "contato": {"type": "string", "description": "Customer e-mail or phone to reply to."},
        },
        ["tipo", "resumo", "contato"],
    ),
]


def call_tool(name: str, arguments: dict[str, Any] | str | None = None) -> str:
    """Execute a tool by name and return its JSON string result.

    ``arguments`` may be the dict or the raw JSON string produced by the model.
    Unknown tools and bad arguments come back as ``{"error": ...}`` so the
    model can recover instead of the program crashing.
    """
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"invalid JSON arguments: {exc}"})
    func = FUNCTIONS.get(name)
    if func is None:
        return json.dumps({"error": f"unknown tool '{name}'"})
    try:
        return json.dumps(func(**(arguments or {})), ensure_ascii=False)
    except TypeError as exc:
        return json.dumps({"error": f"bad arguments for {name}: {exc}"})
