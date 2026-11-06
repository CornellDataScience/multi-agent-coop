from src.agents.llm import OllamaAgent
from src.game.config import GameConfig
from src.game.environment import Environment
from src.information.observation import Observation


def _first_obs():
    return Observation(agent_id=0, round=1, pool=20, n_agents=3, growth_factor=2, phase="first", history=[])


def _second_obs(own_first_announcement=5, own_first_take=5, other_first_announcements=None):
    return Observation(
        agent_id=0, round=1, pool=20, n_agents=3, growth_factor=2, phase="second", history=[],
        own_first_announcement=own_first_announcement,
        own_first_take=own_first_take,
        other_first_announcements=other_first_announcements or {1: 3, 2: 4},
    )


def _chat(content):
    def chat_fn(**kwargs):
        return {"message": {"content": content}}
    return chat_fn


def test_mocked_llm_parses_first_phase_ok():
    agent = OllamaAgent(0, chat_fn=_chat('{"first_announcement": 3, "first_take": 5}'))
    action = agent.act_first(_first_obs())
    assert (action.first_announcement, action.first_take) == (3, 5)
    assert action.parse_status == "ok"
    assert action.raw_output is not None


def test_mocked_llm_parses_second_phase_ok():
    agent = OllamaAgent(0, chat_fn=_chat('{"revise": "yes", "second_announcement": 2, "final_take": 6}'))
    action = agent.act_second(_second_obs())
    assert (action.revise, action.second_announcement, action.final_take) == (True, 2, 6)
    assert action.parse_status == "ok"
    assert action.raw_output is not None


def test_first_phase_retry_then_success():
    responses = iter(["garbage, no json", '{"first_announcement": 2, "first_take": 2}'])

    def chat_fn(**kwargs):
        return {"message": {"content": next(responses)}}

    agent = OllamaAgent(0, chat_fn=chat_fn)
    action = agent.act_first(_first_obs())
    assert action.first_take == 2
    assert action.parse_status == "retry_ok"
    assert agent.parse_failures == 1


def test_first_phase_fallback_after_repeated_failure():
    agent = OllamaAgent(0, chat_fn=_chat("never valid"), fallback_take=0)
    action = agent.act_first(_first_obs())
    assert action.first_announcement == 0 and action.first_take == 0
    assert action.parse_status == "fallback"
    assert agent.parse_failures == 2


def test_second_phase_fallback_keeps_first_announcement_no_revision():
    agent = OllamaAgent(0, chat_fn=_chat("never valid"), fallback_take=0)
    action = agent.act_second(_second_obs(own_first_announcement=7, own_first_take=7))
    assert action.revise is False
    assert action.second_announcement == 7
    assert action.final_take == 0
    assert action.parse_status == "fallback"
    assert agent.parse_failures == 2


def test_llm_agents_run_full_game_with_mock():
    cfg = GameConfig(n_agents=3, initial_pool=20, max_rounds=10)
    content = (
        '{"first_announcement": 3, "first_take": 3, '
        '"revise": "no", "second_announcement": 3, "final_take": 3}'
    )
    agents = [OllamaAgent(i, chat_fn=_chat(content)) for i in range(3)]
    log = Environment(cfg, agents).run()
    assert len(log.rounds) == 10
    assert sum(log.scores.values()) > 0
