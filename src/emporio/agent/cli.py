"""Terminal chat: ``python -m emporio``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Callable

from emporio.agent.config import ConfigError, load_settings
from emporio.agent.llm import LLMClient, LLMError, OpenAIClient
from emporio.agent.loop import HISTORY_WINDOW, Agent, TurnResult
from emporio.agent.prompt import build_system_prompt
from emporio.agent.session import Session, new_session_id
from emporio.tools.common import CLOCK_ENV

WELCOME = (
    "Oi! Eu sou o atendente virtual da Empório da Música. "
    "Posso ajudar com produtos, preços, pedidos, pagamento, entrega e trocas. "
    "(Digite /reset para recomeçar ou /sair para encerrar.)"
)


def print_trace(result: TurnResult, out=sys.stderr) -> None:
    for event in result.tool_events:
        args = json.dumps(event.arguments, ensure_ascii=False)
        print(f"  [ferramenta] {event.name}({args})", file=out)


def open_agent(client: LLMClient, session: Session, history_window: int) -> Agent:
    """Resume the session if its file exists, otherwise start it with a fresh prompt."""
    history = session.load()
    agent = Agent(client, history or None, history_window=history_window)
    if not history:
        session.append(agent.history)
    return agent


def chat(
    client: LLMClient,
    session_id: str | None = None,
    *,
    trace: bool = False,
    history_window: int = HISTORY_WINDOW,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    session = Session(session_id or new_session_id())
    resumed = session.exists()
    agent = open_agent(client, session, history_window)
    write(f"[sessão {session.session_id}{' retomada' if resumed else ''}]")
    write(WELCOME)
    while True:
        try:
            text = read("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            write("\nAté logo!")
            return
        if not text:
            continue
        if text in ("/sair", "/exit"):
            write("Até logo!")
            return
        if text == "/reset":
            session = Session(new_session_id())
            agent = open_agent(client, session, history_window)
            write(f"[nova conversa, sessão {session.session_id}]")
            continue
        try:
            result = agent.respond(text)
        except LLMError as exc:
            write(f"[erro] {exc}")
            continue
        session.append(result.new_messages)
        if trace:
            print_trace(result)
        write(f"\nEmpório: {result.text}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="emporio", description="Atendente virtual da Empório da Música")
    parser.add_argument("--session", help="retoma a sessão com este id")
    parser.add_argument("--trace", action="store_true", help="mostra as ferramentas chamadas")
    parser.add_argument("--now", help=f"ISO 8601; sobrepõe {CLOCK_ENV}")
    parser.add_argument("--history", type=int, default=HISTORY_WINDOW, help="mensagens enviadas ao modelo")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.now:
            os.environ[CLOCK_ENV] = args.now
        build_system_prompt()  # validates the clock before the first turn
        Session(args.session or "x")  # validates the session id early
    except (ConfigError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    chat(OpenAIClient(settings), args.session, trace=args.trace, history_window=args.history)
    return 0
