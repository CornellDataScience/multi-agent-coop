from __future__ import annotations

import argparse
import json
from pathlib import Path

from .experiments.configs import CONDITIONS, get_condition
from .experiments.metrics import aggregate, summarize_game
from .experiments.runner import run_condition


def _cmd_list(args: argparse.Namespace) -> int:
    for name, exp in sorted(CONDITIONS.items()):
        kinds = sorted({s.get("type", "scripted") for s in exp.agent_specs})
        comm = "broadcast" if exp.game.communication else "no-comm"
        print(f"{name:24s} agents={','.join(kinds):10s} {comm:10s} seeds={len(exp.seeds)}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    exp = get_condition(args.condition)
    seeds = list(range(args.seeds)) if args.seeds is not None else None
    paths = run_condition(
        exp,
        out_dir=args.out,
        model_override=args.model,
        seeds=seeds,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="infocoop", description="Fisherman's Dilemma harness")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list available conditions").set_defaults(func=_cmd_list)

    p_run = sub.add_parser("run", help="run a condition over its seeds")
    p_run.add_argument("condition", choices=sorted(CONDITIONS))
    p_run.add_argument("--seeds", type=int, default=None, help="override: run seeds 0..N-1")
    p_run.add_argument("--model", default=None, help="override LLM model id")
    p_run.add_argument("--out", default="results", help="output directory")
    p_run.add_argument("--no-metrics", action="store_true", help="skip metrics summary")
    p_run.set_defaults(func=_cmd_run)

    p_m = sub.add_parser("metrics", help="compute metrics for a game file or directory")
    p_m.add_argument("path")
    p_m.set_defaults(func=_cmd_metrics)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
