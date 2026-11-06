import pytest

from src.agents.llm import OllamaAgent
from src.agents.prompt_variants import VARIANTS
from src.agents.prompts import build_first_user_prompt, build_second_user_prompt, build_system_prompt
from src.experiments.configs import get_condition
from src.experiments.runner import run_condition
from src.information.log import load_game
from src.information.observation import Observation


def _first_obs():
    return Observation(agent_id=1, round=4, pool=37, n_agents=3, growth_factor=2, phase="first", history=[])


def _second_obs():
    return Observation(
        agent_id=1, round=4, pool=37, n_agents=3, growth_factor=2, phase="second", history=[],
        own_first_announcement=10, own_first_take=12, other_first_announcements={0: 5, 2: 8},
    )


def _chat(**kwargs):
    return {
        "message": {
            "content": (
                '{"first_announcement": 3, "first_take": 3, '
                '"revise": "no", "second_announcement": 3, "final_take": 3}'
            )
        }
    }


def test_placeholders_filled_and_json_braces_kept():
    prompt = build_first_user_prompt(_first_obs())
    assert "round 4" in prompt and "37 fish" in prompt and "fisherman 1" in prompt
    assert '{"first_announcement": <non-negative integer>' in prompt
    assert "{" + "pool}" not in prompt


def test_second_prompt_states_own_first_announcement_and_others():
    prompt = build_second_user_prompt(_second_obs())
    assert "Your first announcement this round was 10 fish" in prompt
    assert "first take" in prompt and "12 fish" in prompt
    assert "fisherman 0 announced 5" in prompt and "fisherman 2 announced 8" in prompt
    assert '{"revise": "yes" or "no"' in prompt


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_every_variant_builds(name):
    assert build_system_prompt(_first_obs(), name)
    assert build_first_user_prompt(_first_obs(), name)
    assert build_second_user_prompt(_second_obs(), name)


def test_partial_variant_falls_back_to_neutral():
    assert build_system_prompt(_first_obs(), "community") != build_system_prompt(_first_obs(), "neutral")
    assert build_first_user_prompt(_first_obs(), "community") == build_first_user_prompt(_first_obs(), "neutral")


def test_agent_sends_variant_system_prompt():
    sent = {}

    def chat_fn(**kwargs):
        sent.update(kwargs)
        return _chat()

    OllamaAgent(0, prompt_variant="community", chat_fn=chat_fn).act_first(_first_obs())
    assert sent["messages"][0]["content"] == VARIANTS["community"]["system"]


def test_unknown_variant_rejected():
    with pytest.raises(KeyError):
        OllamaAgent(0, prompt_variant="nope", chat_fn=_chat)


def test_variant_logged_and_in_filename(tmp_path):
    exp = get_condition("broadcast_unverified")
    default = run_condition(exp, out_dir=tmp_path, chat_fn=_chat, seeds=[0])[0]
    other = run_condition(exp, out_dir=tmp_path, chat_fn=_chat, seeds=[0], prompt_variant="community")[0]
    assert default.name == "broadcast_unverified_seed0.jsonl"
    assert other.name == "broadcast_unverified_community_seed0.jsonl"
    assert load_game(default)[0]["prompt_variant"] == "neutral"
    assert load_game(other)[0]["prompt_variant"] == "community"


def test_scripted_games_log_no_variant(tmp_path):
    path = run_condition(get_condition("all_sustainable"), out_dir=tmp_path)[0]
    assert load_game(path)[0]["prompt_variant"] is None
