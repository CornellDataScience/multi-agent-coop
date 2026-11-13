# Knowledge Commons: Architecture Contract

This is the engineering contract for implementing `SPEC.md`. If the two ever
disagree, `SPEC.md` wins for game rules and this file wins for code layout.
Decisions made during implementation go in `DECISIONS.md`.

## 1. Layout

```
src/
├── agents/
│   └── backends.py            # NEW (Phase 0): shared Claude/Ollama call layer
└── knowledge_commons/         # NEW: everything game-specific lives here
    ├── __init__.py
    ├── config.py              # KCConfig dataclass + validation
    ├── events.py              # MessageAction, GuessAction, RoundRecord
    ├── scoring.py             # pure payoff functions
    ├── observation.py         # KCObservation + builders (the ONLY truth -> agent path)
    ├── environment.py         # round loop, owns the code and all ground truth
    ├── log.py                 # KCGameLog: JSONL write/load
    ├── agents/
    │   ├── __init__.py
    │   ├── base.py            # KCAgent ABC
    │   ├── scripted.py        # honest, hoarder, liar, reciprocator, grudger, excluder
    │   ├── parsing.py         # parse + validate model JSON, per phase
    │   ├── prompts.py         # builds system/user prompts from an observation
    │   ├── prompt_variants.py # named wording variants (default "neutral")
    │   └── llm.py             # KCLLMAgent: prompt -> backend -> parse, retry/fallback
    ├── configs.py             # named conditions (lineups + defaults)
    ├── runner.py              # run a condition over seeds, write logs
    ├── metrics.py             # per-game and aggregate metrics from logs
    ├── replay.py              # human-readable round-by-round view
    └── report.py              # data.json + RESULTS.md + charts
tests/kc/
    test_kc_config.py  test_kc_scoring.py  test_kc_environment.py
    test_kc_observation.py  test_kc_scripted.py  test_kc_parsing.py
    test_kc_llm_agent.py  test_kc_metrics.py  test_kc_runner.py
    test_kc_report.py  test_backends.py
docs/knowledge_commons/
    SPEC.md  ARCHITECTURE.md  PHASES.md  DECISIONS.md
    report/                    # `kc report` default --out (Phase 5):
                               # data.json, RESULTS.md, charts
```

Test files in `tests/kc/` use the `test_kc_` prefix so their basenames never
collide with the existing Fisherman tests.

## 2. Allowed changes outside `src/knowledge_commons/`

Only these. Anything else needs a note in `DECISIONS.md` and a reason.

| File | Change |
|---|---|
| `src/agents/backends.py` | New file (Phase 0) |
| `src/agents/claude.py`, `src/agents/llm.py` | `_call` delegates to `backends.py`. Public behavior unchanged |
| `src/main.py` | Add a `kc` subcommand group. Existing commands unchanged |
| `pyproject.toml` | Add optional extra `viz = ["matplotlib>=3.7"]` |
| `README.md` | Add a short "Knowledge Commons" section linking to the docs |
| `CLAUDE.md` | New file: working rules for coding agents on this repo |
| `.claude/settings.json` | New file: Claude Code project settings (no AI attribution in commits) |

**The existing Fisherman test files must pass without being edited.**

## 3. Interfaces

These signatures are the contract. Field names may gain extras, but these must
exist with these meanings.

### 3.1 Backends (Phase 0)

```python
# src/agents/backends.py
@dataclass
class ChatResult:
    text: str
    served_by: str | None
    usage: dict            # {"input_tokens": int, "output_tokens": int}; {} if unknown
    refused: bool = False

class ClaudeBackend:
    def __init__(self, model: str, effort: str = "medium",
                 fallbacks: bool = False, chat_fn: Callable | None = None): ...
    def __call__(self, system: str, prompt: str) -> ChatResult: ...

class OllamaBackend:
    def __init__(self, model: str, temperature: float = 0.7,
                 seed: int | None = None, chat_fn: Callable | None = None): ...
    def __call__(self, system: str, prompt: str) -> ChatResult: ...

class MockBackend:
    """Returns canned or callback-generated JSON. Used for end-to-end runs
    and tests with zero network. Selected with `--model mock`."""
```

`ClaudeAgent._call` / `OllamaAgent._call` become thin wrappers over these.
`chat_fn` injection keeps working exactly as today.

### 3.2 Config

```python
@dataclass(frozen=True)
class KCConfig:
    n_agents: int = 4
    max_rounds: int = 8
    reward_correct: int = 10
    group_bonus: int = 10
    bonus_threshold: int = 3
    alpha: float = 0.5
    info_condition: str = "private_memory"  # no_memory | private_memory | public_reputation
    horizon_known: bool = False              # v1: must be False
    seed: int = 0
    # code_length == n_agents; digits are 0-9
    def max_welfare(self) -> int: ...        # n_agents * (R + B) * max_rounds
```

Validate in `__post_init__`: `n_agents >= 2`, `1 <= bonus_threshold <= n_agents`,
`alpha >= 0`, known `info_condition`, `horizon_known is False`.

### 3.3 Events

```python
@dataclass
class MessageAction:
    sends: dict[int, int | None]   # recipient id -> digit or None; every other agent present
    raw_output: str | None = None
    parse_status: str = "scripted"  # scripted | ok | retry_ok | fallback
    served_by: str | None = None
    usage: dict = field(default_factory=dict)
    reason: str | None = None       # optional model "why", <= 200 chars

@dataclass
class GuessAction:
    guess: tuple[int, ...]          # length n_agents, each 0-9
    confidence: float | None = None
    raw_output: str | None = None
    parse_status: str = "scripted"
    served_by: str | None = None
    usage: dict = field(default_factory=dict)
    reason: str | None = None

@dataclass
class ComprehensionAction:          # pre-game quiz (SPEC §6)
    answers: dict | None            # parsed q1_direction / q1_amount / q2_amount; None if failed
    raw_output: str | None = None
    parse_status: str = "ok"        # ok | retry_ok | failed
    served_by: str | None = None
    usage: dict = field(default_factory=dict)

@dataclass
class RoundRecord:
    round: int
    code: tuple[int, ...]
    message_actions: dict[int, MessageAction]
    guess_actions: dict[int, GuessAction]
    solved: dict[int, bool]
    n_solvers: int
    bonus: bool
    points: dict[int, int]
```

### 3.4 Scoring (pure functions, no state)

```python
def classify_send(digit: int | None, true_digit: int) -> str  # "truthful" | "withheld" | "lie"
def round_points(solved: dict[int, bool], cfg: KCConfig) -> tuple[dict[int, int], int, bool]
def utilities(totals: dict[int, int], alpha: float) -> dict[int, float]
def comprehension_expected(alpha: float) -> dict   # correct quiz answers
def grade_comprehension(answers: dict | None, alpha: float) -> bool
```

### 3.5 Observation (the firewall)

```python
@dataclass(frozen=True)
class KCObservation:
    agent_id: int
    phase: str                       # "message" | "guess"
    round: int | None                # None under no_memory
    n_agents: int
    reward_correct: int; group_bonus: int; bonus_threshold: int; alpha: float
    info_condition: str
    my_position: int                 # == agent_id
    my_digit: int
    received: dict[int, int | None] | None   # guess phase only: sender -> digit
    history: list[dict]              # past rounds, filtered by info_condition
    reputation: dict[int, dict] | None       # public_reputation only

def build_message_obs(cfg, round_no, agent_id, code, past_rounds) -> KCObservation
def build_guess_obs(cfg, round_no, agent_id, code, past_rounds, sends_this_round) -> KCObservation

@dataclass(frozen=True)
class KCRulesObservation:            # comprehension check only: rules, no digit/round/history
    agent_id: int; n_agents: int
    reward_correct: int; group_bonus: int; bonus_threshold: int; alpha: float

def build_rules_obs(cfg, agent_id) -> KCRulesObservation
```

`history` entries for `private_memory` contain only: round number, the
revealed code, what this agent sent to each agent, what each agent sent to
this agent, this agent's guess, solved and points, `n_solvers`, `bonus`.

`reputation[j]` = `{"truthful": float, "withheld": float, "lie": float, "n": int}`
over all of `j`'s past dyad-rounds (all recipients).

There is no `max_rounds` field anywhere in the observation.

### 3.6 Agents

```python
class KCAgent(ABC):
    agent_id: int
    @abstractmethod
    def send_messages(self, obs: KCObservation) -> MessageAction: ...
    @abstractmethod
    def make_guess(self, obs: KCObservation) -> GuessAction: ...
    def comprehension_check(self, obs: KCRulesObservation) -> ComprehensionAction | None:
        return None                  # default: skip (scripted agents)
```

`KCLLMAgent.comprehension_check` makes one call with `build_quiz_prompts`
(same system prompt and rules as the game, plus the two questions), retries
once on bad JSON, and returns `parse_status = "failed"` after that. It keeps
no state from the quiz, so later game prompts are byte-identical to a run
without it. Agents return answers only; the environment grades them.

Both game phases parse an optional `reason` with `extract_reason`, which never
raises, so it cannot change `parse_status`.

`KCLLMAgent(agent_id, backend, prompt_variant="neutral")`: build prompts,
call backend, parse, retry once, fall back per SPEC §6. A refusal counts as a
parse failure. Usage from every attempt (including failed ones) is summed into
the action's `usage`.

Scripted agents may keep internal state, but only from observations they
received.

### 3.7 Environment

```python
class KCEnvironment:
    def __init__(self, cfg: KCConfig, agents: list[KCAgent], condition: str,
                 run_parameters: dict | None = None,
                 codes: list[tuple[int, ...]] | None = None,
                 comprehension: bool = True): ...
    def run(self) -> KCGameLog: ...
```

Before round 1, if `comprehension` is on, `run()` builds a
`KCRulesObservation` for every agent, collects `comprehension_check` results
(skipping `None`), grades them against `cfg.alpha`, and stores them in the log.

`codes` is for tests only: if given, it replaces the RNG draw so golden games
can be hand-computed. Per round: draw code from `random.Random(cfg.seed)` (one RNG per game, codes
drawn before any agent acts, so the code sequence depends only on the seed);
build ALL message observations, then collect all message actions; build ALL
guess observations, then collect all guesses; resolve with `scoring.py`;
append to the log.

Sanitize, do not crash, on scripted or fallback edge cases: ignore a send to
self, treat a missing recipient as `None`. LLM output is validated in
`parsing.py` before it ever reaches the environment.

### 3.8 Log format (JSONL)

```
{"record": "meta", "game": "knowledge_commons", "schema_version": 1,
 "condition": str, "seed": int, "config": {...KCConfig},
 "agents": [{"id": 0, "type": "claude", "model": str, "prompt_variant": str}, ...],
 "run_parameters": {...}}
{"record": "comprehension", "agent": 0, "observation": {...KCRulesObservation},
 "raw_output": str, "parse_status": "ok|retry_ok|failed", "served_by": str,
 "usage": {...}, "answers": {"q1_direction", "q1_amount", "q2_amount"} | null,
 "expected": {"q1_direction", "q1_change", "q2_change"}, "passed": bool}
                                     # one per LLM agent, none for scripted agents
{"record": "round", "round": 1, "code": [..],
 "sends": {"0": {"1": 7, "2": null, "3": 7}, ...},
 "guesses": {"0": [..], ...}, "confidence": {"0": 0.8 | null, ...},
 "solved": {"0": true, ...}, "n_solvers": 4, "bonus": true,
 "points": {"0": 20, ...},
 "actions": {"message": {"0": {"raw_output", "parse_status", "served_by", "usage", "reason"}},
             "guess":   {"0": {...}}},
 "observations": {"message": {"0": {...}}, "guess": {"0": {...}}}}
{"record": "end", "totals": {"0": int}, "utilities": {"0": float}}
```

JSON keys for agent ids are strings. `load_game()` converts them back to ints
and returns `{"meta", "comprehension", "rounds", "end"}`; `comprehension` is
`{agent_id: record}` (empty for logs written before the check existed).

### 3.9 CLI

```
infocoop kc list
infocoop kc run <condition> [--model M] [--effort E] [--temperature T]
                [--prompt V] [--alpha A] [--info no_memory|private_memory|public_reputation]
                [--agents N] [--rounds R] [--seeds N] [--seed-start S]
                [--max-calls N] [--out DIR]
infocoop kc show <file|dir> [--raw]
infocoop kc metrics <file|dir>
infocoop kc report <dir> [<dir> ...] --out docs/knowledge_commons/report
```

`--model mock` uses `MockBackend` (no network). `--max-calls` aborts cleanly
(writing completed games) once the run has made that many model calls. Output
filenames encode condition, model, alpha, info condition, prompt and seed, so
different runs never overwrite each other.

### 3.10 Report output

`report.py` writes into the `--out` directory:

- `data.json`: `{"generated_at", "groups": [{"condition", "model", "alpha",
  "info_condition", "n_games", "metrics": {name: {"mean", "lo", "hi", "n"}}}],
  "episodes": [{"file", "round", "why"}], "cost": {"calls", "input_tokens",
  "output_tokens"}}`. Same spirit as the gh-pages Asymmetry Bench `data.json`
  so it can become a dashboard tab later.
- `RESULTS.md`: tables of the main metrics per group with CIs.
- Charts (PNG, matplotlib, only if the `viz` extra is installed):
  1. `alpha_sweep.png`: information flow and bonus rate vs. alpha, one line
     per model
  2. `behavior_mix.png`: truthful / withheld / lie shares per alpha
  3. `info_conditions.png`: information flow by condition at alpha = 1
  4. `flow_over_rounds.png`: information flow per round

"Episodes worth reading" are picked automatically: first lie in a game,
largest single-round drop in information flow, any round where a single agent
was excluded by all others.

## 4. Invariants (each must have a test)

1. **Determinism of codes.** Same seed gives the same code sequence regardless
   of agents, alpha, or info condition.
2. **Simultaneity.** Within a phase, every observation is built before any
   action in that phase is collected. No agent's message depends on another's
   message in the same round.
3. **Firewall.** No observation ever contains another agent's digit before the
   reveal, messages between other pairs in the current round, other agents'
   guesses, other agents' points (beyond `n_solvers` and `bonus`), or
   `max_rounds`. `no_memory` observations have `round = None`, empty
   `history`, and no `reputation`. Under `public_reputation`, past rounds'
   sends are effectively public by design (the code is revealed each round,
   so differences in reputation between rounds can reveal who sent what); the
   guarantee is about the current round (SPEC §5). The log stores deep copies
   of observations and actions, so agents cannot change logged data.
4. **Reputation correctness.** Reputation rates equal rates computed
   independently from the log of earlier rounds.
5. **Scoring.** `points` match `round_points`; `end.utilities` match
   `utilities(totals, alpha)`. Hand-checked cases in tests.
6. **Parsing.** Invalid output is retried once, then replaced by the SPEC §6
   fallback and logged.
7. **Reproducible metrics.** Metrics are computed from JSONL alone, with no
   model calls and no live objects.
8. **No network in tests.** Every LLM test injects `chat_fn` or uses
   `MockBackend`. `tests/kc/conftest.py` blocks sockets and the real
   Claude/Ollama clients for every KC test.
9. **Fisherman untouched.** Existing tests pass unedited.
