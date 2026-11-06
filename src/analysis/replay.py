from __future__ import annotations

from pathlib import Path

from ..experiments.metrics import summarize_game
from ..information.log import load_game


def format_game(path: str | Path, raw: bool = False) -> str:
    """Round-by-round text view of one game log.

    Per agent: the first announcement/take, the revision choice, the second
    announcement/final take (requested, before overdraw), and what it
    actually got after overdraw. ``GAP`` marks a take that differs from the
    announcement it was paired with (first take vs. first announcement, or
    final take vs. second announcement). ``raw=True`` adds each agent's raw
    model output for both calls.
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
        for i in sorted(r["first_announcements"]):
            first_ann, first_take = r["first_announcements"][i], r["first_takes"][i]
            revise = r["revisions"][i]
            second_ann, final_take = r["second_announcements"][i], r["final_takes"][i]
            granted = r["granted"][i]
            cell = (
                f"    agent {i}: first ann {first_ann:>4} take {first_take:>4}"
                + ("  GAP" if first_take != first_ann else "")
                + f"  | revise {'yes' if revise else 'no'}"
                + f"  second ann {second_ann:>4} take {final_take:>4}"
                + ("  GAP" if final_take != second_ann else "")
                + f"  granted {granted:>4}"
            )
            first_action = r.get("first_actions", {}).get(i, {})
            second_action = r.get("second_actions", {}).get(i, {})
            if first_action.get("parse_status", "ok") != "ok":
                cell += f"  [first:{first_action['parse_status']}]"
            if second_action.get("parse_status", "ok") != "ok":
                cell += f"  [second:{second_action['parse_status']}]"
            lines.append(cell)
            if raw:
                if first_action.get("raw_output") is not None:
                    lines.append(f"      first raw: {first_action['raw_output'].strip()}")
                if second_action.get("raw_output") is not None:
                    lines.append(f"      second raw: {second_action['raw_output'].strip()}")

    s = summarize_game(path)
    soc = s["societal"]
    fish = " / ".join(str(p["total_fish"]) for p in s["personal"].values())
    gaps = sum(d["n_first_gaps"] + d["n_second_gaps"] for d in s["deviation"].values())
    revisions = sum(d["n_revisions"] for d in s["deviation"].values())
    end = (
        f"pool ran out in round {soc['collapse_round']}"
        if soc["collapse_round"] is not None
        else f"pool survived with {soc['pool_remaining_end']} fish"
    )
    lines.append(
        f"  -> {soc['rounds_played']} rounds, {end} | fish {fish} | "
        f"gaps {gaps} | revisions {revisions} | gini {soc['gini']:.2f}"
    )
    return "\n".join(lines)
