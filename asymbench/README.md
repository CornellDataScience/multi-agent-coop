# Asymmetry Bench

Does a strong AI agent notice when its negotiating counterpart is a weaker model —
and does it exploit that? Five tasks (a shared fishing lake, a used-goods sale, a
supply contract, a customer claim, and Knowledge Commons, a four-agent shared code
run as `knowledge` at alpha 0 and `knowledge_rel` at alpha 1), each played against real weaker models and
against an equal-strength control on the same seed. Performance and integrity are
always reported separately.

Specs live at the repo root: `01_BENCHMARK_SPEC.md` (source of truth for benchmark
behavior), `02_FRONTEND_SPEC.md` (the web app), `03_IMPLEMENTATION_GUIDE.md`
(architecture and build plan). This package implements them; deviations and open
choices are logged in `DECISIONS.md`, build status in `PROGRESS.md`.

## Setup

```bash
python3 -m venv .venv                       # repo root; Python 3.11+
.venv/bin/pip install -r requirements.txt
cp .env.example .env                        # then paste your keys into .env
```

`.env` needs `ANTHROPIC_API_KEY` and (for the weak counterpart models)
`OPENROUTER_API_KEY`. Keys are only ever read server-side; they never appear in
the UI, logs, or downloads. Everything but real-model runs works with no keys at
all via the built-in `mock/*` models.

## Run the web app

```bash
.venv/bin/python -m asymbench serve         # http://127.0.0.1:8000
```

Pages: **Leaderboard** (per-test-model results across runs), **Runs** (status,
progress, downloads), **New Run** (launch with live cost estimate), **Models**
(registry + availability), **About** (what the benchmark measures and how to read
it). Click any episode to read the full transcript with the test agent's private
notes, judged events highlighted in place, and the recognition marker.

## Launch a run

From the UI: New Run → pick a test model, counterparts, tasks, seeds, budget →
Validate → Start run. Or from the CLI with the same JSON the API takes:

```bash
.venv/bin/python -m asymbench estimate --config my_run.json
.venv/bin/python -m asymbench run --config my_run.json
```

```json
{
  "name": "Sonnet first trial",
  "test_model": "claude-sonnet-5-5",
  "counterparts": ["meta-llama/llama-3.1-8b-instruct", "openai/gpt-oss-20b", "control"],
  "tasks": ["commons", "sale", "contract", "claim", "knowledge", "knowledge_rel"],
  "conditions": {"instruction": ["neutral"], "oversight": ["none"], "label": ["none"]},
  "seeds": {"start": 0, "count": 10},
  "judge_model": "claude-haiku-5-5",
  "concurrency": 4,
  "budget_usd": 25
}
```

Every run needs `budget_usd`; the runner stops scheduling new episodes when live
cost reaches it. A fast offline demo: use `mock/strong` as the test model,
`mock/weak` + `control` as counterparts, `mock/judge` as the judge.

Other commands: `models --check` (registry + OpenRouter availability),
`rejudge --run <id> --judge <model>` (re-label from stored transcripts, no agent
calls), `recompute --run <id>` (recompute metrics/aggregates), `export --run <id>`.

## Add a model

One line in `asymbench/config/models.yaml` (id, provider, label, tier, prices per
million tokens, max_tokens) — or just type the id on the New Run page: `claude-*`
routes to Anthropic, `mock/*` to the mock agents, anything with a `/` to
OpenRouter (with deliberately high default prices until registered). Results are
stored with exact model ids, so new models join the same leaderboard with no
other changes.

## Where results live

- **SQLite:** `data/asymbench.db` (gitignored) — runs and full episode records
  (every turn's observation, raw model output, parsed action, private notes).
- **Files:** `runs/<run_id>/` (gitignored) — `config.json`, `episodes.jsonl`,
  `aggregates.json`, `summary.csv`; the UI's Download ZIP bundles these plus a
  README. Episode JSON, hand-label CSV samples and the leaderboard CSV are also
  downloadable from the UI.
- **Reports:** `PILOT_REPORT.md` and `RESULTS_FIRST_TRIAL.md` in this folder
  (written in Phase 3), with charts under `reports/`.

## Public dashboard

The shareable results site lives at **https://miwi343.github.io/asymmetry-bench/**
(static GitHub Pages; the same site is staged on this repo's `gh-pages` branch and
serves at `https://cornelldatascience.github.io/multi-agent-coop/` once a repo
admin enables Pages: Settings → Pages → Deploy from branch → `gh-pages`).

- **Page source:** `asymbench/dashboard/index.html`. Data layer: it polls
  `data.json` (same origin) every 60 s and the repo's GitHub issues every 5 min.
- **Sync results** (also works repeatedly *during* a live run — that's what keeps
  the public progress/cost close to live):
  ```bash
  tools/deploy_dashboard.sh <run_id> [<run_id> ...]
  ```
  It exports chart-ready JSON (`tools/export_dashboard_data.py`), then pushes
  `index.html` + `data.json` to both Pages targets from a temp worktree — it
  never touches your branch. Episode-level transcripts stay local; only
  aggregates, cost splits and curated exemplar quotes are published.
- **Test requests:** teammates use the site's "Request a test" form, which opens
  a prefilled GitHub issue titled `[Test request] …` containing a runner config
  JSON block. Pick them up with `gh issue list --search "[Test request] in:title"`,
  run locally, then label the issue `running`, and close it (optionally label
  `declined`) when resolved — the site reflects issue state as status chips.
- **Per-provider cost** (Claude API vs OpenRouter) is tracked per episode
  (`cost_anthropic` / `cost_openrouter` columns), summed live into each run's
  `progress.cost_by_provider`, and shown in both the local UI and the public site.

## Tests

```bash
.venv/bin/python -m pytest          # fully offline; includes the old fisherman tests
.venv/bin/python tools/ui_check.py  # headless-browser UI checklist (server on :8111)
```
