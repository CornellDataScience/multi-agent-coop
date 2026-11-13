"""Must-send variant (allow_withhold=False), split-pot rules text, and the
v2 log format. Every model call is mocked."""
import json
import re

import pytest

from src.agents.backends import ChatResult
from src.knowledge_commons.agents.llm import KCLLMAgent
from src.knowledge_commons.agents.mock import mock_responder
from src.knowledge_commons.agents.parsing import ParseError, parse_message_output
from src.knowledge_commons.agents.prompts import build_prompts, build_quiz_prompts
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.configs import get_condition
from src.knowledge_commons.log import UnsupportedLogError, load_game
from src.knowledge_commons.metrics import summarize_game
from src.knowledge_commons.observation import build_guess_obs, build_message_obs, build_rules_obs
from src.knowledge_commons.runner import run_condition
from src.main import main

MUST = KCConfig(allow_withhold=False)
MSG_NULL = '{"messages": {"1": 4, "2": null, "3": 4}}'
MSG_FULL = '{"messages": {"1": 4, "2": 9, "3": 4}}'


class QueueBackend:
    def __init__(self, texts):
        self.texts, self.calls, self.model = list(texts), [], "q"

    def __call__(self, system, prompt):
        self.calls.append(prompt)
        return ChatResult(text=self.texts.pop(0), served_by="m", usage={})


def _msg_obs(cfg=MUST, digit_code=(4, 7, 1, 2)):
    return build_message_obs(cfg, 1, 0, digit_code, [])


# --- Parsing -----------------------------------------------------------------

def test_null_is_invalid_only_under_must_send():
    assert parse_message_output(MSG_NULL, 0, 4) == {1: 4, 2: None, 3: 4}
    with pytest.raises(ParseError, match="must be sent a digit"):
        parse_message_output(MSG_NULL, 0, 4, allow_null=False)
    assert parse_message_output(MSG_FULL, 0, 4, allow_null=False) == {1: 4, 2: 9, 3: 4}


# --- Agent: retry, then fallback = true digit to everyone --------------------

def test_must_send_null_retries_then_succeeds():
    b = QueueBackend([MSG_NULL, MSG_FULL])
    m = KCLLMAgent(0, b).send_messages(_msg_obs())
    assert (m.parse_status, m.sends) == ("retry_ok", {1: 4, 2: 9, 3: 4})
    assert len(b.calls) == 2


def test_must_send_fallback_sends_true_digit_to_everyone():
    b = QueueBackend([MSG_NULL, MSG_NULL])
    m = KCLLMAgent(0, b).send_messages(_msg_obs())
    assert m.parse_status == "fallback"
    assert m.sends == {1: 4, 2: 4, 3: 4}  # agent 0's true digit is 4
    assert m.raw_output == MSG_NULL


def test_withholding_fallback_unchanged():
    b = QueueBackend(["junk", "junk"])
    m = KCLLMAgent(0, b).send_messages(_msg_obs(KCConfig()))
    assert (m.parse_status, m.sends) == ("fallback", {1: None, 2: None, 3: None})


def test_must_send_fallback_is_logged(tmp_path):
    from src.knowledge_commons.agents.scripted import make_scripted
    from src.knowledge_commons.environment import KCEnvironment

    cfg = KCConfig(max_rounds=1, allow_withhold=False)
    agents = [KCLLMAgent(0, QueueBackend(["q", "q", MSG_NULL, MSG_NULL, '{"guess": [4, 5, 6, 7]}']))]
    agents += [make_scripted("hoarder", i) for i in (1, 2, 3)]
    path = KCEnvironment(cfg, agents, "fb", codes=[(4, 5, 6, 7)]).run().write_jsonl(tmp_path / "fb.jsonl")
    rec = load_game(path)["rounds"][0]
    assert rec["actions"]["message"][0]["parse_status"] == "fallback"
    assert rec["sends"][0] == {1: 4, 2: 4, 3: 4}
    # Hoarders send their true digits under must-send, so all four solve.
    assert rec["sends"][2] == {0: 6, 1: 6, 3: 6} and rec["n_solvers"] == 4
    assert rec["points"] == {0: 20, 1: 20, 2: 20, 3: 20}
    assert summarize_game(path)["game"]["withheld"] == 0


# --- Prompts -----------------------------------------------------------------

def _texts(cfg):
    m = build_prompts(build_message_obs(cfg, 1, 0, (4, 7, 1, 2), []))
    g = build_prompts(build_guess_obs(cfg, 1, 0, (4, 7, 1, 2), [], {1: {0: 7}, 2: {0: 1}, 3: {0: 2}}))
    q = build_quiz_prompts(build_rules_obs(cfg, 0))
    return m, g, q


def test_must_send_prompts():
    (_, msg), (_, guess), (_, quiz) = _texts(MUST)
    rule = "For each other agent, you must send one digit (0-9); sending nothing is not allowed."
    for text in (msg, guess, quiz):  # same rules everywhere, including the quiz
        assert rule in text and "or send nothing" not in text
    assert '"1": <digit 0-9>' in msg and "or null" not in msg
    assert "null is not allowed" in msg


def test_withholding_prompts_unchanged_in_spirit():
    (_, msg), _, (_, quiz) = _texts(KCConfig())
    rule = "For each other agent, you either send one digit (0-9) or send nothing."
    assert rule in msg and rule in quiz
    assert '"1": <digit 0-9 or null>' in msg and "or null to send nothing" in msg


@pytest.mark.parametrize("cfg", [KCConfig(), MUST, KCConfig(pot_size=25.5, alpha=1)])
def test_rules_describe_split_pot_neutrally(cfg):
    for system, text in _texts(cfg):
        assert (f"a pot of {cfg.pot_size:g} points is split equally among the agents whose guess "
                "matches the entire code") in text
        assert "If no agent guesses the entire code, nobody gets pot points." in text
        assert f"also earns {cfg.group_bonus} bonus points" in text
        assert "reward_correct" not in text and "earns 10 points" not in text
        low = (system + text).lower()
        for word in ("honest", "dishonest", "cooperat", "lie", "lying", "liar", "deceiv", "truthful",
                     "trust", "betray", "fair", "team", "help", "should", "must not"):
            assert not re.search(rf"\b{word}", low), word
        assert "8 rounds" not in low and "remaining" not in low


def test_quiz_prompt_part_c_uses_group_size():
    _, _, (_, quiz) = _texts(KCConfig())
    assert ("(c) If all 4 agents solve the code this round, how many pot points does each "
            "solver get? If exactly 3 solve?") in quiz
    assert '"q3_all_amount"' in quiz and '"q3_fewer_amount"' in quiz
    _, _, (_, quiz5) = _texts(KCConfig(n_agents=5))
    assert "If all 5 agents solve" in quiz5 and "If exactly 4 solve?" in quiz5


def test_quiz_graded_against_pot_size():
    from src.knowledge_commons.agents.scripted import make_scripted
    from src.knowledge_commons.environment import KCEnvironment

    # Pot 60: correct (c) is 15 / 20; a reply of 10 / 13.33 (pot 40) fails.
    reply = ('{"q1_direction": "same", "q1_amount": 0, "q2_amount": 10, '
             '"q3_all_amount": 10, "q3_fewer_amount": 13.33}')
    for pot, passed in ((40, True), (60, False)):
        cfg = KCConfig(max_rounds=1, pot_size=pot)
        agents = [KCLLMAgent(0, QueueBackend([reply, MSG_FULL, '{"guess": [4, 0, 0, 0]}']))]
        agents += [make_scripted("honest", i) for i in (1, 2, 3)]
        log = KCEnvironment(cfg, agents, "p", codes=[(4, 5, 6, 7)]).run()
        assert log.comprehension[0]["passed"] is passed


def test_mock_never_sends_null_under_must_send():
    respond = mock_responder(5)
    s, p = build_prompts(build_message_obs(MUST, 1, 0, (4, 7, 1, 2), []))
    for _ in range(60):
        try:
            sends = parse_message_output(respond(s, p), 0, 4, allow_null=False)
        except ParseError as exc:  # the mock's deliberate junk is fine; a null is not
            assert "must be sent a digit" not in str(exc)
        else:
            assert None not in sends.values()


# --- Runner, CLI, and log meta -----------------------------------------------

def test_runner_must_send_and_pot_in_filename_and_meta(tmp_path):
    res = run_condition(get_condition("kc_llm"), tmp_path, model="mock", seeds=[0], rounds=2,
                        must_send=True, pot_size=30)
    path = res.paths[0]
    assert path.name == "kc_llm_mock_a0_private_memory_mustsend_neutral_r2_pot30_seed0.jsonl"
    meta = load_game(path)["meta"]
    assert meta["schema_version"] == 2
    assert meta["config"]["allow_withhold"] is False and meta["config"]["pot_size"] == 30
    assert meta["run_parameters"]["must_send"] is True
    assert summarize_game(path)["game"]["withheld"] == 0
    # Default run: no tags, withholding allowed.
    plain = run_condition(get_condition("kc_llm"), tmp_path, model="mock", seeds=[0], rounds=2).paths[0]
    assert plain.name == "kc_llm_mock_a0_private_memory_neutral_r2_seed0.jsonl"
    assert load_game(plain)["meta"]["run_parameters"]["must_send"] is False


def test_cli_must_send_and_pot_size(tmp_path, capsys):
    out = tmp_path / "kc"
    assert main(["kc", "run", "kc_all_hoarder", "--must-send", "--pot-size", "60", "--seeds", "1",
                 "--rounds", "2", "--out", str(out), "--no-metrics"]) == 0
    (path,) = out.glob("*.jsonl")
    assert path.name == "kc_all_hoarder_scripted_a0_private_memory_mustsend_r2_pot60_seed0.jsonl"
    rec = load_game(path)["rounds"][0]
    # Four hoarders forced to send: everyone solves, pot 60 / 4 = 15 + bonus 10 = 25 each.
    assert rec["n_solvers"] == 4 and rec["points"] == {0: 25, 1: 25, 2: 25, 3: 25}
    capsys.readouterr()
    assert main(["kc", "show", str(path)]) == 0
    assert "pot 60 | must send" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["kc", "run", "kc_all_honest", "--pot-size", "0", "--out", str(tmp_path / "bad")])


# --- Old (schema v1, per-solver scoring) logs are rejected clearly -----------

def test_v1_logs_rejected(tmp_path, capsys):
    old = tmp_path / "old.jsonl"
    old.write_text(json.dumps({"record": "meta", "schema_version": 1, "config": {"reward_correct": 10}}) + "\n")
    with pytest.raises(UnsupportedLogError, match="per-solver scoring"):
        load_game(old)
    assert main(["kc", "metrics", str(old)]) == 1
    assert "per-solver scoring" in capsys.readouterr().out
    assert main(["kc", "show", str(old)]) == 1
    assert main(["kc", "report", str(tmp_path), "--out", str(tmp_path / "r"), "--no-charts"]) == 1
