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
| 2026-11-13 | 3 | `no_memory` prompts omit the round number and the history section | SPEC §5: "each round is presented as if it were the first" |
| 2026-11-13 | 3 | Retry resends the identical prompt (no error feedback) | Matches Fisherman; keeps the one-retry rule simple |
| 2026-11-13 | 3 | Parsing accepts digit strings ("7") and integral floats (7.0); a missing or invalid `confidence` becomes `None` instead of failing the guess | Confidence is optional and only feeds calibration; avoids fallbacks over formatting |
| 2026-11-13 | 3 | JSON is found by scanning every `{` with `raw_decode` and taking the first object with the expected key | JSON inside prose or code fences parses; stray braces don't break it |
| 2026-11-13 | 3 | Prompts state the history without annotating which received digits were false; agents compare against the revealed code themselves | SPEC §5 says agents can "check who lied"; labeling would add framing |
| 2026-11-13 | 3 | Agent type in the log comes from the backend class (claude / ollama / mock) | One `KCLLMAgent` serves every backend |
| 2026-11-13 | 4 | `kc_llm` and probes default to `claude-haiku-5-5` at effort `medium` (Haiku's default), no server-side fallbacks (not supported on Haiku) | SPEC §9 uses Haiku for E1-E4 |
| 2026-11-13 | 4 | `--model`: `mock` -> network-free mock, `claude-*` -> Claude API, anything else -> Ollama (seed = game_seed * 1000 + agent_id) | One flag covers all backends; mirrors Fisherman's Ollama seeding |
| 2026-11-13 | 4 | `--agents N` keeps the first spec and repeats the rest cyclically | Probe conditions keep exactly one LLM at agent 0 |
| 2026-11-13 | 4 | `--max-calls` counts every backend call (retries included) across the whole run; the game in progress is dropped, completed games are kept, exit code 0 | "Aborts cleanly, writing completed games" (ARCHITECTURE §3.9) |
| 2026-11-13 | 4 | Mock model (`agents/mock.py`) reads only the prompt, shares truthfully ~70%, withholds ~15%, lies ~15%, emits junk ~3% and prose-wrapped JSON ~5%; reports usage as chars/4 | Exercises parsing, retries, and cost plumbing end to end with no network |
| 2026-11-13 | 4 | KC CLI lives in `src/knowledge_commons/cli.py`; `src/main.py` only adds one import and one `add_kc_parser(sub)` call | Smallest change to a shared file (ARCHITECTURE §2 allows the `kc` group) |
| 2026-11-13 | 4 | `bonus_threshold` is not rescaled when `--agents` changes; an invalid combination exits with an error | Don't silently change game rules |
| 2026-11-13 | 4 | Default output dir `results/kc` (gitignored via `results/`) | Matches PHASES.md Phase 6 report command |
| 2026-11-13 | 5 | Report groups by (condition, model, alpha, info_condition, prompt_variant); each group also carries `flow_by_round`, `files`, and `std` | Spec keys plus prompt, so wording variants never merge; extras feed charts |
| 2026-11-13 | 5 | Groups with LLM agents get `llm_*` metrics: per-agent metrics averaged over a game's non-scripted agents, then CI'd across games | Probe conditions (E4) are about the LLM, not its scripted opponents |
| 2026-11-13 | 5 | Episodes: one "first lie" and one "largest drop" per game, plus the first round each agent is shut out by all others; LLM games listed first, capped at 40 | Keeps the list readable when scripted lineups repeat the same event every round |
| 2026-11-13 | 5 | Charts use the dataviz reference palette in fixed slot order, two panels instead of a dual axis, hatching on the behavior mix; non-scripted groups are plotted (all groups if there are none); missing data draws an empty panel with a note so all 4 PNGs always exist | Readable without color; gate expects 4 files |
| 2026-11-13 | 5 | `kc report --out` defaults to `docs/knowledge_commons/report`; RESULTS.md is written there, not to `docs/knowledge_commons/RESULTS.md` | ARCHITECTURE §3.10 puts RESULTS.md in `--out`; real results come in Phase 6 |
| 2026-11-13 | Review | Under `public_reputation`, comparing reputation from one round to the next can reveal past sends between other pairs; accepted, no code change. Firewall guarantee is scoped to the current round (SPEC §5, ARCHITECTURE §4.3) | The code is revealed every round, so past sends are public ground truth by design in this condition |
| 2026-11-13 | Review | `KCObservation.round` is `None` under `no_memory` | SPEC §5 "as if it were the first"; the prompt already hid it, now the observation does too |
| 2026-11-13 | Review | The log stores deep copies of observations (taken before the agent acts) and of sanitized actions | An agent holding a reference could otherwise rewrite logged ground truth |
| 2026-11-13 | Review | Rules text says "The digit you send can be your real digit or any other digit" | States the option without singling out sending a false digit |
| 2026-11-13 | Review | `tests/kc/conftest.py` blocks `socket` and the real Claude/Ollama client functions for every KC test | Makes invariant 8 enforced, not a convention |
| 2026-11-13 | Review | `CLAUDE.md` and `.claude/settings.json` added to ARCHITECTURE §2's allowed files | They were added outside the list without a note |
