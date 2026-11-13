"""One test per scripted policy (SPEC §7). Agents are driven with hand-built
observations so each policy is checked in isolation."""
import pytest

from src.knowledge_commons.agents.scripted import SCRIPTED_POLICIES, make_scripted
from src.knowledge_commons.observation import KCObservation


def _obs(agent_id=0, digit=4, phase="message", received=None, history=(), rnd=1, n=4):
    return KCObservation(
        agent_id=agent_id, phase=phase, round=rnd, n_agents=n,
        reward_correct=10, group_bonus=10, bonus_threshold=3, alpha=0.5,
        info_condition="private_memory", my_position=agent_id, my_digit=digit,
        received=received, history=list(history), reputation=None,
    )


def _hist(rnd, code, received, sent=None):
    return {"round": rnd, "code": list(code), "sent": sent or {}, "received": received,
            "my_guess": [0] * len(code), "solved": False, "points": 0, "n_solvers": 0, "bonus": False}


def test_policy_names():
    assert set(SCRIPTED_POLICIES) == {"honest", "hoarder", "liar", "reciprocator", "grudger", "excluder"}
    with pytest.raises(KeyError):
        make_scripted("saint", 0)


def test_honest_sends_truth_and_trusts_everything():
    a = make_scripted("honest", 0)
    assert a.send_messages(_obs()).sends == {1: 4, 2: 4, 3: 4}
    g = a.make_guess(_obs(phase="guess", received={1: 7, 2: None, 3: 2}))
    assert g.guess == (4, 7, 0, 2)  # own digit, received digits, 0 for unknown


def test_hoarder_sends_nothing():
    a = make_scripted("hoarder", 2)
    assert a.send_messages(_obs(agent_id=2)).sends == {0: None, 1: None, 3: None}
    assert a.make_guess(_obs(agent_id=2, digit=5, phase="guess",
                             received={0: 1, 1: 2, 3: 3})).guess == (1, 2, 5, 3)


def test_liar_sends_digit_plus_one_mod_ten():
    a = make_scripted("liar", 1)
    assert a.send_messages(_obs(agent_id=1, digit=9)).sends == {0: 0, 2: 0, 3: 0}
    assert a.send_messages(_obs(agent_id=1, digit=3)).sends == {0: 4, 2: 4, 3: 4}
    assert a.make_guess(_obs(agent_id=1, digit=3, phase="guess",
                             received={0: 1, 2: None, 3: 8})).guess == (1, 3, 0, 8)


def test_reciprocator_mirrors_last_round_truthfulness():
    a = make_scripted("reciprocator", 0)
    assert a.send_messages(_obs()).sends == {1: 4, 2: 4, 3: 4}  # round 1: truth to all
    # Last round: 1 told the truth, 2 withheld, 3 lied. An older lie by 1 is ignored.
    history = [
        _hist(1, (0, 5, 5, 5), {1: 9, 2: 5, 3: 5}),
        _hist(2, (0, 6, 7, 8), {1: 6, 2: None, 3: 1}),
    ]
    assert a.send_messages(_obs(rnd=3, history=history)).sends == {1: 4, 2: None, 3: None}


def test_grudger_stops_forever_after_one_lie_and_ignores_liars():
    a = make_scripted("grudger", 0)
    history = [
        _hist(1, (0, 5, 5, 5), {1: 5, 2: 3, 3: None}),   # 2 lied once
        _hist(2, (0, 6, 7, 8), {1: 6, 2: 7, 3: None}),   # 2 truthful since
    ]
    assert a.send_messages(_obs(rnd=3, history=history)).sends == {1: 4, 2: None, 3: 4}
    g = a.make_guess(_obs(phase="guess", rnd=3, history=history, received={1: 2, 2: 9, 3: 1}))
    assert g.guess == (4, 2, 0, 1)  # digit from liar 2 ignored -> 0


def test_excluder_withholds_from_one_fixed_target():
    a = make_scripted("excluder", 1)  # default target: next agent
    assert a.send_messages(_obs(agent_id=1, digit=6)).sends == {0: 6, 2: None, 3: 6}
    b = make_scripted("excluder", 3, target=0)
    assert b.send_messages(_obs(agent_id=3, digit=2)).sends == {0: None, 1: 2, 2: 2}
    assert b.make_guess(_obs(agent_id=3, digit=2, phase="guess",
                             received={0: 1, 1: 1, 2: None})).guess == (1, 1, 0, 2)
    with pytest.raises(ValueError):
        make_scripted("excluder", 1, target=1)


def test_scripted_agents_describe_themselves():
    assert make_scripted("excluder", 1, target=3).describe() == {
        "id": 1, "type": "scripted", "policy": "excluder", "target": 3}
    assert make_scripted("honest", 0).describe() == {"id": 0, "type": "scripted", "policy": "honest"}
