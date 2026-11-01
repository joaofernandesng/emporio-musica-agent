# Example 4: out-of-stock item and promotions

- **Scenario:** An expired promotion on an out-of-stock product, an open question about active promotions and an active promotion with original price, percentage and final price.
- **Simulated date/time (store clock):** 2026-03-25T10:00 (America/Campo_Grande)
- **Model:** gpt-5.4-mini
- **Recorded:** 2026-10-31 22:28 (real time of the run)
- **Usage:** 18907 prompt + 381 completion tokens, estimated cost US$ 0.0159

Real run of the agent: the attendant's text below is exactly what the model returned. The collapsible blocks list the tools it called (customer data in them is fictional).

---
**Cliente:** o Giannini GF-3D ainda está na Semana do Músico com 40%?

**Atendente:**

> O Giannini GF-3D está **esgotado** no momento e **não está com promoção ativa** agora.
>
> As alternativas que encontrei foram:
> - **Shelby SGD-195E Elétrico Aço Sunburst** — R$ 799,00
> - **Tagima Dallas Tuner Aço Natural** — R$ 749,00
> - **Tagima Woodstock Dreadnought Natural** — R$ 899,00
>
> Se quiser, posso te ajudar a escolher uma dessas ou procurar outro violão parecido.

<details><summary>Tools called (1)</summary>

- `get_product({"name": "Giannini GF-3D"})`  
  → Giannini GF-3D Dreadnought Sunburst: R$ 799,90, esgotado, 3 alternative(s) returned

</details>

**Cliente:** e tem alguma promoção ativa em violão?

**Atendente:**

> Tem sim — encontrei **2 violões em promoção ativa**:
>
> - **Crafter HT-100 Folk Aço Natural**  
>   De **R$ 2.399,00** por **R$ 1.967,18** — **18% off**
> - **Taylor 110e Dreadnought Natural**  
>   De **R$ 5.999,00** por **R$ 5.519,08** — **8% off**
>
> Se quiser, eu posso te mostrar os mais baratos, os eletroacústicos ou os de nylon.

<details><summary>Tools called (1)</summary>

- `search_products({"category": "violões", "on_promotion": true})`  
  → 2 result(s): Crafter HT-100 Folk Aço Natural; Taylor 110e Dreadnought Natural

</details>

**Cliente:** e o Crafter HT-100, quanto está?

**Atendente:**

> O **Crafter HT-100 Folk Aço Natural** está por **R$ 1.967,18**.  
> Preço original: **R$ 2.399,00** — **18% de desconto** (economia de **R$ 431,82**).
>
> Se quiser, posso te passar também as formas de pagamento dele.

<details><summary>Tools called (1)</summary>

- `get_product({"name": "Crafter HT-100"})`  
  → Crafter HT-100 Folk Aço Natural: R$ 1.967,18, disponível, promotion 18% (was R$ 2.399,00)

</details>
