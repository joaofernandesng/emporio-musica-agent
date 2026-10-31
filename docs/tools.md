# Tools (stage 1)

Eight pure Python functions in `src/emporio/tools/`. They need no LLM and no API
key; every return value is JSON-serialisable. `emporio.tools.SCHEMAS` holds the
OpenAI tool-calling schema of each one, and `emporio.tools.call_tool(name, args)`
runs a tool from the model's (JSON string) arguments and always returns a JSON
string, even for unknown tools or bad arguments (`{"error": ...}`).

All money is integer cents internally (no float arithmetic); results expose
`*_brl` numbers plus pre-formatted `*_text` (`R$ 2.199,00`) so the model never has
to format or compute prices.

| Tool | Purpose | Key decisions |
|---|---|---|
| `search_products` | Catalog search with text + filters | Accent/case/plural-insensitive; all query words must match name, category or specs; price filters use the **current** price (promotion applied); unavailable products hidden unless `include_unavailable`; empty categories explain themselves in `notes`. |
| `get_product` | One product by id or approximate name | Handles `gd 20` vs `GD20` and typos; ambiguous names return candidates; unreliable descriptions are withheld (see `data_quality.md` P1). |
| `get_order_status` | Order lookup | Requires order id + e-mail/phone of the order's owner; **one identical generic answer** for unknown order, wrong contact and missing contact; flags `delayed` for overdue `shipped` orders; no unit prices (the data has none). |
| `calculate_payment` | Price, PIX, installments, combinations | PIX 5% only on items without promotion; tiers 2–3x ≥ R$ 50, 4–6x ≥ R$ 80, 7–12x ≥ R$ 100; combination only strictly above R$ 2.000; returns a Portuguese `reason` when refused plus `max_installments`. |
| `estimate_shipping` | Shipping cost and lead time | Campo Grande: free strictly above R$ 500, else R$ 35, 1–3 business days. Other cities: no price (needs ZIP/weight), returns PAC/SEDEX/Jadlog with lead times. Drums, keyboards/pianos and basses are flagged as special freight. |
| `get_store_hours` | Open/closed now, next opening | `America/Campo_Grande`; Mon–Fri 09–18, Sat 09–13; opening minute inclusive, closing minute exclusive; fixed list of national holidays 2025–2026. |
| `search_policies` | Manual lookup | Keyword scoring over numbered sections of `data/processed/policies.md` (title weighs 3×, prefix matching, a few synonyms); returns 1–3 sections; no embeddings. |
| `create_ticket` | Human hand-off | Appends to `data/runtime/tickets.jsonl` (git-ignored); validates type and contact; promises a reply in 24 business hours (manual 7.3). |

## Assumptions encoded in the tools

These are the interpretations proposed in `docs/data_quality.md` (M1–M8); they
are isolated in constants so they can be changed in one place.

- "Metropolitan region" = **Campo Grande only** (`shipping.METRO_CITIES`).
- "Acima de" = **strictly greater** (free shipping at > R$ 500; combined
  payments at > R$ 2.000; the combination test uses the merchandise value after
  promotions, before the PIX discount).
- 2–3x installments: **each installment ≥ R$ 50** (`payment.min_installment_cents`).
- PIX 5% is applied **line by line**, only to items without an active promotion.
- Active promotion = `is_active = 1` (no dates in the data); the highest
  percentage wins if several were active.
- Installment cents that do not divide evenly go to the first installments
  (R$ 200,00 in 3x = 66,67 + 66,67 + 66,66).

## Known limitations

- Holidays: only the national ones listed in `hours.HOLIDAYS` (2025–2026). State
  and municipal holidays, optional holidays (Carnaval, Corpus Christi) and
  extended hours on special dates are not covered; the tool reports this in its
  `limitation` field.
- `search_policies` is lexical: it cannot know that Dourados is outside the
  metropolitan area (it returns 5.1 and 5.2; the agent should use
  `estimate_shipping` for the city-specific answer) and misses paraphrases that
  share no word (partly mitigated by a small synonym table).
- Order history is reported as stored (totals without unit prices, statuses
  months old); only the overdue-shipment rule is computed.
- Product search is a plain scan of a 65-row catalog; it will not scale to a large catalog
  without an index.
