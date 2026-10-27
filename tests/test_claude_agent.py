from types import SimpleNamespace

from src.agents.claude import ClaudeAgent
from src.experiments.configs import get_condition
from src.experiments.runner import run_condition
from src.information.log import load_game
from src.information.observation import Observation


def _obs(communication=True):
    return Observation(
        agent_id=0, round=1, pool=20, n_agents=3,
        growth_factor=2, communication=communication, history=[],
    )


def _resp(text, stop_reason="end_turn", model="claude-sonnet-5-5"):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop_reason,
        model=model,
    )


def test_parses_text_block_and_skips_thinking():
    agent = ClaudeAgent(0, chat_fn=lambda **kw: _resp('{"take": 4, "claimed_take": 2}'))
    action = agent.act(_obs())
    assert (action.take, action.claimed_take) == (4, 2)
    assert action.parse_status == "ok"
    assert action.served_by == "claude-sonnet-5-5"


def test_request_shape():
    sent = {}

    def chat_fn(**kwargs):
        sent.update(kwargs)
        return _resp('{"take": 1, "claimed_take": 1}')

    ClaudeAgent(0, effort="low", fallbacks=True, chat_fn=chat_fn).act(_obs())
    assert sent["model"] == "claude-sonnet-5-5"
    assert isinstance(sent["system"], str) and sent["system"]
    assert [m["role"] for m in sent["messages"]] == ["user"]
    assert sent["output_config"] == {"effort": "low"}
    assert sent["fallbacks"] == "default"
    assert "temperature" not in sent


def test_fallbacks_off_by_default_omits_beta():
    sent = {}

    def chat_fn(**kwargs):
        sent.update(kwargs)
        return _resp('{"take": 1, "claimed_take": 1}')

    ClaudeAgent(0, chat_fn=chat_fn).act(_obs())
    assert "fallbacks" not in sent and "betas" not in sent


def test_refusal_falls_back_to_default_take():
    agent = ClaudeAgent(0, chat_fn=lambda **kw: _resp("", stop_reason="refusal"))
    action = agent.act(_obs())
    assert action.parse_status == "fallback"
    assert action.take == 0
    assert agent.parse_failures == 2


def test_claude_condition_runs_with_mock(tmp_path):
    exp = get_condition("broadcast_unverified_claude")
    chat = lambda **kw: _resp('{"take": 3, "claimed_take": 2}')
    path = run_condition(exp, out_dir=tmp_path, chat_fn=chat, seeds=[0])[0]
    meta, rounds = load_game(path)
    assert meta["prompt_variant"] == "neutral"
    assert len(rounds) == 10
    assert rounds[0]["actions"][0]["served_by"] == "claude-sonnet-5-5"
