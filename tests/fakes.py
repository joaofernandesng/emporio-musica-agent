"""A scripted LLM client for offline tests."""

from __future__ import annotations

import json

from emporio.agent.llm import LLMResponse, Usage


def text(content: str, tokens=(10, 5)) -> LLMResponse:
    return LLMResponse({"role": "assistant", "content": content}, Usage(*tokens))


def calls(*specs: tuple[str, dict], tokens=(20, 8)) -> LLMResponse:
    """An assistant message asking for one or more tool calls (parallel when several)."""
    tool_calls = [
        {"id": f"call_{i}", "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}
        for i, (name, args) in enumerate(specs)
    ]
    return LLMResponse({"role": "assistant", "tool_calls": tool_calls}, Usage(*tokens))


class FakeClient:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, *responses: LLMResponse) -> None:
        self.responses = list(responses)
        self.requests: list[list[dict]] = []

    def chat(self, messages, tools):
        self.requests.append([dict(m) for m in messages])
        return self.responses.pop(0)
