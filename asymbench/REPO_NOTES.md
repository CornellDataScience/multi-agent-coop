# Repo notes: existing fisherman benchmark (pre-Asymmetry Bench)

Survey of the code that was in the repo before `asymbench/` was added, and what was reused.
The existing package is `src/` (installed as `infocoop`), a 3-agent repeated common-pool
("fisherman's dilemma") game with a *pre-announce-with-revision* round structure.

## What each piece does

| File | What it does |
|---|---|
| `src/main.py` | CLI (`infocoop` / `python -m src.main`): `conditions`, `run`, `metrics`, `show`. Loads `.env` manually. |
| `src/game/config.py` | `GameConfig` dataclass: n_agents=3, max_rounds=10, initial_pool=100, growth_factor=2, optional pool_cap, proportional overdraw rule, unknown horizon. |
| `src/game/state.py` | Tiny mutable pool/round holder. |
| `src/game/environment.py` | Runs one game. Each round: phase 1 (simultaneous public first announcement + private uncounted first take), phase 2 (see everyone's first announcements, revise, second announcement + final take that counts). Pool doubles after harvest, optional cap. |
| `src/game/payoff.py` | `clamp`, and `apportion`: proportional largest-remainder split when total requested exceeds the pool. |
| `src/game/events.py` | Frozen dataclasses for first/second phase actions and `RoundResult` (full ground truth per round), with `to_dict`. |
| `src/information/observation.py` | `Observation` dataclass + builders. Information firewall: history carries own true takes and everyone's public announcements, never another agent's true take. |
| `src/information/log.py` | `GameLog`: meta + per-round records including every observation, JSONL writer/loader. Metrics only read saved logs. |
| `src/agents/base.py` | `Agent` ABC with `act_first` / `act_second`. |
| `src/agents/parsing.py` | Regex-extract first `{...}`, `json.loads`, strict typed field checks (`first_announcement`/`first_take`, `revise`/`second_announcement`/`final_take`). Raises `ParseError`. |
| `src/agents/llm.py` | `LLMAgent` base: prompt → call → parse with one retry then fallback action; `OllamaAgent` subclass. |
| `src/agents/claude.py` | `ClaudeAgent`: `anthropic` SDK via `client.beta.messages.create`, `output_config={"effort": ...}`, refusal counts as parse failure, optional server-side fallbacks, injectable `chat_fn` for tests. |
| `src/agents/prompts.py` / `prompt_variants.py` | Named prompt-wording variants (neutral default); placeholder filling; history rendering. |
| `src/agents/scripted.py` | Deterministic baselines: take policies (greedy/sustainable/fair) × claim policies (honest/underreport/always_lie). |
| `src/experiments/configs.py` | `ExperimentConfig` (game + agent lineup + seeds); built-in conditions incl. scripted sanity checks. |
| `src/experiments/runner.py` | `build_agent` + `run_condition`: one JSONL game per seed, filename tags for overrides. |
| `src/experiments/metrics.py` | Per-agent deviation metrics (announcement vs take gaps), personal and societal metrics (efficiency, gini, collapse, parse-fallback rates), aggregation across seeds. |
| `src/analysis/replay.py` | Round-by-round pretty-printer for a game file. |
| `tests/` | 65 passing tests for all of the above (no API keys needed; `chat_fn` injection for LLM paths). |
| `results/` | Tracked JSONL logs of past runs (gitignored going forward, existing ones kept). |

## What was reused in `asymbench/` (ideas, not code imports)

- **Parse-retry-fallback shape** (`llm.py`): the initial-try + one-retry + safe-default loop became
  `asymbench/agent.py::take_turn`, generalized to the spec's 5-step parsing ladder.
- **Injectable chat function for tests**: kept as a pattern — `asymbench` routes `mock/*` model ids
  to `mock.py` instead of the network, so the whole pipeline runs offline.
- **"Environment owns ground truth, metrics read logs"** separation: kept. Every asymbench task's
  environment logic is pure Python over scripted actions; model calls live only in `agent.py`/`providers.py`.
- **Largest-remainder apportionment** (`payoff.py`): not needed — the new T1 per-fisher cap
  (30% of pool, floor) means total requests can never exceed the pool.
- **Old T1 rules NOT reused** (per the implementation guide §2.3): the uncapped doubling and
  pre-announce-with-revision mechanics are replaced by the new commons rules
  (capacity 100, capped regrowth, per-fisher cap, hidden 12 rounds, rotating talk order).
- **Claude call details**: the old code used `beta.messages.create` with `output_config` effort;
  asymbench uses plain `messages.create` with `system` + one user message per the benchmark spec
  (no temperature, no tool use, text blocks only).

## Guardrails observed

- Nothing in `src/` or `tests/` (existing files) is modified. Existing commands
  (`infocoop run/metrics/show`, `python -m src.main ...`) and all 65 existing tests still work.
- New tests are named `tests/test_asym_*.py` to avoid module-name collisions with the
  existing `tests/test_parsing.py`, `test_metrics.py`, `test_runner.py`.
