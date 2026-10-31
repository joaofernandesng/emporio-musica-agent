"""Settings read from the environment (and ``.env`` through python-dotenv)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from emporio.paths import ROOT


class ConfigError(Exception):
    """Missing or invalid configuration; the message is meant for the user."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str | None
    timeout: float = 30.0
    max_retries: int = 2


def load_settings(env_file: Path | None = ROOT / ".env") -> Settings:
    """Load ``.env`` (never overriding real variables) and validate the settings."""
    if env_file is not None:
        load_dotenv(env_file, override=False)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", "").strip()
    missing = [name for name, value in (("OPENAI_API_KEY", api_key), ("OPENAI_MODEL", model)) if not value]
    if missing:
        raise ConfigError(
            f"Configuração incompleta: defina {' e '.join(missing)} no arquivo .env "
            "(veja .env.example) ou no ambiente."
        )
    return Settings(
        api_key=api_key,
        model=model,
        base_url=os.environ.get("OPENAI_BASE_URL", "").strip() or None,
    )
