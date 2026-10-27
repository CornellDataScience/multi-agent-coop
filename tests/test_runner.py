from src.experiments.configs import get_condition
from src.experiments.metrics import aggregate, summarize_game
from src.experiments.runner import run_condition
from src.information.log import load_game


def _chat(**kwargs):
    return {"message": {"content": '{"take": 3, "claimed_take": 2}'}}


def test_run_scripted_condition_writes_loadable_game(tmp_path):
    exp = get_condition("all_sustainable")
    paths = run_condition(exp, out_dir=tmp_path)
    assert len(paths) == 1
    meta, rounds = load_game(paths[0])
    assert meta["condition"] == "all_sustainable"
    assert meta["config"]["n_agents"] == 3
    assert len(rounds) == 10
    # observations are logged per round
    assert "observations" in rounds[0]


def test_run_llm_condition_with_mock_and_metrics(tmp_path):
    exp = get_condition("broadcast_unverified")
    paths = run_condition(exp, out_dir=tmp_path, chat_fn=_chat, seeds=[0, 1])
    assert len(paths) == 2
    summary = summarize_game(paths[0])
    assert summary["condition"] == "broadcast_unverified"
    # every agent lied every round (claimed 2 != took 3)
    assert all(d["lie_frequency"] == 1.0 for d in summary["deception"].values())
    agg = aggregate(paths)
    assert agg["n_games"] == 2
    assert "lie_frequency" in agg


def test_nocomm_condition_has_no_deception(tmp_path):
    exp = get_condition("baseline_nocomm")
    paths = run_condition(exp, out_dir=tmp_path, chat_fn=_chat, seeds=[0])
    summary = summarize_game(paths[0])
    assert summary["deception"] == {}
