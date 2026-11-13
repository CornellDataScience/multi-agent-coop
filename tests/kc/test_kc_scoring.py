import pytest

from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.scoring import classify_send, round_points, utilities


def test_classify_send():
    assert classify_send(7, 7) == "truthful"
    assert classify_send(None, 7) == "withheld"
    assert classify_send(8, 7) == "lie"
    assert classify_send(0, 0) == "truthful"


def test_round_points_bonus_triggers_at_threshold():
    cfg = KCConfig()  # R=10, B=10, T=3
    points, n, bonus = round_points({0: True, 1: True, 2: True, 3: False}, cfg)
    assert (n, bonus) == (3, True)
    # solvers: 10 + 10; the non-solver still gets the bonus: 0 + 10
    assert points == {0: 20, 1: 20, 2: 20, 3: 10}


def test_round_points_below_threshold_no_bonus():
    cfg = KCConfig()
    points, n, bonus = round_points({0: True, 1: True, 2: False, 3: False}, cfg)
    assert (n, bonus) == (2, False)
    assert points == {0: 10, 1: 10, 2: 0, 3: 0}


def test_round_points_custom_values():
    cfg = KCConfig(n_agents=3, reward_correct=7, group_bonus=2, bonus_threshold=1)
    points, n, bonus = round_points({0: False, 1: True, 2: False}, cfg)
    assert (n, bonus) == (1, True)
    assert points == {0: 2, 1: 9, 2: 2}


def test_utilities_hand_checked():
    # U_i = P_i - alpha * mean_{j != i} P_j
    u = utilities({0: 0, 1: 0, 2: 0, 3: 20}, 0.5)
    assert u[3] == pytest.approx(20.0)                 # others all 0
    assert u[0] == pytest.approx(0 - 0.5 * 20 / 3)     # -3.333...
    u = utilities({0: 40, 1: 20, 2: 0}, 1.0)
    assert u[0] == pytest.approx(40 - 10)              # mean(20, 0) = 10
    assert u[1] == pytest.approx(20 - 20)              # mean(40, 0) = 20
    assert u[2] == pytest.approx(0 - 30)               # mean(40, 20) = 30


def test_utilities_alpha_zero_is_points():
    assert utilities({0: 5, 1: 9}, 0.0) == {0: 5.0, 1: 9.0}
