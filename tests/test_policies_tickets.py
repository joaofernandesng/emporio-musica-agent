import inspect
import json

import pytest

from emporio.tools import FUNCTIONS, SCHEMAS, call_tool
from emporio.tools.policies import load_chunks, search_policies
from emporio.tools.tickets import create_ticket


# ---- policies -------------------------------------------------------------------
def sections(query):
    return [r["section"] for r in search_policies(query)["results"]]


def test_chunks_cover_all_numbered_sections():
    numbers = {c.number for c in load_chunks()}
    assert {"1", "1.2", "2", "3", "3.1", "4.1", "4.2", "5.1", "5.2", "6.2", "7.3", "8.1", "9", "10"} <= numbers


@pytest.mark.parametrize("query, expected_first", [
    ("Me arrependi da minha compra, posso devolver?", "4.1"),
    ("Qual o horário de funcionamento?", "2"),
    ("posso parcelar em 12x?", "3.1"),
    ("o produto veio com defeito", "4.2"),
    ("o pix tem desconto em produto em promoção?", "6.2"),
    ("vocês dão garantia?", "8"),
])
def test_policy_routing(query, expected_first):
    results = search_policies(query)["results"]
    assert results, query
    assert results[0]["section"] == expected_first or results[0]["section"].startswith(expected_first + "."), results[0]["section"]


def test_delivery_question_returns_both_shipping_sections():
    # keyword search cannot know Dourados is outside the metro area; the agent
    # gets 5.1 and 5.2 and uses estimate_shipping for the city-specific answer.
    assert {"5.1", "5.2"} <= set(sections("qual o prazo de entrega para Dourados?"))


def test_policy_results_are_bounded_and_have_titles():
    out = search_policies("troca devolução frete pagamento garantia")
    assert 1 <= out["count"] <= 3
    for r in out["results"]:
        assert r["section"] and r["title"] and r["text"]


def test_no_match_returns_empty():
    assert search_policies("xyzzy qwerty")["count"] == 0


def test_payment_table_is_readable():
    text = next(c.text for c in load_chunks() if c.number == "3")
    assert "| PIX | Pagamento à vista | 5% de desconto sobre o preço de tabela |" in text


# ---- tickets --------------------------------------------------------------------
def test_ticket_is_appended_as_json_line(tmp_path):
    path = tmp_path / "t.jsonl"
    a = create_ticket("reclamacao", "Pedido 8 atrasado", "ana@example.com", path=path)
    b = create_ticket("troca_devolucao", "Quero devolver", "(67) 99999-0000", path=path)
    assert a["created"] and b["created"] and a["ticket_id"] != b["ticket_id"]
    assert a["expected_response"] == "24 horas úteis"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [t["tipo"] for t in lines] == ["reclamacao", "troca_devolucao"]
    assert lines[0]["status"] == "open" and lines[0]["created_at"].endswith("-04:00")


@pytest.mark.parametrize("args", [
    ("invalido", "x", "a@b.com"),
    ("reclamacao", "  ", "a@b.com"),
    ("reclamacao", "x", "123"),
    ("reclamacao", "x", ""),
])
def test_invalid_ticket_is_rejected(tmp_path, args):
    path = tmp_path / "t.jsonl"
    result = create_ticket(*args, path=path)
    assert result["created"] is False and "error" in result
    assert not path.exists()


# ---- registry -------------------------------------------------------------------
def test_every_schema_matches_a_function_signature():
    assert {s["function"]["name"] for s in SCHEMAS} == set(FUNCTIONS)
    for schema in SCHEMAS:
        fn = schema["function"]
        params = inspect.signature(FUNCTIONS[fn["name"]]).parameters
        assert set(fn["parameters"]["properties"]) <= set(params), fn["name"]
        assert set(fn["parameters"]["required"]) <= set(fn["parameters"]["properties"])
        assert fn["description"]


def test_call_tool_returns_json_strings():
    out = json.loads(call_tool("get_product", '{"name": "Takamine GD20"}'))
    assert out["product"]["price_brl"] == 2199.0
    assert "is_open" in json.loads(call_tool("get_store_hours", {}))


def test_call_tool_errors_do_not_raise():
    assert "unknown tool" in json.loads(call_tool("rm_rf", {}))["error"]
    assert "invalid JSON" in json.loads(call_tool("get_product", "{bad"))["error"]


# Only arguments declared in a tool's schema reach Python; extras are dropped and
# reported in ``ignored_arguments`` (visible in --trace and eval reports).
def test_model_cannot_set_the_clock_of_store_hours(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")  # Wednesday, open
    out = json.loads(call_tool("get_store_hours", {"now": "2026-03-29T10:00"}))  # a Sunday
    assert out["is_open"] is True and out["weekday"] == "quarta-feira"
    assert out["ignored_arguments"] == ["now"]


def test_model_cannot_set_today_of_an_order(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")
    args = {"order_id": 7, "email_or_phone": "leticia.rocha@jmail.com", "today": "2026-02-18"}
    out = json.loads(call_tool("get_order_status", args))
    assert out["order"]["return_windows"]["arrependimento"]["within_deadline"] is False
    assert out["ignored_arguments"] == ["today"]


@pytest.mark.parametrize("name, args, extra", [
    ("get_product", {"name": "Takamine GD20", "conn": "x"}, "conn"),
    ("search_products", {"query": "violão", "limit": 500}, "limit"),
    ("get_product", {"name": "Takamine GD20", "bogus": 1}, "bogus"),
])
def test_arguments_outside_the_schema_are_ignored(name, args, extra):
    out = json.loads(call_tool(name, args))
    assert "error" not in out and out["ignored_arguments"] == [extra]


def test_declared_arguments_carry_no_ignored_field():
    assert "ignored_arguments" not in json.loads(call_tool("get_product", {"name": "Takamine GD20"}))


def test_contact_query_carries_the_official_number_note():
    out = search_policies("qual o telefone e whatsapp da loja?")
    assert any("3341-4444" in n for n in out["notes"])


@pytest.mark.parametrize("query", [
    "me arrependi, posso devolver?",
    "meu violão veio com defeito, tem garantia?",
    "trocar por preferência de cor",
])
def test_policy_notes_never_instruct_opening_a_ticket(query):
    # Whether to open a ticket is decided by the prompt (rule 8), not by a tool note.
    notes = " ".join(search_policies(query).get("notes", [])).lower()
    assert "ticket" not in notes and "create_ticket" not in notes and "abra" not in notes


def test_defect_note_says_warranty_runs_in_parallel():
    note = " ".join(search_policies("meu violão veio com defeito, tem garantia?")["notes"])
    assert "em paralelo" in note and "RECEBIMENTO" in note


@pytest.mark.parametrize("query", [
    "trocar por preferência de cor",
    "garantia do fabricante",
    "direito de arrependimento",
    "comprei na loja física e me arrependi, posso devolver?",
    "itens que não podem ser trocados",
])
def test_defect_note_comes_with_any_exchange_or_warranty_section(query):
    out = search_policies(query)
    sections = [r["section"] for r in out["results"]]
    assert any(s.split(".")[0] in ("4", "8") for s in sections), sections
    assert any("em paralelo" in n for n in out.get("notes", [])), (query, sections)


def test_no_defect_note_for_unrelated_sections():
    out = search_policies("vocês parcelam em quantas vezes?")
    assert not any("em paralelo" in n for n in out.get("notes", []))
