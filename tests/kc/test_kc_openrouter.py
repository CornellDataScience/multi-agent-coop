"""OpenRouter backend and ``openrouter/`` routing. Mocked chat_fn / urlopen only."""
import io
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest

from src.agents import backends
from src.agents.backends import ChatResult, OpenRouterBackend, OpenRouterError
from src.knowledge_commons.agents.mock import mock_responder
from src.knowledge_commons.configs import get_condition
from src.knowledge_commons.log import load_game
from src.knowledge_commons.runner import make_backend, run_condition

# Captured at import, before conftest swaps it for the network blocker.
_REAL_POST = backends._openrouter_post


def _resp(text="hi", model="deepseek/deepseek-v4-pro-20261101", usage=(80, 12)):
    body = {"model": model, "choices": [{"message": {"role": "assistant", "content": text}}]}
    if usage is not None:
        body["usage"] = {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)}
    return body


def test_request_shape_and_result():
    sent = {}

    def chat_fn(**kw):
        sent.update(kw)
        return _resp('{"ok": 1}')

    result = OpenRouterBackend("deepseek/deepseek-v4-pro", chat_fn=chat_fn)("sys", "prompt")
    assert sent == {"model": "deepseek/deepseek-v4-pro",
                    "messages": [{"role": "system", "content": "sys"},
                                 {"role": "user", "content": "prompt"}]}
    assert result == ChatResult(text='{"ok": 1}', served_by="deepseek/deepseek-v4-pro-20261101",
                                usage={"input_tokens": 80, "output_tokens": 12})


def test_temperature_sent_only_when_set():
    sent = {}
    OpenRouterBackend("m", temperature=0.3, chat_fn=lambda **kw: sent.update(kw) or _resp())("s", "p")
    assert sent["temperature"] == 0.3


def test_missing_usage_and_null_content():
    result = OpenRouterBackend("m", chat_fn=lambda **kw: _resp(text=None, usage=None))("s", "p")
    assert result.text == "" and result.usage == {}


def test_error_payload_and_empty_choices_raise():
    with pytest.raises(OpenRouterError, match="rate limited"):
        OpenRouterBackend("m", chat_fn=lambda **kw: {"error": {"code": 429, "message": "rate limited"}})("s", "p")
    with pytest.raises(OpenRouterError, match="no choices"):
        OpenRouterBackend("m", chat_fn=lambda **kw: {"choices": []})("s", "p")


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY is not set"):
        OpenRouterBackend("m")("s", "p")


def test_default_path_is_blocked_in_tests(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with pytest.raises(RuntimeError, match="network access is disabled"):
        OpenRouterBackend("m")("s", "p")


def test_post_builds_request_and_parses_json(monkeypatch):
    seen = {}

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, method=req.get_method(), auth=req.get_header("Authorization"),
                    ctype=req.get_header("Content-type"), body=json.loads(req.data))
        return FakeResp(json.dumps(_resp("ok")).encode())

    monkeypatch.setattr(backends.urllib.request, "urlopen", fake_urlopen)
    out = _REAL_POST({"model": "m", "messages": []}, "k123")
    assert out["choices"][0]["message"]["content"] == "ok"
    assert seen == {"url": "https://openrouter.ai/api/v1/chat/completions", "method": "POST",
                    "auth": "Bearer k123", "ctype": "application/json",
                    "body": {"model": "m", "messages": []}}


def test_http_error_is_a_clear_error(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(b'{"error":{"message":"No auth credentials found"}}'))

    monkeypatch.setattr(backends.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OpenRouterError, match="HTTP 401.*No auth credentials"):
        _REAL_POST({"model": "m", "messages": []}, "bad")


def test_routing_strips_prefix():
    b = make_backend("openrouter/deepseek/deepseek-v4-pro", 0, 0, temperature=0.5)
    assert isinstance(b, OpenRouterBackend)
    assert b.model == "deepseek/deepseek-v4-pro" and b.temperature == 0.5
    assert type(make_backend("llama3.1:8b", 0, 0)).__name__ == "OllamaBackend"
    with pytest.raises(ValueError, match="needs a model ID"):
        make_backend("openrouter/", 0, 0)


def test_run_uses_openrouter_and_filename_is_safe(tmp_path):
    seen = []

    def chat_fn(**kw):
        seen.append(kw)
        system, prompt = kw["messages"][0]["content"], kw["messages"][1]["content"]
        return _resp(mock_responder(0)(system, prompt), model="deepseek/deepseek-v4-pro")

    res = run_condition(get_condition("kc_probe_honest"), tmp_path, model="openrouter/deepseek/deepseek-v4-pro:free",
                        seeds=[0], rounds=2, chat_fn=chat_fn)
    assert seen and all(kw["model"] == "deepseek/deepseek-v4-pro:free" for kw in seen)
    path = res.paths[0]
    assert path.parent == tmp_path
    assert path.name == "kc_probe_honest_openrouter-deepseek-deepseek-v4-pro-free_a0_private_memory_neutral_r2_seed0.jsonl"
    agent = load_game(path)["meta"]["agents"][0]
    assert agent["type"] == "openrouter" and agent["model"] == "deepseek/deepseek-v4-pro:free"


def test_experiment_script_accepts_openrouter_and_sanitizes_out_dir():
    """Run the script with a bad stage (exits before any model call) to check
    it accepts openrouter/ names, and apply its own OUT line to one."""
    script = Path("scripts/kc_experiments.sh")
    ok = subprocess.run(["bash", str(script), "openrouter/deepseek/deepseek-v4-pro", "nope", "1"],
                        capture_output=True, text=True)
    assert ok.returncode == 1 and "stage must be sweep or followup" in ok.stdout
    bad = subprocess.run(["bash", str(script), "openrouter/", "sweep", "1"], capture_output=True, text=True)
    assert bad.returncode == 1 and "usage:" in bad.stdout

    out_line = next(l for l in script.read_text().splitlines() if l.startswith("OUT="))
    out = subprocess.run(["bash", "-c", f'set -- "$0"; {out_line}; echo "$OUT"',
                          "openrouter/deepseek/deepseek-v4-pro:free"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "results/kc/openrouter_deepseek_deepseek-v4-pro_free"
