"""Record a scripted conversation with the real agent as a Markdown transcript.

``python -m emporio.demo examples/scripts/01-catalogo.json`` runs the customer
messages of the script, in order, in ONE session (so the agent keeps context),
with the simulated clock ``EMPORIO_NOW=2026-03-25T10:00``, and writes
``examples/<script name>.md``. The agent's text is copied exactly; each turn also
gets a collapsible block with the tools it called and a short result summary.
This module only drives the agent: it never changes its prompt or tools.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from emporio.agent.config import ConfigError, load_settings
from emporio.agent.llm import LLMClient, LLMError, OpenAIClient, Usage
from emporio.agent.loop import Agent, ToolEvent
from emporio.evals import estimate_cost
from emporio.paths import ROOT
from emporio.tools import call_tool
from emporio.tools.common import CLOCK_ENV
from emporio.tools.tickets import create_ticket

DEMO_NOW = "2026-03-25T10:00"
EXAMPLES_DIR = ROOT / "examples"


def summarize_result(name: str, raw: str) -> str:
    """One short line describing a tool result (the full JSON is not reproduced)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:160]
    if "error" in data:
        return f"error: {data['error']}"
    if name == "search_products":
        if data.get("not_sold_accessory"):
            return "not_sold_accessory=true (the store sells instruments only), no catalog results"
        names = [r["name"] for r in data["results"][:4]]
        more = " ..." if data["count"] > len(names) else ""
        return f"{data['count']} result(s): " + "; ".join(names) + more
    if name == "get_product":
        p = data.get("product")
        if not p:
            return f"status={data['status']}"
        text = f"{p['name']}: {p['current_price_text']}, {p['availability_label']}"
        if p.get("promotion"):
            text += f", promotion {p['promotion']['discount_percent']}% (was {p['promotion']['original_price_text']})"
        if "alternatives" in p:
            text += f", {len(p['alternatives'])} alternative(s) returned"
        return text
    if name == "get_order_status":
        if not data.get("verified"):
            return "verified=false (generic answer, nothing disclosed)"
        o = data["order"]
        text = f"verified=true, status={o['status']}, delayed={o['delayed']}"
        windows = o.get("return_windows")
        if windows:
            text += "; " + ", ".join(
                f"{k}: {'within' if v['within_deadline'] else 'expired'} (deadline {v['deadline']})"
                for k, v in windows.items()
            )
        return text
    if name == "search_policies":
        sections = ", ".join(f"{r['section']} {r['title']}" for r in data["results"])
        return f"sections returned: {sections}" + (f" (+{len(data['notes'])} note(s))" if data.get("notes") else "")
    if name == "calculate_payment":
        if not data.get("allowed", True):
            return f"allowed=false: {data.get('reason')}"
        return (f"{data['method']}: total {data['total_text']}"
                + (f", {data['installments']}x {data['installment_text']}" if data["installments"] > 1 else ""))
    if name == "get_store_hours":
        return f"is_open={data['is_open']}, now={data['now']}"
    if name == "create_ticket":
        return f"created={data.get('created')}, ticket_id={data.get('ticket_id')}"
    return json.dumps(data, ensure_ascii=False)[:160]


def _quote(text: str) -> str:
    return "\n".join("> " + line if line else ">" for line in text.splitlines())


def render_turn(user: str, reply: str, events: list[ToolEvent]) -> str:
    parts = [f"**Cliente:** {user}", "", "**Lira:**", "", _quote(reply), ""]
    if events:
        parts += [f"<details><summary>Tools called ({len(events)})</summary>", ""]
        for e in events:
            args = json.dumps(e.arguments, ensure_ascii=False)
            parts.append(f"- `{e.name}({args})`  \n  → {summarize_result(e.name, e.result)}")
        parts += ["", "</details>", ""]
    else:
        parts += ["<details><summary>Tools called (0)</summary>", "", "No tool was needed.", "", "</details>", ""]
    return "\n".join(parts)


def record(
    script: dict[str, Any],
    client: LLMClient,
    *,
    model: str,
    recorded_at: datetime | None = None,
    tickets_path: Path | None = None,
) -> tuple[str, Usage]:
    """Run the scripted messages and return the Markdown transcript and total usage."""
    simulated = script.get("now", DEMO_NOW)
    previous = os.environ.get(CLOCK_ENV)
    os.environ[CLOCK_ENV] = simulated
    own_tmp = tempfile.TemporaryDirectory() if tickets_path is None else None
    tickets = tickets_path or Path(own_tmp.name) / "tickets.jsonl"

    def dispatch(name: str, raw: str) -> str:
        if name == "create_ticket":  # keep demo tickets out of the real queue
            try:
                return json.dumps(create_ticket(**json.loads(raw or "{}"), path=tickets), ensure_ascii=False)
            except (json.JSONDecodeError, TypeError) as exc:
                return json.dumps({"error": f"bad arguments for create_ticket: {exc}"})
        return call_tool(name, raw)

    try:
        agent = Agent(client, dispatch=dispatch)
        usage = Usage()
        turns = []
        for message in script["messages"]:
            result = agent.respond(message)
            usage.add(result.usage)
            turns.append(render_turn(message, result.text, result.tool_events))
    finally:
        if previous is None:
            os.environ.pop(CLOCK_ENV, None)
        else:
            os.environ[CLOCK_ENV] = previous
        if own_tmp:
            own_tmp.cleanup()

    cost = estimate_cost(usage)
    cost_text = "n/a" if cost is None else f"US$ {cost:.4f}"
    stamp = (recorded_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    header = [
        f"# {script['title']}",
        "",
        f"- **Scenario:** {script['description']}",
        f"- **Simulated date/time (store clock):** {simulated} (America/Campo_Grande)",
        f"- **Model:** {model}",
        f"- **Recorded:** {stamp} (real time of the run)",
        f"- **Usage:** {usage.prompt_tokens} prompt + {usage.completion_tokens} completion tokens, "
        f"estimated cost {cost_text}",
        "",
        "Real run of the agent: the attendant's text below is exactly what the model returned. "
        "The collapsible blocks list the tools it called (customer data in them is fictional).",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + "\n".join(turns), usage


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="emporio.demo", description="Record scripted conversations.")
    parser.add_argument("scripts", nargs="+", type=Path, help="script JSON files (see examples/scripts/)")
    parser.add_argument("--out-dir", type=Path, default=EXAMPLES_DIR)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    client = OpenAIClient(settings)
    total = Usage()
    for path in args.scripts:
        script = json.loads(path.read_text(encoding="utf-8"))
        try:
            text, usage = record(script, client, model=settings.model)
        except LLMError as exc:
            print(f"Erro: {exc}", file=sys.stderr)
            return 2
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / f"{path.stem}.md"
        target.write_text(text, encoding="utf-8")
        total.add(usage)
        cost = estimate_cost(usage)
        print(f"{target}: {usage.total_tokens} tokens, "
              f"{'cost n/a' if cost is None else f'US$ {cost:.4f}'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
