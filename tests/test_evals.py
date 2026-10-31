import json

from emporio.evals import check, normalize, run_all
from tests.fakes import FakeClient, calls, text


def test_normalize_is_accent_and_case_insensitive():
    assert normalize("  Não   PODEMOS  ") == "nao podemos"


def test_check_reports_each_kind_of_failure():
    scenario = {"tools_any": ["a"], "tools_all": ["b"], "tools_none": ["c"],
                "must": [["xx", "yy"]], "must_not": ["zz"]}
    assert check(scenario, ["a", "b"], ["tem YY aqui"]) == []
    failures = check(scenario, ["c"], ["zz"])
    assert len(failures) == 5


def test_runner_end_to_end_with_scripted_client(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "")
    scenarios = tmp_path / "s.json"
    scenarios.write_text(json.dumps({"default_now": "2026-03-25T10:00", "scenarios": [
        {"id": "aberto", "messages": ["aberto?"], "tools_any": ["get_store_hours"], "must": [["aberto"]]},
        {"id": "falha", "messages": ["oi"], "tools_any": ["get_store_hours"]},
    ]}), encoding="utf-8")
    client = FakeClient(calls(("get_store_hours", {})), text("Estamos ABERTOS, sim!"), text("Olá"))
    results, report = run_all(client, scenarios, reports_dir=tmp_path / "out", stamp="t")
    assert [r.passed for r in results] == [True, False]
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["passed"] == 1 and data["total"] == 2 and data["tokens"]["total"] > 0
    # the injected clock reached the tool: Wednesday 10:00 is open
    hours_result = json.loads(client.requests[1][-1]["content"])
    assert hours_result["is_open"] is True


def test_real_scenarios_file_is_well_formed():
    from emporio.evals import SCENARIOS_PATH
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    ids = [s["id"] for s in data["scenarios"]]
    assert len(ids) == len(set(ids)) >= 12
    assert all(s["messages"] for s in data["scenarios"])


def test_replies_must_not_mention_the_internal_manual():
    assert check({}, [], ["Pelo manual, seção 4.1, pode."])  # both words flagged
    assert check({}, [], ["Pela nossa política de trocas, sim."]) == []
    assert check({}, [], ["com acessórios e manuais"]) == []  # plural product manuals are fine


def test_list_item_limit():
    five = "Opções:\n- a\n- b\n* c\n3. d\n• e"
    four = "- a\n- b\n- c\n- d"
    assert check({"max_list_items": 4}, [], [five])
    assert check({"max_list_items": 4}, [], [four]) == []
