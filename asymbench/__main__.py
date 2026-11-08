"""CLI: python -m asymbench <command>. The CLI and the server share all logic;
runs started here appear in the UI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import db, export, runner
from .providers import check_openrouter_ids
from .settings import key_available, registry, runs_dir


def _load_config(path: str) -> dict:
    return json.loads(Path(path).read_text())


def cmd_serve(args) -> int:
    import uvicorn
    uvicorn.run("asymbench.server:app", host=args.host, port=args.port, log_level="info")
    return 0


def cmd_run(args) -> int:
    config = _load_config(args.config)

    async def go():
        est = runner.estimate(config)
        print(f"Estimate: {est['episodes']} episodes, ~{est['calls']} calls, "
              f"${est['cost_low']:.2f} to ${est['cost_high']:.2f} "
              f"(mid ${est['cost_mid']:.2f})")
        for w in est["warnings"]:
            print(f"  warning: {w}")
        run_id = await runner.create_run(config)
        print(f"Run {run_id} created; executing...")
        await runner.execute_run(run_id)
        run = db.get_run(run_id)
        print(f"Run {run_id} finished with status {run['status']}; "
              f"cost ${run['cost_usd']:.2f} of ${run['budget_usd']:.2f}; "
              f"progress {run['progress']}")
        print(f"Files: {runs_dir() / run_id}")
        return 0

    return asyncio.run(go())


def cmd_models(args) -> int:
    specs = registry()
    or_ids = [m.id for m in specs if m.provider == "openrouter"]
    availability: dict = {}
    if args.check and or_ids:
        try:
            availability = asyncio.run(check_openrouter_ids(or_ids))
        except Exception as exc:  # noqa: BLE001
            print(f"OpenRouter availability check failed: {exc}", file=sys.stderr)
    print(f"{'id':44s} {'provider':11s} {'tier':5s} {'$/M in':>7s} {'$/M out':>8s} "
          f"{'key':>4s} {'avail':>6s}")
    for m in specs:
        key = "yes" if key_available(m.provider) else "NO"
        if m.provider == "openrouter" and args.check:
            avail = "yes" if availability.get(m.id) else "NO"
        elif m.provider == "mock":
            avail = "mock"
        else:
            avail = "key" if key_available(m.provider) else "NO"
        print(f"{m.id:44s} {m.provider:11s} {m.tier:5s} {m.price_in:7.2f} "
              f"{m.price_out:8.2f} {key:>4s} {avail:>6s}")
    return 0


def cmd_rejudge(args) -> int:
    asyncio.run(runner.rejudge_run(args.run, args.judge))
    print(f"Re-judged run {args.run} with {args.judge}")
    return 0


def cmd_recompute(args) -> int:
    runner.recompute_run(args.run)
    print(f"Recomputed run {args.run}")
    return 0


def cmd_export(args) -> int:
    data = export.zip_run(args.run)
    out = Path(args.out) if args.out else Path(f"{args.run}.zip")
    out.write_bytes(data)
    print(f"Wrote {out} ({len(data)} bytes)")
    return 0


def cmd_estimate(args) -> int:
    est = runner.estimate(_load_config(args.config))
    print(json.dumps(est, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="asymbench", description="Asymmetry Bench")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("serve", help="start the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("run", help="run a config (same JSON as POST /api/runs)")
    s.add_argument("--config", required=True)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("models", help="list the registry and check availability")
    s.add_argument("--check", action="store_true")
    s.set_defaults(func=cmd_models)

    s = sub.add_parser("rejudge", help="re-judge a run from stored transcripts")
    s.add_argument("--run", required=True)
    s.add_argument("--judge", required=True)
    s.set_defaults(func=cmd_rejudge)

    s = sub.add_parser("recompute", help="recompute metrics and aggregates")
    s.add_argument("--run", required=True)
    s.set_defaults(func=cmd_recompute)

    s = sub.add_parser("export", help="write a run's ZIP")
    s.add_argument("--run", required=True)
    s.add_argument("--out")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("estimate", help="cost estimate for a config")
    s.add_argument("--config", required=True)
    s.set_defaults(func=cmd_estimate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
