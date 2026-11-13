"""``infocoop kc ...`` subcommands (ARCHITECTURE §3.9). ``src/main.py`` only
registers this group, so Fisherman's commands stay unchanged."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agents.prompt_variants import KC_VARIANTS
from .config import INFO_CONDITIONS
from .configs import KC_CONDITIONS, get_condition
from .metrics import aggregate, summarize_game
from .replay import format_game
from .runner import run_condition


def _files(path: str) -> list[Path]:
    target = Path(path)
    if target.is_dir():
        return sorted(target.glob("*.jsonl"))
    return [target] if target.is_file() else []


def _cmd_list(args) -> int:
    for name, c in sorted(KC_CONDITIONS.items()):
        kinds = ",".join(s.get("policy", s["type"]) for s in c.agent_specs)
        print(f"{name:26s} seeds={len(c.seeds):<3d} agents={kinds}")
    return 0


def _cmd_run(args) -> int:
    if args.seeds is not None and args.seeds < 1:
        raise SystemExit("--seeds must be at least 1")
    if args.seed_start < 0:
        raise SystemExit("--seed-start must be non-negative")
    if args.max_calls is not None and args.max_calls < 0:
        raise SystemExit("--max-calls must be non-negative")
    cond = get_condition(args.condition)
    seeds = list(range(args.seed_start, args.seed_start + args.seeds)) if args.seeds is not None else None
    try:
        res = run_condition(
            cond, args.out, model=args.model, seeds=seeds, prompt_variant=args.prompt,
            alpha=args.alpha, info=args.info, n_agents=args.agents, rounds=args.rounds,
            effort=args.effort, temperature=args.temperature, max_calls=args.max_calls,
        )
    except ValueError as exc:  # invalid config (e.g. alpha < 0, threshold > agents)
        raise SystemExit(f"invalid settings: {exc}")
    print(f"Ran '{cond.name}' -> {len(res.paths)} game(s) in {args.out}; {res.calls} model call(s)")
    for p in res.paths:
        print(f"  {p}")
    if res.aborted:
        print(f"Stopped early (--max-calls {args.max_calls}): {res.message}. Completed games were kept.")
    if res.paths and not args.no_metrics:
        print("\nAggregate metrics:")
        print(json.dumps(aggregate(res.paths)["game"], indent=2))
    return 0


def _cmd_metrics(args) -> int:
    files = _files(args.path)
    if not files:
        print(f"no .jsonl games found at {args.path}")
        return 1
    out = summarize_game(files[0]) if len(files) == 1 else aggregate(files)
    print(json.dumps(out, indent=2))
    return 0


def _cmd_show(args) -> int:
    files = _files(args.path)
    if not files:
        print(f"no .jsonl games found at {args.path}")
        return 1
    print("\n\n".join(format_game(f, raw=args.raw) for f in files))
    return 0


def add_kc_parser(sub) -> None:
    kc = sub.add_parser("kc", help="Knowledge Commons game (see docs/knowledge_commons)")
    ksub = kc.add_subparsers(dest="kc_command", required=True)

    p = ksub.add_parser("list", help="list Knowledge Commons conditions")
    p.set_defaults(func=_cmd_list)

    p = ksub.add_parser("run", help="run one condition over one or more seeds")
    p.add_argument("condition", choices=sorted(KC_CONDITIONS))
    p.add_argument("--model", help="model for LLM agents: 'mock', a claude-* ID, or an Ollama model")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="Claude effort")
    p.add_argument("--temperature", type=float, help="Ollama sampling temperature")
    p.add_argument("--prompt", choices=sorted(KC_VARIANTS), help="prompt wording variant")
    p.add_argument("--alpha", type=float, help="rivalry weight on others' points")
    p.add_argument("--info", choices=INFO_CONDITIONS, help="information condition")
    p.add_argument("--agents", type=int, help="number of agents")
    p.add_argument("--rounds", type=int, help="rounds per game (never shown to agents)")
    p.add_argument("--seeds", type=int, help="number of seeds (default: condition setting)")
    p.add_argument("--seed-start", type=int, default=0, help="first seed when --seeds is set")
    p.add_argument("--max-calls", type=int, help="stop cleanly after this many model calls")
    p.add_argument("--out", default="results/kc", help="directory for JSONL logs")
    p.add_argument("--no-metrics", action="store_true", help="skip the post-run metrics summary")
    p.set_defaults(func=_cmd_run)

    p = ksub.add_parser("show", help="round-by-round view of a game file or directory")
    p.add_argument("path")
    p.add_argument("--raw", action="store_true", help="also print raw model output")
    p.set_defaults(func=_cmd_show)

    p = ksub.add_parser("metrics", help="metrics for a game file, or aggregate over a directory")
    p.add_argument("path")
    p.set_defaults(func=_cmd_metrics)
