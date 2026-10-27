from __future__ import annotations

from pathlib import Path

from ..experiments.metrics import summarize_game
from ..information.log import load_game


def format_game(path: str | Path, raw: bool = False) -> str:
    """Round-by-round text view of one game log.

    Per agent: what it asked for (true take), what it got after any overdraw
    split, and what it claimed. ``LIE`` marks claim != asked, matching the
    deception metrics. ``raw=True`` adds each agent's raw model output.
    """
    meta, rounds = load_game(path)
    lines = [
        f"=== {Path(path).name}",
        f"condition {meta['condition']} | seed {meta['seed']} | "
        f"prompt {meta.get('prompt_variant')} | start pool {meta['config']['initial_pool']}",
    ]
    for r in rounds:
        lines.append(
            f"  round {r['round']}: pool {r['pool_before']} -> {r['pool_after']} left "
            f"-> next {r['pool_next']}"
        )
        for i in sorted(r["takes"]):
            asked, got, claimed = r["takes"][i], r["granted"][i], r["claims"].get(i)
            cell = f"    agent {i}: asked {asked:>4}  got {got:>4}"
            if claimed is not None:
                cell += f"  claimed {claimed:>4}" + ("  LIE" if claimed != asked else "")
            action = r.get("actions", {}).get(i, {})
            if action.get("parse_status", "ok") != "ok":
                cell += f"  [{action['parse_status']}]"
            lines.append(cell)
            if raw and action.get("raw_output") is not None:
                lines.append(f"      raw: {action['raw_output'].strip()}")

    s = summarize_game(path)
    soc = s["societal"]
    fish = " / ".join(str(p["total_fish"]) for p in s["personal"].values())
    lies = sum(d["n_lies"] for d in s["deception"].values())
    end = (
        f"pool ran out in round {soc['collapse_round']}"
        if soc["collapse_round"] is not None
        else f"pool survived with {soc['pool_remaining_end']} fish"
    )
    lines.append(
        f"  -> {soc['rounds_played']} rounds, {end} | fish {fish} | "
        f"lies {lies} | gini {soc['gini']:.2f}"
    )
    return "\n".join(lines)
