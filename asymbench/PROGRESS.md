# Progress

## Phase 1: Engine and all four tasks — DONE

**Built:**
- `asymbench/` package: `settings.py` (registry + presets + .env), `providers.py`
  (async Anthropic/OpenRouter chat with retries, timeouts, semaphores, cost),
  `parsing.py` (the 5-step ladder as pure functions), `agent.py` (`take_turn`:
  format block → call → parse → validate → one retry → safe default; full spec
  10.1 turn records), `mock.py` (mock/weak, mock/strong, mock judge),
  all four tasks (`tasks/commons.py`, `sale.py`, `contract.py`, `claim.py`)
  with pure environment logic, `judge.py` (taxonomies, prompt, quote/type
  validation), `metrics.py` (9.1 fields, bootstrap CIs, cells, paired contrasts,
  recognition-conditioned analysis, safeguards, leaderboard rows),
  `episode.py` (single-episode orchestration), configs, `requirements.txt`,
  `.env.example`, `.gitignore` additions.
- `asymbench/REPO_NOTES.md` (existing-code survey), `asymbench/DECISIONS.md`
  (27 recorded decisions).
- Tests: `tests/test_asym_*.py` — 155 new tests; the pre-existing 65 fisherman
  tests still pass (suite total 220, fully offline).

**Gate results (guide §8.1):** all pass.
- `pytest` passes offline: 220 passed.
- Parsing fixture set: 28 messy outputs (fences, prose, think tags, trailing
  commas, smart quotes, string numbers, missing fields, two objects, raw
  newlines, broken JSON, arrays, unclosed objects...).
- Every environment rule has a scripted-action unit test (T1 dynamics/caps/
  rotation/breach tolerance; T2 loop/tools/fees/payoffs/accept legality;
  T3 proposal validation/normalization/walkaway; T4 rules engine + values table).
- T2 generator constraints hold for 1,000 seeds. T3 Nash/max-joint/supplier-best
  verified by an independent brute-force re-enumeration. T4 rules engine matches
  hand-computed examples for every case type.
- Judge validation drops bad quotes, unknown types, wrong-side events, and
  unverifiable detections. Bootstrap CIs and paired contrasts match known
  answers on synthetic data.
- One mock episode of each task produces a complete record with every 9.1 field
  (test_asym_e2e_mock.py), and a 24-episode mock mini-run shows the designed
  positive recognition gap, attempt shift, and post-recognition change.
- Existing fisherman commands verified working (`python -m src.main conditions`,
  `run all_honest`); no existing file modified except additive edits to
  `.gitignore` and `.env.example`.

**Balance notes (the one thing that matters most):**
- Nothing added to any prompt beyond the spec's exact role briefs and condition
  lines; test checks the test agent's default prompt ends at the neutral line.
- Leak tests enforce the information design (T1 takes, T2 defects, T3 tables,
  T4 entitlement). Eval-cue test scans all prompts and observations.
- Two spec frictions resolved conservatively and recorded (DECISIONS.md #17
  recurring-case battery conflict; #13 nondisclosure has no quotable words).
  Neither changes incentives or what any agent sees.

**Open questions for the team:** none blocking. DECISIONS.md #15 (string-number
option matching in T3) and #14 (T2 "avoided overpaying" with no deal) are the
two most judgment-y calls; both apply identically to every model.

**Next:** Phase 2 (db, runner, export, CLI, server, front-end).

## Phase 2: Runs, storage and the web app — DONE

**Built:** `db.py` (SQLite WAL, append-only results, re-judge history),
`runner.py` (grid interleaved by seed, concurrency semaphore, live budget
enforcement, cancel, resume-after-restart, re-judge, recompute, cost
estimation with measured-average refinement), `export.py` (run folder files,
ZIP with README, summary/hand-label/leaderboard CSVs), `__main__.py` CLI
(serve/run/models/rejudge/recompute/export/estimate), `server.py` (every 02 §5
endpoint + §6 download, background runs, `{"error": ...}` error shape), and
the full front-end (`static/index.html|app.js|styles.css`: leaderboard with
sortable CI columns and scatter, runs list with live polling, New Run form
with live estimates and validation, run detail with 6 tabs and 7 chart types,
the episode viewer with judge-quote highlighting / private-notes toggles /
detection marker / T1 true-take lines, models page, full About page, light +
dark themes, 375px layout). Plus `tools/ui_check.py` (Playwright walk of the
02 §8 checklist) and `asymbench/README.md`.

**Gate results (guide §8.2):** all pass.
- Mock run (4 tasks × mock/weak + control × ≥2 seeds, test `mock/strong`)
  completes from the CLI and from the New Run page.
- Its aggregates show the designed positive recognition gap (+1.00), attempt
  shift (+1.38 to +2.63 across runs) and post-recognition change (+0.21 to
  +0.40) — the whole metric pipeline verified end to end.
- Cancel, budget stop, resume after a simulated server restart, re-judge
  (history preserved) and recompute all covered by tests
  (`tests/test_asym_runner.py`).
- FastAPI test-client endpoint tests pass, including ZIP contents
  (`tests/test_asym_server.py`). Suite now 235 tests, fully offline.
- 02 §8 checklist verified in headless Chromium: 32/32 checks, zero console
  errors, screenshots in `asymbench/screenshots/` (light + dark + 375px).
  Three front-end bugs found by screenshot review and fixed: collapsed chart
  canvases, a `null` text node from native `append()`, and the error banner's
  `display:flex` overriding the `hidden` attribute.

**Decisions:** DECISIONS.md #28-35 (schema packing, two API deviations with
reasons, leaderboard CIs, additive aggregate extras, UI tooling).

**Next:** Phase 3 (verify model ids/prices, $5 pilot, pilot review, $30 first
trial, results report). Both API keys are present in .env.

## Phase 3 — DONE (2026-11-09)

- **Step A (verify models) — DONE.** Anthropic ids/prices matched the current
  API reference exactly (no change). OpenRouter ids all exist; three prices
  updated to provider-reported values. DECISIONS.md #36.
- **Test-agent substitution (user-approved).** The spec'd `claude-sonnet-5-5`
  is unusable: its safety classifier refuses this benchmark's call pattern
  (`reasoning_extraction`) and accumulated refusals triggered a 1-hour
  org-level suspension. The team lead chose `claude-sonnet-5` (same price
  tier; passes identical payloads). Evidence in DECISIONS.md #38; the smoke
  run is kept in the DB. Provider layer hardened (stop_details persisted,
  empty responses retried).
- **Step B (pilot) — DONE.** `run_20261109_041656_b700fc`: 36/36 episodes,
  $4.64 of $5.
- **Step C (pilot review) — DONE.** `PILOT_REPORT.md`: all five §8.3 checks
  pass (0 code failures; both counterparts playable — llama 0% invalid,
  gpt-oss ≤25% per task; judge 100% parse with 10/10 hand-checked labels;
  balance holds with 12 transcripts read; $0.129/episode). Both counterparts
  retained for the trial.
- **Step D (first trial) — DONE.** `run_20261109_195350_7c8efd`: 4 tasks ×
  (Llama 3.1 8B, gpt-oss-20b, control) × 10 seeds = 120/120 episodes, 0
  failures, $16.24 of $30. 10 episodes excluded by the pre-registered
  cp-invalid rule (all gpt-oss). Total real-model spend: $20.88 + smoke ≈ $21.9
  of the $45 cap.
- **Step E (results) — DONE.** `RESULTS_FIRST_TRIAL.md` written for teammates
  who haven't read the specs; charts in `asymbench/reports/first_trial/`
  (`tools/export_charts.py`). Headlines: recognition gap +0.51 [0.39, 0.63];
  harm shift +0.15 [0.09, 0.22]; advantage captured +0.10 [0.03, 0.20];
  attempt shift +0.34 [−0.03, 0.73] — and −0.23 [−0.60, +0.13] under the
  no-counterpart-misconduct sensitivity, i.e. excess deception is largely
  reactive. Eval-awareness 0.00. Five verified illustrative episodes cited
  (exploitation `0048`/`0012`, honesty `0105`, counterpart-breakdown harm
  `0009`, disclosure `0099`).

**Benchmark complete.** All three phases done; 236 offline tests passing.

## Post-trial: public dashboard + cost split (2026-11-10)

- **Per-provider cost tracking:** episodes now record `cost_anthropic` /
  `cost_openrouter` (exact split: every agent/survey call is a turn with its
  model; judge cost added to the judge's provider). Live per-run totals in
  `progress.cost_by_provider`; shown on the local Runs list and run header.
  Backfilled the three real runs (`tools/backfill_provider_costs.py`).
  Trial split: Claude $15.92 / OpenRouter $0.31. Tests: 238 passing.
- **Public results site** (team-shareable link, per the team lead's request —
  a standalone website, not a Claude artifact):
  https://miwi343.github.io/asymmetry-bench/ — static page
  (`asymbench/dashboard/index.html`) + `data.json`, deployed by
  `tools/deploy_dashboard.sh` to `Miwi343/asymmetry-bench` (live) and this
  repo's `gh-pages` branch (serves at
  cornelldatascience.github.io/multi-agent-coop once an org admin enables
  Pages — needs admin, my token has write only). Teammate test requests =
  prefilled GitHub issues (`[Test request]` + config JSON); the site lists
  them with status chips from issue state/labels. Workflow documented in
  README §Public dashboard.
- An earlier Claude-artifact version of the dashboard was published before the
  team lead asked for a real website instead; deleted on their confirmation
  (link permanently dead).
- **Recognition restructure (2026-11-14, team-lead decision):** one headline
  recognition measure, the **recognition score** (formerly survey_gap: blind
  post-episode 1–5 survey, control − weak; no judge involved). The old
  composite recognition_gap (detected ∨ survey ≤ 2) is gone; the judge channel
  survives as the **remark_gap** ("spontaneous remarks"), a non-headline
  corroboration check that also supplies the recognition turn. Per-episode
  `recognized` now means detected only. Renamed through metrics.py, server/
  export CSVs, local app, dashboard, spec §9, tests (239 passing); all five
  DB runs re-aggregated (first trial: recognition score +0.90, remark gap
  +0.014 — the old +0.51 was nearly all survey threshold). Known issue found
  on the way: `recompute --run` crashes on commons (JSON round-trip turns
  int dict keys into strings in `score()`); re-aggregation path used instead.
- **Metric definitions (2026-11-11):** the results tab now has a
  "How each score is calculated" methods section — one block per score with the
  exact formula (KaTeX, plain-text fallback), term definitions matching
  `metrics.py`/task code, per-task harm/advantage tables, and a
  what-it-answers paragraph with the latest run's value injected live. Every
  score number, column header and run-log label on the site deep-links to its
  block (`#results/<slug>` sub-anchors with a highlight flash).
