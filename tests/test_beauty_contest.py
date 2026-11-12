import pytest

from src.game.beauty_contest import BeautyContestGame


class Picks:
    def __init__(self, agent_id, pick):
        self.agent_id = agent_id
        self.pick = pick

    def choose(self, observation):
        return self.pick


def test_target_round_points_and_totals():
    result = BeautyContestGame().run([Picks(i, p) for i, p in enumerate([1, 20, 40, 60, 100])])
    first = result["rounds"][0]
    assert first["mean"] == 44.2
    assert first["target"] == pytest.approx(37.57)
    assert first["round_ranking"] == [2, 1, 3, 0, 4]
    assert first["points"] == {2: 10, 1: 7, 3: 5, 0: 3, 4: 0}
    assert len(result["rounds"]) == 10
    assert result["total_points"] == {0: 30, 1: 70, 2: 100, 3: 50, 4: 0}
    assert result["winner"] == 2


def test_invalid_pick_is_rejected():
    with pytest.raises(ValueError, match="integer from 1 to 100"):
        BeautyContestGame(max_rounds=1).run([Picks(i, 101 if i == 0 else 50) for i in range(5)])
