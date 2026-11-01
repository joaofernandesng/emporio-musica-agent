# Example 3 (non-trivial): withdrawal, warranty and a ticket

- **Scenario:** Combines live order data (return windows computed from the order) with the store policies, then hands a defect claim to a human through a ticket.
- **Simulated date/time (store clock):** 2026-03-25T10:00 (America/Campo_Grande)
- **Model:** gpt-5.4-mini
- **Recorded:** 2026-10-31 22:27 (real time of the run)
- **Usage:** 26397 prompt + 640 completion tokens, estimated cost US$ 0.0227

Real run of the agent: the attendant's text below is exactly what the model returned. The collapsible blocks list the tools it called (customer data in them is fictional).

---
**Cliente:** Me arrependi da minha compra, posso devolver?

**Atendente:**

> Se a compra foi **online**, pode sim: pela nossa política de trocas, o arrependimento vale em até **7 dias corridos após o recebimento**. O produto precisa voltar sem sinais de uso, na embalagem original e com tudo que veio junto.
>
> Se foi **na loja física**, aí o arrependimento não se aplica; nesse caso, a gente vê as opções de troca por preferência ou por defeito. Se quiser, me diz se a compra foi online ou presencial que eu te oriento certinho.

<details><summary>Tools called (1)</summary>

- `search_policies({"query": "arrependimento de compra devolução troca direito de arrependimento compra online e loja física prazo e regras"})`  
  → sections returned: 4.1 Direito de Arrependimento (Compras Online), 4.2 Trocas por Defeito, 4 Política de Trocas e Devoluções (+1 note(s))

</details>

**Cliente:** foi online

**Atendente:**

> Perfeito. Sendo **compra online**, você pode pedir a devolução em até **7 dias corridos após o recebimento**.
>
> Pela nossa política, o item precisa estar:
> - na embalagem original
> - sem sinais de uso
> - com acessórios e manuais
>
> O reembolso volta na mesma forma de pagamento, e o frete de devolução fica por nossa conta nesse caso.
>
> Se quiser, eu também posso te orientar no próximo passo para abrir a solicitação.

<details><summary>Tools called (0)</summary>

No tool was needed.

</details>

**Cliente:** Meu pedido é o 7 e meu e-mail é leticia.rocha@jmail.com

**Atendente:**

> Conferi aqui: o pedido 7 está **entregue**.
>
> Como o prazo de arrependimento já passou, **não dá para abrir devolução por esse motivo**. Pela nossa política, esse prazo vai até **24/02/2026**.
>
> Ainda vale a **garantia legal até 18/05/2026**. Se o motivo for defeito, eu posso te ajudar com isso também. Se quiser, eu abro um atendimento pra analisar o caso — é só me dizer qual é o problema.

<details><summary>Tools called (1)</summary>

- `get_order_status({"order_id": 7, "email_or_phone": "leticia.rocha@jmail.com"})`  
  → verified=true, status=delivered, delayed=False; arrependimento: expired (deadline 2026-02-24), troca_por_preferencia: expired (deadline 2026-02-24), troca_por_defeito: expired (deadline 2026-03-05), garantia_legal: within (deadline 2026-05-18)

</details>

**Cliente:** na verdade ele está com um defeito no tampo

**Atendente:**

> Poxa, sinto muito por isso. Pelo que conferi, o pedido 7 já passou do prazo de **troca por defeito** e a **garantia legal segue válida até 18/05/2026**.
>
> Já abri um atendimento para análise do caso: **T-20260325-BC9D0A**.  
> O retorno deve chegar em **até 24 horas úteis** no seu e-mail.
>
> Se quiser, posso te orientar também sobre o que separar de fotos ou informações do defeito pra agilizar.

<details><summary>Tools called (2)</summary>

- `search_policies({"query": "troca por defeito garantia legal defeito no produto prazo 30 dias compra online e 90 dias recebimento como proceder"})`  
  → sections returned: 4.2 Trocas por Defeito, 4.1 Direito de Arrependimento (Compras Online), 8.1 Garantia Legal (+1 note(s))
- `create_ticket({"tipo": "garantia_defeito", "resumo": "Pedido 7, produto Shelby SU-21S Soprano Sunburst com defeito no tampo. Cliente informou e-mail leticia.rocha@jmail.com. Pedido entregue; prazo de troca por defeito já expirou, mas garantia legal ainda está dentro do prazo.", "contato": "leticia.rocha@jmail.com"})`  
  → created=True, ticket_id=T-20260325-BC9D0A

</details>
