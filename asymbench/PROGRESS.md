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
