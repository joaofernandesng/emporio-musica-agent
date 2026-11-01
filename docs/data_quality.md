# Data quality report

Every finding below was **computed** (not eyeballed) by
`python scripts/quality_checks.py 2026-10-31`; the script prints the rows quoted
as evidence. Reference date for date-dependent checks: **2026-10-31**
(America/Campo_Grande).

**Guiding rules**

1. `data/raw/` is never edited. A fix is a derived column or flag in
   `store.db` (built by `src/emporio/build_db.py`), so raw and interpreted
   values coexist.
2. Structured fields (name, price, stock, specs, status) are the source of truth.
   Free text (descriptions, order notes) is secondary and is never used to state
   a fact that contradicts a structured field.
3. When the data cannot answer, the agent says so and offers a human ticket
   instead of guessing.

Findings are grouped: **P** products, **R** promotions, **O** orders,
**C** customers, **M** policies manual. Items marked **ASSUMPTION** are
interpretations; they are listed in the README (section 6, S1–S20).

---

## Products

### P1. Description contradicts name/specs (products 135–144)

**Evidence** (`products.description_reliable = 0`, 7 rows):

| id | name | conflict found by code |
|---|---|---|
| 135 | Music Man Bass 1X | description describes a *Fender Jazz Bass* |
| 136 | Ibanez Bass 2X | description describes a *Precision* (Fender model) |
| 137 | Yamaha Bass 3X | describes an *Ibanez*; says **5 strings**, specs say **4** |
| 139 | Bateria Yamaha Kit 1 | describes a *Pearl Export* |
| 140 | Bateria Pearl Kit 2 | describes a *Tama* kit |
| 142 | Korg Synth 1 Pro | describes a *Roland*; says **88 keys**, specs say **61** |
| 144 | Roland Synth 3 Pro | describes a *Yamaha* arranger |

Products 138, 141 and 143 have **no detectable** contradiction (name and
description agree on brand). They sit in the same generated block, though:
135–138 share identical specs apart from color (`Ash/Maple/4 strings`), and
142–144 share identical specs (`61 keys, Synthesizer, polyphony 128`). Their
prices also look arbitrary (e.g. an "Ibanez Bass 2X" at R$ 441.00 vs. "Yamaha
Bass 3X" at R$ 11,445.00), which cannot be verified.

**Impact:** repeating the description would make the agent state a wrong brand
or spec ("88 teclas", "5 cordas") — a misleading-advertising risk (manual 7.1).

**Decision:** name + structured fields win. For flagged products the agent
tool returns `description_reliable = false` and **omits the description**; it
never repeats a brand or count that conflicts with the name/specs. 138/141/143
are served normally (no evidence of conflict) but listed in the report as
"same block, lower confidence".

### P2. Product states that are not "available"

**Evidence:** `availability` counts → available 61, out_of_stock 1,
discontinued 2, coming_soon 1.

| id | raw status | stock | derived availability |
|---|---|---|---|
| 96 Giannini GF-3D | active | **0** | `out_of_stock` |
| 113 Shelby SN-7C | discontinued | 0 | `discontinued` |
| 136 Ibanez Bass 2X | discontinued | **13** | `discontinued` |
| 130 Kala KA-ABP-CTG | coming_soon | **2** | `coming_soon` |

**Impact:** `status = active` alone would offer 96 as buyable; raw stock on
130 and 136 would suggest units that cannot be sold.

**Decision:** one derived `availability` column. `discontinued` and
`coming_soon` win over stock (stock is ignored); `active` with stock 0 is
`out_of_stock`. `search_products` hides non-available items by default
(`include_unavailable=False`); `get_product` always reports the state so the
agent can suggest alternatives (manual 7.3).

### P3. `product_id` 145 is out of order

**Evidence:** CSV row order jumps `130 → 145 → 131`; ids 81–145 are otherwise
contiguous (65 products).

**Impact:** none functional. Any code assuming sorted ids or `max(id)` row
order would be wrong.

**Decision:** ids are used only as keys, never as positions; results are sorted
explicitly.

### P4. Categories 6, 7 and 8 have no products; catalog is far smaller than the manual claims

**Evidence:** products per category → 1:5, 2:4, 3:3, 4:3, **5:35**, **6:0, 7:0,
8:0**, 9:15; total **65**. Manual §1 says "mais de 300 instrumentos" and lists
sopro and cordas orquestrais. Category 4 is described as including digital
pianos/arrangers/MIDI controllers, but only 3 synthesizers exist.

**Impact:** a customer asking for a flute or violin would be told "yes, we sell
that" by the manual and find nothing in the catalog. Claiming "300+ items"
would be false.

**Decision:** the **catalog is the source of truth for what is in stock**. For
empty categories the agent says it has no such items listed right now and offers
a human ticket (it does not deny that the store may carry them, and does not
repeat the "300+" figure). `search_products` returns an empty list with a note,
and the system prompt maps it to this wording.

### P5. Spec fields

**Evidence:** `name` vs `specs` cross-checks (Aço/Nylon vs `strings`,
"Elétrico" vs `electronics`) → **0 mismatches**. Spec keys differ by category
(violão/ukulele: top, strings, electronics…; guitars: body, neck, strings = count;
drums: shells, pieces; keys: keys, polyphony). `specs.strings` means material for
categories 5/9 but a *count* for categories 1/2.

**Decision:** specs are parsed and re-serialised; `string_type` (steel/nylon)
and `has_electronics` are derived only for categories 5/9 where the key means
that. Other categories keep specs as-is.

---

## Promotions

### R1. Only `is_active = 1` is valid; the table has no dates

**Evidence:** 25 rows, **4 active** (promotion 12→product 127 10%, 14→121 20%,
19→90 18%, 24→94 8%). The table has no start/end columns.

**Impact:** validity cannot be checked against a calendar; the flag is the only
signal. Manual 7.3: never promise an expired discount.

**Decision:** an **active promotion = `is_active = 1`**, nothing else. If a
product had several active rows, the highest percentage would apply (computed:
**0** such products today). Everything inactive is "expired/not valid" and is
never offered. Tests: product 90 → 18%; product 96 → no active promotion.

### R2. Duplicated promotions for the same product

**Evidence:** products 93 (15% and 10%), 96 (18% and 40%), 99 (8% and 14%) have
two rows each — **all inactive**. 96 is also out of stock; 113 (discontinued)
has an inactive promotion.

**Impact:** a naive "latest/biggest discount" would offer 96 at 40% even though it
is out of stock and the promotion is off.

**Decision:** inactive rows are ignored entirely; nothing is deduplicated or
deleted in the DB (kept for audit).

### R3. Percentages outside the ranges the manual advertises

**Evidence:** promo 1 (product 102, *Black Friday*) is 10%, manual §6.1 says
15–30%; promo 17 (product 125, *Aniversário*) is 30%, manual says 10–25%. Both
are inactive.

**Impact:** none today, because both are inactive. Would matter if activated.

**Decision:** the **promotion table is authoritative for percentages**; the manual
ranges are descriptive of campaigns. No correction made; noted only.

---

## Orders

### O1. Order total ≠ list price × quantity (orders 3 and 20)

**Evidence** (`orders.total_matches_list = 0`):

| order | stored total | Σ list price × qty | difference |
|---|---|---|---|
| 3 | R$ 3,450.00 | R$ 3,498.00 (2 × 1,749.00) | R$ 48.00 (1.37%) |
| 20 | R$ 1,400.00 | R$ 1,488.00 (689.00 + 799.00) | R$ 88.00 (5.91%) |

The other 18 orders match exactly. `order_items` has **no unit price**, so the
price actually charged is unknown.

**Impact:** the agent can only say "the order total is R$ X" — it cannot
itemise prices or explain the difference (no discount record exists).

**Decision:** `total_brl` is reported as the order total; item lines show
product and quantity only, **no unit prices**. Derived columns
`items_list_total_cents` and `total_matches_list` keep the discrepancy
visible but are not exposed to customers. Order totals are assumed to exclude
shipping (all 18 consistent orders equal merchandise exactly, including a
R$ 159.90 order below the R$ 500 shipping threshold).

### O2. PIX orders do not show the 5% discount

**Evidence:** the 5 PIX orders (1, 5, 10, 13, 17) all have total == list price.

**Impact:** by manual §3, PIX gets 5% off list price (when not promotional).
Historical totals do not reflect it.

**Decision:** history is reported as stored. `calculate_payment` always applies
the manual's rule to *new* quotes. No inference about past orders.

### O3. Shipped order with an overdue estimate (order 8)

**Evidence:** order 8 `shipped`, `estimated_delivery = 2026-02-28`, **245 days**
before the reference date (2026-10-31). It is the only shipped order.

**Impact:** telling the customer "it is on its way, arriving 2026-02-28" is
misleading.

**Decision:** `get_order_status` sets `delayed = true` when `status = shipped`
and `estimated_delivery < today (America/Campo_Grande)`; the agent must
acknowledge the delay and offer a ticket. `today` is injectable for tests.

### O4. Stale open orders

**Evidence:** 8 orders (9–16) are `confirmed`/`pending` and 223–253 days old at
the reference date.

**Impact:** the dataset looks like a snapshot taken around March 2026; against
the real clock, "pending" orders are months old.

**Decision:** statuses are reported as recorded with the order date, so the
customer sees how old the order is. Only the `shipped` overdue rule above is
computed. Flagging open orders older than N days was considered and rejected:
the manual sets no processing deadline, so any N would be invented (README S15).

### O5. Orders containing `coming_soon`, out-of-stock or discontinued products

**Evidence:** product 130 (`coming_soon`) is in order 3 (delivered, qty 2) and
order 14 (pending); product 96 (now out of stock) is in order 4 (delivered).

**Impact:** a "coming soon" product with a *delivered* order contradicts the
catalog state.

**Decision:** order data is shown as recorded (item names come from the
catalog), but availability statements for new purchases follow P2 only. No
reconciliation is attempted.

### O6. Cancelled "out of stock" order vs. current stock

**Evidence:** order 18 cancelled with note *"Item fora de estoque no momento do
pedido"*; its product (85) has **10 units** today.

**Impact:** consistent only if stock was replenished since; the customer could
ask "it is in stock now, why was it cancelled?".

**Decision:** the note is reported as the recorded reason, together with the
statement that the current catalog stock is checked separately
(`search_products`). The agent must not infer a cause.

### O7. Estimated delivery ignores the 1–3 business day promise

**Evidence:** for all 8 orders with an estimate, `estimated_delivery − order_date`
is **10–15 days**, including 7 orders for customers in Campo Grande (manual §5.1
promises 1–3 business days there).

**Impact:** quoting the manual's 1–3 days for an existing order would contradict
its recorded estimate.

**Decision:** for existing orders the agent uses the recorded estimate only; the
1–3 day figure is used only in `estimate_shipping` for *new* purchases.

### O8. Installments below the manual's minimum parcel

**Evidence:** order 9 (`credit_6x`, R$ 349.90 → R$ 58.32/parcel), order 16
(`credit_6x`, R$ 429.90 → R$ 71.65) and order 18 (cancelled, `credit_12x`,
R$ 459.90 → R$ 38.32) violate §3.1 (4–6x: min R$ 80; 7–12x: min R$ 100).

**Impact:** the store itself accepted terms its manual forbids; the agent could
be asked to confirm them.

**Decision:** history is reported as stored; `calculate_payment` enforces the
manual for new quotes. The agent does not volunteer commentary on past orders.

### O9. Other checks (clean)

No orphan customers or products; every order has items; all tracking codes
match `BR` + 9 alphanumerics + `BR`; tracking and estimate are present exactly
for `shipped`/`delivered` orders. Order 20's cancellation reason (invalid
address) cannot be cross-checked, since addresses are not in the data.

### O10. No receipt date; channel unknown — **ASSUMPTION**

**Evidence:** `orders` has `order_date` and `estimated_delivery` but no real
receipt date, and no sales channel (online vs. store).

**Decision:** (1) `estimated_delivery` stands in for the
receipt date; (2) every system order has shipping and tracking, so it is treated
as a remote (online) purchase, to which the 7-day right of withdrawal (4.1)
applies. `get_order_status` computes `return_windows` for **delivered** orders
only: withdrawal and preference exchange = receipt + 7 days (4.1, 4.3), defect
exchange = purchase date + 30 days (4.2), legal warranty = receipt + 90 days
(8.1), all calendar days, the deadline day included. Example, order 7 (bought
2026-02-03, received ~2026-02-17) on 2026-03-25: withdrawal expired 2026-02-24,
defect exchange expired 2026-03-05, legal warranty valid until 2026-05-18
(54 days left). Other statuses get no windows. In-store purchases are not in the
data; the agent explains that case from the policy text (no withdrawal right).

---

## Customers

### C1. Same e-mail on two different customers (11 and 43)

**Evidence:** `bruno.martins@jmail.com` belongs to customer 11 (*Bruno Carvalho
Martins*, (67) 98543-2109) and customer 43 (*Bruno Martins*, (67) 99456-3456),
both Três Lagoas. Phones are unique; no other duplicate e-mail.

**Impact:** an e-mail alone does not identify one person. If verification matched
e-mail across the whole customer table, customer 43 could unlock customer 11's
order 10.

**Decision:** order verification compares the supplied e-mail/phone **only
against the customer who owns the requested order**. Because both rows are likely
the same person, the duplicate is documented but nothing is merged.

### C2. Contact formats

**Evidence:** phones always `(67) 9XXXX-XXXX`; e-mails lowercase already.

**Decision:** phones are normalised to digits and e-mails trimmed/lowercased
for comparison (derived `phone_digits`, `email_norm`); a country code `55` prefix
in user input is stripped.

---

## Policies manual

### M1. Two different phone/WhatsApp numbers — **ASSUMPTION**

**Evidence:** cover and table §1.2: **(67) 3341-4444**; §7: **(67) 3321-4500**
("canal de WhatsApp").

**Decision:** use **(67) 3341-4444** (2 of 3 mentions, incl. the company-data
table) as the store contact and never mention the other number. The tool output
for policies keeps both source texts intact (no editing) and adds a note with
the official number, so the agent quotes only (67) 3341-4444. To be confirmed
with the store.

### M2. E-mail written with and without accent — **ASSUMPTION**

**Evidence:** `contato@emporiodamusica.com.br` (cover) vs
`contato@empóriodamusica.com.br` (§1.2 table). Domain names cannot contain
raw accents in practice.

**Decision:** use the unaccented address.

### M3. Payment table vs. §3.1 installment rules — **ASSUMPTION**

**Evidence:** the table says credit "até 12x, parcela mínima de R$ 100,00";
§3.1 says 1–3x min R$ 50 (see M4), 4–6x min R$ 80, 7–12x min R$ 100.

**Decision:** §3.1 is the more specific rule and wins; the table row is read as
the cap (12x) and the highest minimum. 1x credit has no minimum.

### M4. "Até 3x sem valor mínimo (exceto abaixo de R$ 50,00)" is ambiguous — **ASSUMPTION**

Two readings: (A) each installment must be at least R$ 50; (B) purchases under
R$ 50 in total cannot be split at all (installment size unrestricted above that).

**Decision:** **(A)**, the conservative one and consistent with the 80/100
tiers (all tiers are a *minimum installment value*). Example: R$ 120 in 3x
(R$ 40) is **not** allowed; R$ 120 in 2x (R$ 60) is. The tool returns the
reason so the agent explains the limit instead of just refusing.

### M5. PIX discount vs promotions — **ASSUMPTION**

**Evidence:** §3 grants 5% on list price; §6.2 says it does not apply on
already-promotional prices (promotions are not cumulative).

**Decision:** per item: the 5% applies to items **without an active promotion**
only; promotional items keep the promotional price. In a mixed cart the discount
is applied line by line.

### M6. Boundaries "acima de" — **ASSUMPTION**

Free metropolitan shipping is "acima de R$ 500,00" and combined payment methods
"acima de R$ 2.000,00". Taken literally: **strictly greater** (exactly R$ 500.00
pays R$ 35.00; exactly R$ 2,000.00 does not allow combinations). Base value =
merchandise total after promotions and before the PIX discount, excluding
shipping.

### M7. "Região metropolitana de Campo Grande" is undefined — **ASSUMPTION**

The manual gives the rule but no city list. All non-capital customers are in
Dourados, Três Lagoas, Ponta Porã and Corumbá (all far away).

**Decision:** treat only **Campo Grande** as covered by §5.1; any other city is
"other city" (Correios/Jadlog, quote by CEP).

### M8. Defect exchange (30 days) vs legal warranty (90 days)

**Evidence:** §4.2: exchange for defect within 30 days, then manufacturer
warranty; §8.1: legal warranty of 90 days from receipt.

**Decision:** the agent quotes both texts as written and does **not** promise an
outcome; for any defect claim it opens a ticket so the team decides (and
mentions that the 90-day legal warranty exists). **Question for the store.**

### M9. Smaller notes

- Manual version date is June 2025 while orders run to March 2026; the manual may
  be outdated for newer campaigns (e.g. "Volta às Aulas" has no promotion rows).
- §4.1 right of withdrawal is stated for **online** purchases; in-store
  purchases are not covered. For an in-store purchase the agent explains, from
  the policy text, the alternatives that still apply (preference exchange within
  7 days, defect exchange and warranty).
- Holidays are not listed in the manual; a fixed national-holiday list is used
  (see `docs/tools.md`).
- Special dates (Black Friday, Natal) "may extend hours" with no dates given; the
  hours tool reports regular hours and notes this limitation.
