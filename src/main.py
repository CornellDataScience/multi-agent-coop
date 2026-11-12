from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .agents.prompt_variants import VARIANTS
from .analysis.replay import format_game
from .experiments.configs import CONDITIONS, get_condition
from .experiments.metrics import aggregate, summarize_game
from .experiments.runner import run_condition
from .game.beauty_contest import BeautyContestGame, FixedPickAgent, OllamaBeautyContestAgent


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=value lines from .env into the environment (existing vars win)."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def _cmd_list(args: argparse.Namespace) -> int:
    for name, exp in sorted(CONDITIONS.items()):
        kinds = sorted({s.get("type", "scripted") for s in exp.agent_specs})
        print(f"{name:24s} agents={','.join(kinds):10s} seeds={len(exp.seeds)}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.seeds is not None and args.seeds < 1:
        raise SystemExit("--seeds must be at least 1")
    if args.seed_start < 0:
        raise SystemExit("--seed-start must be non-negative")
    if args.fallback_take is not None and args.fallback_take < 0:
        raise SystemExit("--fallback-take must be non-negative")
    if args.temperature is not None and args.temperature < 0:
        raise SystemExit("--temperature must be non-negative")
    exp = get_condition(args.condition)
    seeds = (
        list(range(args.seed_start, args.seed_start + args.seeds))
        if args.seeds is not None else None
    )
    paths = run_condition(
        exp,
        out_dir=args.out,
        model_override=args.model,
        seeds=seeds,
        prompt_variant=args.prompt,
        game_overrides={k: v for k, v in {
            "initial_pool": args.initial_pool,
            "max_rounds": args.rounds,
            "n_agents": args.agents,
            "growth_factor": args.growth_factor,
            "pool_cap": args.pool_cap,
        }.items() if v is not None},
        temperature=args.temperature,
        fallback_take=args.fallback_take,
        effort=args.effort,
    )
    print(f"Ran '{exp.name}' -> {len(paths)} game(s) in {args.out}")
    for p in paths:
        print(f"  {p}")
    if not args.no_metrics:
        print("\nAggregate metrics:")
        print(json.dumps(aggregate(paths), indent=2))
    return 0


def _cmd_metrics(args: argparse.Namespace) -> int:
    target = Path(args.path)
    files = sorted(target.glob("*.jsonl")) if target.is_dir() else [target]
    if not files:
        print(f"no .jsonl games found at {target}")
        return 1
    if len(files) == 1:
        print(json.dumps(summarize_game(files[0]), indent=2))
    else:
        print(json.dumps(aggregate(files), indent=2))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    target = Path(args.path)
    files = sorted(target.glob("*.jsonl")) if target.is_dir() else [target]
    if not files:
        print(f"no .jsonl games found at {target}")
        return 1
    print("\n\n".join(format_game(f, raw=args.raw) for f in files))
    return 0


def _cmd_beauty_contest(args: argparse.Namespace) -> int:
    game = BeautyContestGame()
    if args.model:
        agents = [OllamaBeautyContestAgent(
            i, args.model, temperature=args.temperature, seed=args.seed * 1000 + i
        ) for i in range(game.n_agents)]
    else:
        agents = [FixedPickAgent(i, args.pick) for i in range(game.n_agents)]
    def progress(round_no: int, agent_id: int) -> None:
        print(f"Round {round_no}/10: waiting for player {agent_id + 1}/5 model response...", flush=True)

    if args.model:
        print(f"Running 5 Ollama players with {args.model}; this requires 50 model responses.", flush=True)
    result = game.run(agents, seed=args.seed, progress=progress if args.model else None)
    result["meta"]["agents"] = "ollama" if args.model else "fixed_pick"
    result["meta"]["model"] = args.model
    result["meta"]["temperature"] = args.temperature if args.model else None
    path = game.write_jsonl(result, Path(args.out) / f"keynesian_beauty_contest_seed{args.seed}.jsonl")
    print(f"Ran {len(result['rounds'])} rounds -> {path}")
    totals = {i: 0 for i in result["total_points"]}
    print("\nRound results (player: pick / points / cumulative):")
    for rnd in result["rounds"]:
        cells = []
        for i in sorted(rnd["picks"]):
            totals[i] += rnd["points"][i]
            cells.append(f"P{i}: {rnd['picks'][i]} / +{rnd['points'][i]} / {totals[i]}")
        print(f"R{rnd['round']:>2}  target={rnd['target']:.2f}  " + " | ".join(cells))
    print(f"\nWinner: P{result['winner']} with {result['total_points'][result['winner']]} points")
    print("Final scores:")
    for i in result["final_ranking"]:
        print(f"  P{i}: {result['total_points'][i]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Run and analyze the Fisherman's Dilemma LLM experiments.",
        epilog="Run 'python -m src.main run --help' for model and game options.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("conditions", aliases=["list"], help="list available experiment conditions")
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser("run", help="run one condition over one or more seeds")
    p_run.add_argument("condition", choices=sorted(CONDITIONS))
    run_group = p_run.add_argument_group("run selection")
    run_group.add_argument("--seeds", type=int, help="number of seeds to run (default: condition setting)")
    run_group.add_argument("--seed-start", type=int, default=0, help="first seed when --seeds is set")
    run_group.add_argument("--out", default="results", help="directory for JSONL game logs")

    model_group = p_run.add_argument_group("model settings")
    model_group.add_argument("--model", help="model ID override (e.g. llama3.1:8b or claude-sonnet-5-5)")
    model_group.add_argument("--prompt", choices=sorted(VARIANTS), help="prompt wording variant")
    model_group.add_argument("--temperature", type=float, help="Ollama sampling temperature")
    model_group.add_argument("--effort", choices=["low", "medium", "high"], help="Claude reasoning effort")
    model_group.add_argument("--fallback-take", type=int, help="take used after invalid model output")

    game_group = p_run.add_argument_group("game settings")
    game_group.add_argument("--agents", type=int, help="number of agents; condition lineup repeats cyclically")
    game_group.add_argument("--rounds", type=int, help="maximum rounds (agents are not told this value)")
    game_group.add_argument("--initial-pool", type=int, help="fish in the pool at the start of the game")
    game_group.add_argument("--growth-factor", type=int, help="pool multiplier after each round")
    game_group.add_argument("--pool-cap", type=int, help="maximum pool size; default is no cap")

    p_run.add_argument("--no-metrics", action="store_true", help="skip the post-run metrics summary")
    p_run.set_defaults(func=_cmd_run)

    p_m = sub.add_parser("metrics", help="compute metrics for a game file or directory")
    p_m.add_argument("path")
    p_m.set_defaults(func=_cmd_metrics)

    p_s = sub.add_parser("show", help="round-by-round view of a game file or directory")
    p_s.add_argument("path")
    p_s.add_argument("--raw", action="store_true", help="also print each agent's raw model output")
    p_s.set_defaults(func=_cmd_show)

    p_b = sub.add_parser("beauty-contest", help="run a 5-agent Keynesian beauty contest")
    p_b.add_argument("--pick", type=int, default=50, help="fixed pick used by each baseline agent (1-100)")
    p_b.add_argument("--model", help="use this Ollama model for all five players (e.g. qwen3:8b)")
    p_b.add_argument("--temperature", type=float, default=0.7, help="Ollama sampling temperature")
    p_b.add_argument("--seed", type=int, default=0)
    p_b.add_argument("--out", default="results")
    p_b.set_defaults(func=_cmd_beauty_contest)

    return parser


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
