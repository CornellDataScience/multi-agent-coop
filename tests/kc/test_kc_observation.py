import dataclasses

import pytest

from src.knowledge_commons.agents.scripted import make_scripted
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.environment import KCEnvironment
from src.knowledge_commons.log import load_game
from src.knowledge_commons.observation import KCObservation, build_guess_obs, build_message_obs


def _past(cfg, names=("honest", "liar", "hoarder", "excluder"), rounds=3):
    agents = [make_scripted(n, i) for i, n in enumerate(names)]
    return KCEnvironment(cfg, agents, "obs", codes=None).run().rounds[:rounds]


def test_observation_has_no_max_rounds_field():
    assert "max_rounds" not in {f.name for f in dataclasses.fields(KCObservation)}


@pytest.mark.parametrize("info", ["no_memory", "private_memory", "public_reputation"])
def test_message_obs_independent_of_other_agents_digits(info):
    cfg = KCConfig(info_condition=info, seed=4)
    past = _past(cfg)
    a = build_message_obs(cfg, 4, 0, (1, 2, 3, 4), past)
    b = build_message_obs(cfg, 4, 0, (1, 9, 0, 7), past)
    assert a == b
    assert a.my_digit == 1 and a.received is None


@pytest.mark.parametrize("info", ["no_memory", "private_memory", "public_reputation"])
def test_guess_obs_independent_of_other_pairs_messages(info):
    cfg = KCConfig(info_condition=info, seed=4)
    past = _past(cfg)
    sends = {0: {1: 1, 2: 1, 3: 1}, 1: {0: 2, 2: 2, 3: 2}, 2: {0: None, 1: 3, 3: 3}, 3: {0: 5, 1: 4, 2: 4}}
    other = {0: {1: 1, 2: 1, 3: 1}, 1: {0: 2, 2: 8, 3: None}, 2: {0: None, 1: 0, 3: 6}, 3: {0: 5, 1: None, 2: 1}}
    a = build_guess_obs(cfg, 4, 0, (1, 2, 3, 4), past, sends)
    b = build_guess_obs(cfg, 4, 0, (1, 6, 6, 6), past, other)
    assert a == b
    assert a.received == {1: 2, 2: None, 3: 5}


def test_no_memory_has_empty_history_and_no_reputation():
    cfg = KCConfig(info_condition="no_memory")
    obs = build_message_obs(cfg, 5, 2, (1, 2, 3, 4), _past(cfg, rounds=4))
    assert obs.history == [] and obs.reputation is None


def test_private_memory_history_is_own_view_only():
    cfg = KCConfig(info_condition="private_memory", seed=4)
    past = _past(cfg)
    obs = build_message_obs(cfg, 4, 1, (0, 0, 0, 0), past)
    assert obs.reputation is None
    assert len(obs.history) == 3
    h = obs.history[0]
    assert h["sent"] == past[0].message_actions[1].sends
    assert h["received"] == {j: past[0].message_actions[j].sends[1] for j in (0, 2, 3)}
    assert h["my_guess"] == list(past[0].guess_actions[1].guess)
    assert h["points"] == past[0].points[1]


# --- Invariant 4: reputation correctness ------------------------------------

def _independent_reputation(rounds, before_round, n):
    """Recompute from the JSONL records: every dyad-round j sent before
    ``before_round``, over all recipients."""
    counts = {j: {"truthful": 0, "withheld": 0, "lie": 0} for j in range(n)}
    for rec in rounds:
        if rec["round"] >= before_round:
            continue
        for j, sends in rec["sends"].items():
            for _, d in sends.items():
                kind = "withheld" if d is None else ("truthful" if d == rec["code"][j] else "lie")
                counts[j][kind] += 1
    rep = {}
    for j, c in counts.items():
        total = sum(c.values())
        rep[j] = {k: (v / total if total else 0.0) for k, v in c.items()}
        rep[j]["n"] = total
    return rep


def test_reputation_matches_independent_recomputation_from_log(tmp_path):
    cfg = KCConfig(info_condition="public_reputation", seed=21)
    agents = [make_scripted(n, i) for i, n in enumerate(["liar", "reciprocator", "excluder", "grudger"])]
    path = KCEnvironment(cfg, agents, "rep").run().write_jsonl(tmp_path / "rep.jsonl")
    rounds = load_game(path)["rounds"]
    checked = 0
    for rec in rounds:
        for phase in ("message", "guess"):
            for i, obs in rec["observations"][phase].items():
                expected = _independent_reputation(rounds, rec["round"], 4)
                assert set(obs["reputation"]) == set(expected)
                for j in expected:
                    assert obs["reputation"][j]["n"] == expected[j]["n"]
                    for k in ("truthful", "withheld", "lie"):
                        assert obs["reputation"][j][k] == pytest.approx(expected[j][k])
                checked += 1
    assert checked == 8 * 2 * 4
    # Sanity: by round 8 the liar has a lie rate of 1.0 over 7 rounds * 3 recipients.
    last = rounds[-1]["observations"]["message"][1]["reputation"][0]
    assert last["lie"] == 1.0 and last["n"] == 21
