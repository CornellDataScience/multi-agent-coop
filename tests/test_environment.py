from src.agents.scripted import ScriptedAgent
from src.game.config import GameConfig
from src.game.environment import Environment


def _agents(n, take, claim="honest", communication=True):
    return [ScriptedAgent(i, take, claim, communication=communication) for i in range(n)]


def test_all_greedy_collapses_round_one():
    cfg = GameConfig(n_agents=3, initial_pool=20)
    log = Environment(cfg, _agents(3, "greedy")).run()
    assert len(log.rounds) == 1
    r = log.rounds[0]
    assert r.pool_after == 0 and r.pool_next == 0  # collapse
    assert sum(r.granted.values()) == 20
    assert log.scores == {0: 7, 1: 7, 2: 6}  # 20 split by largest remainder


def test_all_sustainable_survives_to_horizon():
    cfg = GameConfig(n_agents=3, initial_pool=20, max_rounds=10)
    log = Environment(cfg, _agents(3, "sustainable")).run()
    assert len(log.rounds) == 10
    assert all(r.pool_next > 0 for r in log.rounds[:-1])


def test_invariants_hold_every_round():
    cfg = GameConfig(n_agents=3, initial_pool=20, growth_factor=2)
    log = Environment(cfg, _agents(3, "sustainable")).run()
    for r in log.rounds:
        # conservation
        assert sum(r.granted.values()) + r.pool_after == r.pool_before
        # growth (no cap configured)
        assert r.pool_next == r.pool_after * cfg.growth_factor
        # non-negativity
        assert r.pool_after >= 0 and r.pool_next >= 0
        assert all(g >= 0 for g in r.granted.values())


def test_determinism_scripted():
    cfg = GameConfig(n_agents=3, initial_pool=20)
    a = Environment(cfg, _agents(3, "fair", "underreport")).run()
    b = Environment(cfg, _agents(3, "fair", "underreport")).run()
    assert [r.to_dict() for r in a.rounds] == [r.to_dict() for r in b.rounds]
    assert a.scores == b.scores


def test_overdraw_round_ends_game():
    # fair take = pool // 3; force collapse via greedy to check termination flag
    cfg = GameConfig(n_agents=2, initial_pool=10, max_rounds=5)
    log = Environment(cfg, _agents(2, "greedy")).run()
    assert log.rounds[-1].pool_next == 0
    assert len(log.rounds) == 1


def test_take_capped_at_current_pool():
    # An agent asking for more than the pool holds is recorded as taking the pool.
    from src.agents.llm import OllamaAgent

    def chat(**kwargs):
        return {"message": {"content": '{"take": 500, "claimed_take": 1}'}}

    cfg = GameConfig(n_agents=1, initial_pool=20)
    log = Environment(cfg, [OllamaAgent(0, chat_fn=chat)]).run()
    r = log.rounds[0]
    assert r.takes[0] == 20 and r.granted[0] == 20
    assert r.pool_next == 0
