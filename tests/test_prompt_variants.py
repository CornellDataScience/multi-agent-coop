import pytest

from src.agents.llm import OllamaAgent
from src.agents.prompt_variants import VARIANTS
from src.agents.prompts import build_system_prompt, build_user_prompt
from src.experiments.configs import get_condition
from src.experiments.runner import run_condition
from src.information.log import load_game
from src.information.observation import Observation


def _obs(communication=True):
    return Observation(
        agent_id=1, round=4, pool=37, n_agents=3,
        growth_factor=2, communication=communication, history=[],
    )


def _chat(**kwargs):
    return {"message": {"content": '{"take": 3, "claimed_take": 3}'}}


def test_placeholders_filled_and_json_braces_kept():
    prompt = build_user_prompt(_obs())
    assert "round 4" in prompt and "37 fish" in prompt and "fisherman 1" in prompt
    assert '{"take": <non-negative integer>' in prompt
    assert "{" + "pool}" not in prompt


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_every_variant_builds(name):
    for comm in (True, False):
        assert build_system_prompt(_obs(comm), name)
        assert build_user_prompt(_obs(comm), name)


def test_partial_variant_falls_back_to_neutral():
    obs = _obs()
    assert build_system_prompt(obs, "community") != build_system_prompt(obs, "neutral")
    assert build_user_prompt(obs, "community") == build_user_prompt(obs, "neutral")


def test_agent_sends_variant_system_prompt():
    sent = {}

    def chat_fn(**kwargs):
        sent.update(kwargs)
        return _chat()

    OllamaAgent(0, prompt_variant="community", chat_fn=chat_fn).act(_obs())
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
