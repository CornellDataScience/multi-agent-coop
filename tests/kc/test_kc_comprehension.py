"""Pre-game comprehension check (quiz). Every model call is mocked."""
import json
import re
from pathlib import Path

import pytest

from src.agents.backends import ChatResult, MockBackend
from src.knowledge_commons.agents.llm import KCLLMAgent
from src.knowledge_commons.agents.mock import mock_responder
from src.knowledge_commons.agents.parsing import ParseError, parse_comprehension_output
from src.knowledge_commons.agents.prompts import build_prompts, build_quiz_prompts
from src.knowledge_commons.agents.scripted import make_scripted
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.environment import KCEnvironment
from src.knowledge_commons.log import load_game
from src.knowledge_commons.metrics import aggregate, summarize_game
from src.knowledge_commons.observation import build_message_obs, build_rules_obs
from src.knowledge_commons.replay import format_game
from src.knowledge_commons.scoring import (QUIZ_OTHERS_GAIN, QUIZ_OWN_GAIN, comprehension_expected,
                                           grade_comprehension)

FIXTURE = Path(__file__).parent / "fixtures" / "hand_game.jsonl"
PASS = '{"q1_direction": "down", "q1_amount": 10, "q2_amount": 10}'  # correct at alpha 0.5
WRONG = '{"q1_direction": "up", "q1_amount": 10, "q2_amount": 10}'


def _r(text, usage=None, refused=False):
    return ChatResult(text=text, served_by="m", usage=usage or {}, refused=refused)


class QueueBackend:
    def __init__(self, results):
        self.results, self.calls, self.model = list(results), [], "q"

    def __call__(self, system, prompt):
        self.calls.append((system, prompt))
        return self.results.pop(0)


def _game_responder(quiz_reply=PASS):
    """Deterministic: quiz -> quiz_reply; message -> share the true digit;
    guess -> own + received digits."""
    def respond(system, prompt):
        if '"q1_direction"' in prompt:
            return quiz_reply
        digit = re.search(r"this round is (\d)", prompt).group(1)
        if '"messages"' in prompt:
            keys = re.findall(r'"(\d+)": <digit', prompt)
            return '{"messages": {%s}}' % ", ".join(f'"{k}": {digit}' for k in keys)
        n = int(re.search(r"exactly (\d+) digits", prompt).group(1))
        me = int(re.search(r"position (\d+)\)", prompt).group(1))
        g = [0] * n
        for j, d in re.findall(r"agent (\d+) sent you (\d)", prompt):
            g[int(j)] = int(d)
        g[me] = int(digit)
        return json.dumps({"guess": g})
    return respond


# --- Grading -----------------------------------------------------------------

def test_expected_answers_follow_alpha():
    assert comprehension_expected(0.5) == {"q1_direction": "down", "q1_change": -10.0, "q2_change": 10.0}
    assert comprehension_expected(1.5)["q1_change"] == pytest.approx(-30.0)
    assert comprehension_expected(0.0) == {"q1_direction": "same", "q1_change": 0.0, "q2_change": 10.0}
    assert (QUIZ_OTHERS_GAIN, QUIZ_OWN_GAIN) == (20, 10)


@pytest.mark.parametrize("answers, alpha, ok", [
    ({"q1_direction": "down", "q1_amount": 10, "q2_amount": 10}, 0.5, True),
    ({"q1_direction": "down", "q1_amount": -10, "q2_amount": 10}, 0.5, True),  # signed amount
    ({"q1_direction": "down", "q1_amount": 30, "q2_amount": 10}, 1.5, True),
    ({"q1_direction": "same", "q1_amount": 0, "q2_amount": 10}, 0.0, True),
    ({"q1_direction": "up", "q1_amount": 10, "q2_amount": 10}, 0.5, False),
    ({"q1_direction": "down", "q1_amount": 20, "q2_amount": 10}, 0.5, False),
    ({"q1_direction": "down", "q1_amount": 10, "q2_amount": -10}, 0.5, False),
    ({"q1_direction": "down", "q1_amount": 0, "q2_amount": 10}, 0.0, False),
    (None, 0.5, False),
])
def test_grading(answers, alpha, ok):
    assert grade_comprehension(answers, alpha) is ok


# --- Parsing -----------------------------------------------------------------

def test_parse_valid_and_lenient_forms():
    assert parse_comprehension_output(PASS) == {"q1_direction": "down", "q1_amount": 10.0, "q2_amount": 10.0}
    wrapped = 'Sure:\n```json\n{"q1_direction": " Down ", "q1_amount": "-10", "q2_amount": "+10"}\n```'
    assert parse_comprehension_output(wrapped) == {"q1_direction": "down", "q1_amount": -10.0,
                                                   "q2_amount": 10.0}


@pytest.mark.parametrize("text", [
    "", "no idea", '{"q1_amount": 1, "q2_amount": 1}',
    '{"q1_direction": "sideways", "q1_amount": 1, "q2_amount": 1}',
    '{"q1_direction": "down", "q2_amount": 1}',
    '{"q1_direction": "down", "q1_amount": "ten", "q2_amount": 10}',
    '{"q1_direction": "down", "q1_amount": true, "q2_amount": 10}',
    '{"q1_direction": "down", "q1_amount": NaN, "q2_amount": 10}',
])
def test_parse_invalid(text):
    with pytest.raises(ParseError):
        parse_comprehension_output(text)


# --- Prompt ------------------------------------------------------------------

def test_quiz_prompt_reuses_system_and_rules_and_is_neutral():
    cfg = KCConfig(alpha=0.5)
    qsys, quiz = build_quiz_prompts(build_rules_obs(cfg, 1))
    gsys, game = build_prompts(build_message_obs(cfg, 1, 1, (1, 2, 3, 4), []))
    assert qsys == gsys
    assert quiz.split("\n\n")[0] == game.split("\n\n")[0]  # identical rules section
    assert ("(a) If every other agent earns 20 more points and your own points don't change, "
            "does your final score go up, down, or stay the same, and by how much?") in quiz
    assert "If you earn 10 more points" in quiz
    assert '"q1_direction"' in quiz and '"q2_amount"' in quiz
    assert "0.5 x" in quiz  # numeric alpha in the payoff formula
    text = (qsys + quiz).lower()
    assert "8 rounds" not in text and "this round is" not in text  # no limit, no digit
    for word in ("honest", "cooperat", "lie", "liar", "truthful", "trust", "fair", "team", "help"):
        assert not re.search(rf"\b{word}", text), word


# --- Agent -------------------------------------------------------------------

def test_agent_quiz_ok_retry_and_failed():
    obs = build_rules_obs(KCConfig(), 0)
    a = KCLLMAgent(0, QueueBackend([_r(PASS, {"input_tokens": 5})])).comprehension_check(obs)
    assert (a.parse_status, a.answers["q1_direction"], a.raw_output) == ("ok", "down", PASS)

    b = QueueBackend([_r("junk", {"input_tokens": 5}), _r(WRONG, {"input_tokens": 7})])
    agent = KCLLMAgent(0, b)
    a = agent.comprehension_check(obs)
    assert (a.parse_status, a.answers["q1_direction"]) == ("retry_ok", "up")
    assert a.usage == {"input_tokens": 12} and b.calls[0] == b.calls[1]

    b = QueueBackend([_r("junk"), _r(PASS, refused=True), _r("never used")])
    agent = KCLLMAgent(0, b)
    a = agent.comprehension_check(obs)
    assert (a.parse_status, a.answers, a.raw_output) == ("failed", None, PASS)
    assert len(b.calls) == 2  # one retry only
    assert agent.parse_failures == 0  # game parse counter untouched by the quiz


def test_scripted_agents_skip_quiz():
    assert make_scripted("honest", 0).comprehension_check(build_rules_obs(KCConfig(), 0)) is None


# --- Environment, log, no memory ---------------------------------------------

def _run(comprehension=True, quiz_reply=PASS, alpha=0.5, tmp_path=None):
    cfg = KCConfig(max_rounds=3, alpha=alpha, seed=4)
    backends = [MockBackend(responder=_game_responder(quiz_reply)) for _ in range(2)]
    agents = [KCLLMAgent(i, backends[i]) for i in range(2)] + [make_scripted("honest", i) for i in (2, 3)]
    log = KCEnvironment(cfg, agents, "quiz", comprehension=comprehension).run()
    return log, backends


def test_quiz_runs_once_before_round_one_and_is_logged(tmp_path):
    log, backends = _run()
    for b in backends:
        assert '"q1_direction"' in b.calls[0][1]
        assert sum('"q1_direction"' in p for _, p in b.calls) == 1
        assert len(b.calls) == 1 + 3 * 2
    path = log.write_jsonl(tmp_path / "g.jsonl")
    kinds = [json.loads(line)["record"] for line in path.read_text().splitlines()]
    assert kinds == ["meta", "comprehension", "comprehension", "round", "round", "round", "end"]
    quiz = load_game(path)["comprehension"]
    assert set(quiz) == {0, 1}  # scripted agents 2 and 3 skipped
    rec = quiz[0]
    assert rec["raw_output"] == PASS and rec["parse_status"] == "ok" and rec["passed"] is True
    assert rec["answers"] == {"q1_direction": "down", "q1_amount": 10.0, "q2_amount": 10.0}
    assert rec["expected"] == {"q1_direction": "down", "q1_change": -10.0, "q2_change": 10.0}
    assert rec["observation"] == {"agent_id": 0, "n_agents": 4, "reward_correct": 10, "group_bonus": 10,
                                  "bonus_threshold": 3, "alpha": 0.5}


def test_quiz_graded_against_alpha():
    log, _ = _run(alpha=1.5)  # PASS says 10, correct is 30
    assert [q["passed"] for q in log.comprehension.values()] == [False, False]


def test_quiz_leaves_no_trace_in_game():
    """Same game prompts, actions, and observations with or without the quiz."""
    with_quiz, b1 = _run(comprehension=True)
    without, b2 = _run(comprehension=False)
    assert [c for c in b1[0].calls[1:]] == b2[0].calls
    assert [c for c in b1[1].calls[1:]] == b2[1].calls
    assert not without.comprehension
    r1 = [r for r in with_quiz.records() if r["record"] == "round"]
    r2 = [r for r in without.records() if r["record"] == "round"]
    assert r1 == r2
    assert "q1" not in json.dumps(r1)


def test_mock_quiz_does_not_shift_mock_game_play():
    """The mock answers the quiz from its own RNG stream."""
    plain, quizzed = mock_responder(3), mock_responder(3)
    s, p = build_prompts(build_message_obs(KCConfig(), 1, 0, (1, 2, 3, 4), []))
    qs, qp = build_quiz_prompts(build_rules_obs(KCConfig(), 0))
    parse_comprehension_output(quizzed(qs, qp))
    assert [plain(s, p) for _ in range(10)] == [quizzed(s, p) for _ in range(10)]


# --- Metrics and show --------------------------------------------------------

def test_pass_rate_metrics_and_show(tmp_path):
    cfg = KCConfig(max_rounds=2, alpha=0.5)
    agents = [KCLLMAgent(0, MockBackend(responder=_game_responder(PASS))),
              KCLLMAgent(1, MockBackend(responder=_game_responder(WRONG))),
              KCLLMAgent(2, MockBackend(replies=["junk"])),
              make_scripted("honest", 3)]
    path = KCEnvironment(cfg, agents, "m").run().write_jsonl(tmp_path / "m.jsonl")
    s = summarize_game(path)
    assert s["game"]["comprehension_tested"] == 3
    assert s["game"]["comprehension_pass_rate"] == pytest.approx(1 / 3)
    assert [s["agents"][i]["comprehension_pass"] for i in range(4)] == [1.0, 0.0, 0.0, None]
    # Quiz calls count toward cost: 1 + 1 + 2 quiz calls, game actions on top.
    game_calls = sum({"ok": 1, "retry_ok": 2, "fallback": 2}[a["parse_status"]]
                     for r in load_game(path)["rounds"] for ph in ("message", "guess")
                     for a in r["actions"][ph].values() if a["parse_status"] != "scripted")
    assert s["game"]["calls"] == 4 + game_calls
    agg = aggregate([path, path])
    assert agg["game"]["comprehension_pass_rate"]["mean"] == pytest.approx(1 / 3)

    out = format_game(path)
    assert "quiz agent 0: PASS [ok] | answered down 10, 10 | expected down 10, 10" in out
    assert "quiz agent 1: FAIL [ok] | answered up 10, 10" in out
    assert "quiz agent 2: FAIL [failed] | answered no valid answer" in out
    assert "quiz agent 3" not in out
    assert "raw quiz: junk" in format_game(path, raw=True)


def test_old_logs_without_quiz_still_load():
    s = summarize_game(FIXTURE)
    assert load_game(FIXTURE)["comprehension"] == {}
    assert s["game"]["comprehension_pass_rate"] is None and s["game"]["comprehension_tested"] == 0
    assert "quiz agent" not in format_game(FIXTURE)
