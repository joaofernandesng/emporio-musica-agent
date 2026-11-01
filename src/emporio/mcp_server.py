"""MCP server over stdio that exposes the agent's tools to any MCP client.

Run it with ``python -m emporio.mcp_server``. It needs no OpenAI key: it never
calls a model, it only serves the tools.

There is one source of truth. The tool list is built from ``emporio.tools.SCHEMAS``
(names, descriptions and JSON Schemas as the agent sends them to the model), and
every call goes through ``emporio.tools.call_tool``, the same dispatcher the agent
loop uses. So the argument filter (anything outside the schema, such as ``now``,
is dropped and reported in ``ignored_arguments``), the order verification and
every business rule apply here exactly as they do in the agent. The clock comes
from ``EMPORIO_NOW`` or the real time, never from the client. ``create_ticket``
appends to the normal queue, ``data/runtime/tickets.jsonl``.
"""

from __future__ import annotations

import json
import sys
from importlib.metadata import PackageNotFoundError, version

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from emporio.build_db import connect
from emporio.paths import DB_PATH
from emporio.tools import SCHEMAS, call_tool

SERVER_NAME = "emporio"
WRITING_TOOLS = frozenset({"create_ticket"})


def _server_version() -> str:
    try:
        return version("emporio")
    except PackageNotFoundError:
        return "0.0.0"


def mcp_tools() -> list[types.Tool]:
    """The registry's tools, translated field by field into MCP tool definitions."""
    tools = []
    for schema in SCHEMAS:
        fn = schema["function"]
        writes = fn["name"] in WRITING_TOOLS
        tools.append(
            types.Tool(
                name=fn["name"],
                description=fn["description"],
                input_schema=fn["parameters"],
                annotations=types.ToolAnnotations(
                    read_only_hint=not writes,
                    destructive_hint=False,
                    idempotent_hint=not writes,
                    open_world_hint=False,
                ),
            )
        )
    return tools


def dispatch(name: str, arguments: dict | None) -> str:
    """Run ``call_tool`` and turn an unexpected exception into an error result.

    Same wrapping as the agent loop: a broken tool returns ``{"error": ...}``.
    """
    try:
        return call_tool(name, arguments or {})
    except Exception as exc:
        return json.dumps({"error": f"tool '{name}' failed: {type(exc).__name__}: {exc}"})


def _is_error(text: str) -> bool:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return True
    return isinstance(data, dict) and "error" in data


async def _list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=mcp_tools())


async def _call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    text = await anyio.to_thread.run_sync(dispatch, params.name, params.arguments)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        is_error=_is_error(text),
    )


def build_server() -> Server:
    """A low-level MCP server whose tools are the agent's registry."""
    return Server(
        SERVER_NAME,
        version=_server_version(),
        instructions=(
            "Ferramentas de atendimento da Empório da Música (loja de instrumentos). "
            "Pedidos só são revelados com o número e o e-mail ou telefone da compra."
        ),
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )


def ensure_database() -> None:
    """Open the store DB (building it from the CSVs if missing) or exit with a clear message."""
    try:
        connect().close()
    except Exception as exc:
        sys.exit(
            f"emporio.mcp_server: could not open or build the store database at {DB_PATH} "
            f"({type(exc).__name__}: {exc}). Run `python -m emporio.build_db` from the "
            "project root and check that data/raw/ has the CSV files."
        )


async def _serve() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    ensure_database()
    anyio.run(_serve)


if __name__ == "__main__":
    main()
