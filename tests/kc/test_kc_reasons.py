"""Optional one-sentence "reason" on both phases. Every model call is mocked."""
import pytest

from src.agents.backends import ChatResult
from src.knowledge_commons.agents.llm import KCLLMAgent
from src.knowledge_commons.agents.parsing import REASON_MAX_CHARS, extract_reason
from src.knowledge_commons.agents.prompts import build_prompts
from src.knowledge_commons.agents.scripted import make_scripted
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.environment import KCEnvironment
from src.knowledge_commons.log import load_game
from src.knowledge_commons.observation import build_guess_obs, build_message_obs
from src.knowledge_commons.replay import format_game

CFG = KCConfig()
MSG_OBS = build_message_obs(CFG, 1, 0, (4, 7, 1, 2), [])
GUESS_OBS = build_guess_obs(CFG, 1, 0, (4, 7, 1, 2), [], {1: {0: 7}, 2: {0: 1}, 3: {0: 2}})


class QueueBackend:
    def __init__(self, texts):
        self.texts, self.calls, self.model = list(texts), [], "q"

    def __call__(self, system, prompt):
        self.calls.append(prompt)
        return ChatResult(text=self.texts.pop(0), served_by="m", usage={})


def _msg(reason_json=""):
    return '{"messages": {"1": 4, "2": null, "3": 4}%s}' % reason_json


def _guess(reason_json=""):
    return '{"guess": [4, 7, 1, 2], "confidence": 0.9%s}' % reason_json


@pytest.mark.parametrize("text, expected", [
    (_msg(', "reason": "Agent 2 lied to me."'), "Agent 2 lied to me."),
    (_msg(', "reason": "  two\\n lines  "'), "two lines"),
    (_msg(), None),
    (_msg(', "reason": 42'), None),
    (_msg(', "reason": ["a"]'), None),
    (_msg(', "reason": null'), None),
    (_msg(', "reason": "   "'), None),
    ("not json at all", None),
])
def test_extract_reason(text, expected):
    assert extract_reason(text, "messages") == expected


def test_long_reason_is_truncated_not_rejected():
    r = extract_reason(_msg(', "reason": "%s"' % ("x" * 500)), "messages")
    assert r == "x" * REASON_MAX_CHARS


@pytest.mark.parametrize("reason_json, expected", [
    (', "reason": "Sharing keeps the bonus alive."', "Sharing keeps the bonus alive."),
    ("", None),
    (', "reason": 7', None),
    (', "reason": {"why": "nested"}', None),
    (', "reason": "%s"' % ("y" * 400), "y" * REASON_MAX_CHARS),
])
def test_reason_never_triggers_retry_or_fallback(reason_json, expected):
    b = QueueBackend([_msg(reason_json), _guess(reason_json)])
    agent = KCLLMAgent(0, b)
    m = agent.send_messages(MSG_OBS)
    g = agent.make_guess(GUESS_OBS)
    assert (m.parse_status, m.reason, m.sends) == ("ok", expected, {1: 4, 2: None, 3: 4})
    assert (g.parse_status, g.reason, g.guess) == ("ok", expected, (4, 7, 1, 2))
    assert len(b.calls) == 2 and agent.parse_failures == 0


def test_reason_comes_from_the_reply_that_parsed():
    b = QueueBackend(['{"messages": {"1": 99}, "reason": "bad"}', _msg(', "reason": "good"')])
    m = KCLLMAgent(0, b).send_messages(MSG_OBS)
    assert (m.parse_status, m.reason) == ("retry_ok", "good")
    b = QueueBackend(['{"guess": [1], "reason": "x"}', '{"guess": [1], "reason": "y"}'])
    g = KCLLMAgent(0, b).make_guess(GUESS_OBS)
    assert (g.parse_status, g.reason) == ("fallback", None)


def test_both_schemas_ask_for_optional_reason():
    for obs in (MSG_OBS, GUESS_OBS):
        _, prompt = build_prompts(obs)
        assert '"reason": "<one short sentence on why>"' in prompt
        assert '"reason" is optional: one short sentence on why.' in prompt


def test_reason_logged_per_action_and_shown(tmp_path):
    replies = [
        '{"q1_direction": "down", "q1_amount": 10, "q2_amount": 10}',
        _msg(', "reason": "Everyone shared last time."'),
        _guess(),
    ]
    agents = [KCLLMAgent(0, QueueBackend(replies))] + [make_scripted("honest", i) for i in (1, 2, 3)]
    log = KCEnvironment(KCConfig(max_rounds=1), agents, "r", codes=[(4, 7, 1, 2)]).run()
    path = log.write_jsonl(tmp_path / "r.jsonl")
    acts = load_game(path)["rounds"][0]["actions"]
    assert acts["message"][0]["reason"] == "Everyone shared last time."
    assert acts["guess"][0]["reason"] is None
    assert acts["message"][1]["reason"] is None  # scripted
    out = format_game(path)
    assert "why message: Everyone shared last time." in out
    assert "why guess" not in out
