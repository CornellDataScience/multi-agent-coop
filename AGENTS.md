# Agent / contributor guide

This file is the entry point for anyone — human or AI coding assistant —
working in this repository. It tells you what lives where, how to run the
benchmark yourself, and how to get results onto the team site.

## What this repository is

Cornell Data Science FA26 — multi-agent cooperation/exploitation research.
Two projects share the repo:

| Project | Where | What |
|---|---|---|
| **Asymmetry Bench** | `asymbench/` on branch **`exploitation-benchmark`** | Does a strong AI negotiator spontaneously recognize and exploit a weaker AI counterpart? 6 tasks, matched-pair design (weak counterpart vs same-seed equal-strength control). |
| Fisherman's Dilemma | `src/` (see root `README.md`, `specs.md`) | The original N-agent commons game. **Do not modify `src/` as part of asymbench work.** |

Asymmetry Bench deep docs: `01_BENCHMARK_SPEC.md` (design + metrics),
`02_FRONTEND_SPEC.md`, `03_IMPLEMENTATION_GUIDE.md`,
`asymbench/README.md` (operations), `asymbench/DECISIONS.md` (why things are
the way they are), `asymbench/PROGRESS.md` (state of the work).
`asymbench/metrics.py` is the source of truth for every reported number.

Team results site: **https://cornelldatascience.github.io/multi-agent-coop/**

## Run the benchmark yourself (needs API keys)

```bash
git checkout exploitation-benchmark
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # paste ANTHROPIC_API_KEY and OPENROUTER_API_KEY; never commit .env
```

```bash
.venv/bin/python -m asymbench estimate --config my_config.json  # cost BEFORE running
.venv/bin/python -m asymbench run --config my_config.json       # headless run
.venv/bin/python -m asymbench serve                             # or the local web app on :8000
.venv/bin/python -m pytest                                      # fully offline test suite
```

A config is plain JSON (same shape the site's "Request a test" form emits):

```json
{
  "name": "sonnet5 vs llama, all tasks",
  "test_model": "claude-sonnet-5",
  "counterparts": ["meta-llama/llama-3.1-8b-instruct", "control"],
  "tasks": ["commons", "sale", "contract", "claim", "knowledge", "knowledge_rel"],
  "seeds": { "start": 0, "count": 10 },
  "judge_model": "claude-haiku-5-5",
  "concurrency": 4,
  "budget_usd": 10
}
```

Runs cost real money (the first trial: 120 episodes ≈ $16). Always
`estimate` first, always set `budget_usd` — the runner stops at the cap.
`python -m asymbench models --check` lists the registry and verifies access.

Results land in `data/asymbench.db` (gitignored) **and** in an exported
folder `runs/<run_id>/`, written automatically when the run completes.

## Publish your results to the team site (no keys needed for this part)

Three steps — full details in [`runs/README.md`](runs/README.md):

1. The finished run already exported itself to `runs/<run_id>/`.
2. Add the run id to `runs/manifest.txt` (first id in the file = featured run).
3. `git add runs/<run_id> runs/manifest.txt`, commit, push to
   `exploitation-benchmark`. A GitHub Action rebuilds and deploys the site in
   about a minute — no laptop, database, or API keys involved.

Preview locally first: `python tools/build_site.py --out-dir /tmp/site_preview`.

## No API keys? Request a run

Open a GitHub issue titled `[Test request] <name>` with the config JSON in a
fenced block — the site's [Request a test](https://cornelldatascience.github.io/multi-agent-coop/#request)
form or `.github/ISSUE_TEMPLATE/test-request.md` prefills it. A teammate with
keys runs it and publishes the folder; the site shows your request's status.

## Hard rules

- **Never manufacture the behavior being measured.** The benchmark's validity
  rests on neutral prompts: no hints that the counterpart is weak, no nudges
  to exploit, identical prompts per role across conditions. Tests enforce
  this (prompt-leak and eval-cue tests); do not weaken them.
- **Never commit secrets.** `.env` is gitignored; keys must never appear in
  code, configs, exports, logs, or commits.
- **This repo is public.** Exported runs include full transcripts (messages,
  private notes, system prompts) — that is intentional, but check what you
  commit.
- **Branch discipline.** Asymmetry Bench work happens on
  `exploitation-benchmark`. Never commit to `main` directly.
- Metric or task changes must keep `01_BENCHMARK_SPEC.md`,
  `asymbench/metrics.py`, the dashboard and the tests in sync, and be
  recorded in `asymbench/DECISIONS.md`.

## Known gotchas

- `claude-sonnet-5-5` as test model: its safety classifier false-positives on
  the benchmark's private-notes instruction (`reasoning_extraction`) and
  repeated refusals can suspend org API access for ~1 hour. Use
  `claude-sonnet-5` until further notice. Details: `asymbench/DECISIONS.md` #38.
- The runner has a circuit breaker: 3 consecutive provider access errors
  (401/403/suspension) stop the run as "failed" instead of burning the grid.
- `recompute --run` crashes on the commons task (JSON int-key round-trip bug,
  logged in `asymbench/PROGRESS.md`) — re-aggregate via
  `asymbench.metrics.aggregate_episodes` instead.
