"""Human-readable round-by-round view of a Knowledge Commons log."""
from __future__ import annotations

from pathlib import Path

from .log import load_game
from .metrics import dyad_kinds, summarize_game

_MARK = {"truthful": "", "withheld": "", "lie": " LIE"}


def _digits(seq) -> str:
    return " ".join(str(d) for d in seq)


def format_game(path: str | Path, raw: bool = False) -> str:
    """One block per round: the code, each agent's sends (``--`` = sent
    nothing, ``LIE`` = false digit), guesses, and points. ``raw=True`` adds
    each model's raw output for both phases (and the quiz). Optional model
    reasons and pre-game quiz results are always shown."""
    game = load_game(path)
    meta, rounds = game["meta"], game["rounds"]
    cfg = meta["config"]
    s = summarize_game(path)
    agents = {a["id"]: a for a in meta.get("agents", [])}
    lines = [
        f"=== {Path(path).name}",
        f"condition {meta['condition']} | seed {meta['seed']} | alpha {cfg['alpha']} | "
        f"info {cfg['info_condition']} | pot {cfg['pot_size']:g} | "
        f"{'withholding allowed' if cfg['allow_withhold'] else 'must send'} | model {s['model']}",
        "agents: " + ", ".join(
            f"{i}={agents.get(i, {}).get('policy') or agents.get(i, {}).get('model') or '?'}"
            for i in range(cfg["n_agents"])),
    ]
    for i, q in sorted((game.get("comprehension") or {}).items()):
        a = q.get("answers")
        got = (f"{a['q1_direction']} {a['q1_amount']:g}, {a['q2_amount']:g}, "
               f"{a['q3_all_amount']:g}/{a['q3_fewer_amount']:g}" if a else "no valid answer")
        exp = q["expected"]
        lines.append(f"  quiz agent {i}: {'PASS' if q['passed'] else 'FAIL'} [{q['parse_status']}]"
                     f" | answered {got} | expected {exp['q1_direction']} "
                     f"{abs(exp['q1_change']):g}, {exp['q2_change']:g}, "
                     f"{exp['q3_all_share']:g}/{exp['q3_fewer_share']:g}")
        if raw and q.get("raw_output") is not None:
            lines.append(f"    raw quiz: {q['raw_output'].strip()}")
    for r in rounds:
        kinds = dyad_kinds(r)
        lines.append(f"  round {r['round']}: code {_digits(r['code'])} | solvers {r['n_solvers']}"
                     f" | bonus {'yes' if r['bonus'] else 'no'}")
        for i in sorted(r["sends"]):
            cells = []
            for j, d in sorted(r["sends"][i].items()):
                cells.append(f"{j}:{'--' if d is None else d}{_MARK[kinds[(i, j)]]}")
            conf = r.get("confidence", {}).get(i)
            lines.append(
                f"    agent {i} sends [{', '.join(cells)}] | guess {_digits(r['guesses'][i])}"
                f" {'OK' if r['solved'][i] else 'x '} | +{r['points'][i]:g}"
                + (f" | conf {conf:.2f}" if conf is not None else "")
            )
            for phase in ("message", "guess"):
                why = r.get("actions", {}).get(phase, {}).get(i, {}).get("reason")
                if why:
                    lines.append(f"      why {phase}: {why}")
            if raw:
                for phase in ("message", "guess"):
                    act = r.get("actions", {}).get(phase, {}).get(i, {})
                    if act.get("raw_output") is not None:
                        lines.append(f"      raw {phase} [{act.get('parse_status')}]: "
                                     f"{act['raw_output'].strip()}")
    end = game["end"] or {}
    if end:
        lines.append("  totals: " + ", ".join(f"{i}={p:g}" for i, p in sorted(end["totals"].items())))
        lines.append("  scores: " + ", ".join(f"{i}={u:.2f}" for i, u in sorted(end["utilities"].items())))
    g = s["game"]
    lines.append(f"  information flow {g['information_flow']:.2f} | bonus rate {g['bonus_rate']:.2f}"
                 f" | efficiency {g['efficiency']:.2f}")
    return "\n".join(lines)
