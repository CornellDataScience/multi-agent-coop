"""Build the public dashboard site from committed run folders — no API keys,
no local database. This is what CI (.github/workflows/publish-site.yml) runs
on every push, and what you run locally to preview the site before pushing.

Usage:
  python tools/build_site.py [--out-dir _site] [--manifest runs/manifest.txt]

What it does:
  1. Reads runs/manifest.txt: one run id per line, '#' starts a comment.
     The FIRST id is the featured run — the site's Results tab tells its story.
  2. Validates each listed runs/<run_id>/ folder (see checks below) and
     imports it into a scratch SQLite DB (your real data/asymbench.db is
     never touched).
  3. Exports chart-ready data.json (tools/export_dashboard_data.py, with
     exemplar quotes merged when asymbench/reports/first_trial/exemplars.json
     covers a run) and copies the static page + .nojekyll beside it.

A run folder is publishable when (checked here, with a specific error if not):
  - runs/<run_id>/ exists and is committed to the branch you push;
  - it contains config.json, episodes.jsonl and aggregates.json
    (the runner writes all of these automatically when a run finishes;
    regenerate any time with:
      python -c "from asymbench.export import write_run_files; write_run_files('<run_id>')" );
  - the run_id inside episodes.jsonl matches the folder name;
  - aggregates.json uses the current metric names (recognition_score, ...).
    Folders exported before the 2026-11-14 metric rename fail this check:
    pull the latest branch and re-export with the command above.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REQUIRED_FILES = ("config.json", "episodes.jsonl", "aggregates.json")
EXEMPLARS = REPO / "asymbench" / "reports" / "first_trial" / "exemplars.json"


def fail(msg: str) -> None:
    raise SystemExit(f"build_site: {msg}")


def read_manifest(path: Path) -> list[str]:
    if not path.exists():
        fail(f"{path} not found — it lists the run ids to publish, one per line")
    ids = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    if not ids:
        fail(f"{path} lists no runs")
    if len(ids) != len(set(ids)):
        fail(f"{path} lists a run id twice")
    return ids


def validate_folder(run_id: str) -> Path:
    folder = REPO / "runs" / run_id
    if not folder.is_dir():
        fail(f"runs/{run_id}/ does not exist. Export it from the machine that "
             f"ran it (the runner writes it on completion) and commit it, or "
             f"remove '{run_id}' from runs/manifest.txt.")
    for name in REQUIRED_FILES:
        if not (folder / name).exists():
            fail(f"runs/{run_id}/{name} is missing — re-export the run "
                 f"(see this script's docstring) and commit the folder again.")
    with (folder / "episodes.jsonl").open() as fh:
        first = fh.readline().strip()
    if not first:
        fail(f"runs/{run_id}/episodes.jsonl is empty")
    inner = json.loads(first).get("run_id")
    if inner != run_id:
        fail(f"runs/{run_id}/episodes.jsonl belongs to run '{inner}' — the "
             f"folder name must equal the run id inside it.")
    overall = (json.loads((folder / "aggregates.json").read_text())
               or {}).get("overall") or {}
    if "recognition_score" not in overall:
        fail(f"runs/{run_id}/aggregates.json predates the 2026-11-14 metric "
             f"rename (no recognition_score). Re-export the run from an "
             f"up-to-date checkout (see this script's docstring).")
    return folder


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default="_site")
    ap.add_argument("--manifest", default=str(REPO / "runs" / "manifest.txt"))
    args = ap.parse_args()

    run_ids = read_manifest(Path(args.manifest))
    folders = [validate_folder(rid) for rid in run_ids]

    with tempfile.TemporaryDirectory(prefix="asymbench-site-") as tmp:
        env = dict(os.environ, ASYMBENCH_DB=str(Path(tmp) / "scratch.db"))
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [sys.executable, str(REPO / "tools" / "import_run_folder.py"),
             *map(str, folders)],
            env=env, check=True)
        export_cmd = [sys.executable,
                      str(REPO / "tools" / "export_dashboard_data.py"),
                      *run_ids, "--out", str(out_dir / "data.json")]
        if EXEMPLARS.exists():
            export_cmd += ["--exemplars", str(EXEMPLARS)]
        subprocess.run(export_cmd, env=env, check=True)

    shutil.copy(REPO / "asymbench" / "dashboard" / "index.html",
                out_dir / "index.html")
    (out_dir / ".nojekyll").touch()
    print(f"site built in {out_dir}/ — featured run: {run_ids[0]}; "
          f"{len(run_ids)} run(s) total")


if __name__ == "__main__":
    main()
