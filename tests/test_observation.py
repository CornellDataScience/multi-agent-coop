from dataclasses import fields

from src.agents.scripted import ScriptedAgent
from src.game.config import GameConfig
from src.game.environment import Environment
from src.information.observation import (
    Observation,
    build_first_observation,
    build_second_observation,
)


def _run():
    cfg = GameConfig(n_agents=3, initial_pool=30, max_rounds=10)
    agents = [ScriptedAgent(i, "sustainable", "underreport") for i in range(3)]
    return cfg, Environment(cfg, agents).run()


def test_observation_has_no_horizon():
    # The unknown-horizon guarantee: nothing in the observation reveals max_rounds.
    assert "max_rounds" not in {f.name for f in fields(Observation)}
    cfg, log = _run()
    obs = build_first_observation(log, 0, cfg, pool=10, round=3)
    assert "max_rounds" not in obs.to_dict()


def test_info_firewall_hides_others_true_takes_and_revisions():
    cfg, log = _run()
    obs = build_first_observation(log, 0, cfg, pool=10, round=3)
    for entry in obs.history:
        # Own true first/final take, revision choice, and grant are visible;
        # only PUBLIC announcements (every agent's) are visible otherwise --
        # never another agent's true take or revision choice.
        assert set(entry) == {
            "round", "pool_before", "pool_after",
            "first_announcements", "second_announcements",
            "your_first_take", "your_final_take", "your_revision", "your_granted",
        }
        past = log.rounds[entry["round"] - 1]
        assert entry["your_first_take"] == past.first_takes[0]
        assert entry["your_final_take"] == past.final_takes[0]
        assert entry["your_revision"] == past.revisions[0]
        assert entry["your_granted"] == past.granted[0]


def test_first_observation_has_no_second_phase_fields():
    cfg, log = _run()
    obs = build_first_observation(log, 1, cfg, pool=10, round=4)
    assert obs.phase == "first"
    assert obs.own_first_announcement is None
    assert obs.own_first_take is None
    assert obs.other_first_announcements is None


def test_second_observation_reveals_only_first_announcements():
    cfg, log = _run()
    first_announcements = {0: 5, 1: 7, 2: 9}
    first_takes = {0: 50, 1: 60, 2: 70}  # true first takes -- must stay hidden
    obs = build_second_observation(
        log, 1, cfg, pool=10, round=4, first_announcements=first_announcements, first_takes=first_takes
    )
    assert obs.phase == "second"
    assert obs.own_first_announcement == 7
    assert obs.own_first_take == 60
    # sees every OTHER agent's first announcement, never its own echoed back
    assert obs.other_first_announcements == {0: 5, 2: 9}
    # no other agent's true first take appears anywhere in the observation
    assert set(obs.to_dict()) == {
        "agent_id", "round", "pool", "n_agents", "growth_factor", "phase",
        "history", "own_first_announcement", "own_first_take", "other_first_announcements",
    }
