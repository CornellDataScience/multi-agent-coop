"""Import an exported run folder (config.json + episodes.jsonl [+ aggregates.json])
into the local SQLite DB, so teammate runs appear in the local app, the episode
viewer, and the public dashboard export.

Usage:
  .venv/bin/python tools/import_run_folder.py <run_dir> [<run_dir> ...] [--replace]

Idempotent: a run that is already in the DB is skipped unless --replace is given.
Per-provider cost split is taken from the episode records when present (exports
made after the cost-split migration carry it), otherwise it defaults to 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from asymbench import db  # noqa: E402


def import_folder(path: Path, replace: bool) -> None:
    cfg = json.loads((path / "config.json").read_text())
    eps = [json.loads(line) for line in
           (path / "episodes.jsonl").read_text().splitlines() if line.strip()]
    if not eps:
        raise SystemExit(f"{path}: no episodes")
    agg_file = path / "aggregates.json"
    agg = json.loads(agg_file.read_text()) if agg_file.exists() else None
    run_id = eps[0]["run_id"]
    if db.get_run(run_id):
        if not replace:
            print(f"{run_id}: already in DB, skipping (use --replace to reimport)")
            return
        db.delete_run(run_id)
    done = sum(1 for e in eps if e.get("status") == "done")
    failed = sum(1 for e in eps if e.get("status") == "failed")
    cost = round(sum(e.get("cost_usd") or 0.0 for e in eps), 6)
    db.insert_run({
        "id": run_id,
        "name": cfg.get("name") or run_id,
        "created_at": min(filter(None, (e.get("started_at") for e in eps)),
                          default=None),
        "status": "done",
        "test_model": cfg.get("test_model"),
        "config": cfg,
        "progress": {"done": done, "total": len(eps), "failed": failed},
        "cost_usd": cost,
        "budget_usd": cfg.get("budget_usd"),
        "aggregates": agg,
        "code_version": f"imported:{path.name}",
    })
    for e in eps:
        db.insert_episode(e)
        db.update_episode(e["id"],
                          cost_anthropic=e.get("cost_anthropic", 0.0),
                          cost_openrouter=e.get("cost_openrouter", 0.0))
    db.update_run(run_id, progress={"done": done, "total": len(eps),
                                    "failed": failed,
                                    "cost_by_provider": db.run_cost_split(run_id)})
    print(f"{run_id}: imported {len(eps)} episodes (${cost:.2f}) from {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", nargs="+")
    ap.add_argument("--replace", action="store_true",
                    help="delete and reimport a run that is already in the DB")
    args = ap.parse_args()
    for d in args.run_dirs:
        import_folder(Path(d), args.replace)


if __name__ == "__main__":
    main()
