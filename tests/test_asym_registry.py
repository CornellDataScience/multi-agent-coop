"""Model registry and prefix routing."""

import pytest

from asymbench.settings import defaults, registry, resolve_model


def test_registry_contents():
    ids = {m.id for m in registry()}
    assert "claude-sonnet-5-5" in ids
    assert "meta-llama/llama-3.1-8b-instruct" in ids
    assert "mock/strong" in ids and "mock/weak" in ids
    d = defaults()
    assert d["test_model"] == "claude-sonnet-5-5"
    assert d["judge_model"] == "claude-haiku-5-5"


def test_known_id_resolves_with_registry_prices():
    spec = resolve_model("claude-sonnet-5-5")
    assert spec.provider == "anthropic" and spec.registered
    assert spec.price_in == 2.0 and spec.price_out == 10.0 and spec.max_tokens == 4000


def test_prefix_routing_unknown_ids():
    a = resolve_model("claude-hypothetical-9")
    assert a.provider == "anthropic" and not a.registered
    assert a.price_in >= 10.0  # conservative (high) default prices
    o = resolve_model("somevendor/new-model-7b")
    assert o.provider == "openrouter" and not o.registered and o.max_tokens == 1500
    m = resolve_model("mock/judge")
    assert m.provider == "mock" and m.price_in == 0


def test_unroutable_id_raises():
    with pytest.raises(ValueError):
        resolve_model("gpt-5")  # no claude- prefix, no slash


def test_mock_never_reaches_providers():
    import asyncio

    from asymbench.providers import ProviderError, chat
    with pytest.raises(ProviderError):
        asyncio.run(chat("mock/strong", "s", "u"))
