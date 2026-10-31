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
    assert json.loads(call_tool("get_store_hours", {"now": "2026-10-31T12:00"}))["is_open"] is True


def test_call_tool_errors_do_not_raise():
    assert "unknown tool" in json.loads(call_tool("rm_rf", {}))["error"]
    assert "invalid JSON" in json.loads(call_tool("get_product", "{bad"))["error"]
    assert "bad arguments" in json.loads(call_tool("get_product", {"bogus": 1}))["error"]
