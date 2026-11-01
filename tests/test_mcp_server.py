"""The MCP server exposes the agent's own tool registry, offline and unchanged."""

import asyncio
import json
import os
import sys

import pytest

mcp = pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters  # noqa: E402

from emporio import mcp_server  # noqa: E402
from emporio.paths import ROOT  # noqa: E402
from emporio.tools import SCHEMAS  # noqa: E402
from emporio.tools.orders import NOT_VERIFIED  # noqa: E402

REGISTRY = {s["function"]["name"]: s["function"] for s in SCHEMAS}


def run(coro):
    return asyncio.run(coro)


async def _list_tools(server, mode="auto"):
    async with Client(server, mode=mode) as client:
        return (await client.list_tools()).tools


async def _call(name, arguments):
    async with Client(mcp_server.build_server()) as client:
        result = await client.call_tool(name, arguments)
    assert len(result.content) == 1
    return result, json.loads(result.content[0].text)


def test_lists_exactly_the_eight_registry_tools():
    tools = run(_list_tools(mcp_server.build_server()))
    assert [t.name for t in tools] == list(REGISTRY)
    assert len(tools) == 8


def test_schemas_and_descriptions_are_the_registry_ones():
    for tool in run(_list_tools(mcp_server.build_server())):
        assert tool.input_schema == REGISTRY[tool.name]["parameters"]
        assert tool.description == REGISTRY[tool.name]["description"]


def test_only_create_ticket_is_marked_as_writing():
    tools = {t.name: t for t in run(_list_tools(mcp_server.build_server()))}
    assert tools["create_ticket"].annotations.read_only_hint is False
    assert all(t.annotations.read_only_hint for n, t in tools.items() if n != "create_ticket")


def test_get_product_returns_the_catalog_price():
    result, data = run(_call("get_product", {"name": "Takamine GD20"}))
    assert result.is_error is False
    assert data["status"] == "found"
    assert data["product"]["current_price_text"] == "R$ 2.199,00"


def test_wrong_contact_gets_the_generic_reply_and_nothing_leaks():
    _, data = run(_call("get_order_status", {"order_id": 8, "email_or_phone": "someone@else.com"}))
    assert data == NOT_VERIFIED
    assert "order" not in data


def test_now_from_the_client_is_ignored(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-11-01T10:00")  # a Sunday
    _, data = run(_call("get_store_hours", {"now": "2026-11-03T15:00"}))
    assert data["now"].startswith("2026-11-01T10:00")
    assert data["is_open"] is False
    assert data["ignored_arguments"] == ["now"]


def test_accessory_search_is_flagged_as_not_sold():
    _, data = run(_call("search_products", {"query": "cordas"}))
    assert data["not_sold_accessory"] is True
    assert data["count"] == 0


def test_unknown_tool_is_an_error_result():
    result, data = run(_call("delete_everything", {}))
    assert result.is_error is True
    assert "unknown tool" in data["error"]


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_stdio_subprocess_lists_the_tools(mode):
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "emporio.mcp_server"], cwd=str(ROOT), env=env
    )
    tools = run(_list_tools(params, mode))
    assert [t.name for t in tools] == list(REGISTRY)
