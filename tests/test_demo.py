import json

from emporio.demo import record, render_turn, summarize_result
from emporio.agent.loop import ToolEvent
from tests.fakes import FakeClient, calls, text


def test_record_writes_exact_text_tools_and_header(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "")
    script = {"title": "Example X", "description": "demo", "messages": ["aberto?", "obrigado"]}
    client = FakeClient(calls(("get_store_hours", {})), text("Estamos *abertos*!\n\nAté 18h."), text("Disponha!"))
    md, usage = record(script, client, model="fake-model", tickets_path=tmp_path / "t.jsonl")
    assert md.startswith("# Example X")
    assert "- **Model:** fake-model" in md and "2026-03-25T10:00" in md
    assert "**Cliente:** aberto?" in md and "**Cliente:** obrigado" in md
    assert "> Estamos *abertos*!\n>\n> Até 18h." in md  # exact text, blank line kept
    assert "`get_store_hours({})`" in md and "is_open=True" in md  # the injected clock reached the tool
    assert "No tool was needed." in md
    assert usage.total_tokens > 0
    # one session: the second request carries the first exchange
    assert [m["content"] for m in client.requests[2] if m["role"] == "user"] == ["aberto?", "obrigado"]


def test_ticket_goes_to_the_given_path_not_the_real_queue(tmp_path):
    script = {"title": "T", "description": "d", "messages": ["defeito"]}
    args = {"tipo": "garantia_defeito", "resumo": "tampo", "contato": "a@b.com"}
    client = FakeClient(calls(("create_ticket", args)), text("Aberto."))
    md, _ = record(script, client, model="m", tickets_path=tmp_path / "t.jsonl")
    assert "created=True" in md and (tmp_path / "t.jsonl").exists()


def test_summaries_are_short_and_safe():
    assert summarize_result("get_order_status", json.dumps({"verified": False, "message": "x"})).startswith("verified=false")
    assert summarize_result("search_products", json.dumps({"not_sold_accessory": True})).startswith("not_sold_accessory")
    assert summarize_result("whatever", "not json") == "not json"
    assert "error" in summarize_result("get_product", json.dumps({"error": "boom"}))
    block = render_turn("oi", "olá", [ToolEvent("get_store_hours", {}, json.dumps({"is_open": True, "now": "x"}))])
    assert "<details>" in block and "</details>" in block


def test_agent_turns_are_labelled_lira():
    block = render_turn("oi", "olá", [])
    assert "**Lira:**" in block and "**Atendente:**" not in block
