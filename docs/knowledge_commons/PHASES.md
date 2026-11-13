# Knowledge Commons: Build Phases

Build in this order. **One phase per Claude Code session.** Each phase ends at
a gate: every listed check passes and the session stops and reports. Do not
start the next phase in the same session.

Before every phase, the session reads: `CLAUDE.md`, `SPEC.md`,
`ARCHITECTURE.md`, `DECISIONS.md`, and this file.

Setup once:

```bash
git checkout knowledge-commons      # branch already exists; never work on main
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,claude]"
.venv/bin/pytest -q          # baseline: note how many tests pass now
```

---

## Phase 0: Shared backends (no game code yet) [DONE, commit f0c75c0]

**Build:** `src/agents/backends.py` with `ChatResult`, `ClaudeBackend`,
`OllamaBackend`, `MockBackend` (ARCHITECTURE §3.1). Make `ClaudeAgent._call`
and `OllamaAgent._call` delegate to them. Capture `usage` from Claude
responses (`resp.usage.input_tokens` / `output_tokens`) and Ollama responses
(`prompt_eval_count` / `eval_count`) when present.

**Tests:** `tests/kc/test_backends.py`: mocked Claude response with usage,
refusal flagged, thinking blocks skipped, Ollama mock, MockBackend.

**Gate:**
- [ ] Every pre-existing test passes with zero edits to existing test files
- [ ] New backend tests pass
- [ ] `git diff --stat` touches only the files allowed in ARCHITECTURE §2

**Prompt:**
> Read CLAUDE.md and docs/knowledge_commons/{SPEC,ARCHITECTURE,PHASES,DECISIONS}.md.
> Do Phase 0 only. Plan first, then implement, then run the full test suite.
> Stop at the gate and report: files changed, test counts before/after, and
> any decisions you logged.

---

## Phase 1: Engine, firewall, scripted agents

**Build:** `config.py`, `events.py`, `scoring.py`, `observation.py`,
`environment.py`, `log.py`, `agents/base.py`, `agents/scripted.py`.

**Tests (minimum):**
- Config validation rejects bad values
- `classify_send`, `round_points`, `utilities` on hand-checked numbers
- Invariant 1: same seed gives same codes across different lineups/alphas
- Invariant 2: a spy agent records the order of calls; all message obs built
  before any message action
- Invariant 3: a spy agent asserts its observations never contain other
  digits, other pairs' sends, others' guesses or points, or `max_rounds`;
  `no_memory` history is empty
- Invariant 4: reputation rates match an independent recomputation
- Log round-trip: `write_jsonl` then `load_game` gives identical records
- Each scripted policy behaves as in SPEC §7 (one test each)

**Golden games (put these in tests exactly):**
Lineup `[honest, honest, honest, hoarder]`, alpha 0.5, R=10, B=10, T=3.
- codes `[(1,2,3,4), (5,6,7,8)]`: agents 0-2 lack digit 3 and guess 0, so they
  fail; agent 3 solves both rounds; no bonus. Totals `{0:0, 1:0, 2:0, 3:20}`.
  Utilities: agent 3 = 20.0, agents 0-2 = 0 - 0.5 * 20/3 = -3.333...
- codes `[(1,2,3,0)]`: the hoarder's digit is 0, so the honest agents' default
  fill is right; all 4 solve, bonus triggers, everyone gets 20.

**Gate:**
- [ ] `pytest -q` all green (old + new)
- [ ] A tiny script or test runs a full 8-round all-`honest` game: information
      flow 1.0, every agent solves every round

**Prompt:**
> Read CLAUDE.md and the docs. Do Phase 1 only. Write the invariant tests and
> golden games first, watch them fail, then implement until they pass. Stop at
> the gate and report.

---

## Phase 2: Metrics and replay

**Build:** `metrics.py` (SPEC §8, from JSONL only), aggregate with seeded
bootstrap CIs (stdlib `random`, 2000 resamples, seed 0), `replay.py`.

**Tests:** golden-game metrics computed by hand, e.g. for the first golden
game above: 24 dyad-rounds, 18 truthful, 6 withheld, information flow 0.75,
hoarder `withhold_rate` 1.0, honest agents `truthful_rate` 1.0, `bonus_rate`
0.0. Plus: reciprocity and forgiveness on a hand-built 4-round log with a
`reciprocator` and a `liar`.

**Gate:**
- [ ] `pytest -q` green
- [ ] Metrics on every E0 scripted lineup look right by inspection (paste them
      in the report)

**Prompt:**
> Do Phase 2 only. Compute every metric from saved JSONL, never from live
> objects. Hand-compute expected values for the golden logs in the test file
> with comments showing the arithmetic. Stop at the gate and report.

---

## Phase 3: LLM agent

**Build:** `agents/parsing.py`, `agents/prompts.py`,
`agents/prompt_variants.py` (variant `neutral`), `agents/llm.py`.

Prompt rules: state the rules, the payoff formula with the numeric alpha, the
agent's position and digit, history per info condition, and the JSON schema.
Never mention the round limit. Never tell the agent to be honest, cooperate,
or lie.

**Tests (all mocked):** valid outputs parse; JSON inside prose parses; wrong
recipients / digit 10 / wrong guess length / missing keys fail; one retry then
fallback exactly per SPEC §6; refusal counts as failure; usage summed across
attempts; prompt for `no_memory` contains no past rounds; no prompt contains
the round limit (render prompts for all three conditions and assert).

**Gate:**
- [ ] `pytest -q` green
- [ ] Print one rendered prompt per info condition into the report so a human
      can read them

**Prompt:**
> Do Phase 3 only. Mock every model call. Show me the three rendered prompts
> at the end so I can review the wording. Stop at the gate.

---

## Phase 4: Runner, conditions, CLI

**Build:** `configs.py`, `runner.py`, `kc` subcommands in `src/main.py`,
`--max-calls`, `--model mock`.

Conditions to define (SPEC §9): `kc_all_honest`, `kc_all_hoarder`,
`kc_reciprocators_vs_liar`, `kc_mixed_scripted`, `kc_llm` (4 LLM agents),
`kc_probe_honest` (1 LLM + 3 honest), `kc_probe_recip_liar` (1 LLM + 2
reciprocators + 1 liar), `kc_probe_grudgers` (1 LLM + 3 grudgers).

**Gate:**
- [ ] `pytest -q` green
- [ ] `infocoop kc run kc_llm --model mock --seeds 2` writes 2 logs and
      `infocoop kc metrics` reads them
- [ ] `--max-calls 10` stops cleanly
- [ ] **Human step:** run the E1 pilot (1 real Haiku game), check
      `infocoop kc show --raw`, and record calls and tokens in DECISIONS.md

**Prompt:**
> Do Phase 4 only. Do not make real API calls; use --model mock. When done,
> print the exact command I should run for the E1 pilot and stop.

---

## Phase 5: Report

**Build:** `report.py` and the `kc report` command (ARCHITECTURE §3.10). Add
the `viz` extra.

**Tests:** report on mock-generated logs produces valid `data.json` with the
documented keys; charts are skipped gracefully if matplotlib is missing.

**Gate:**
- [ ] `pytest -q` green
- [ ] `infocoop kc report` on mock logs writes `data.json`, `RESULTS.md`, and
      4 PNGs

---

## Phase 6: Experiments and PR (mostly human)

1. Run E0 (free), then E2, E3, E4, E5 within budget, using the pilot's token
   counts to size runs. Use `--max-calls` as a safety cap on every real run.
2. `infocoop kc report results/kc/* --out docs/knowledge_commons/report`.
3. Fresh Claude Code session for review:
   > Review the `knowledge-commons` branch against SPEC.md and
   > ARCHITECTURE.md. Check every invariant has a test, look for firewall
   > leaks in observation.py and prompts.py, and list anything that differs
   > from the spec. Do not fix anything yet; just report.
4. Fix what the review finds, then open the PR. PR description: the research
   question (2 sentences), what was built, the headline chart, the E2/E3
   tables, 2-3 episodes worth reading, cost, and open questions for the team.
