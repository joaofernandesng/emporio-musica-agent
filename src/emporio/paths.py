"""Filesystem locations shared by the whole project."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
RUNTIME_DIR = ROOT / "data" / "runtime"

DB_PATH = RUNTIME_DIR / "store.db"
TICKETS_PATH = RUNTIME_DIR / "tickets.jsonl"
POLICIES_PATH = PROCESSED_DIR / "policies.md"
POLICIES_PDF = RAW_DIR / "políticas_da_loja.pdf"
