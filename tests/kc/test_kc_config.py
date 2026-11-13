import pytest

from src.knowledge_commons.config import INFO_CONDITIONS, KCConfig


def test_defaults_match_spec():
    cfg = KCConfig()
    assert (cfg.n_agents, cfg.max_rounds) == (4, 8)
    assert (cfg.reward_correct, cfg.group_bonus, cfg.bonus_threshold) == (10, 10, 3)
    assert cfg.alpha == 0.5
    assert cfg.info_condition == "private_memory"
    assert cfg.horizon_known is False
    assert set(INFO_CONDITIONS) == {"no_memory", "private_memory", "public_reputation"}


def test_max_welfare():
    # 4 agents * (10 + 10) * 8 rounds
    assert KCConfig().max_welfare() == 640
    assert KCConfig(n_agents=3, max_rounds=2, reward_correct=5, group_bonus=1,
                    bonus_threshold=2).max_welfare() == 36


@pytest.mark.parametrize("kwargs", [
    {"n_agents": 1},
    {"bonus_threshold": 0},
    {"bonus_threshold": 5},
    {"alpha": -0.1},
    {"info_condition": "gossip"},
    {"horizon_known": True},
    {"max_rounds": 0},
])
def test_rejects_bad_values(kwargs):
    with pytest.raises(ValueError):
        KCConfig(**kwargs)


def test_to_dict_round_trips():
    cfg = KCConfig(alpha=1.5, info_condition="no_memory", seed=7)
    assert KCConfig(**cfg.to_dict()) == cfg
