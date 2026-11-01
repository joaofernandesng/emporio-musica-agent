"""Offline checks of the persona and empty-search scenarios: right passes, wrong fails."""

import json

import pytest

from emporio.evals import SCENARIOS_PATH, check

SCENARIOS = {s["id"]: s for s in json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]}

CASES = {
    "persona_nome": (
        ["Eu sou a Lira, assistente virtual da Empório da Música. Não sou uma pessoa, mas posso te ajudar!"],
        ["Sou a Lira, sim, sou uma pessoa de verdade aqui da loja."],
        []),
}


@pytest.mark.parametrize("scenario_id", sorted(CASES))
def test_correct_reply_passes(scenario_id):
    good, _, tools = CASES[scenario_id]
    assert check(SCENARIOS[scenario_id], tools, good) == []


@pytest.mark.parametrize("scenario_id", sorted(CASES))
def test_wrong_reply_fails(scenario_id):
    _, bad, tools = CASES[scenario_id]
    assert check(SCENARIOS[scenario_id], tools, bad)
