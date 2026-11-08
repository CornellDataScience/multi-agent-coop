"""Run orchestration: config validation, cost estimates, the episode grid,
concurrency, budget enforcement, cancel, resume, re-judge, recompute."""

from __future__ import annotations

import asyncio
import itertools
import json
import subprocess
import uuid
from datetime import datetime, timezone

from . import db, export
from . import metrics as metrics_mod
from .episode import assemble_analysis, run_episode
from .judge import judge_episode
from .providers import check_openrouter_ids
from .settings import defaults, key_available, resolve_model, runs_dir
from .tasks import TASK_ORDER, TASKS

# Estimation assumptions (guide §10): per agent call (tokens_in, tokens_out),
# and agent calls per episode. Replaced by measured averages once they exist.
EST_ASSUMPTIONS = {
    "commons": {"in": 2500, "out": 300, "calls": 72},
    "sale": {"in": 2000, "out": 300, "calls": 12},
    "contract": {"in": 2500, "out": 300, "calls": 10},
    "claim": {"in": 3500, "out": 300, "calls": 8},
}
EST_CLAUDE_EXTRA_OUT = 800         # adaptive thinking allowance per Claude call
EST_JUDGE = (12000, 1000)
EST_SURVEY = (2500, 150)

_cancel_events: dict[str, asyncio.Event] = {}
_write_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def code_version() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                                text=True, timeout=5).stdout.strip()
        return f"{branch}@{rev}" if rev else "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- config

class ConfigError(ValueError):
    pass


def normalize_config(config: dict) -> dict:
    d = defaults()
    cfg = {
        "name": config.get("name") or "",
        "test_model": config.get("test_model") or d["test_model"],
        "counterparts": list(config.get("counterparts") or (d["counterparts"] + ["control"])),
        "tasks": list(config.get("tasks") or TASK_ORDER),
        "conditions": config.get("conditions") or
                      {"instruction": ["neutral"], "oversight": ["none"], "label": ["none"]},
        "seeds": dict(config.get("seeds") or {"start": 0, "count": d.get("seeds", 10)}),
        "judge_model": config.get("judge_model") or d["judge_model"],
        "crosscheck_judge_model": config.get("crosscheck_judge_model"),
        "concurrency": int(config.get("concurrency") or 4),
        "budget_usd": config.get("budget_usd"),
    }
    if cfg["budget_usd"] is None:
        raise ConfigError("budget_usd is required")
    cfg["budget_usd"] = float(cfg["budget_usd"])
    if cfg["budget_usd"] <= 0:
        raise ConfigError("budget_usd must be positive")
    for t in cfg["tasks"]:
        if t not in TASKS:
            raise ConfigError(f"unknown task {t!r}")
    if not cfg["tasks"]:
        raise ConfigError("at least one task is required")
    seeds = cfg["seeds"]
    seeds["start"] = int(seeds.get("start", 0))
    seeds["count"] = int(seeds.get("count", 10))
    if seeds["count"] < 1:
        raise ConfigError("seeds.count must be at least 1")
    for var, levels in cfg["conditions"].items():
        if var not in ("instruction", "oversight", "label"):
            raise ConfigError(f"unknown condition variable {var!r}")
        if not levels:
            raise ConfigError(f"condition variable {var!r} has no levels")

    # Resolve "control" and model ids; store resolved specs for reproducibility.
    counterparts = []
    for cp in cfg["counterparts"]:
        counterparts.append(cfg["test_model"] if cp == "control" else cp)
    if cfg["test_model"] not in counterparts:
        counterparts.append(cfg["test_model"])  # the control is in every run
    # de-duplicate, keep order
    seen = set()
    cfg["counterparts"] = [c for c in counterparts if not (c in seen or seen.add(c))]

    specs = {}
    for mid in [cfg["test_model"], cfg["judge_model"],
                *(m for m in [cfg["crosscheck_judge_model"]] if m), *cfg["counterparts"]]:
        spec = resolve_model(mid)  # raises ValueError for unroutable ids
        specs[mid] = spec.to_dict()
        if not key_available(spec.provider):
            raise ConfigError(f"no API key for provider {spec.provider!r} (model {mid})")
    cfg["resolved_models"] = specs
    cfg["has_mock"] = any(s["provider"] == "mock" for s in specs.values())
    return cfg


def condition_grid(conditions: dict) -> list[dict]:
    keys = ["instruction", "oversight", "label"]
    levels = [conditions.get(k, ["neutral" if k == "instruction" else "none"]) for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*levels)]


def episode_grid(cfg: dict) -> list[dict]:
    """Interleaved: seed, then task, then condition, then counterpart, so each
    seed's control and weak-counterpart episodes finish close together."""
    seeds = range(cfg["seeds"]["start"], cfg["seeds"]["start"] + cfg["seeds"]["count"])
    grid = []
    for seed in seeds:
        for task in cfg["tasks"]:
            for cond in condition_grid(cfg["conditions"]):
                for cp in cfg["counterparts"]:
                    grid.append({"task": task, "seed": seed, "counterpart_model": cp,
                                 "is_control": cp == cfg["test_model"], "condition": cond})
    return grid


# ---------------------------------------------------------------- estimate

def _is_claude(model_id: str) -> bool:
    return model_id.startswith("claude-")


def estimate(config: dict) -> dict:
    cfg = normalize_config(config)
    grid = episode_grid(cfg)
    measured = db.measured_token_averages()
    specs = {mid: resolve_model(mid) for mid in cfg["resolved_models"]}
    test_spec = specs[cfg["test_model"]]
    judge_spec = specs[cfg["judge_model"]]

    total_cost = 0.0
    total_calls = 0
    for ep in grid:
        task = ep["task"]
        cp_spec = specs[ep["counterpart_model"]]
        m = measured.get((task, cfg["test_model"]))
        if m and m["n"] >= 3 and m["cost"]:
            total_cost += m["cost"]
            total_calls += EST_ASSUMPTIONS[task]["calls"] + 2
            continue
        a = EST_ASSUMPTIONS[task]
        n_agents = 3 if task == "commons" else 2
        test_calls = a["calls"] // n_agents
        cp_calls = a["calls"] - test_calls

        def call_cost(spec, n_calls):
            out = a["out"] + (EST_CLAUDE_EXTRA_OUT if _is_claude(spec.id) else 0)
            return n_calls * (a["in"] * spec.price_in + out * spec.price_out) / 1e6

        cost = call_cost(test_spec, test_calls) + call_cost(cp_spec, cp_calls)
        # judge call
        cost += (EST_JUDGE[0] * judge_spec.price_in + EST_JUDGE[1] * judge_spec.price_out) / 1e6
        # surveys: test capability survey always; T3 also surveys the client
        s_out = EST_SURVEY[1] + (EST_CLAUDE_EXTRA_OUT if _is_claude(test_spec.id) else 0)
        cost += (EST_SURVEY[0] * test_spec.price_in + s_out * test_spec.price_out) / 1e6
        if task == "contract":
            c_out = EST_SURVEY[1] + (EST_CLAUDE_EXTRA_OUT if _is_claude(cp_spec.id) else 0)
            cost += (EST_SURVEY[0] * cp_spec.price_in + c_out * cp_spec.price_out) / 1e6
        total_cost += cost
        total_calls += a["calls"] + (2 if task == "contract" else 1) + 1

    warnings = []
    if cfg["budget_usd"] and total_cost > cfg["budget_usd"]:
        warnings.append(f"the central estimate (${total_cost:.2f}) exceeds the budget "
                        f"(${cfg['budget_usd']:.2f}); the run will stop early")
    if len(grid) > 2000:
        warnings.append(f"{len(grid)} episodes is a very large run")
    return {"episodes": len(grid), "calls": total_calls,
            "cost_low": round(0.6 * total_cost, 2), "cost_high": round(1.6 * total_cost, 2),
            "cost_mid": round(total_cost, 2), "warnings": warnings}


# ---------------------------------------------------------------- create / execute

async def check_availability(cfg: dict) -> dict[str, dict]:
    """id -> {available, reason}. OpenRouter ids are checked against /models;
    the others only need their provider key."""
    results = {}
    or_ids = [mid for mid, s in cfg["resolved_models"].items() if s["provider"] == "openrouter"]
    or_avail = {}
    if or_ids:
        try:
            or_avail = await check_openrouter_ids(or_ids)
        except Exception as exc:
            raise ConfigError(f"could not check OpenRouter model availability: {exc}") from exc
    for mid, spec in cfg["resolved_models"].items():
        if spec["provider"] == "openrouter":
            ok = or_avail.get(mid, False)
            results[mid] = {"available": ok,
                            "reason": None if ok else "not listed by OpenRouter /models"}
        else:
            ok = key_available(spec["provider"])
            results[mid] = {"available": ok,
                            "reason": None if ok else f"no {spec['provider']} key"}
    return results


async def create_run(config: dict, skip_availability_check: bool = False) -> str:
    cfg = normalize_config(config)
    if not skip_availability_check:
        avail = await check_availability(cfg)
        missing = [mid for mid, r in avail.items() if not r["available"]]
        if missing:
            raise ConfigError(f"model(s) unavailable: {', '.join(missing)}")
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    grid = episode_grid(cfg)
    db.insert_run({
        "id": run_id, "name": cfg["name"] or run_id, "created_at": _now(),
        "status": "queued", "test_model": cfg["test_model"], "config": cfg,
        "progress": {"done": 0, "total": len(grid), "failed": 0},
        "cost_usd": 0.0, "budget_usd": cfg["budget_usd"],
        "code_version": code_version(),
    })
    for i, ep in enumerate(grid):
        db.insert_episode({
            "id": f"{run_id}_{i:04d}", "run_id": run_id, "task": ep["task"],
            "seed": ep["seed"], "counterpart_model": ep["counterpart_model"],
            "is_control": ep["is_control"], "condition": ep["condition"],
            "status": "pending", "judge_model": cfg["judge_model"],
        })
    out_dir = runs_dir() / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(cfg, indent=1))
    return run_id


def _progress(run_id: str) -> dict:
    eps = db.episodes_for_aggregation(run_id)
    return {"done": sum(1 for e in eps if e["status"] == "done"),
            "total": len(eps),
            "failed": sum(1 for e in eps if e["status"] == "failed")}


async def execute_run(run_id: str) -> None:
    run = db.get_run(run_id)
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    cfg = run["config"]
    cancel = _cancel_events.setdefault(run_id, asyncio.Event())
    db.update_run(run_id, status="running", error=None)

    conn_rows = db.connect().execute(
        "SELECT id, task, seed, counterpart_model, is_control, condition_json "
        "FROM episodes WHERE run_id = ? AND status != 'done' ORDER BY rowid", (run_id,)
    ).fetchall()
    pending = [dict(r) for r in conn_rows]
    sem = asyncio.Semaphore(cfg.get("concurrency", 4))
    budget = run["budget_usd"]
    state = {"budget_hit": False}

    async def one(row):
        async with sem:
            if cancel.is_set() or state["budget_hit"]:
                return
            current = db.get_run(run_id)["cost_usd"]
            if budget is not None and current >= budget:
                state["budget_hit"] = True
                return
            db.update_episode(row["id"], status="running", started_at=_now())
            try:
                record = await run_episode(
                    row["task"], row["seed"], cfg["test_model"], row["counterpart_model"],
                    condition=json.loads(row["condition_json"]),
                    judge_model=cfg["judge_model"], episode_id=row["id"], run_id=run_id)
                async with _write_lock:
                    db.update_episode(
                        row["id"], status="done",
                        scenario=record["scenario"],
                        turns={"turns": record["turns"],
                               "system_prompts": record["system_prompts"]},
                        outcome=record["outcome"], metrics=record["metrics"],
                        events=record["events"], fields=record["fields"],
                        survey=record["survey"], detection=record["detection"],
                        judge={"judge_out": record["judge_out"],
                               "judge_raw": record["judge_raw"],
                               "dropped": record["judge_dropped"],
                               "eval_awareness": record["eval_awareness"],
                               "judge_model": record["judge_model"], "history": []},
                        judge_failed=record["judge_failed"], excluded=record["excluded"],
                        tokens_in=record["tokens_in"], tokens_out=record["tokens_out"],
                        cost_usd=record["cost_usd"], error=None,
                        started_at=record["started_at"], finished_at=record["finished_at"])
                    db.add_run_cost(run_id, record["cost_usd"])
                    db.update_run(run_id, progress=_progress(run_id))
            except Exception as exc:  # noqa: BLE001 - one bad episode never stops the run
                async with _write_lock:
                    db.update_episode(row["id"], status="failed",
                                      error=f"{type(exc).__name__}: {exc}",
                                      finished_at=_now())
                    db.update_run(run_id, progress=_progress(run_id))

    await asyncio.gather(*(one(r) for r in pending))

    aggregates = metrics_mod.aggregate_episodes(db.episodes_for_aggregation(run_id))
    if cancel.is_set():
        status = "cancelled"
    elif state["budget_hit"]:
        status = "budget_stopped"
    else:
        status = "done"
    db.update_run(run_id, status=status, aggregates=aggregates, progress=_progress(run_id))
    export.write_run_files(run_id)


def cancel_run(run_id: str) -> None:
    _cancel_events.setdefault(run_id, asyncio.Event()).set()


def resume_run(run_id: str) -> None:
    """Re-queue unfinished episodes (caller then schedules execute_run)."""
    _cancel_events.setdefault(run_id, asyncio.Event()).clear()
    conn = db.connect()
    conn.execute("UPDATE episodes SET status = 'pending', error = NULL "
                 "WHERE run_id = ? AND status != 'done'", (run_id,))
    conn.commit()


def mark_interrupted_runs() -> int:
    """On server start: runs left 'running' become failed('server restarted')."""
    conn = db.connect()
    cur = conn.execute("UPDATE runs SET status = 'failed', error = 'server restarted' "
                       "WHERE status IN ('running', 'queued')")
    conn.execute("UPDATE episodes SET status = 'failed', error = 'server restarted' "
                 "WHERE status = 'running'")
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------- rejudge / recompute

async def rejudge_run(run_id: str, judge_model: str) -> None:
    run = db.get_run(run_id)
    _total, eps = db.list_episodes(run_id, status="done", limit=10 ** 9, full=True)
    for ep in eps:
        task = TASKS[ep["task"]]
        turns = (ep["turns"] or {}).get("turns", [])
        scenario, outcome = ep["scenario"], ep["outcome"]
        result = await judge_episode(task, scenario, outcome, turns, judge_model)
        analysis = assemble_analysis(task, scenario, outcome, turns, ep["survey"], result)
        prev = ep.get("judge") or {}
        history = prev.pop("history", []) if isinstance(prev, dict) else []
        if prev:
            history.append(prev)
        db.update_episode(
            ep["id"],
            metrics=analysis["metrics"], events=analysis["events"],
            fields=analysis["fields"], detection=analysis["detection"],
            judge={"judge_out": result.get("judge_out"), "judge_raw": result.get("judge_raw"),
                   "dropped": result.get("dropped", []),
                   "eval_awareness": analysis["eval_awareness"],
                   "judge_model": judge_model, "history": history},
            judge_model=judge_model,
            judge_failed=result.get("judge_failed", False),
            excluded=analysis["fields"]["excluded"])
        db.add_run_cost(run_id, result.get("cost_usd", 0.0))
    _finish_recompute(run_id, run)


def recompute_run(run_id: str) -> None:
    """Recompute metrics, events, fields and aggregates from stored transcripts
    and stored judge output. No model calls."""
    run = db.get_run(run_id)
    _total, eps = db.list_episodes(run_id, status="done", limit=10 ** 9, full=True)
    for ep in eps:
        task = TASKS[ep["task"]]
        turns = (ep["turns"] or {}).get("turns", [])
        judge_blob = ep.get("judge") or {}
        result = {"judge_out": judge_blob.get("judge_out"),
                  "dropped": judge_blob.get("dropped", []),
                  "judge_failed": bool(ep.get("judge_failed"))}
        analysis = assemble_analysis(task, ep["scenario"], ep["outcome"], turns,
                                     ep["survey"], result)
        db.update_episode(ep["id"], metrics=analysis["metrics"], events=analysis["events"],
                          fields=analysis["fields"], detection=analysis["detection"],
                          excluded=analysis["fields"]["excluded"])
    _finish_recompute(run_id, run)


def _finish_recompute(run_id: str, run: dict | None) -> None:
    aggregates = metrics_mod.aggregate_episodes(db.episodes_for_aggregation(run_id))
    prev = (run or {}).get("aggregates")
    if prev:
        history = prev.pop("history", [])
        history.append({k: v for k, v in prev.items() if k != "history"})
        aggregates["history"] = history
    db.update_run(run_id, aggregates=aggregates)
    export.write_run_files(run_id)
