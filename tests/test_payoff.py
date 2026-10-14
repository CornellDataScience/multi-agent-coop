from infocoop.game.payoff import apportion, clamp


def test_clamp():
    assert clamp(-5, 0, 10) == 0
    assert clamp(15, 0, 10) == 10
    assert clamp(7, 0, 10) == 7


def test_under_pool_returns_requests():
    takes = {0: 3, 1: 4, 2: 2}
    assert apportion(takes, pool=20) == takes


def test_exactly_at_pool_returns_requests():
    takes = {0: 5, 1: 5}
    assert apportion(takes, pool=10) == takes


def test_overdraw_conserves_pool_exactly():
    takes = {0: 10, 1: 6, 2: 4}  # total 20 > 10
    granted = apportion(takes, pool=10)
    assert sum(granted.values()) == 10
    assert granted == {0: 5, 1: 3, 2: 2}


def test_overdraw_largest_remainder_tiebreak():
    # Each wants 1 fish from a pool of 2: equal fractions -> lowest ids win.
    granted = apportion({0: 1, 1: 1, 2: 1}, pool=2)
    assert sum(granted.values()) == 2
    assert granted == {0: 1, 1: 1, 2: 0}


def test_single_greedy_capped_at_pool():
    assert apportion({0: 100}, pool=20) == {0: 20}


def test_all_zero_takes():
    assert apportion({0: 0, 1: 0}, pool=20) == {0: 0, 1: 0}
