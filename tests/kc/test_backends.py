from types import SimpleNamespace

from src.agents.backends import ChatResult, ClaudeBackend, MockBackend, OllamaBackend


def _claude_resp(text, stop_reason="end_turn", model="claude-haiku-5-5", usage=(120, 30)):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="hidden"),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop_reason,
        model=model,
        usage=None if usage is None else SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
    )


def test_claude_backend_returns_text_model_and_usage():
    sent = {}

    def chat_fn(**kw):
        sent.update(kw)
        return _claude_resp('{"ok": 1}')

    result = ClaudeBackend(model="claude-haiku-5-5", effort="low", chat_fn=chat_fn)("sys", "hi")
    assert result == ChatResult(text='{"ok": 1}', served_by="claude-haiku-5-5",
                                usage={"input_tokens": 120, "output_tokens": 30}, refused=False)
    assert sent["system"] == "sys"
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["output_config"] == {"effort": "low"}
    assert "betas" not in sent and "fallbacks" not in sent


def test_claude_backend_flags_refusal_and_handles_missing_usage():
    result = ClaudeBackend(chat_fn=lambda **kw: _claude_resp("", stop_reason="refusal", usage=None))("s", "p")
    assert result.refused is True
    assert result.usage == {}


def test_claude_backend_fallbacks_adds_beta():
    sent = {}

    def chat_fn(**kw):
        sent.update(kw)
        return _claude_resp("x")

    ClaudeBackend(fallbacks=True, chat_fn=chat_fn)("s", "p")
    assert sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"]


def test_ollama_backend_text_options_and_usage():
    sent = {}

    def chat_fn(**kw):
        sent.update(kw)
        return {"message": {"content": "hello"}, "prompt_eval_count": 50, "eval_count": 7}

    result = OllamaBackend(model="m", temperature=0.2, seed=9, chat_fn=chat_fn)("sys", "p")
    assert result.text == "hello"
    assert result.usage == {"input_tokens": 50, "output_tokens": 7}
    assert sent["options"] == {"temperature": 0.2, "seed": 9}
    assert sent["messages"][0] == {"role": "system", "content": "sys"}


def test_ollama_backend_without_counts_has_empty_usage():
    result = OllamaBackend(chat_fn=lambda **kw: {"message": {"content": "x"}})("s", "p")
    assert result.usage == {}


def test_mock_backend_cycles_replies_and_records_calls():
    backend = MockBackend(replies=["a", "b"])
    assert [backend("s", str(i)).text for i in range(3)] == ["a", "b", "a"]
    assert backend.calls[1] == ("s", "1")


def test_mock_backend_responder_sees_prompt():
    backend = MockBackend(responder=lambda system, prompt: prompt.upper())
    assert backend("s", "abc").text == "ABC"
    assert backend("s", "abc").served_by == "mock"
