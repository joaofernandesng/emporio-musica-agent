# Evaluation

How the agent was evaluated, what each round revealed, and what is still known to
be imperfect. The agent is frozen at the tag `agent-frozen`; the numbers below
are for that version.

## Method

- **Model:** `gpt-5.4-mini` through Chat Completions (no sampling or reasoning
  parameters are sent).
- **Scenarios:** 21, in `evals/scenarios.json`. Each has one or more customer
  messages and objective checks. They cover products and prices, store data,
  opening hours, out-of-stock and discontinued items, active and expired
  promotions (including "which guitars are on promotion?"), PIX with a promotion, order status (verified, wrong e-mail, late
  order), withdrawal and exchange (generic, in-store, delivered order, defect with
  and without an order), accessories, out-of-scope questions, a prompt-injection
  attempt and a complaint.
- **Checks (automatic):** expected tools called (`tools_any`, `tools_all`,
  `tools_none`); phrases that must appear (alternatives per item) or must not
  appear; list size limits. Text matching ignores case and accents. **Global bans
  apply to every reply:** the words "manual" and "seção" (the policy manual is
  internal), "ferramenta" (the agent must not talk about its tools), "prioridade",
  and wording that makes the legal warranty start *after* the 30-day exchange.
- **Fixed clock:** `EMPORIO_NOW=2026-03-25T10:00` (Wednesday, store open), so
  opening hours, late orders and return windows are reproducible.
- **Repetitions:** 3 executions per scenario in the final validation, because the
  model is not deterministic.
- **Tickets** created during evals go to a temporary file, not to the real queue.
- **Human reading:** after each round the replies were read for tone, invented
  facts, undue promises, policy errors and arithmetic done by the model. Several
  defects were found this way that no automatic check covered.

## Results of the final version

57 of 63 runs passed (90%). Executions: 19/21, 19/21, 19/21. The previous
validation (before the promotion fix, 20 scenarios) was 56/60; the pass rate is
within the noise of a non-deterministic model, and the new scenario passed 3/3.

| Scenario | Passed |
|---|---|
| violoes_ate_1000 | 2/3 |
| preco_takamine_gd20 | 3/3 |
| endereco_e_horario | 3/3 |
| aberto_agora | 3/3 |
| produto_esgotado_96 | 3/3 |
| produto_descontinuado_113 | 3/3 |
| promocao_ativa_90 | 3/3 |
| promocao_vencida_96 | 3/3 |
| pix_com_promocao | 2/3 |
| pedido_8_atrasado | 3/3 |
| pedido_8_email_errado | 3/3 |
| arrependimento_generico | 3/3 |
| acessorio_cordas_amplificador | 3/3 |
| fora_do_escopo_receita | 3/3 |
| injecao_desconto | 3/3 |
| reclamacao_ticket | 2/3 |
| arrependimento_pedido_7_vencido | 2/3 |
| arrependimento_loja_fisica | 3/3 |
| defeito_com_pedido_7 | 3/3 |
| defeito_sem_pedido | 1/3 |
| promocoes_ativas_violao (new) | 3/3 |
| **Total** | **57/63** |

Cost of this validation: US$ 0.29 (349,209 tokens at US$ 0.75 / 4.50 per 1M
input/output tokens), about US$ 0.10 per full execution. Accumulated over all
evaluation rounds: about US$ 1.25 and 1.48 M tokens (recording the example
conversations cost about US$ 0.16 more).

## History

| Round | Scenarios | Result | What it revealed, and what changed |
|---|---|---|---|
| 1 | 16 | 15/16 | Out-of-stock product: the agent *offered* alternatives instead of showing them. Prompt rule tightened. Long lists (12 items) and an "accessory" offer in an out-of-scope refusal also found by reading. |
| 2 | 16 | 15/16 (16/16 after fixing one brittle check) | A correct answer ("fechamos às 18:00") was rejected by an over-strict check. Reading found the agent citing the internal manual and inventing "prioridade" in a ticket. |
| 3 | 19 | 16/19 | New return-window scenarios. The agent opened a ticket nobody asked for. Prompt: tickets only on complaint, defect or delay. Two checks were too narrow and were widened for correct replies. |
| Final | 19 × 3 | 52/57 (54/57 after two brittle checks) | Alternatives for unavailable products worked only 1 in 3 times and accessory refusals were imprecise: the prompt alone was inconsistent. **These became deterministic tool behaviour** (`alternatives`, `not_sold_accessory`). |
| Validation | 20 × 3 | 53/60 | Both fixed (3/3). Reading found the model subtracting a promotion amount itself, "prioridade" in a late-order reply and a warranty described as starting after the exchange. |
| Freeze | 20 × 3 | 56/60 | The tool now returns `discount_brl`/`discount_text`; global bans for "prioridade" and sequential-warranty wording; the defect note is attached to every exchange or warranty section; the prompt asks for the order first on defects and for deadlines. |
| Promotion fix | 21 × 3 | **57/63** | Recording example 4 showed the agent claiming there was no promotion on guitars: the search was capped at 20 results sorted by price and the model concluded "none" from an incomplete list (the evals had no scenario for it). The tool gained an `on_promotion` filter, `total_count`/`returned_count`/`truncated` and a warning note; the prompt now says to use the filter, not to conclude absence from a truncated list and never to mention internal tools to the customer. New scenario (3/3) and a global ban on the word "ferramenta". |

Design lesson: facts and rules that must be exact (prices, discounts, deadlines,
alternatives, what the store does not sell) were moved into deterministic tools;
the prompt now only governs tone and conversation flow.

## Known limitations

Remaining failures are model behaviour in a minority of runs, not tool errors:

- **`defeito_sem_pedido` (1/3):** the agent sometimes opens a ticket, or asks for
  an e-mail or phone, without first asking for the order number that would let
  it check the deadlines.
- **`arrependimento_pedido_7_vencido` (2/3):** after confirming that the
  withdrawal period has passed, it sometimes opens a ticket on its own instead of
  offering one.
- **`reclamacao_ticket` (2/3):** once it said the case would be analysed "com
  prioridade de atendimento", a promise the tools do not support; the global ban
  caught it.
- **`pix_com_promocao` (2/3):** once it answered from the product data without
  calling the payment tool (the answer was correct; the scenario expects the tool).
- **`violoes_ate_1000` (2/3):** one reply listed 4 products plus a second list of 4
  filter options; the checker counts bullets per reply, so it failed. I did not
  relax the check.
- **Alternatives** are matched by category, string type, string count (read from
  the product name, since it is not a structured spec) and price; they do not
  distinguish acoustic from electro-acoustic.
- **Order status** shows what the data holds (statuses months old, no unit prices);
  receipt date is approximated by the estimated delivery date (see
  `data_quality.md`, O10).
- Only one model and one fixed date were evaluated; with 3 runs per scenario a
  pass rate is indicative, not statistical.

## How to run

```
# real model; needs OPENAI_API_KEY and OPENAI_MODEL in .env
EMPORIO_NOW=2026-03-25T10:00 python -m emporio.evals            # all scenarios, one run
EMPORIO_NOW=2026-03-25T10:00 python -m emporio.evals --only produto_esgotado_96
```

In PowerShell, set the variable first: `$env:EMPORIO_NOW="2026-03-25T10:00"`.
Optional `OPENAI_PRICE_INPUT_PER_1M` and `OPENAI_PRICE_OUTPUT_PER_1M` add a cost
estimate. Each run writes `data/runtime/evals/eval-<timestamp>.json` (git-ignored)
with, per scenario, the result, failed checks, tools called with their arguments,
the policy sections returned by `search_policies`, tokens and the replies. The
offline test suite (`pytest`) needs no key.
