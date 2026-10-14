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
.venv/bin/pip install -e ".[dev]"      # dev: adds pytest
.venv/bin/pip install -e ".[dev,llm]"  # also installs the ollama client
```

> **Note (Homebrew Python):** Homebrew's `sitecustomize.py` rewrites `sys.path`
> and can stop pip's editable `__editable__*.pth` from loading, so the
> `infocoop` console script may fail to import. If so, either install normally
> (`pip install .`) or run via the module with `PYTHONPATH`:
> `PYTHONPATH=src .venv/bin/python -m infocoop.main ...`. Tests are unaffected
> (pytest adds `src` itself).

## Run

```bash
infocoop list                         # show conditions
infocoop run all_sustainable          # a deterministic scripted sanity check
infocoop run one_defector             # greedy liar among sustainable honest agents
infocoop run broadcast_unverified --seeds 5 --model llama3.1:8b   # LLM (needs Ollama)
infocoop metrics results/             # aggregate metrics over a directory of games
```

Equivalently: `python -m infocoop.main <args>`.

LLM conditions need a running [Ollama](https://ollama.com) with the chosen model
pulled. Scripted conditions need no LLM and are fully deterministic.

## Conditions (`src/infocoop/experiments/configs.py`)

| Condition | Agents | Comm. | Purpose |
|---|---|---|---|
| `broadcast_unverified` | LLM ×3 | broadcast | **Main condition** |
| `baseline_nocomm` | LLM ×3 | none | No-communication control |
| `all_greedy` / `all_sustainable` / `all_honest` / `all_lie` | scripted | broadcast | Environment + metric validation |
| `one_defector` | scripted | broadcast | Greedy under-reporter vs. sustainable honest |

## Layout

```
src/infocoop/
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
