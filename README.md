# Fisherman's Dilemma

An N-agent repeated common-pool resource game for studying whether LLM agents'
**stated plans diverge from their private actions** under self-interested
objectives, and how that affects individual and collective outcomes.

- Full behavioral spec: [`specs.md`](specs.md)
- Engineering contract / design decisions: [`IMPLEMENTATION_PROMPT.md`](IMPLEMENTATION_PROMPT.md)

Each round has two decision stages. First, each agent simultaneously makes a
public announcement and a private take; that first take is uncounted and does
not change the pool. Agents then see the first announcements, decide whether
to revise, and simultaneously make a second announcement and final take. The
final take is scored and is the only take subject to the overdraw rule. The
remainder doubles to form the next round's pool. Announcements are never
verified against the real takes. The environment owns all ground truth;
metrics are computed only from saved logs.

## Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"          # development tools
.venv/bin/python -m pip install -e ".[dev,llm]"      # Ollama backend
.venv/bin/python -m pip install -e ".[dev,claude]"   # Claude API backend
```

Run the commands below from the repository root. Run commands from the repository root with `.venv/bin/python -m src.main`.

## Terminal guide

### 1. See available conditions and options

```bash
.venv/bin/python -m src.main --help
.venv/bin/python -m src.main conditions
.venv/bin/python -m src.main run --help
```

`conditions` lists the built-in experiment conditions. Each `run` takes one
condition name, then optional model and game settings. Unspecified options use
the condition or game defaults.

The separate Keynesian beauty contest can be run with:

```bash
.venv/bin/python -m src.main beauty-contest --pick 50
```

This runs five fixed-pick baseline agents for ten rounds. To use five Ollama
players instead, install the optional backend, start Ollama, pull a model, and
pass its model ID:

```bash
.venv/bin/python -m pip install -e ".[llm]"
ollama pull qwen3:8b
.venv/bin/python -m src.main beauty-contest --model qwen3:8b --temperature 0.7
```

All five agents use the selected model, with separate reproducible seeds. The
model ID, temperature, picks, targets, and scores are saved in the JSONL log.
The game engine is also available as `BeautyContestGame` for custom agents.

### 2. Run a condition

Start with a deterministic scripted condition to inspect the game mechanics:

```bash
.venv/bin/python -m src.main run all_sustainable
.venv/bin/python -m src.main run one_defector
```

For Ollama, install the `llm` extra, start Ollama, and pull a model. Then run
the main condition:

```bash
ollama pull llama3.1:8b
.venv/bin/python -m src.main run broadcast_unverified --model llama3.1:8b --seeds 5
```

The Claude condition uses the Claude API. Install the `claude` extra and set
`ANTHROPIC_API_KEY` in `.env` (see [`.env.example`](.env.example)):

```bash
.venv/bin/python -m src.main run broadcast_unverified_claude --model claude-sonnet-5-5 --seeds 5
```

### 3. Change run settings from the terminal

These options apply consistently to the model agents in the selected
condition, so you can compare runs without editing Python files:

| Option | Applies to | Example |
|---|---|---|
| `--model` | Ollama or Claude model ID | `--model qwen3:8b` |
| `--temperature` | Ollama sampling | `--temperature 0.2` |
| `--effort` | Claude reasoning effort | `--effort high` |
| `--prompt` | LLM prompt variant | `--prompt neutral_explained` |
| `--fallback-take` | fallback after invalid output | `--fallback-take 0` |
| `--seeds N` | number of games | `--seeds 5` |
| `--seed-start N` | first seed when `--seeds` is set | `--seeds 5 --seed-start 10` |
| `--agents` | group size; repeats the condition lineup | `--agents 4` |
| `--rounds` | round limit | `--rounds 8` |
| `--initial-pool` | starting pool | `--initial-pool 80` |
| `--growth-factor` | pool growth after each round | `--growth-factor 2` |
| `--pool-cap` | maximum pool size | `--pool-cap 10000` |
| `--out` | output directory | `--out results/qwen` |

For example, this runs five Qwen games with a lower sampling temperature and
a changed pool setup:

```bash
.venv/bin/python -m src.main run broadcast_unverified \
  --model qwen3:8b --temperature 0.2 --prompt neutral_explained \
  --seeds 5 --initial-pool 80 --rounds 8 --out results/qwen_explained
```

Each game is saved as JSONL. The filename includes the selected model, prompt,
and parameter overrides; the JSONL metadata records the game configuration
and explicit run overrides. Ollama calls use deterministic per-agent seeds
derived from each game seed. Claude responses are not seed-controlled.

### 4. Inspect and analyze results

```bash
.venv/bin/python -m src.main show results/qwen_explained/          # round-by-round replay
.venv/bin/python -m src.main show results/qwen_explained/ --raw     # include model responses
.venv/bin/python -m src.main metrics results/qwen_explained/        # aggregate across games
.venv/bin/python -m src.main metrics results/qwen_explained/<file>.jsonl  # one game
```

For this experiment, metrics distinguish first-announcement/first-take
divergence from the final announcement/final-take divergence, and also report
revision behavior, outcomes, pool sustainability, inequality, overdraw, and
invalid-output retries or fallbacks.

### Research metrics

`metrics <game.jsonl>` reports per-agent fish acquired, share and rank; how
often and by how much the first take diverges from the first announcement,
how often and by how much the final take diverges from the second
announcement (compared to the requested final take, before the overdraw rule,
since agents announce before overdraw is applied), under/over-shoot shares,
and how often agents choose to revise; plus game-level extraction, resource
sustainability, collapse, inequality, overdraw losses, and model-output
retry/fallback rates. Running `metrics <directory>` reports mean and standard
deviation across games.

### Prompt variants

LLM prompt wording lives in [`src/agents/prompt_variants.py`](src/agents/prompt_variants.py)
as named variants (default: `neutral`). Add a variant there, then select it with
`--prompt <name>`. The variant is recorded in each game's meta record, and
non-default variants are added to the output filename
(e.g. `broadcast_unverified_community_seed0.jsonl`).

## Conditions (`src/experiments/configs.py`)

| Condition | Agents | Purpose |
|---|---|---|
| `broadcast_unverified` | LLM ×3 | **Main condition** (Ollama) |
| `broadcast_unverified_claude` | Claude ×3 | Main condition via the Claude API |
| `all_greedy` / `all_sustainable` / `all_honest` / `all_lie` | scripted | Environment + metric validation |
| `one_defector` | scripted | Greedy under-reporter vs. sustainable honest |

Every condition uses the pre-announce-with-revision round structure (§3.1 of
`specs.md`); there is no no-communication control, since the mechanic requires
announcements to function at all.

## Layout

```
src/
├── game/          # config, state, events, payoff (overdraw), environment (round loop)
├── information/   # log (JSONL ground truth) + observation builder (the only log→agent path)
├── agents/        # base, scripted, llm (Ollama), claude, prompts, parsing
├── experiments/   # configs (conditions), runner, metrics
└── main.py        # CLI
tests/             # environment, payoff, metrics, observation, parsing, llm, claude, runner
results/           # per-game JSONL (gitignored)
```

## Tests

```bash
.venv/bin/pytest -q
```

Covers the conservation/growth/termination invariants, the information firewall
(agents never see another agent's true take or revision choice, no horizon
leak), overdraw apportionment (applied only to the final take), parsing
retry/fallback for both phases, and metrics on hand-checked golden games.
```
