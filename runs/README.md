# runs/ — exported benchmark runs, and how they get on the team site

Every `run_*/` folder here is one exported Asymmetry Bench run. The team
results site is built **entirely from the folders committed in this
directory** — publishing a run means committing its folder and pushing.
Nobody's laptop, database, or API keys are in the loop after that.

Site: **https://cornelldatascience.github.io/multi-agent-coop/**
Deployed by: `.github/workflows/publish-site.yml` on every push to
`exploitation-benchmark` that touches `runs/` or the dashboard.

## Publish a run you ran yourself — 3 steps

1. **Run the benchmark** (setup and commands: [`AGENTS.md`](../AGENTS.md) or
   [`asymbench/README.md`](../asymbench/README.md)). When the run finishes,
   the runner has **already written the export folder** — `runs/<run_id>/`
   with `config.json`, `episodes.jsonl`, `aggregates.json`, `summary.csv`.
   Nothing extra to generate.

2. **List the run id in [`manifest.txt`](manifest.txt)** — one id per line,
   `#` starts a comment. The **first** id in the file is the featured run
   (the site's Results tab tells its story); add yours below it unless it
   should take over the headline.

3. **Commit and push** on the `exploitation-benchmark` branch:

   ```bash
   git add runs/<run_id> runs/manifest.txt
   git commit -m "Publish <run_id>: <what it tests>"
   git push
   ```

   The GitHub Action builds and deploys in about a minute. If the site
   doesn't update, open the repo's **Actions** tab — the build fails with a
   specific message when a folder is malformed (see "What the build checks").

Preview locally before pushing (exactly what CI runs):

```bash
python tools/build_site.py --out-dir /tmp/site_preview
open /tmp/site_preview/index.html   # needs a local server for data.json: python3 -m http.server -d /tmp/site_preview
```

## No API keys? Request a run instead

Open a GitHub issue titled **`[Test request] <short name>`** containing a
runner-config JSON block — either from the site's
[Request a test](https://cornelldatascience.github.io/multi-agent-coop/#request)
form (it prefills everything) or from the repo's issue template
(`.github/ISSUE_TEMPLATE/test-request.md`). A teammate with keys runs it,
commits the folder back here, and the site updates. The site lists open
requests with status chips taken from the issue state and labels.

## Folder format (the contract)

```
runs/<run_id>/
  config.json       the full, normalized run configuration
  episodes.jsonl    one JSON object per episode: every turn, system prompts,
                    judge output, survey, normalized fields, costs
  aggregates.json   per-cell aggregates + paired contrasts vs control
                    (95% bootstrap CIs), safeguards
  summary.csv       one row per episode (spec §9.1 fields) — optional for the
                    site build, but the runner writes it anyway
```

These are produced by `asymbench.export.write_run_files(run_id)` — the runner
calls it automatically when a run completes. To regenerate a folder (e.g.
after a re-judge, or if it was exported by an old checkout):

```bash
.venv/bin/python -c "from asymbench.export import write_run_files; write_run_files('<run_id>')"
```

## What the build checks (what "well-formed" means)

`tools/build_site.py` fails the deploy with a named reason when:

- a manifest id has no `runs/<run_id>/` folder committed;
- `config.json`, `episodes.jsonl` or `aggregates.json` is missing;
- the `run_id` inside `episodes.jsonl` doesn't match the folder name;
- `aggregates.json` predates the 2026-11-14 metric rename (no
  `recognition_score` in `overall`) — re-export from an up-to-date checkout
  with the command above.

## Be aware: this repository is public

`episodes.jsonl` contains **full transcripts** — every message, the test
agent's private notes, and system prompts. That is the point (the benchmark
is a research artifact and the team wants runs inspectable), but don't commit
a run whose config or episodes contain anything you wouldn't publish.
API keys never appear in exports; never commit `.env`.
