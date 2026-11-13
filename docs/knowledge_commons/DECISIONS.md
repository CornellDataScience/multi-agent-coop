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
| 2026-11-13 | 2 | `forgiveness_lag`: every lie j -> i is its own event; lag = rounds until i next sends j the truth; reported as mean over uncensored events plus `n_events` / `n_censored` | Simplest reading of SPEC §8; censoring stays visible |
| 2026-11-13 | 2 | `reciprocity` and rate metrics are `None` (not 0) when a conditioning case never occurs | Avoid inventing a value from zero observations |
| 2026-11-13 | 2 | `uptake` counts a received digit as used iff the guess has that digit in the sender's position; "prior liar" = lied to this agent in an earlier round | Direct reading of SPEC §8 from logged data only |
| 2026-11-13 | 2 | Model calls are inferred from `parse_status` (ok = 1, retry_ok / fallback = 2); halves split at `rounds // 2`; bootstrap is the percentile CI of the mean | Logs record status, not attempt counts; standard, stdlib-only choices |
| 2026-11-13 | 2 | Aggregates group per-agent metrics by label: scripted policy, else model | Lets probe conditions (E4) compare the LLM against each opponent type |
