# CLAUDE.md

Repo for the Multi Agent Co-op project (Cornell Data Science): LLM agents in
repeated social dilemmas. Two games:

- **Fisherman's Dilemma** (existing): `src/game`, `src/information`,
  `src/agents`, `src/experiments`. Docs: `specs.md`, `IMPLEMENTATION_PROMPT.md`.
- **Knowledge Commons** (in progress): `src/knowledge_commons`. Docs:
  `docs/knowledge_commons/` (SPEC, ARCHITECTURE, PHASES, DECISIONS).

## Commands

```bash
.venv/bin/pytest -q                      # full suite, must stay green
.venv/bin/pytest -q tests/kc             # Knowledge Commons tests only
.venv/bin/infocoop --help
.venv/bin/infocoop kc --help             # after Phase 4
```

## Working on Knowledge Commons

1. Before coding, read `docs/knowledge_commons/SPEC.md`, `ARCHITECTURE.md`,
   `PHASES.md`, and `DECISIONS.md`.
2. Do **only the phase you were asked for**. Stop at its gate and report:
   files changed, test results, decisions logged. Do not start the next phase.
3. Plan before implementing. Write the phase's tests first where the phase
   lists them.
4. If the spec is ambiguous, pick the simplest option consistent with it and
   add a row to `DECISIONS.md`. Do not silently change rules in SPEC.md; if a
   rule seems wrong, say so in your report.

## Hard rules

- **Git: work only on the `knowledge-commons` branch.** Never commit to,
  merge into, or push `main`. Never force-push. Don't push at all unless the
  user asks in that message; the change goes to main only through a reviewed PR.

- **No network in tests.** Mock every model call (`chat_fn` or `MockBackend`).
  Never make real API calls unless the user explicitly asks in that message.
- **Don't break Fisherman.** Existing test files must pass without edits. Only
  touch files outside `src/knowledge_commons/` that ARCHITECTURE §2 allows.
- **Firewall.** Agents get information only through `observation.py`. Never
  pass the code, the log, or other agents' private actions to an agent or
  into a prompt any other way.
- **Prompts are neutral.** Never instruct agents to be honest, cooperate, or
  lie. Never reveal the round limit.
- **Metrics come from saved JSONL only**, never live objects or model calls.
- **Determinism.** All randomness in the engine comes from the seeded
  per-game RNG.
- Standard library plus existing deps only. `matplotlib` only behind the
  `viz` extra, imported lazily.
- Match the existing style: `from __future__ import annotations`, dataclasses,
  type hints, short docstrings that explain why, no new frameworks.
