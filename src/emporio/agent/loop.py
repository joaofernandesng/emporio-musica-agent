"""The tool-calling loop: model -> tools -> model, until a plain answer comes back."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from emporio.agent.llm import LLMClient, Message, Usage
from emporio.agent.prompt import build_system_prompt
from emporio.tools import SCHEMAS, call_tool

MAX_ITERATIONS = 6
HISTORY_WINDOW = 30
FALLBACK_REPLY = (
    "Desculpe, me enrolei para responder isso agora. Pode me mandar a pergunta de novo, "
    "ou prefere que eu passe para um atendente da equipe?"
)

Dispatcher = Callable[[str, str], str]


@dataclass
class ToolEvent:
    name: str
    arguments: dict[str, Any]
    result: str


@dataclass
class TurnResult:
    text: str
    tool_events: list[ToolEvent] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    new_messages: list[Message] = field(default_factory=list)


def window(messages: list[Message], size: int) -> list[Message]:
    """Keep roughly the last ``size`` messages without splitting a tool exchange.

    The slice always starts at a user message, so an assistant ``tool_calls``
    message is never separated from its ``tool`` results (and no result is left
    orphaned). The system message (first) is always kept.
    """
    system = [m for m in messages[:1] if m["role"] == "system"]
    rest = messages[len(system):]
    if len(rest) <= size:
        return system + rest
    tail = rest[-size:]
    start = next((i for i, m in enumerate(tail) if m["role"] == "user"), None)
    if start is None:  # one huge turn: fall back to the last user message
        last_user = max(i for i, m in enumerate(rest) if m["role"] == "user")
        return system + rest[last_user:]
    return system + tail[start:]


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class Agent:
    """One conversation. ``history`` holds the system message plus everything said."""

    def __init__(
        self,
        client: LLMClient,
        history: list[Message] | None = None,
        *,
        dispatch: Dispatcher = call_tool,
        max_iterations: int = MAX_ITERATIONS,
        history_window: int = HISTORY_WINDOW,
    ) -> None:
        self.client = client
        self.dispatch = dispatch
        self.max_iterations = max_iterations
        self.history_window = history_window
        self.history: list[Message] = history or [
            {"role": "system", "content": build_system_prompt()}
        ]

    def respond(self, user_text: str) -> TurnResult:
        """Answer one customer message. History only changes if the turn completes."""
        turn: list[Message] = [{"role": "user", "content": user_text}]
        result = TurnResult(text=FALLBACK_REPLY)
        for _ in range(self.max_iterations):
            context = window(self.history + turn, self.history_window)
            response = self.client.chat(context, SCHEMAS)
            result.usage.add(response.usage)
            message = response.message
            turn.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                result.text = message.get("content") or ""
                break
            for call in calls:
                name, raw_args = call["function"]["name"], call["function"].get("arguments", "")
                output = self._run_tool(name, raw_args)
                result.tool_events.append(ToolEvent(name, _parse_arguments(raw_args), output))
                turn.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        else:
            turn.append({"role": "assistant", "content": FALLBACK_REPLY})
        self.history.extend(turn)
        result.new_messages = turn
        return result

    def _run_tool(self, name: str, raw_args: str) -> str:
        try:
            return self.dispatch(name, raw_args)
        except Exception as exc:  # a broken tool must not kill the conversation
            return json.dumps({"error": f"tool '{name}' failed: {type(exc).__name__}: {exc}"})
