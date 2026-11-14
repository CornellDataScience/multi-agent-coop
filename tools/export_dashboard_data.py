"""Build the public dashboard's data.json for one or more runs: chart-ready
shapes the static site (asymbench/dashboard/index.html) renders directly —
keep the two in sync. tools/deploy_dashboard.sh pushes the result to the
gh-pages branch, which serves the site.

Usage:
  .venv/bin/python tools/export_dashboard_data.py <run_id> [<run_id> ...]
      [--exemplars path.json] [--out out.json]

The FIRST run id is the featured run: the site's results tab tells its story,
whatever other runs exist. Order the rest however you like.

Output: {"runs": {<run_id>: {...}}, "meta": {...}} written to --out
(default: asymbench/reports/dashboard_data.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from asymbench import db  # noqa: E402
from asymbench.metrics import bootstrap_mean_ci  # noqa: E402

CP_SHORT = {"meta-llama/llama-3.1-8b-instruct": "Llama 3.1 8B",
            "openai/gpt-oss-20b": "gpt-oss-20b",
            "claude-haiku-5-5": "Claude Haiku 5.5"}
OVERALL_KEYS = ("recognition_gap", "survey_gap", "attempt_shift", "success_shift",
                "harm_shift", "advantage_captured", "disclosure_shift",
                "baseline_exploitation", "eval_aware_rate", "n_pairs")


def short(cp: str) -> str:
    return CP_SHORT.get(cp, cp.split("/")[-1])


def ci(d: dict | None) -> dict | None:
    if not d or d.get("mean") is None:
        return None
    return {k: d.get(k) for k in ("mean", "lo", "hi", "n")}


def sensitivity(run_id: str) -> dict:
    """No-counterpart-misconduct recomputation of the three key shifts."""
    _t, eps = db.list_episodes(run_id, status="done", limit=1000, full=True)
    ok = [e for e in eps if not (e.get("fields") or {}).get("excluded")]
    ctrl = {(e["task"], e["seed"]): e for e in ok if e["is_control"]}
    diffs: dict[str, list] = {"attempt_events": [], "harm": [], "recognized": []}
    for e in ok:
        if e["is_control"] or (e["fields"] or {}).get("counterpart_misconduct"):
            continue
        c = ctrl.get((e["task"], e["seed"]))
        if not c:
            continue
        for k in diffs:
            w, cv = e["fields"].get(k), c["fields"].get(k)
            if w is not None and cv is not None:
                diffs[k].append(float(w) - float(cv))
    return {k: bootstrap_mean_ci(v) for k, v in diffs.items() if v}


def run_doc(run_id: str, exemplars: list | None) -> dict:
    run = db.get_run(run_id)
    if run is None:
        raise SystemExit(f"no such run: {run_id}")
    cfg = run.get("config") or {}
    agg = run.get("aggregates") or {}
    prog = run.get("progress") or {}
    contrasts = agg.get("contrasts") or []
    cells = agg.get("cells") or []
    overall = agg.get("overall") or {}
    cps = sorted({c["counterpart"] for c in contrasts})

    def cell_mean(cp_sel, field):
        sel = [c for c in cells if (c["is_control"] if cp_sel == "control"
               else (c["counterpart"] == cp_sel and not c["is_control"]))]
        vals = [c["fields"][field]["mean"] for c in sel
                if (c["fields"].get(field) or {}).get("mean") is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    tasks = sorted({c["task"] for c in contrasts})
    attempt_chart = {"tasks": tasks, "series": []}
    for cp in cps:
        row = {"label": short(cp), "mean": [], "lo": [], "hi": []}
        for t in tasks:
            match = [c for c in contrasts if c["task"] == t and c["counterpart"] == cp]
            v = ci(match[0].get("attempt_shift")) if match else None
            row["mean"].append(v and v["mean"])
            row["lo"].append(v and v["lo"])
            row["hi"].append(v and v["hi"])
        attempt_chart["series"].append(row)

    groups = [short(c) for c in cps] + ["control"]
    recognition_chart = {
        "groups": groups,
        "rate": [cell_mean(c, "recognized") for c in cps] + [cell_mean("control", "recognized")],
        "survey": [cell_mean(c, "survey_rating") for c in cps] + [cell_mean("control", "survey_rating")],
    }

    def pooled(cp, key):
        cs = [ci(c.get(key)) for c in contrasts if c["counterpart"] == cp]
        cs = [c for c in cs if c]
        if len(cs) == 1:
            return cs[0]
        if not cs:
            return None
        return {"mean": round(sum(c["mean"] for c in cs) / len(cs), 4),
                "lo": None, "hi": None, "n": sum(c.get("n") or 0 for c in cs)}

    shift_charts = {}
    for key in ("harm_shift", "advantage_captured"):
        vals = [pooled(cp, key) for cp in cps]
        shift_charts[key] = {"labels": [short(c) for c in cps],
                             "mean": [v and v["mean"] for v in vals],
                             "lo": [v and v["lo"] for v in vals],
                             "hi": [v and v["hi"] for v in vals]}

    commons = [c for c in cells if c["task"] == "commons"]
    commons_pool = None
    if commons:
        series = []
        for c in sorted(commons, key=lambda c: (not c["is_control"], c["counterpart"])):
            traj = (c.get("extras") or {}).get("pool_by_round") or []
            if traj:
                series.append({"label": "control" if c["is_control"] else short(c["counterpart"]),
                               "control": bool(c["is_control"]),
                               "values": [round(v, 1) for v in traj]})
        if series:
            commons_pool = {"series": series}

    per_task = []
    for c in contrasts:
        per_task.append({
            "task": c["task"], "cp": short(c["counterpart"]),
            "recognition_gap": ci(c.get("recognition_gap")),
            "attempt_shift": ci(c.get("attempt_shift")),
            "harm_shift": ci(c.get("harm_shift")),
            "advantage_captured": ci(c.get("advantage_captured")),
            "survey_gap": ci(c.get("survey_gap")),
        })

    split = db.run_cost_split(run_id)
    doc = {
        "name": run.get("name") or run_id,
        "status": run["status"],
        "created_at": run.get("created_at"),
        "test_model": run.get("test_model"),
        "judge_model": cfg.get("judge_model"),
        "tasks": cfg.get("tasks") or [],
        "counterparts": [c for c in (cfg.get("counterparts") or [])
                         if c != run.get("test_model")],
        "seeds": (cfg.get("seeds") or {}).get("count"),
        "episodes": {"done": prog.get("done", 0), "total": prog.get("total", 0),
                     "failed": prog.get("failed", 0),
                     "excluded": (agg.get("totals") or {}).get("excluded", 0)},
        "cost": {"total": round(run.get("cost_usd") or 0.0, 2),
                 "anthropic": round(split["anthropic"], 2),
                 "openrouter": round(split["openrouter"], 2),
                 "budget": run.get("budget_usd")},
        "overall": {k: (ci(overall.get(k)) if isinstance(overall.get(k), dict)
                        else overall.get(k)) for k in OVERALL_KEYS},
        "per_task": per_task,
        "recognition_chart": recognition_chart,
        "attempt_chart": attempt_chart,
        "shift_charts": shift_charts,
        "commons_pool": commons_pool,
        "sensitivity": sensitivity(run_id) if run["status"] == "done" else None,
        "exemplars": exemplars or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_ids", nargs="+")
    ap.add_argument("--exemplars", help="JSON file: {run_id: [exemplar, ...]}")
    ap.add_argument("--out", default="asymbench/reports/dashboard_data.json")
    args = ap.parse_args()
    exemplars = {}
    if args.exemplars:
        exemplars = json.loads(Path(args.exemplars).read_text())
    runs: dict[str, dict] = {}
    latest = None
    for rid in args.run_ids:
        runs[rid] = run_doc(rid, exemplars.get(rid))
        runs[rid]["featured"] = rid == args.run_ids[0]
        if latest is None or (runs[rid]["created_at"] or "") > \
                (runs[latest]["created_at"] or ""):
            latest = rid
    payload = {
        "runs": runs,
        "meta": {"latest_run": latest,
                 "updated_at": datetime.now(timezone.utc).isoformat()},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    print(f"wrote {out} ({len(runs)} runs, "
          f"{out.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
