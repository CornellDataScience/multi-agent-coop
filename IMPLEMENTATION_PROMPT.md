# Implementation Notes

This document records the repository's implementation boundaries. The game
rules and experiment semantics are defined in [`specs.md`](specs.md).

## Core boundaries

- `src/game/environment.py` owns all ground truth and runs the two decision
  phases. It resolves and scores only `final_take` values through
  `src/game/payoff.py`.
- Agents receive `Observation` objects from `src/information/observation.py`.
  The first observation contains prior rounds only. The second also contains
  every other agent's first announcement and the current agent's own first
  take and announcement. It never exposes another agent's actual take or
  revision choice.
- `src/information/log.py` stores the full record as JSONL. Analysis reads
  those saved records rather than live agent state.
- `src/agents/llm.py` owns Ollama calls and phase-specific parsing/retries;
  `src/agents/claude.py` supplies the Claude backend. Both use the same agent
  interface and prompt variants.
- `src/experiments/configs.py` defines built-in lineups. The CLI and
  `src/experiments/runner.py` apply run-level model, prompt, seed, and game
  parameter overrides.

## Invariants to preserve

1. First takes do not change the pool or scores. Only final takes are subject
   to proportional overdraw apportionment.
2. Granted fish plus the remaining pool equals the pool before final takes.
   The pool never becomes negative.
3. All agents choose within a phase from observations built before any action
   in that phase is resolved. No agent sees another agent's private take or
   revision choice.
4. The round limit is not included in agent observations or prompts.
5. Invalid model output is retried once, then replaced with the configured
   fallback and recorded in the log.
6. Metrics are reproducible from JSONL logs without calling a model.

## Running and extending

Use `infocoop run --help` for terminal options. Add a condition in
`src/experiments/configs.py` when the agent lineup or condition differs. Add a
prompt wording in `src/agents/prompt_variants.py` when only the wording
changes. Keep parameter changes in the CLI or `GameConfig` rather than
embedding experiment-specific behavior in the environment.

The test suite covers environment invariants, observation privacy, parsing,
metrics, and mocked model calls. Run it with `pytest -q` after implementation
changes.
