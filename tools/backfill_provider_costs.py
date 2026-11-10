"""Backfill per-provider episode costs for runs recorded before the
cost_anthropic / cost_openrouter columns existed.

Usage: .venv/bin/python tools/backfill_provider_costs.py

Every agent call (surveys included) is a turn record with its model and cost;
the judge's cost was never a turn, so it is the remainder episode_total - sum
of turn costs, attributed to the judge model's provider.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from asymbench import db  # noqa: E402
from asymbench.settings import resolve_model  # noqa: E402


def main() -> None:
    conn = db.connect()
    rows = conn.execute(
        "SELECT id, run_id, turns_json, judge_model, cost_usd FROM episodes "
        "WHERE status = 'done' AND cost_usd > 0 "
        "AND cost_anthropic = 0 AND cost_openrouter = 0").fetchall()
    import json
    touched_runs = set()
    for r in rows:
        turns = (json.loads(r["turns_json"]) or {}).get("turns", []) if r["turns_json"] else []
        split: dict[str, float] = {}
        turn_sum = 0.0
        for t in turns:
            c = t.get("cost_usd") or 0.0
            turn_sum += c
            if c:
                prov = resolve_model(t.get("model", "")).provider
                split[prov] = split.get(prov, 0.0) + c
        judge_cost = max(0.0, (r["cost_usd"] or 0.0) - turn_sum)
        if judge_cost:
            prov = resolve_model(r["judge_model"] or "").provider
            split[prov] = split.get(prov, 0.0) + judge_cost
        db.update_episode(r["id"], cost_anthropic=split.get("anthropic", 0.0),
                          cost_openrouter=split.get("openrouter", 0.0))
        touched_runs.add(r["run_id"])
    for run_id in touched_runs:
        run = db.get_run(run_id)
        if not run:
            continue
        prog = dict(run.get("progress") or {})
        prog["cost_by_provider"] = db.run_cost_split(run_id)
        db.update_run(run_id, progress=prog)
    print(f"backfilled {len(rows)} episodes across {len(touched_runs)} runs")
    for run_id in sorted(touched_runs):
        print(" ", run_id, db.run_cost_split(run_id))


if __name__ == "__main__":
    main()
