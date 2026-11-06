from types import SimpleNamespace

from src.agents.claude import ClaudeAgent
from src.experiments.configs import get_condition
from src.experiments.runner import run_condition
from src.information.log import load_game
from src.information.observation import Observation


def _first_obs():
    return Observation(agent_id=0, round=1, pool=20, n_agents=3, growth_factor=2, phase="first", history=[])


def _second_obs(own_first_announcement=5, own_first_take=5):
    return Observation(
        agent_id=0, round=1, pool=20, n_agents=3, growth_factor=2, phase="second", history=[],
        own_first_announcement=own_first_announcement,
        own_first_take=own_first_take,
        other_first_announcements={1: 3, 2: 4},
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


def test_parses_first_phase_text_block_and_skips_thinking():
    agent = ClaudeAgent(0, chat_fn=lambda **kw: _resp('{"first_announcement": 4, "first_take": 2}'))
    action = agent.act_first(_first_obs())
    assert (action.first_announcement, action.first_take) == (4, 2)
    assert action.parse_status == "ok"
    assert action.served_by == "claude-sonnet-5-5"


def test_parses_second_phase_text_block():
    agent = ClaudeAgent(
        0, chat_fn=lambda **kw: _resp('{"revise": "yes", "second_announcement": 1, "final_take": 2}')
    )
    action = agent.act_second(_second_obs())
    assert (action.revise, action.second_announcement, action.final_take) == (True, 1, 2)
    assert action.parse_status == "ok"
    assert action.served_by == "claude-sonnet-5-5"


def test_request_shape():
    sent = {}

    def chat_fn(**kwargs):
        sent.update(kwargs)
        return _resp('{"first_announcement": 1, "first_take": 1}')

    ClaudeAgent(0, effort="low", fallbacks=True, chat_fn=chat_fn).act_first(_first_obs())
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
        return _resp('{"first_announcement": 1, "first_take": 1}')

    ClaudeAgent(0, chat_fn=chat_fn).act_first(_first_obs())
    assert "fallbacks" not in sent and "betas" not in sent


def test_refusal_falls_back_to_default_take():
    agent = ClaudeAgent(0, chat_fn=lambda **kw: _resp("", stop_reason="refusal"))
    action = agent.act_first(_first_obs())
    assert action.parse_status == "fallback"
    assert action.first_announcement == 0 and action.first_take == 0
    assert agent.parse_failures == 2


def test_claude_condition_runs_with_mock(tmp_path):
    exp = get_condition("broadcast_unverified_claude")
    content = (
        '{"first_announcement": 3, "first_take": 2, '
        '"revise": "no", "second_announcement": 3, "final_take": 2}'
    )
    chat = lambda **kw: _resp(content)
    path = run_condition(exp, out_dir=tmp_path, chat_fn=chat, seeds=[0])[0]
    meta, rounds = load_game(path)
    assert meta["prompt_variant"] == "neutral"
    assert len(rounds) == 10
    assert rounds[0]["first_actions"][0]["served_by"] == "claude-sonnet-5-5"
