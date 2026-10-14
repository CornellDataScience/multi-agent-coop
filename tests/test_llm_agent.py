from infocoop.agents.llm import OllamaAgent
from infocoop.game.config import GameConfig
from infocoop.game.environment import Environment
from infocoop.information.observation import Observation


def _obs(communication=True):
    return Observation(
        agent_id=0, round=1, pool=20, n_agents=3,
        growth_factor=2, communication=communication, history=[],
    )


def _chat(content):
    def chat_fn(**kwargs):
        return {"message": {"content": content}}
    return chat_fn


def test_mocked_llm_parses_ok():
    agent = OllamaAgent(0, chat_fn=_chat('{"take": 5, "claimed_take": 3}'))
    action = agent.act(_obs())
    assert (action.take, action.claimed_take) == (5, 3)
    assert action.parse_status == "ok"
    assert action.raw_output is not None


def test_retry_then_success():
    responses = iter(["garbage, no json", '{"take": 2, "claimed_take": 2}'])

    def chat_fn(**kwargs):
        return {"message": {"content": next(responses)}}

    agent = OllamaAgent(0, chat_fn=chat_fn)
    action = agent.act(_obs())
    assert action.take == 2
    assert action.parse_status == "retry_ok"
    assert agent.parse_failures == 1


def test_fallback_after_repeated_failure():
    agent = OllamaAgent(0, chat_fn=_chat("never valid"), fallback_take=0)
    action = agent.act(_obs())
    assert action.take == 0
    assert action.parse_status == "fallback"
    assert agent.parse_failures == 2


def test_llm_agents_run_full_game_with_mock():
    cfg = GameConfig(n_agents=3, initial_pool=20, max_rounds=10)
    agents = [OllamaAgent(i, chat_fn=_chat('{"take": 3, "claimed_take": 3}')) for i in range(3)]
    log = Environment(cfg, agents).run()
    assert len(log.rounds) == 10
    assert sum(log.scores.values()) > 0
