import json

import openai
from types import SimpleNamespace
import pytest

import emporio.agent.cli as cli
from emporio.agent.cli import chat, main
from emporio.agent.config import ConfigError, Settings, load_settings
from emporio.agent.llm import LLMError, OpenAIClient
from emporio.agent.loop import FALLBACK_REPLY, Agent, window
from emporio.agent.prompt import build_system_prompt
from emporio.agent.session import Session
from tests.fakes import FakeClient, calls, text


def dispatcher(log):
    def dispatch(name, raw):
        log.append((name, raw))
        return json.dumps({"ok": name})
    return dispatch


# ---- loop ---------------------------------------------------------------------

def test_tool_result_goes_back_to_the_model():
    log = []
    client = FakeClient(calls(("get_store_hours", {})), text("Estamos abertos!"))
    agent = Agent(client, dispatch=dispatcher(log))
    result = agent.respond("Está aberto?")
    assert result.text == "Estamos abertos!"
    assert log == [("get_store_hours", "{}")]
    second_request = client.requests[1]
    assert second_request[-1] == {
        "role": "tool", "tool_call_id": "call_0", "content": '{"ok": "get_store_hours"}'}
    assert second_request[-2]["tool_calls"][0]["function"]["name"] == "get_store_hours"
    assert result.tool_events[0].name == "get_store_hours"
    assert result.usage.total_tokens == 20 + 8 + 10 + 5


def test_parallel_tool_calls_all_answered():
    log = []
    client = FakeClient(
        calls(("get_product", {"name": "GD20"}), ("search_policies", {"query": "troca"})),
        text("Pronto"),
    )
    agent = Agent(client, dispatch=dispatcher(log))
    agent.respond("preço e troca")
    assert [n for n, _ in log] == ["get_product", "search_policies"]
    tool_msgs = [m for m in client.requests[1] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_0", "call_1"]


def test_iteration_limit_returns_polite_fallback():
    client = FakeClient(*[calls(("get_store_hours", {})) for _ in range(3)])
    agent = Agent(client, dispatch=dispatcher([]), max_iterations=3)
    result = agent.respond("oi")
    assert result.text == FALLBACK_REPLY
    assert agent.history[-1] == {"role": "assistant", "content": FALLBACK_REPLY}
    assert len(client.requests) == 3


def test_tool_exception_becomes_error_result_for_the_model():
    def boom(name, raw):
        raise RuntimeError("db down")
    client = FakeClient(calls(("get_product", {"name": "x"})), text("Não consegui consultar agora."))
    result = Agent(client, dispatch=boom).respond("oi")
    tool_msg = client.requests[1][-1]
    assert "error" in json.loads(tool_msg["content"]) and "db down" in tool_msg["content"]
    assert result.text.startswith("Não consegui")


def test_real_dispatch_returns_json_error_for_unknown_tool():
    client = FakeClient(calls(("nope", {})), text("ok"))
    Agent(client).respond("oi")
    assert json.loads(client.requests[1][-1]["content"]) == {"error": "unknown tool 'nope'"}


def test_failed_turn_leaves_history_untouched():
    class Broken:
        def chat(self, messages, tools):
            raise LLMError("fora do ar")
    agent = Agent(Broken())
    before = list(agent.history)
    with pytest.raises(LLMError):
        agent.respond("oi")
    assert agent.history == before


# ---- history window -------------------------------------------------------------

def _conversation(turns):
    messages = [{"role": "system", "content": "s"}]
    for i in range(turns):
        messages += [
            {"role": "user", "content": f"u{i}"},
            {"role": "assistant", "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {"name": "t", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "{}"},
            {"role": "assistant", "content": f"a{i}"},
        ]
    return messages


@pytest.mark.parametrize("size", range(1, 14))
def test_window_never_splits_tool_pairs(size):
    out = window(_conversation(4), size)
    assert out[0]["role"] == "system"
    body = out[1:]
    assert body and body[0]["role"] == "user"
    ids = {c["id"] for m in body for c in m.get("tool_calls", [])}
    results = {m["tool_call_id"] for m in body if m["role"] == "tool"}
    assert ids == results


def test_window_keeps_everything_when_short():
    messages = _conversation(2)
    assert window(messages, 30) == messages


# ---- prompt and clock -------------------------------------------------------------

def test_prompt_uses_emporio_now(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-25T10:00")
    prompt = build_system_prompt()
    assert "quarta-feira, 25/03/2026, 10:00" in prompt and "{{AGORA}}" not in prompt


# ---- config and CLI -----------------------------------------------------------------

def test_missing_config_is_a_clear_error(monkeypatch, tmp_path):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY e OPENAI_MODEL"):
        load_settings(tmp_path / "missing.env")


def test_settings_loaded_from_env_file(monkeypatch, tmp_path):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=k\nOPENAI_MODEL=m\nOPENAI_BASE_URL=\n", encoding="utf-8")
    settings = load_settings(env)
    assert (settings.api_key, settings.model, settings.base_url) == ("k", "m", None)
    # load_dotenv wrote into os.environ; undo it so other tests stay isolated.
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_main_exits_cleanly_without_config(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(cli, "load_settings", lambda: load_settings(None))
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "Configuração incompleta" in err and "Traceback" not in err


def test_main_rejects_bad_now(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: Settings("k", "m", None))
    monkeypatch.setenv("EMPORIO_NOW", "")
    assert main(["--now", "amanhã"]) == 2
    assert "EMPORIO_NOW" in capsys.readouterr().err


# ---- sessions ------------------------------------------------------------------------

def run_chat(client, inputs, tmp_path, session_id=None, **kw):
    out, feed = [], iter(inputs)

    def read(_):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError

    original = cli.Session
    cli.Session = lambda sid: original(sid, tmp_path / "sessions")
    try:
        chat(client, session_id, read=read, write=out.append, **kw)
    finally:
        cli.Session = original
    return out


def test_session_persists_and_resumes(tmp_path):
    run_chat(FakeClient(text("Olá!")), ["oi", "/sair"], tmp_path, "abc")
    lines = (tmp_path / "sessions" / "abc.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["role"] for line in lines] == ["system", "user", "assistant"]

    second = FakeClient(text("Voltei!"))
    out = run_chat(second, ["e então?", "/sair"], tmp_path, "abc")
    assert any("retomada" in line for line in out)
    sent = [m["content"] for m in second.requests[0] if m["role"] in ("user", "assistant")]
    assert sent == ["oi", "Olá!", "e então?"]


def test_reset_starts_a_new_conversation(tmp_path):
    client = FakeClient(text("a"), text("b"))
    run_chat(client, ["um", "/reset", "dois", "/sair"], tmp_path, "r1")
    assert [m["content"] for m in client.requests[1] if m["role"] == "user"] == ["dois"]


def test_llm_error_does_not_crash_chat(tmp_path):
    class Broken:
        def chat(self, messages, tools):
            raise LLMError("fora do ar")
    out = run_chat(Broken(), ["oi"], tmp_path, "e1")
    assert any("[erro] fora do ar" in line for line in out)


def test_session_id_is_validated():
    with pytest.raises(ValueError):
        Session("../../etc")


# ---- OpenAI wrapper: retry policy --------------------------------------------------------

def _status_error(cls, code):
    response = SimpleNamespace(status_code=code, headers={}, request=SimpleNamespace(method="POST"))
    return cls("boom", response=response, body=None)


class _Message:
    def model_dump(self, exclude_none=True):
        return {"role": "assistant", "content": "oi", "refusal": None}


class _Completion:
    usage = type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})()
    choices = [type("Ch", (), {"message": _Message()})()]


class _Sdk:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


SETTINGS = Settings("k", "m", None)


def test_transient_errors_are_retried_with_backoff():
    sleeps = []
    sdk = _Sdk(_status_error(openai.RateLimitError, 429),
               _status_error(openai.InternalServerError, 503), _Completion())
    response = OpenAIClient(SETTINGS, sdk=sdk, sleep=sleeps.append).chat([], [])
    assert sdk.calls == 3 and sleeps == [1, 2]
    assert response.message == {"role": "assistant", "content": "oi"}
    assert (response.usage.prompt_tokens, response.usage.completion_tokens) == (7, 3)


def test_gives_up_after_two_retries():
    sdk = _Sdk(*[_status_error(openai.InternalServerError, 500) for _ in range(3)])
    with pytest.raises(LLMError):
        OpenAIClient(SETTINGS, sdk=sdk, sleep=lambda s: None).chat([], [])
    assert sdk.calls == 3


def test_auth_error_is_not_retried():
    sdk = _Sdk(_status_error(openai.AuthenticationError, 401), _Completion())
    with pytest.raises(LLMError, match="autenticação"):
        OpenAIClient(SETTINGS, sdk=sdk, sleep=lambda s: None).chat([], [])
    assert sdk.calls == 1
