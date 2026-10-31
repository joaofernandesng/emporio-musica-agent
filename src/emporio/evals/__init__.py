"""Scenario-based evaluation of the agent against a real or scripted model."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from emporio.agent.llm import LLMClient, Usage
from emporio.agent.loop import Agent
from emporio.paths import ROOT, RUNTIME_DIR
from emporio.tools import call_tool
from emporio.tools.common import CLOCK_ENV
from emporio.tools.tickets import create_ticket

SCENARIOS_PATH = ROOT / "evals" / "scenarios.json"
REPORTS_DIR = RUNTIME_DIR / "evals"


def normalize(text: str) -> str:
    """Lowercase, no accents, collapsed whitespace: makes text checks tolerant."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", plain.lower()).strip()


@dataclass
class ScenarioResult:
    id: str
    passed: bool
    failures: list[str]
    tools: list[str]
    replies: list[str]
    usage: Usage = field(default_factory=Usage)
    calls: list[dict[str, Any]] = field(default_factory=list)


# The policies manual is internal: replies to customers must never mention it.
GLOBAL_FORBIDDEN = (r"\bmanual\b", r"\bsecao\b", r"\bsecoes\b")
LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.MULTILINE)


def count_list_items(replies: list[str]) -> int:
    """Largest number of list items (bullets or numbered lines) in a single reply."""
    return max((len(LIST_ITEM.findall(r)) for r in replies), default=0)


def check(scenario: dict[str, Any], tools: list[str], replies: list[str]) -> list[str]:
    """Return the list of failed checks (empty = scenario passed)."""
    text = normalize(" ".join(replies))
    failures: list[str] = []
    if scenario.get("tools_any") and not set(scenario["tools_any"]) & set(tools):
        failures.append(f"expected one of tools {scenario['tools_any']}, got {tools}")
    for name in scenario.get("tools_all", []):
        if name not in tools:
            failures.append(f"expected tool {name}, got {tools}")
    for name in scenario.get("tools_none", []):
        if name in tools:
            failures.append(f"tool {name} must not be called")
    for alternatives in scenario.get("must", []):
        if not any(normalize(a) in text for a in alternatives):
            failures.append(f"reply should contain one of {alternatives}")
    for forbidden in scenario.get("must_not", []):
        if normalize(forbidden) in text:
            failures.append(f"reply must not contain {forbidden!r}")
    for pattern in GLOBAL_FORBIDDEN:
        if re.search(pattern, text):
            failures.append(f"reply must not mention the internal manual/section ({pattern})")
    minimum = scenario.get("min_list_items")
    if minimum is not None and count_list_items(replies) < minimum:
        failures.append(f"list has {count_list_items(replies)} items, expected at least {minimum}")
    limit = scenario.get("max_list_items")
    if limit is not None and count_list_items(replies) > limit:
        failures.append(f"list has {count_list_items(replies)} items, limit is {limit}")
    return failures


def run_scenario(client: LLMClient, scenario: dict[str, Any], now: str, tickets_path: Path) -> ScenarioResult:
    os.environ[CLOCK_ENV] = scenario.get("now", now)

    def dispatch(name: str, raw: str) -> str:
        if name == "create_ticket":  # keep eval tickets out of the real queue
            try:
                args = json.loads(raw or "{}")
                return json.dumps(create_ticket(**args, path=tickets_path), ensure_ascii=False)
            except (json.JSONDecodeError, TypeError) as exc:
                return json.dumps({"error": f"bad arguments for create_ticket: {exc}"})
        return call_tool(name, raw)

    agent = Agent(client, dispatch=dispatch)
    tools: list[str] = []
    calls: list[dict[str, Any]] = []
    replies: list[str] = []
    usage = Usage()
    for message in scenario["messages"]:
        turn = agent.respond(message)
        tools += [e.name for e in turn.tool_events]
        calls += [_describe(e) for e in turn.tool_events]
        replies.append(turn.text)
        usage.add(turn.usage)
    failures = check(scenario, tools, replies)
    return ScenarioResult(scenario["id"], not failures, failures, tools, replies, usage, calls)


def _describe(event) -> dict[str, Any]:
    """Tool call with its arguments and, for policy searches, the sections returned."""
    call: dict[str, Any] = {"name": event.name, "arguments": event.arguments}
    if event.name == "search_policies":
        try:
            call["sections"] = [r["section"] for r in json.loads(event.result).get("results", [])]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return call


def estimate_cost(usage: Usage) -> float | None:
    """USD estimate from OPENAI_PRICE_INPUT_PER_1M / OPENAI_PRICE_OUTPUT_PER_1M, if set."""
    try:
        price_in = float(os.environ["OPENAI_PRICE_INPUT_PER_1M"])
        price_out = float(os.environ["OPENAI_PRICE_OUTPUT_PER_1M"])
    except (KeyError, ValueError):
        return None
    return (usage.prompt_tokens * price_in + usage.completion_tokens * price_out) / 1_000_000


def run_all(
    client: LLMClient,
    scenarios_path: Path = SCENARIOS_PATH,
    only: list[str] | None = None,
    reports_dir: Path = REPORTS_DIR,
    stamp: str | None = None,
) -> tuple[list[ScenarioResult], Path]:
    data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    scenarios = [s for s in data["scenarios"] if not only or s["id"] in only]
    now = os.environ.get(CLOCK_ENV, "").strip() or data["default_now"]
    previous = os.environ.get(CLOCK_ENV)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        try:
            for scenario in scenarios:
                results.append(run_scenario(client, scenario, now, Path(tmp) / "tickets.jsonl"))
        finally:
            if previous is None:
                os.environ.pop(CLOCK_ENV, None)
            else:
                os.environ[CLOCK_ENV] = previous
    return results, write_report(results, now, reports_dir, stamp)


def write_report(results: list[ScenarioResult], now: str, reports_dir: Path, stamp: str | None) -> Path:
    total = Usage()
    for r in results:
        total.add(r.usage)
    cost = estimate_cost(total)
    report = {
        "now": now,
        "model": os.environ.get("OPENAI_MODEL", ""),
        "passed": sum(r.passed for r in results),
        "total": len(results),
        "tokens": {"prompt": total.prompt_tokens, "completion": total.completion_tokens, "total": total.total_tokens},
        "estimated_cost_usd": cost,
        "scenarios": [
            {"id": r.id, "passed": r.passed, "failures": r.failures, "tools": r.tools, "calls": r.calls,
             "tokens": r.usage.total_tokens, "replies": r.replies}
            for r in results
        ],
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"eval-{stamp or datetime.now():%Y%m%d-%H%M%S}.json" if not isinstance(stamp, str) \
        else reports_dir / f"eval-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
