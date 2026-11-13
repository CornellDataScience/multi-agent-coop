# Knowledge Commons: Decision Log

Record any choice the spec did not settle, one entry each:
date, phase, decision, why. Keep entries short.

| Date | Phase | Decision | Why |
|---|---|---|---|
| 2026-11-13 | Plan | Digits 0-9, claims only about own position, numbers-only messages | Keep v1 simple and lies exactly measurable |
| 2026-11-13 | Plan | Same seed gives the same codes across conditions | Paired comparisons across alpha and info conditions |
| 2026-11-13 | 0 | Backends return `ChatResult`; Fisherman agents store `last_usage` but do not log it yet | Keep Fisherman logs unchanged; KC logs usage per action |
| 2026-11-13 | 1 | Scripted agents remember only through `obs.history`; under `no_memory` reciprocator and grudger act as in round 1 | Keeps scripted agents inside the same firewall as LLM agents |
| 2026-11-13 | 1 | `excluder` default target is `(id + 1) % n`; configurable via `target` | Spec says "one fixed target" without naming it |
| 2026-11-13 | 1 | Reputation rates are 0.0 when an agent has no past dyad-rounds (`n = 0`) | Round 1 has no history; `n` tells readers the rates are empty |
| 2026-11-13 | 1 | All codes are drawn up front from `random.Random(seed)` | Code sequence depends only on the seed (invariant 1) |
| 2026-11-13 | 1 | Environment sanitizes scripted actions: non-digit sends become `None`; guesses are padded/truncated and non-digits become 0 | ARCHITECTURE §3.7 says sanitize, don't crash |
| 2026-11-13 | 1 | `load_game` returns `{"meta", "rounds", "end"}` and converts every all-digit-string-keyed dict to int keys, recursively | One rule covers sends, observations, history, and reputation |
