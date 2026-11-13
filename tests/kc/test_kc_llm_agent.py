"""KCLLMAgent and prompt tests. Every model call is mocked."""
import re

import pytest

from src.agents.backends import ChatResult, ClaudeBackend, MockBackend
from src.knowledge_commons.agents.llm import KCLLMAgent
from src.knowledge_commons.agents.prompts import build_prompts
from src.knowledge_commons.agents.prompt_variants import KC_VARIANTS, get_variant
from src.knowledge_commons.agents.scripted import make_scripted
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.environment import KCEnvironment
from src.knowledge_commons.observation import build_guess_obs, build_message_obs

MSG_OK = '{"messages": {"1": 4, "2": null, "3": 4}}'
GUESS_OK = '{"guess": [4, 7, 0, 2], "confidence": 0.5}'


class ScriptedBackend:
    """Returns queued ChatResults and records every call."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.model = "scripted-backend"

    def __call__(self, system, prompt):
        self.calls.append((system, prompt))
        return self.results.pop(0)


def _r(text, usage=None, refused=False, served_by="m"):
    return ChatResult(text=text, served_by=served_by, usage=usage or {}, refused=refused)


def _past(cfg, rounds=2):
    agents = [make_scripted(n, i) for i, n in enumerate(["honest", "liar", "hoarder", "excluder"])]
    return KCEnvironment(cfg, agents, "p", codes=[(4, 5, 6, 7), (1, 2, 3, 0), (9, 9, 9, 9)][: cfg.max_rounds]
                         + [(0, 0, 0, 0)] * max(0, cfg.max_rounds - 3)).run().rounds[:rounds]


def _msg_obs(info="private_memory", rnd=3, agent_id=0, code=(4, 7, 1, 2), alpha=0.5):
    cfg = KCConfig(info_condition=info, alpha=alpha)
    return build_message_obs(cfg, rnd, agent_id, code, _past(cfg, rnd - 1))


def _guess_obs(info="private_memory", rnd=3, code=(4, 7, 1, 2)):
    cfg = KCConfig(info_condition=info)
    sends = {0: {1: 4, 2: 4, 3: 4}, 1: {0: 7, 2: 7, 3: 7}, 2: {0: None, 1: 1, 3: 1}, 3: {0: 2, 1: 2, 2: 2}}
    return build_guess_obs(cfg, rnd, 0, code, _past(cfg, rnd - 1), sends)


# --- Agent: parse, retry, fallback -------------------------------------------

def test_valid_outputs_parse_ok():
    b = ScriptedBackend([_r(MSG_OK, {"input_tokens": 10, "output_tokens": 2}), _r(GUESS_OK)])
    agent = KCLLMAgent(0, b)
    m = agent.send_messages(_msg_obs())
    assert m.sends == {1: 4, 2: None, 3: 4}
    assert (m.parse_status, m.raw_output, m.served_by) == ("ok", MSG_OK, "m")
    assert m.usage == {"input_tokens": 10, "output_tokens": 2}
    g = agent.make_guess(_guess_obs())
    assert (g.guess, g.confidence, g.parse_status) == ((4, 7, 0, 2), 0.5, "ok")
    assert len(b.calls) == 2


def test_one_retry_then_success_sums_usage():
    b = ScriptedBackend([_r("not json", {"input_tokens": 100, "output_tokens": 5}),
                         _r(MSG_OK, {"input_tokens": 100, "output_tokens": 7})])
    m = KCLLMAgent(0, b).send_messages(_msg_obs())
    assert m.parse_status == "retry_ok" and m.sends == {1: 4, 2: None, 3: 4}
    assert m.usage == {"input_tokens": 200, "output_tokens": 12}
    assert b.calls[0] == b.calls[1]  # retry resends the same prompt


def test_message_fallback_after_two_failures_sends_nothing():
    b = ScriptedBackend([_r('{"messages": {"1": 10}}', {"input_tokens": 3, "output_tokens": 1}),
                         _r("still bad", {"input_tokens": 4, "output_tokens": 1})])
    m = KCLLMAgent(0, b).send_messages(_msg_obs())
    assert m.parse_status == "fallback"
    assert m.sends == {1: None, 2: None, 3: None}
    assert m.raw_output == "still bad"
    assert m.usage == {"input_tokens": 7, "output_tokens": 2}
    assert len(b.calls) == 2  # exactly one retry


def test_guess_fallback_uses_own_and_received_digits():
    b = ScriptedBackend([_r('{"guess": [1, 2]}'), _r('{"guess": [1, 2, 3]}')])
    obs = _guess_obs()  # own digit 4; received 1:7, 2:None, 3:2
    g = KCLLMAgent(0, b).make_guess(obs)
    assert g.parse_status == "fallback"
    assert g.guess == (4, 7, 0, 2) and g.confidence is None


def test_refusal_counts_as_failure():
    b = ScriptedBackend([_r("", refused=True, usage={"input_tokens": 9, "output_tokens": 0}),
                         _r(MSG_OK, usage={"input_tokens": 9, "output_tokens": 3})])
    m = KCLLMAgent(0, b).send_messages(_msg_obs())
    assert m.parse_status == "retry_ok"
    assert m.usage == {"input_tokens": 18, "output_tokens": 3}
    # A refusal with parseable text still counts as failure.
    b = ScriptedBackend([_r(MSG_OK, refused=True), _r(MSG_OK, refused=True)])
    assert KCLLMAgent(0, b).send_messages(_msg_obs()).parse_status == "fallback"


def test_works_with_real_backends_via_chat_fn():
    """ClaudeBackend with an injected chat_fn: refusal + usage flow through."""
    from types import SimpleNamespace as NS

    replies = [
        NS(content=[], stop_reason="refusal", model="claude-haiku-5-5", usage=NS(input_tokens=50, output_tokens=0)),
        NS(content=[NS(type="text", text=MSG_OK)], stop_reason="end_turn", model="claude-haiku-5-5",
           usage=NS(input_tokens=50, output_tokens=12)),
    ]
    backend = ClaudeBackend(model="claude-haiku-5-5", chat_fn=lambda **kw: replies.pop(0))
    agent = KCLLMAgent(0, backend)
    m = agent.send_messages(_msg_obs())
    assert (m.parse_status, m.served_by) == ("retry_ok", "claude-haiku-5-5")
    assert m.usage == {"input_tokens": 100, "output_tokens": 12}
    assert agent.describe() == {"id": 0, "type": "claude", "model": "claude-haiku-5-5",
                                "prompt_variant": "neutral"}


def test_mock_backend_end_to_end_game():
    def responder(system, prompt):
        if '"messages"' in prompt:
            keys = re.findall(r'"(\d+)": <digit', prompt)
            return '{"messages": {%s}}' % ", ".join(f'"{k}": 1' for k in keys)
        return '{"guess": [1, 1, 1, 1]}'

    cfg = KCConfig(max_rounds=2)
    agents = [KCLLMAgent(i, MockBackend(responder=responder)) for i in range(4)]
    log = KCEnvironment(cfg, agents, "mock", codes=[(1, 1, 1, 1), (2, 1, 1, 1)]).run()
    assert all(log.rounds[0].solved.values()) and not any(log.rounds[1].solved.values())
    assert log.rounds[0].message_actions[2].sends == {0: 1, 1: 1, 3: 1}
    assert log.agents[0] == {"id": 0, "type": "mock", "model": "mock", "prompt_variant": "neutral"}


def test_always_junk_backend_falls_back_and_is_logged(tmp_path):
    """Invariant 6 end to end: two bad replies per action -> SPEC §6 fallback,
    recorded as parse_status "fallback" in the JSONL."""
    from src.knowledge_commons.log import load_game
    from src.knowledge_commons.metrics import summarize_game

    cfg = KCConfig(max_rounds=3)
    codes = [(1, 2, 3, 4), (5, 6, 7, 8), (9, 0, 1, 2)]
    backend = MockBackend(replies=["I'd rather not say.", "{not json"])
    agents = [KCLLMAgent(0, backend)] + [make_scripted("honest", i) for i in (1, 2, 3)]
    path = KCEnvironment(cfg, agents, "junk", codes=codes).run().write_jsonl(tmp_path / "junk.jsonl")

    game = load_game(path)
    # Quiz (try + retry), then 3 rounds x 2 phases x (try + retry).
    assert len(backend.calls) == 2 + 3 * 2 * 2
    quiz = game["comprehension"][0]
    assert (quiz["parse_status"], quiz["passed"], quiz["answers"]) == ("failed", False, None)
    assert set(game["comprehension"]) == {0}  # scripted agents skip the quiz
    for rec, code in zip(game["rounds"], codes):
        for phase in ("message", "guess"):
            act = rec["actions"][phase][0]
            assert act["parse_status"] == "fallback"
            assert act["raw_output"] == "{not json"
        assert rec["sends"][0] == {1: None, 2: None, 3: None}
        # Fallback guess: own digit + received digits (honest agents told the truth).
        assert rec["guesses"][0] == list(code)
        assert rec["confidence"][0] is None
    g = summarize_game(path)["game"]
    assert g["fallback_rate"] == pytest.approx(1.0) and g["calls"] == 14
    assert g["comprehension_pass_rate"] == 0.0


def test_unknown_variant_fails_fast():
    with pytest.raises(KeyError):
        KCLLMAgent(0, MockBackend(replies=["x"]), prompt_variant="nope")


# --- Prompts -----------------------------------------------------------------

def test_neutral_variant_is_default_and_complete():
    assert "neutral" in KC_VARIANTS
    v = get_variant("neutral")
    assert {"system", "rules", "state", "state_no_round", "history_header", "reputation_header",
            "received", "schema_message", "schema_guess"} <= set(v)


@pytest.mark.parametrize("info", ["no_memory", "private_memory", "public_reputation"])
@pytest.mark.parametrize("phase", ["message", "guess"])
def test_prompts_never_reveal_round_limit_or_steer(info, phase):
    obs = _msg_obs(info) if phase == "message" else _guess_obs(info)
    system, prompt = build_prompts(obs)
    text = (system + "\n" + prompt).lower()
    assert "8 rounds" not in text and "max_rounds" not in text
    assert not re.search(r"\b(final|last) round\b", text)
    assert not re.search(r"\bof 8\b|\b8 total\b|/ ?8\b", text)
    assert "rounds remain" not in text and "remaining" not in text
    # Word-start match so e.g. "earlier" doesn't trip "lie".
    for word in ("honest", "dishonest", "cooperat", "collaborat", "lie", "lied", "lying", "liar",
                 "deceiv", "decept", "truthful", "trust", "betray", "fair", "team", "help"):
        assert not re.search(rf"\b{word}", text), word
    assert "0.5" in prompt  # numeric alpha in the payoff formula
    assert "you are not told how many rounds" in text


def test_prompt_contents_by_condition():
    s, p = build_prompts(_msg_obs("no_memory"))
    assert "Round 1:" not in p and "round 3" not in p.lower()
    assert "your digit" in p.lower() and " 4." in p
    s, p = build_prompts(_msg_obs("private_memory"))
    assert "This is round 3." in p
    assert "Round 1: the code was 4 5 6 7" in p and "Round 2: the code was 1 2 3 0" in p
    assert "reputation" not in p.lower() and "Record of every agent" not in p
    s, p = build_prompts(_msg_obs("public_reputation"))
    assert "Record of every agent" in p
    assert "agent 1: true 0%, nothing 0%, false 100% (6 chances to send)" in p


def test_message_prompt_states_send_options_neutrally():
    s, p = build_prompts(_msg_obs())
    assert "The digit you send can be your real digit or any other digit" in p
    assert "does not have to be" not in p


@pytest.mark.parametrize("phase", ["message", "guess"])
def test_no_memory_prompt_works_with_hidden_round(phase):
    obs = _msg_obs("no_memory") if phase == "message" else _guess_obs("no_memory")
    assert obs.round is None
    s, p = build_prompts(obs)
    assert "None" not in p and "round 3" not in p.lower()
    assert "You are agent 0. Your digit (position 0) this round is 4." in p


def test_no_memory_prompt_contains_no_past_rounds():
    obs = _msg_obs("no_memory")
    s, p = build_prompts(obs)
    for code in ("4 5 6 7", "1 2 3 0"):
        assert code not in p
    assert "past rounds" not in p.lower()


def test_prompt_depends_only_on_observation():
    a = build_prompts(_msg_obs(code=(4, 7, 1, 2)))
    b = build_prompts(_msg_obs(code=(4, 0, 0, 0)))  # other agents' digits differ
    assert a == b


def test_guess_prompt_lists_received_digits_and_schema():
    s, p = build_prompts(_guess_obs())
    assert "agent 1 sent you 7" in p and "agent 2 sent you nothing" in p and "agent 3 sent you 2" in p
    assert '"guess"' in p and "exactly 4 digits" in p


def test_message_prompt_lists_every_recipient():
    s, p = build_prompts(_msg_obs(agent_id=2, code=(4, 7, 1, 2)))
    assert '"0": <digit' in p and '"1": <digit' in p and '"3": <digit' in p and '"2": <digit' not in p
    assert "your digit" in p.lower() and "position 2" in p


def test_alpha_formatting():
    s, p = build_prompts(_msg_obs(alpha=1.0))
    assert "1 x (the average" in p
    s, p = build_prompts(_msg_obs(alpha=0.0))
    assert "0 x (the average" in p
