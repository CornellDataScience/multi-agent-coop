import math

from infocoop.experiments.metrics import (
    deception_metrics,
    gini,
    personal_metrics,
    societal_metrics,
)

# Hand-built 2-agent, 2-round game with known takes/claims.
META = {
    "condition": "golden",
    "seed": 0,
    "config": {"n_agents": 2, "communication": True, "initial_pool": 10},
    "cooperative_optimum": 24,
}
ROUNDS = [
    {
        "round": 1,
        "pool_before": 10,
        "pool_after": 2,
        "pool_next": 4,
        "takes": {0: 5, 1: 3},
        "granted": {0: 5, 1: 3},
        "claims": {0: 5, 1: 1},  # agent1 under-reports by 2
    },
    {
        "round": 2,
        "pool_before": 4,
        "pool_after": 0,
        "pool_next": 0,
        "takes": {0: 2, 1: 2},
        "granted": {0: 2, 1: 2},
        "claims": {0: 0, 1: 2},  # agent0 under-reports by 2
    },
]


def test_deception_metrics():
    d = deception_metrics(META, ROUNDS)
    assert d[0]["lie_frequency"] == 0.5
    assert d[1]["lie_frequency"] == 0.5
    assert d[0]["underreport_share"] == 1.0
    assert d[1]["underreport_share"] == 1.0
    assert math.isclose(d[0]["lie_severity_pool_norm"], 0.25)  # (0/10 + 2/4)/2
    assert math.isclose(d[1]["lie_severity_pool_norm"], 0.1)  # (2/10 + 0/4)/2
    assert math.isclose(d[1]["lie_severity_rel"], (2 / 3) / 2)


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


def test_deception_empty_without_communication():
    meta = {**META, "config": {**META["config"], "communication": False}}
    assert deception_metrics(meta, ROUNDS) == {}
