"""FastAPI app: JSON API under /api/*, static front-end at /. Runs execute as
background asyncio tasks in the server's event loop. API keys never appear in
any response."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, db, export, runner
from . import metrics as metrics_mod
from .providers import check_openrouter_ids
from .settings import defaults, key_available, presets, registry, resolve_model, runs_dir
from .tasks import TASK_ORDER, TASKS

app = FastAPI(title="Asymmetry Bench", version=__version__)
STATIC_DIR = Path(__file__).resolve().parent / "static"

_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


@app.on_event("startup")
async def startup() -> None:
    db.connect()
    runner.mark_interrupted_runs()


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def error_handler(request: Request, exc: Exception):
    return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)


def _run_summary(run: dict) -> dict:
    cfg = run.get("config") or {}
    return {
        "id": run["id"], "name": run.get("name"), "created_at": run["created_at"],
        "status": run["status"], "test_model": run["test_model"],
        "tasks": cfg.get("tasks", []), "counterparts": cfg.get("counterparts", []),
        "progress": run.get("progress") or {}, "cost_usd": run.get("cost_usd", 0.0),
        "budget_usd": run.get("budget_usd"), "has_mock": bool(cfg.get("has_mock")),
        "error": run.get("error"),
    }


# ---------------------------------------------------------------- basics

@app.get("/api/health")
async def health():
    return {"ok": True, "version": __version__}


@app.get("/api/models")
async def models():
    return {
        "models": [{**m.to_dict(), "key_available": key_available(m.provider)}
                   for m in registry()],
        "keys": {"anthropic": key_available("anthropic"),
                 "openrouter": key_available("openrouter"), "mock": True},
        "defaults": defaults(),
    }


@app.post("/api/models/check")
async def models_check(body: dict):
    ids = body.get("model_ids") or []
    results = {}
    or_ids = []
    for mid in ids:
        try:
            spec = resolve_model(mid)
        except ValueError as exc:
            results[mid] = {"available": False, "reason": str(exc)}
            continue
        if spec.provider == "openrouter":
            or_ids.append(mid)
        else:
            ok = key_available(spec.provider)
            results[mid] = {"available": ok,
                            "reason": None if ok else f"no {spec.provider} key"}
    if or_ids:
        try:
            avail = await check_openrouter_ids(or_ids)
            for mid in or_ids:
                ok = avail.get(mid, False) and key_available("openrouter")
                reason = None if ok else (
                    "no openrouter key" if not key_available("openrouter")
                    else "not listed by OpenRouter /models")
                results[mid] = {"available": ok, "reason": reason}
        except Exception as exc:  # network failure
            for mid in or_ids:
                results[mid] = {"available": False, "reason": f"check failed: {exc}"}
    return {"results": results}


@app.get("/api/tasks")
async def tasks():
    return [{"id": t.id, "name": t.name, "description": t.description, "roles": t.roles}
            for t in (TASKS[tid] for tid in TASK_ORDER)]


@app.get("/api/presets")
async def get_presets():
    return presets()


@app.post("/api/estimate")
async def estimate(body: dict):
    try:
        return runner.estimate(body)
    except (runner.ConfigError, ValueError) as exc:
        raise HTTPException(400, str(exc))


# ---------------------------------------------------------------- runs

@app.post("/api/runs")
async def create_run(body: dict):
    try:
        run_id = await runner.create_run(body)
    except (runner.ConfigError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    _spawn(runner.execute_run(run_id))
    return {"run_id": run_id}


@app.get("/api/runs")
async def list_runs(status: str | None = None, test_model: str | None = None,
                    q: str | None = None):
    return [_run_summary(r) for r in db.list_runs(status, test_model, q)]


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    out = _run_summary(run)
    out["config"] = run.get("config")
    out["code_version"] = run.get("code_version")
    aggregates = run.get("aggregates")
    if not aggregates and run["status"] in ("running", "queued"):
        aggregates = metrics_mod.aggregate_episodes(db.episodes_for_aggregation(run_id))
        aggregates["partial"] = True
    out["aggregates"] = aggregates
    return out


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    runner.cancel_run(run_id)
    return {"ok": True}


@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run["status"] == "running":
        raise HTTPException(400, "run is already running")
    runner.resume_run(run_id)
    _spawn(runner.execute_run(run_id))
    return {"ok": True}


@app.post("/api/runs/{run_id}/rejudge")
async def rejudge(run_id: str, body: dict):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    judge_model = body.get("judge_model")
    if not judge_model:
        raise HTTPException(400, "judge_model is required")
    try:
        resolve_model(judge_model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.update_run(run_id, status="running")

    async def task():
        try:
            await runner.rejudge_run(run_id, judge_model)
            db.update_run(run_id, status="done")
        except Exception as exc:  # noqa: BLE001
            db.update_run(run_id, status="failed", error=f"re-judge failed: {exc}")
    _spawn(task())
    return {"ok": True}


@app.post("/api/runs/{run_id}/recompute")
async def recompute(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    runner.recompute_run(run_id)
    return {"ok": True}


@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    db.delete_run(run_id)
    folder = runs_dir() / run_id
    if folder.exists():
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True}


@app.get("/api/runs/{run_id}/episodes")
async def run_episodes(run_id: str, task: str | None = None,
                       counterpart: str | None = None, condition: str | None = None,
                       flags: str | None = None,
                       limit: int = Query(100, le=1000), offset: int = 0):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    total, eps = db.list_episodes(run_id, task=task, counterpart=counterpart,
                                  condition=condition, limit=10 ** 9, offset=0)
    if flags:
        want = set(flags.split(","))
        def keep(ep):
            f = ep.get("fields") or {}
            if "attempts" in want and not f.get("attempt_any"):
                return False
            if "success" in want and not f.get("success_any"):
                return False
            if "excluded" in want and not f.get("excluded"):
                return False
            if "judge_failed" in want and not f.get("judge_failed"):
                return False
            if "failed" in want and ep.get("status") != "failed":
                return False
            return True
        eps = [e for e in eps if keep(e)]
        total = len(eps)
    items = eps[offset:offset + limit]
    for ep in items:
        ep["outcome_summary"] = _outcome_summary(ep)
    return {"total": total, "items": items}


def _outcome_summary(ep: dict) -> str:
    if ep.get("status") == "failed":
        return "failed"
    if ep.get("status") != "done":
        return ep.get("status", "")
    m = ep.get("metrics") or {}
    task = ep["task"]
    if task == "commons":
        return f"caught {m.get('test_catch', '?')} fish ({m.get('breach_rounds', 0)} breach rounds)"
    if task == "sale":
        if m.get("deal"):
            extra = " (buyer overpaid)" if m.get("buyer_overpaid") else ""
            return f"deal at ${m.get('price'):g}{extra}"
        return f"no deal ({m.get('end_reason', '')})"
    if task == "contract":
        if m.get("deal"):
            extra = " (client below walkaway)" if m.get("client_below_walkaway") else ""
            return f"deal: supplier {m.get('s')} / client {m.get('c')} points{extra}"
        return f"no deal ({m.get('end_reason', '')})"
    if task == "claim":
        res = m.get("resolution")
        if res == "accepted":
            return f"settled at ${m.get('customer_value', 0):.2f} of ${m.get('entitlement', 0):.2f} owed"
        return res or "?"
    if task in ("knowledge", "knowledge_rel"):
        return (f"{m.get('test_points') or 0:g} points, solved {m.get('solve_rate', 0):.0%} of rounds "
                f"({m.get('lies', 0)} false digits sent)")
    return ""


@app.get("/api/episodes/{ep_id}")
async def get_episode(ep_id: str):
    ep = db.get_episode(ep_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    return ep


# ---------------------------------------------------------------- leaderboard & models

@app.get("/api/leaderboard")
async def leaderboard(task: str | None = None, condition: str | None = None,
                      include_mock: bool = False):
    eps = db.episodes_for_leaderboard(include_mock=include_mock)
    cond = condition or metrics_mod.DEFAULT_CONDITION_KEY
    if condition == "all":
        cond = None
    rows = metrics_mod.leaderboard_rows(eps, include_mock=include_mock,
                                        task_filter=task or None, condition_filter=cond)
    for row in rows:
        per_task = {}
        for tid in TASK_ORDER:
            t_rows = metrics_mod.leaderboard_rows(
                [e for e in eps if e["test_model"] == row["model"]],
                include_mock=include_mock, task_filter=tid, condition_filter=cond)
            if t_rows:
                per_task[tid] = {k: t_rows[0][k] for k in
                                 ("principal_value", "advantage_captured", "attempt_shift",
                                  "success_shift", "disclosure_shift",
                                  "baseline_exploitation", "recognition_gap",
                                  "post_recognition_change", "episodes")}
        row["per_task"] = per_task
        try:
            row["label"] = resolve_model(row["model"]).label
        except ValueError:
            row["label"] = row["model"]
    return rows


@app.get("/api/models/usage")
async def models_usage(id: str):
    usage = db.model_usage(id)
    usage["as_test"] = [_run_summary(r) for r in usage["as_test"]]
    usage["as_counterpart"] = [_run_summary(r) for r in usage["as_counterpart"]]
    return usage


@app.get("/api/about")
async def about():
    d = defaults()
    return {
        "defaults": d,
        "tasks": [{"id": t.id, "name": t.name, "description": t.description}
                  for t in (TASKS[tid] for tid in TASK_ORDER)],
        "models": [{**m.to_dict(), "key_available": key_available(m.provider)}
                   for m in registry()],
        "links": {"repo": "https://github.com/CornellDataScience/multi-agent-coop",
                  "proposal": ""},
    }


# ---------------------------------------------------------------- downloads

def _stamp(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (name or "run"))
    return f"{safe}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"


@app.get("/api/runs/{run_id}/download.zip")
async def download_zip(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    data = export.zip_run(run_id)
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="asymbench_{_stamp(run["name"])}.zip"'})


@app.get("/api/runs/{run_id}/summary.csv")
async def download_summary(run_id: str):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    return PlainTextResponse(export.summary_csv(run_id), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="asymbench_summary_{_stamp(run_id)}.csv"'})


@app.get("/api/runs/{run_id}/aggregates.json")
async def download_aggregates(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return JSONResponse(run.get("aggregates") or {}, headers={
        "Content-Disposition": f'attachment; filename="asymbench_aggregates_{_stamp(run_id)}.json"'})


@app.get("/api/episodes/{ep_id}/download.json")
async def download_episode(ep_id: str):
    ep = db.get_episode(ep_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    return JSONResponse(ep, headers={
        "Content-Disposition": f'attachment; filename="asymbench_episode_{ep_id}.json"'})


@app.get("/api/runs/{run_id}/handlabel.csv")
async def download_handlabel(run_id: str, frac: float = 0.1, seed: int = 0):
    if not db.get_run(run_id):
        raise HTTPException(404, "run not found")
    return PlainTextResponse(export.handlabel_csv(run_id, frac, seed), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f'attachment; filename="asymbench_handlabel_{_stamp(run_id)}.csv"'})


@app.get("/api/leaderboard.csv")
async def download_leaderboard(task: str | None = None, condition: str | None = None,
                               include_mock: bool = False):
    rows = await leaderboard(task, condition, include_mock)
    return PlainTextResponse(export.leaderboard_csv(rows), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="asymbench_leaderboard_{_stamp("all")}.csv"'})


# ---------------------------------------------------------------- static

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
