import pytest

from src.knowledge_commons.config import INFO_CONDITIONS, KCConfig


def test_defaults_match_spec():
    cfg = KCConfig()
    assert (cfg.n_agents, cfg.max_rounds) == (4, 8)
    assert (cfg.pot_size, cfg.group_bonus, cfg.bonus_threshold) == (40, 10, 3)
    assert cfg.alpha == 0.0
    assert cfg.allow_withhold is True
    assert not hasattr(cfg, "reward_correct")
    assert cfg.info_condition == "private_memory"
    assert cfg.horizon_known is False
    assert set(INFO_CONDITIONS) == {"no_memory", "private_memory", "public_reputation"}


def test_max_welfare():
    # Per round: pot 40 + 4 agents * bonus 10 = 80; times 8 rounds = 640.
    assert KCConfig().max_welfare_per_round() == 80
    assert KCConfig().max_welfare() == 640
    # Pot 5 + 3 * 1 = 8 per round, 2 rounds = 16.
    assert KCConfig(n_agents=3, max_rounds=2, pot_size=5, group_bonus=1,
                    bonus_threshold=2).max_welfare() == 16


@pytest.mark.parametrize("kwargs", [
    {"n_agents": 1},
    {"bonus_threshold": 0},
    {"bonus_threshold": 5},
    {"alpha": -0.1},
    {"info_condition": "gossip"},
    {"horizon_known": True},
    {"max_rounds": 0},
    {"pot_size": 0},
    {"group_bonus": -1},
])
def test_rejects_bad_values(kwargs):
    with pytest.raises(ValueError):
        KCConfig(**kwargs)


def test_to_dict_round_trips():
    cfg = KCConfig(alpha=1.5, info_condition="no_memory", seed=7, pot_size=25.5, allow_withhold=False)
    assert KCConfig(**cfg.to_dict()) == cfg
