"""Runner: config validation, grid interleaving, mock run end to end, budget
stop, cancel, resume after a simulated restart, re-judge, recompute, estimates."""

import asyncio
import json

import pytest

from asymbench import db, runner
from asymbench.metrics import DEFAULT_CONDITION_KEY


MOCK_CONFIG = {
    "name": "t",
    "test_model": "mock/strong",
    "counterparts": ["mock/weak", "control"],
    "tasks": ["sale", "claim"],
    "conditions": {"instruction": ["neutral"], "oversight": ["none"], "label": ["none"]},
    "seeds": {"start": 0, "count": 2},
    "judge_model": "mock/judge",
    "concurrency": 4,
    "budget_usd": 5,
}


@pytest.fixture(autouse=True)
def temp_storage(tmp_path, monkeypatch):
    db.set_db_path(tmp_path / "test.db")
    monkeypatch.setenv("ASYMBENCH_RUNS_DIR", str(tmp_path / "runs"))
    yield
    db.set_db_path(None)


def test_normalize_config_validation():
    cfg = runner.normalize_config(MOCK_CONFIG)
    assert cfg["counterparts"] == ["mock/weak", "mock/strong"]  # control resolved
    assert cfg["has_mock"] is True
    assert "mock/strong" in cfg["resolved_models"]
    with pytest.raises(runner.ConfigError):
        runner.normalize_config({**MOCK_CONFIG, "budget_usd": None})
    with pytest.raises(runner.ConfigError):
        runner.normalize_config({**MOCK_CONFIG, "tasks": ["nope"]})
    with pytest.raises(runner.ConfigError):
        runner.normalize_config({**MOCK_CONFIG, "seeds": {"start": 0, "count": 0}})


def test_episode_grid_interleaves_seeds():
    cfg = runner.normalize_config(MOCK_CONFIG)
    grid = runner.episode_grid(cfg)
    assert len(grid) == 2 * 2 * 2  # tasks x counterparts x seeds
    # seed-major order: all of seed 0 before any of seed 1
    seeds = [g["seed"] for g in grid]
    assert seeds == sorted(seeds)
    # within a seed, each task's counterparts stay adjacent
    assert grid[0]["task"] == grid[1]["task"]


def test_estimate_counts():
    est = runner.estimate(MOCK_CONFIG)
    assert est["episodes"] == 8
    assert est["cost_low"] == 0 and est["cost_high"] == 0  # mock prices are zero
    est2 = runner.estimate({**MOCK_CONFIG, "test_model": "claude-sonnet-5-5",
                            "counterparts": ["mock/weak", "control"],
                            "judge_model": "mock/judge"})
    assert est2["cost_high"] > est2["cost_low"] > 0


def run_mock() -> str:
    async def go():
        run_id = await runner.create_run(MOCK_CONFIG)
        await runner.execute_run(run_id)
        return run_id
    return asyncio.run(go())


def test_mock_run_end_to_end(tmp_path):
    run_id = run_mock()
    run = db.get_run(run_id)
    assert run["status"] == "done"
    assert {k: run["progress"][k] for k in ("done", "total", "failed")} == \
        {"done": 8, "total": 8, "failed": 0}
    assert run["progress"]["heartbeat_at"]
    agg = run["aggregates"]
    assert agg["totals"]["done"] == 8
    assert agg["overall"]["recognition_gap"]["mean"] > 0
    # export files exist
    folder = tmp_path / "runs" / run_id
    for name in ("config.json", "episodes.jsonl", "aggregates.json", "summary.csv"):
        assert (folder / name).exists(), name
    lines = (folder / "episodes.jsonl").read_text().strip().splitlines()
    assert len(lines) == 8
    ep = json.loads(lines[0])
    assert ep["fields"] and ep["turns"]["turns"] and ep["turns"]["system_prompts"]


def test_budget_stop():
    async def go():
        run_id = await runner.create_run(MOCK_CONFIG)
        db.add_run_cost(run_id, 99.0)  # already over budget before starting
        await runner.execute_run(run_id)
        return run_id
    run_id = asyncio.run(go())
    run = db.get_run(run_id)
    assert run["status"] == "budget_stopped"
    assert run["progress"]["done"] == 0


def test_cancel():
    async def go():
        run_id = await runner.create_run(MOCK_CONFIG)
        runner.cancel_run(run_id)  # cancel before any episode starts
        await runner.execute_run(run_id)
        return run_id
    run_id = asyncio.run(go())
    assert db.get_run(run_id)["status"] == "cancelled"


def test_live_run_survives_server_start():
    """A run with a fresh heartbeat (another process is executing it) must NOT
    be marked failed by startup recovery."""
    run_id = run_mock()
    run = db.get_run(run_id)
    prog = dict(run["progress"])  # run_mock leaves a fresh heartbeat_at
    assert prog.get("heartbeat_at")
    db.update_run(run_id, status="running", progress=prog)
    assert runner.mark_interrupted_runs() == 0
    assert db.get_run(run_id)["status"] == "running"
    db.update_run(run_id, status="done")  # restore


def test_resume_after_simulated_restart():
    run_id = run_mock()
    # simulate a crash: run marked running with a dead (absent) heartbeat
    db.update_run(run_id, status="running",
                  progress={"done": 8, "total": 8, "failed": 0})
    conn = db.connect()
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM episodes WHERE run_id = ? LIMIT 2", (run_id,))]
    for eid in ids:
        db.update_episode(eid, status="running")
    n = runner.mark_interrupted_runs()
    assert n == 1
    run = db.get_run(run_id)
    assert run["status"] == "failed" and run["error"] == "server restarted"
    assert db.get_episode(ids[0])["status"] == "failed"

    runner.resume_run(run_id)
    assert db.get_episode(ids[0])["status"] == "pending"
    asyncio.run(runner.execute_run(run_id))
    run = db.get_run(run_id)
    assert run["status"] == "done" and run["progress"]["done"] == 8


def test_rejudge_and_recompute_keep_history():
    run_id = run_mock()
    before = db.get_run(run_id)["aggregates"]
    asyncio.run(runner.rejudge_run(run_id, "mock/judge"))
    _total, eps = db.list_episodes(run_id, status="done", limit=5, full=True)
    assert eps[0]["judge"]["history"], "previous judge output must be kept"
    after = db.get_run(run_id)["aggregates"]
    assert after["history"], "previous aggregates must be kept"
    # same mock judge -> same headline numbers
    assert after["overall"]["attempt_shift"]["mean"] == before["overall"]["attempt_shift"]["mean"]

    runner.recompute_run(run_id)
    final = db.get_run(run_id)["aggregates"]
    assert len(final["history"]) == 2
    assert final["overall"]["attempt_shift"]["mean"] == before["overall"]["attempt_shift"]["mean"]


def test_registry_custom_id_end_to_end():
    """A model id that is not in models.yaml works end to end (prefix-routed)
    and shows up in the leaderboard."""
    cfg = {**MOCK_CONFIG, "tasks": ["claim"], "counterparts": ["mock/custom-tiny", "control"]}

    async def go():
        run_id = await runner.create_run(cfg)
        await runner.execute_run(run_id)
        return run_id
    run_id = asyncio.run(go())
    assert db.get_run(run_id)["status"] == "done"
    from asymbench.metrics import leaderboard_rows
    eps = db.episodes_for_leaderboard(include_mock=True)
    rows = leaderboard_rows(eps, include_mock=True)
    assert any(r["model"] == "mock/strong" for r in rows)
    cps = {e["counterpart_model"] for e in eps}
    assert "mock/custom-tiny" in cps
