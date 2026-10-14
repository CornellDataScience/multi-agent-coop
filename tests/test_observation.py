from dataclasses import fields

from infocoop.agents.scripted import ScriptedAgent
from infocoop.game.config import GameConfig
from infocoop.game.environment import Environment
from infocoop.information.observation import Observation, build_observation


def _run(communication):
    cfg = GameConfig(n_agents=3, initial_pool=30, max_rounds=10, communication=communication)
    agents = [ScriptedAgent(i, "sustainable", "underreport", communication=communication)
              for i in range(3)]
    return cfg, Environment(cfg, agents).run()


def test_observation_has_no_horizon():
    # The unknown-horizon guarantee: nothing in the observation reveals max_rounds.
    assert "max_rounds" not in {f.name for f in fields(Observation)}
    cfg, log = _run(communication=True)
    obs = build_observation(log, 0, cfg, pool=10, round=3)
    assert "max_rounds" not in obs.to_dict()


def test_info_firewall_hides_others_true_takes():
    cfg, log = _run(communication=True)
    obs = build_observation(log, 0, cfg, pool=10, round=3)
    for entry in obs.history:
        # own take/grant visible; only others' CLAIMS, never their true takes
        assert set(entry) == {
            "round", "pool_before", "your_take", "your_granted",
            "claims", "inferred_total_take",
        }
        assert 0 not in entry["claims"]  # own claim not echoed as "other"
        assert entry["your_take"] == log.rounds[entry["round"] - 1].takes[0]


def test_control_condition_omits_claims():
    cfg, log = _run(communication=False)
    obs = build_observation(log, 1, cfg, pool=10, round=3)
    assert obs.communication is False
    for entry in obs.history:
        assert "claims" not in entry
        assert "inferred_total_take" not in entry
