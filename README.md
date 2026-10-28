# Fisherman's Dilemma

An N-agent repeated common-pool resource game for studying whether LLM agents
**lie** when broadcasting private takes under self-interested objectives, and how
that affects individual and collective outcomes.

- Full behavioral spec: [`specs.md`](specs.md)
- Engineering contract / design decisions: [`IMPLEMENTATION_PROMPT.md`](IMPLEMENTATION_PROMPT.md)

Each round, every agent privately chooses how many fish to take from a shared
pool; the remainder doubles. Agents also **broadcast a claimed take** (the main
condition) that is not verified against the truth. The environment owns all
ground truth; metrics are computed only from saved logs.

## Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"      # dev: adds pytest
.venv/bin/python -m pip install -e ".[dev,llm]"  # also installs the ollama client
```

Run commands from the repository root. The source tree is a `src` package, so
invoke the CLI as `src.main`; the project folder name (`multi-agent-coop`) does
not affect the module path.

## Run

```bash
.venv/bin/python -m src.main list                         # show conditions
.venv/bin/python -m src.main run all_sustainable          # deterministic scripted sanity check
.venv/bin/python -m src.main run one_defector             # greedy liar among sustainable honest agents
.venv/bin/python -m src.main run broadcast_unverified --seeds 5 --model llama3.1:8b  # LLM (needs Ollama)
.venv/bin/python -m src.main metrics results/             # aggregate metrics over a directory of games
.venv/bin/python -m src.main show results/                # round-by-round view of every game (add --raw for model output)
```

Equivalently, with the virtual environment activated: `python -m src.main <args>`.

LLM conditions need a running [Ollama](https://ollama.com) with the chosen model
pulled. Scripted conditions need no LLM and are fully deterministic.

### Prompt variants

LLM prompt wording lives in [`src/agents/prompt_variants.py`](src/agents/prompt_variants.py)
as named variants (default: `neutral`). Add a variant there, then select it with
`--prompt <name>`. The variant is recorded in each game's meta record, and
non-default variants are added to the output filename
(e.g. `broadcast_unverified_community_seed0.jsonl`).

## Conditions (`src/experiments/configs.py`)

| Condition | Agents | Comm. | Purpose |
|---|---|---|---|
| `broadcast_unverified` | LLM ×3 | broadcast | **Main condition** |
| `baseline_nocomm` | LLM ×3 | none | No-communication control |
| `all_greedy` / `all_sustainable` / `all_honest` / `all_lie` | scripted | broadcast | Environment + metric validation |
| `one_defector` | scripted | broadcast | Greedy under-reporter vs. sustainable honest |

## Layout

```
src/
├── game/          # config, state, events, payoff (overdraw), environment (round loop)
├── information/   # log (JSONL ground truth) + observation builder (the only log→agent path)
├── agents/        # base, scripted, llm (Ollama), prompts, parsing
├── experiments/   # configs (conditions), runner, metrics
└── main.py        # CLI
tests/             # environment, payoff, metrics, observation, parsing, llm, runner
results/           # per-game JSONL (gitignored)
```

## Tests

```bash
.venv/bin/pytest -q
```

Covers the conservation/growth/termination invariants, the information firewall
(agents never see others' true takes, no horizon leak), overdraw apportionment,
parsing retry/fallback, and metrics on hand-checked golden games.
```
