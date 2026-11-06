import math

from src.experiments.metrics import deviation_metrics, gini, personal_metrics, societal_metrics

# Hand-built 2-agent, 2-round game with known announcements/takes.
META = {
    "condition": "golden",
    "seed": 0,
    "config": {"n_agents": 2, "initial_pool": 10},
    "cooperative_optimum": 24,
}
ROUNDS = [
    {
        "round": 1,
        "pool_before": 10,
        "pool_after": 2,
        "pool_next": 4,
        "first_announcements": {0: 5, 1: 1},
        "first_takes": {0: 5, 1: 3},  # agent1 takes 2 more than it first announced
        "revisions": {0: False, 1: False},
        "second_announcements": {0: 5, 1: 1},
        "final_takes": {0: 5, 1: 3},  # agent1's final take also exceeds its 2nd announcement
        "granted": {0: 5, 1: 3},
    },
    {
        "round": 2,
        "pool_before": 4,
        "pool_after": 0,
        "pool_next": 0,
        "first_announcements": {0: 4, 1: 2},
        "first_takes": {0: 2, 1: 2},  # agent0 takes 2 LESS than it first announced
        "revisions": {0: True, 1: False},
        "second_announcements": {0: 4, 1: 2},
        "final_takes": {0: 2, 1: 2},  # agent0's final take also undershoots its 2nd announcement
        "granted": {0: 2, 1: 2},
    },
]


def test_deviation_metrics_first_gap():
    d = deviation_metrics(META, ROUNDS)
    assert d[0]["first_gap_frequency"] == 0.5
    assert d[1]["first_gap_frequency"] == 0.5
    assert d[0]["first_gap_under_share"] == 1.0 and d[0]["first_gap_over_share"] == 0.0
    assert d[1]["first_gap_over_share"] == 1.0 and d[1]["first_gap_under_share"] == 0.0
    assert math.isclose(d[0]["first_gap_severity_pool_norm"], 0.25)  # (0 + 2/4)/2
    assert math.isclose(d[1]["first_gap_severity_pool_norm"], 0.1)  # (2/10 + 0)/2
    assert math.isclose(d[1]["first_gap_severity_rel"], 1.0)  # (2/1 + 0)/2


def test_deviation_metrics_second_gap_and_revision():
    d = deviation_metrics(META, ROUNDS)
    assert d[0]["second_gap_frequency"] == 0.5
    assert d[1]["second_gap_frequency"] == 0.5
    assert d[0]["second_gap_under_share"] == 1.0
    assert d[1]["second_gap_over_share"] == 1.0
    assert d[0]["revision_frequency"] == 0.5 and d[0]["n_revisions"] == 1
    assert d[1]["revision_frequency"] == 0.0 and d[1]["n_revisions"] == 0


def test_deviation_metrics_empty_without_rounds():
    assert deviation_metrics(META, []) == {}


def test_personal_metrics():
    p = personal_metrics(META, ROUNDS)
    assert p[0]["total_fish"] == 7
    assert p[1]["total_fish"] == 5
    assert math.isclose(p[0]["group_share"], 7 / 12)
    assert p[0]["rank"] == 1 and p[1]["rank"] == 2


def test_societal_metrics():
    s = societal_metrics(META, ROUNDS)
    assert s["total_extracted"] == 12
    assert s["collapse_round"] == 2
    assert math.isclose(s["efficiency"], 12 / 24)
    assert math.isclose(s["gini"], 1 / 12, abs_tol=1e-9)


def test_gini_equality_is_zero():
    assert gini([5, 5, 5]) == 0.0
