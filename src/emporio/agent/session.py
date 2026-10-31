"""Conversation persistence: one JSON line per message in data/runtime/sessions/."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from emporio.paths import RUNTIME_DIR

SESSIONS_DIR = RUNTIME_DIR / "sessions"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def new_session_id() -> str:
    return uuid.uuid4().hex[:8]


class Session:
    """An append-only message log. The first line is the system message."""

    def __init__(self, session_id: str, directory: Path = SESSIONS_DIR) -> None:
        if not SESSION_ID_RE.match(session_id):
            raise ValueError("session id may only contain letters, digits, '-' and '_'")
        self.session_id = session_id
        self.path = directory / f"{session_id}.jsonl"

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> list[dict]:
        if not self.exists():
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def append(self, messages: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for message in messages:
                fh.write(json.dumps(message, ensure_ascii=False) + "\n")
