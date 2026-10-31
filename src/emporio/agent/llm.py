"""Thin wrapper around the official OpenAI SDK.

The agent only depends on the small ``LLMClient`` protocol, so tests can plug in a
scripted fake. ``OpenAIClient`` adds an explicit timeout and up to two retries with
exponential backoff for transient errors (429, 5xx, timeouts, dropped connections);
authentication and other client errors are never retried.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import openai

from emporio.agent.config import Settings

Message = dict[str, Any]


class LLMError(Exception):
    """The model could not be reached or refused the request; message is user-facing."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


@dataclass
class LLMResponse:
    """One assistant message (OpenAI chat format) plus the tokens it cost."""

    message: Message
    usage: Usage


class LLMClient(Protocol):
    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse: ...


def is_transient(exc: Exception) -> bool:
    """True for errors worth retrying: rate limit, 5xx, timeouts, connection drops."""
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError)):
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


class OpenAIClient:
    def __init__(
        self,
        settings: Settings,
        sdk: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = settings.model
        self.max_retries = settings.max_retries
        self._sleep = sleep
        # SDK-level retries are off: this wrapper owns the retry policy.
        self._sdk = sdk or openai.OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout,
            max_retries=0,
        )

    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        for attempt in range(self.max_retries + 1):
            try:
                completion = self._sdk.chat.completions.create(
                    model=self.model, messages=messages, tools=tools
                )
                break
            except openai.AuthenticationError as exc:
                raise LLMError("A chave da API foi recusada (autenticação). Confira OPENAI_API_KEY.") from exc
            except openai.OpenAIError as exc:
                if is_transient(exc) and attempt < self.max_retries:
                    self._sleep(2**attempt)  # 1 s, then 2 s
                    continue
                raise LLMError(f"Não consegui falar com o modelo agora ({type(exc).__name__}).") from exc
        message = completion.choices[0].message.model_dump(exclude_none=True)
        message.pop("refusal", None)
        message.pop("annotations", None)
        message.pop("audio", None)
        raw = completion.usage
        usage = Usage(getattr(raw, "prompt_tokens", 0) or 0, getattr(raw, "completion_tokens", 0) or 0)
        return LLMResponse(message=message, usage=usage)
