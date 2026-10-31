"""``python -m emporio.evals [--only id ...]``: run the scenarios against the real model."""

from __future__ import annotations

import argparse
import sys

from emporio.agent.config import ConfigError, load_settings
from emporio.agent.llm import LLMError, OpenAIClient, Usage
from emporio.evals import estimate_cost, run_all


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="emporio.evals")
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        results, path = run_all(OpenAIClient(settings), only=args.only)
    except (ConfigError, LLMError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    total = Usage()
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.id}  tools={r.tools}  tokens={r.usage.total_tokens}")
        for failure in r.failures:
            print(f"        - {failure}")
        total.add(r.usage)
    cost = estimate_cost(total)
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} passed | tokens: {total.prompt_tokens} in, "
          f"{total.completion_tokens} out | cost: {'n/d' if cost is None else f'US$ {cost:.4f}'}")
    print(f"Report: {path}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
