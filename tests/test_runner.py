from src.experiments.configs import get_condition
from src.experiments.metrics import aggregate, summarize_game
from src.experiments.runner import run_condition
from src.information.log import load_game


def _chat(**kwargs):
    # Every agent announces 2 but actually takes 3, both phases, every round:
    # a steady, detectable gap plus zero revisions, for a predictable fixture.
    return {
        "message": {
            "content": (
                '{"first_announcement": 2, "first_take": 3, '
                '"revise": "no", "second_announcement": 2, "final_take": 3}'
            )
        }
    }


def test_run_scripted_condition_writes_loadable_game(tmp_path):
    exp = get_condition("all_sustainable")
    paths = run_condition(exp, out_dir=tmp_path)
    assert len(paths) == 1
    meta, rounds = load_game(paths[0])
    assert meta["condition"] == "all_sustainable"
    assert meta["config"]["n_agents"] == 3
    assert len(rounds) == 10
    # observations are logged per round, for both phases
    assert "first_observations" in rounds[0]
    assert "second_observations" in rounds[0]


def test_run_llm_condition_with_mock_and_metrics(tmp_path):
    exp = get_condition("broadcast_unverified")
    paths = run_condition(exp, out_dir=tmp_path, chat_fn=_chat, seeds=[0, 1])
    assert len(paths) == 2
    summary = summarize_game(paths[0])
    assert summary["condition"] == "broadcast_unverified"
    # every agent took 1 more than it announced, every round, both phases
    assert all(d["first_gap_frequency"] == 1.0 for d in summary["deviation"].values())
    assert all(d["second_gap_frequency"] == 1.0 for d in summary["deviation"].values())
    assert all(d["revision_frequency"] == 0.0 for d in summary["deviation"].values())
    agg = aggregate(paths)
    assert agg["n_games"] == 2
    assert "first_gap_frequency" in agg
    assert "revision_frequency" in agg


def test_show_formats_rounds_gaps_and_revisions(tmp_path):
    from src.analysis.replay import format_game

    exp = get_condition("broadcast_unverified")
    path = run_condition(exp, out_dir=tmp_path, chat_fn=_chat, seeds=[0])[0]
    text = format_game(path, raw=True)
    assert "round 1:" in text
    assert (
        "agent 0: first ann    2 take    3  GAP  | revise no  "
        "second ann    2 take    3  GAP  granted    3" in text
    )
    assert 'first raw: {"first_announcement": 2, "first_take": 3' in text
    assert 'second raw: {"first_announcement": 2, "first_take": 3' in text
    assert "gaps 60" in text  # 3 agents x 10 rounds x 2 phases
    assert "revisions 0" in text
