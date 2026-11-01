# Example 4: out-of-stock item and promotions

- **Scenario:** An expired promotion on an out-of-stock product, an open question about active promotions and an active promotion with original price, percentage and final price.
- **Simulated date/time (store clock):** 2026-03-25T10:00 (America/Campo_Grande)
- **Model:** gpt-5.4-mini
- **Recorded:** 2026-10-31 21:36 (real time of the run)
- **Usage:** 23022 prompt + 325 completion tokens, estimated cost US$ 0.0187

Real run of the agent: the attendant's text below is exactly what the model returned. The collapsible blocks list the tools it called (customer data in them is fictional).

---
**Cliente:** o Giannini GF-3D ainda está na Semana do Músico com 40%?

**Atendente:**

> O Giannini GF-3D está **esgotado** e, no momento, **não está com promoção ativa**.
>
> Alternativas que encontrei agora:
> - **Shelby SGD-195E Elétrico Aço Sunburst** — **R$ 799,00**
> - **Tagima Dallas Tuner Aço Natural** — **R$ 749,00**
> - **Tagima Woodstock Dreadnought Natural** — **R$ 899,00**
>
> Se quiser, eu posso te passar mais opções parecidas.

<details><summary>Tools called (1)</summary>

- `get_product({"name": "Giannini GF-3D"})`  
  → Giannini GF-3D Dreadnought Sunburst: R$ 799,90, esgotado, 3 alternative(s) returned

</details>

**Cliente:** e tem alguma promoção ativa em violão?

**Atendente:**

> No momento, **não encontrei nenhum violão com promoção ativa**.
>
> Tem **33 opções disponíveis** no catálogo, e todas as que apareceram pra mim estão com o **mesmo preço original e final**.
>
> Se quiser, eu posso te mostrar:
> - os **violões mais baratos**
> - os **elétricos**
> - ou os **de nylon**.

<details><summary>Tools called (1)</summary>

- `search_products({"category": "Violões", "include_unavailable": false})`  
  → 33 result(s): Tagima Memphis AC-39 Nylon Natural; Rozini RC-104 Nylon Estudante; Shelby SN-100 Folk Aço Preto; Giannini GF-1R Aço Folk Sunburst ...

</details>

**Cliente:** e o Crafter HT-100, quanto está?

**Atendente:**

> O **Crafter HT-100** está com promoção ativa:
>
> - **De R$ 2.399,00**
> - **18% off**
> - **Por R$ 1.967,18**
>
> Tem **3 unidades disponíveis**. Se quiser, também posso te passar as formas de pagamento.

<details><summary>Tools called (1)</summary>

- `get_product({"name": "Crafter HT-100"})`  
  → Crafter HT-100 Folk Aço Natural: R$ 1.967,18, disponível, promotion 18% (was R$ 2.399,00)

</details>
