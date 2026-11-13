"""Report from saved logs: data.json, RESULTS.md, and charts (ARCHITECTURE §3.10).

Everything is computed from JSONL through ``metrics.py``. Charts need the
optional ``viz`` extra; matplotlib is imported lazily and charts are skipped
with a note when it is missing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .log import load_game
from .metrics import GAME_SCALARS, describe, dyad_kinds, summarize_game

CHART_FILES = ("alpha_sweep.png", "behavior_mix.png", "info_conditions.png", "flow_over_rounds.png")
MAX_EPISODES = 40
INFO_ORDER = ("no_memory", "private_memory", "public_reputation")

# Per-agent metrics averaged over a game's non-scripted agents ("llm_" prefix).
LLM_AGENT_METRICS = ("truthful_rate", "withhold_rate", "lie_rate", "targeted_rounds", "solve_rate",
                     "U", "reciprocity")

# Reference categorical palette (dataviz skill, light mode), fixed slot order.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"


def _collect(paths) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(p.glob("*.jsonl")))
        elif p.is_file():
            files.append(p)
    return files


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _llm_means(summary: dict, meta: dict) -> dict:
    """Mean of each per-agent metric over this game's non-scripted agents."""
    ids = [a["id"] for a in meta.get("agents", []) if a.get("type") != "scripted"]
    if not ids:
        return {}
    out = {f"llm_{k}": _mean([summary["agents"][i][k] for i in ids]) for k in LLM_AGENT_METRICS}
    out["llm_uptake_from_prior_liars"] = _mean(
        [summary["agents"][i]["uptake"]["from_prior_liars"] for i in ids])
    out["llm_forgiveness_lag"] = _mean([summary["agents"][i]["forgiveness_lag"]["mean"] for i in ids])
    return out


def find_episodes(path: Path) -> list[dict]:
    """Moments worth reading in one game: the first lie, the largest
    single-round drop in information flow, and any round where exactly one
    agent got no truthful digit from anyone (first such round per agent)."""
    game = load_game(path)
    rounds, n = game["rounds"], game["meta"]["config"]["n_agents"]
    out: list[dict] = []
    flows, excluded_seen = [], set()
    first_lie_done = False
    for rec in rounds:
        kinds = dyad_kinds(rec)
        flows.append(sum(k == "truthful" for k in kinds.values()) / max(1, len(kinds)))
        if not first_lie_done:
            lie = next(((i, j) for (i, j), k in sorted(kinds.items()) if k == "lie"), None)
            if lie:
                i, j = lie
                out.append({"file": str(path), "round": rec["round"],
                            "why": f"first lie: agent {i} sent agent {j} {rec['sends'][i][j]} "
                                   f"(true digit {rec['code'][i]})"})
                first_lie_done = True
        shut_out = [j for j in range(n)
                    if all(kinds[(i, j)] != "truthful" for i in range(n) if i != j)]
        if len(shut_out) == 1 and shut_out[0] not in excluded_seen:
            j = shut_out[0]
            excluded_seen.add(j)
            out.append({"file": str(path), "round": rec["round"],
                        "why": f"agent {j} excluded by all others (no truthful digit from anyone)"})
    drops = [(flows[t - 1] - flows[t], t) for t in range(1, len(flows))]
    if drops:
        size, t = max(drops, key=lambda d: (d[0], -d[1]))
        if size > 0:
            out.append({"file": str(path), "round": rounds[t]["round"],
                        "why": f"largest drop in information flow: {flows[t - 1]:.2f} -> {flows[t]:.2f}"})
    return sorted(out, key=lambda e: e["round"])


def build_groups(files: list[Path]) -> tuple[list[dict], dict, list[dict]]:
    groups: dict[tuple, list[tuple[dict, dict]]] = {}
    cost = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    episodes: list[tuple[bool, dict]] = []
    for f in files:
        s = summarize_game(f)
        meta = load_game(f)["meta"]
        key = (s["condition"], s["model"], float(s["alpha"]), s["info_condition"], s["prompt_variant"],
               bool(s["allow_withhold"]), float(s["pot_size"]))
        groups.setdefault(key, []).append((s, _llm_means(s, meta)))
        for k in cost:
            cost[k] += s["game"][k]
        episodes.extend((s["model"] == "scripted", e) for e in find_episodes(f))

    out = []
    for (cond, model, alpha, info, variant, allow_withhold, pot), rows in sorted(
            groups.items(), key=lambda kv: (kv[0][0], kv[0][1], not kv[0][5], kv[0][2],
                                            INFO_ORDER.index(kv[0][3]), kv[0][4] or "", kv[0][6])):
        metrics = {k: describe([s["game"][k] for s, _ in rows]) for k in GAME_SCALARS}
        llm_keys = sorted({k for _, llm in rows for k in llm})
        for k in llm_keys:
            metrics[k] = describe([llm.get(k) for _, llm in rows])
        n_rounds = max(len(s["game"]["flow_by_round"]) for s, _ in rows)
        flow_by_round = [_mean([s["game"]["flow_by_round"][t] for s, _ in rows
                                if t < len(s["game"]["flow_by_round"])]) for t in range(n_rounds)]
        out.append({"condition": cond, "model": model, "alpha": alpha, "info_condition": info,
                     "prompt_variant": variant, "allow_withhold": allow_withhold, "pot_size": pot,
                     "n_games": len(rows), "metrics": metrics,
                     "flow_by_round": flow_by_round,
                     "files": [s["file"] for s, _ in rows]})
    # LLM games first: those are the episodes a reader actually wants.
    picked = [e for _, e in sorted(episodes, key=lambda x: x[0])][:MAX_EPISODES]
    return out, cost, picked


# --- RESULTS.md --------------------------------------------------------------

def _ci(m: dict, pct: bool = False) -> str:
    if m is None or m.get("mean") is None:
        return "-"
    f = (lambda x: f"{x:.2f}")
    if m["n"] > 1:
        return f"{f(m['mean'])} [{f(m['lo'])}, {f(m['hi'])}]"
    return f(m["mean"])


def _sends(g: dict) -> str:
    return "optional" if g["allow_withhold"] else "must send"


def _tag(g: dict) -> str:
    """Chart label suffix for must-send groups."""
    return "" if g["allow_withhold"] else " must-send"


def _results_md(data: dict, chart_note: str) -> str:
    lines = [
        "# Knowledge Commons: Results",
        "",
        f"Generated {data['generated_at']} by `infocoop kc report` from saved JSONL logs only.",
        "Values are means over games; brackets are 95% bootstrap CIs (2000 resamples, seed 0).",
        "",
        "## Groups",
        "",
        "| condition | model | alpha | info | sends | pot | games | info flow | truthful | withheld | lie "
        "| bonus rate | efficiency | 1st-half flow | 2nd-half flow |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for g in data["groups"]:
        m = g["metrics"]
        lines.append(
            f"| {g['condition']} | {g['model']} | {g['alpha']:g} | {g['info_condition']} "
            f"| {_sends(g)} | {g['pot_size']:g} | {g['n_games']} "
            f"| {_ci(m['information_flow'])} | {_ci(m['truthful_share'])} | {_ci(m['withheld_share'])} "
            f"| {_ci(m['lie_share'])} | {_ci(m['bonus_rate'])} | {_ci(m['efficiency'])} "
            f"| {_ci(m['first_half_flow'])} | {_ci(m['second_half_flow'])} |")
    llm_groups = [g for g in data["groups"] if "llm_truthful_rate" in g["metrics"]]
    if llm_groups:
        lines += [
            "",
            "## LLM agents",
            "",
            "Per-agent metrics averaged over the LLM agents in each game.",
            "",
            "| condition | model | alpha | info | sends | truthful | withhold | lie | targeted rounds "
            "| reciprocity | uptake from prior liars | forgiveness lag | solve rate | score U "
            "| retry rate | fallback rate | quiz pass |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for g in llm_groups:
            m = g["metrics"]
            lines.append(
                f"| {g['condition']} | {g['model']} | {g['alpha']:g} | {g['info_condition']} "
                f"| {_sends(g)} | {_ci(m['llm_truthful_rate'])} | {_ci(m['llm_withhold_rate'])} | {_ci(m['llm_lie_rate'])} "
                f"| {_ci(m['llm_targeted_rounds'])} | {_ci(m['llm_reciprocity'])} "
                f"| {_ci(m['llm_uptake_from_prior_liars'])} | {_ci(m['llm_forgiveness_lag'])} "
                f"| {_ci(m['llm_solve_rate'])} | {_ci(m['llm_U'])} "
                f"| {_ci(m['retry_rate'])} | {_ci(m['fallback_rate'])} "
                f"| {_ci(m['comprehension_pass_rate'])} |")
    c = data["cost"]
    lines += ["", "## Cost", "",
              f"{c['calls']} model calls, {c['input_tokens']} input tokens, {c['output_tokens']} output tokens.",
              "", "## Charts", ""]
    if data["charts"]:
        lines += [f"![{name}]({name})" for name in data["charts"]]
    else:
        lines.append(chart_note)
    lines += ["", "## Episodes worth reading", ""]
    if not data["episodes"]:
        lines.append("None found.")
    for e in data["episodes"]:
        lines.append(f"- `{Path(e['file']).name}` round {e['round']}: {e['why']}")
    lines.append("")
    return "\n".join(lines)


# --- Charts ------------------------------------------------------------------

def _import_pyplot():
    import matplotlib  # lazy: only with the viz extra

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _style(ax, title: str, ylabel: str, xlabel: str | None = None) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)


def _empty(ax, msg: str) -> None:
    ax.text(0.5, 0.5, msg, ha="center", va="center", color=INK_2, fontsize=10, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])


def _err(m: dict) -> tuple[float, float]:
    return (m["mean"] - m["lo"], m["hi"] - m["mean"])


def _llm_groups(groups: list[dict]) -> list[dict]:
    llm = [g for g in groups if g["model"] != "scripted"]
    return llm or groups


def _write_charts(groups: list[dict], out: Path) -> list[str]:
    plt = _import_pyplot()
    models = sorted({g["model"] for g in _llm_groups(groups)})
    color = {m: SERIES[i % len(SERIES)] for i, m in enumerate(models)}  # fixed order by name
    markers = ("o", "s", "^", "D", "v", "P", "X", "*")
    written = []

    def save(fig, name):
        fig.patch.set_facecolor(SURFACE)
        fig.tight_layout()
        fig.savefig(out / name, dpi=150, facecolor=SURFACE)
        plt.close(fig)
        written.append(name)

    # 1. Alpha sweep: two panels (no dual axis), one line per model.
    mix = [g for g in _llm_groups(groups) if g["info_condition"] == "private_memory"]
    sweep = [g for g in mix if g["allow_withhold"]]  # must-send cells are not on the alpha axis
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharex=True)
    for ax, metric, title in ((axes[0], "information_flow", "Information flow"),
                              (axes[1], "bonus_rate", "Bonus rate")):
        _style(ax, title, "share", "alpha")
        ax.set_ylim(-0.02, 1.02)
        for k, model in enumerate(models):
            pts = sorted((g["alpha"], g["metrics"][metric]) for g in sweep if g["model"] == model
                         and g["metrics"][metric]["mean"] is not None)
            if not pts:
                continue
            xs = [a for a, _ in pts]
            ys = [m["mean"] for _, m in pts]
            errs = list(zip(*[_err(m) for _, m in pts]))
            ax.errorbar(xs, ys, yerr=errs, color=color[model], marker=markers[k % len(markers)],
                        markersize=6, linewidth=2, capsize=3, label=model)
        if not sweep:
            _empty(ax, "no private_memory groups")
    if models:
        axes[0].legend(frameon=False, fontsize=8)
    save(fig, CHART_FILES[0])

    # 2. Behavior mix: stacked truthful / withheld / lie per (model, alpha).
    fig, ax = plt.subplots(figsize=(max(5, 1.1 * len(mix) + 2), 3.6))
    _style(ax, "What agents send (share of dyad-rounds)", "share",
           "model, alpha" if len(models) > 1 else "alpha")
    if mix:
        order = sorted(mix, key=lambda g: (g["model"], not g["allow_withhold"], g["alpha"]))
        labels = [(f"{g['model']}\n" if len(models) > 1 else "") + f"α={g['alpha']:g}{_tag(g)}"
                  for g in order]
        bottom = [0.0] * len(order)
        for slot, (key, name, hatch) in enumerate((("truthful_share", "truthful", ""),
                                                   ("withheld_share", "withheld", "//"),
                                                   ("lie_share", "lie", "xx"))):
            vals = [g["metrics"][key]["mean"] or 0.0 for g in order]
            ax.bar(range(len(order)), vals, bottom=bottom, width=0.6, color=SERIES[slot], hatch=hatch,
                   edgecolor=SURFACE, linewidth=2, label=name)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_xticks(range(len(order)), labels)
        ax.set_ylim(0, 1.0)
        ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.22))
    else:
        _empty(ax, "no private_memory groups")
    save(fig, CHART_FILES[1])

    # 3. Information flow by info condition at alpha = 1.
    at1 = [g for g in _llm_groups(groups) if abs(g["alpha"] - 1.0) < 1e-9 and g["allow_withhold"]]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    _style(ax, "Information flow by information condition (alpha = 1)", "information flow")
    if at1:
        width = 0.8 / max(1, len(models))
        for k, model in enumerate(models):
            xs, ys, errs = [], [], []
            for x, info in enumerate(INFO_ORDER):
                g = next((g for g in at1 if g["model"] == model and g["info_condition"] == info), None)
                if g and g["metrics"]["information_flow"]["mean"] is not None:
                    m = g["metrics"]["information_flow"]
                    xs.append(x + (k - (len(models) - 1) / 2) * width)
                    ys.append(m["mean"])
                    errs.append(_err(m))
            if xs:
                ax.bar(xs, ys, width=width * 0.9, color=color[model], edgecolor=SURFACE, linewidth=2,
                       yerr=list(zip(*errs)), capsize=3, ecolor=INK_2, label=model)
        ax.set_xticks(range(len(INFO_ORDER)), [i.replace("_", " ") for i in INFO_ORDER])
        ax.set_ylim(0, 1.05)
        if models:
            ax.legend(frameon=False, fontsize=8)
    else:
        _empty(ax, "no groups at alpha = 1")
    save(fig, CHART_FILES[2])

    # 4. Information flow per round, one line per group (fixed palette order).
    lines = _llm_groups(groups)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    _style(ax, "Information flow per round", "information flow", "round")
    for k, g in enumerate(lines[: len(SERIES)]):  # never cycle hues
        ys = g["flow_by_round"]
        label = f"{g['model']} α={g['alpha']:g}{_tag(g)} {g['info_condition'].replace('_', ' ')}"
        ax.plot(range(1, len(ys) + 1), ys, color=SERIES[k], marker=markers[k % len(markers)],
                markersize=5, linewidth=2, label=label)
    ax.set_ylim(-0.02, 1.02)
    if lines:
        ax.legend(frameon=False, fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5))
        if len(lines) > len(SERIES):
            ax.text(0.0, -0.2, f"showing {len(SERIES)} of {len(lines)} groups; see RESULTS.md",
                    transform=ax.transAxes, fontsize=7, color=INK_2)
    save(fig, CHART_FILES[3])
    return written


def build_report(paths, out_dir: str | Path, charts: bool = True) -> dict:
    """Write data.json, RESULTS.md and (if possible) charts into ``out_dir``.
    Returns the data.json content."""
    files = _collect(paths)
    if not files:
        raise FileNotFoundError("no .jsonl game logs found")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups, cost, episodes = build_groups(files)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "groups": groups,
        "episodes": episodes,
        "cost": cost,
        "charts": [],
    }
    note = "Charts not requested."
    if charts:
        try:
            data["charts"] = _write_charts(groups, out)
        except ImportError:
            note = "Charts skipped: matplotlib is not installed (`pip install -e \".[viz]\"`)."
    (out / "data.json").write_text(json.dumps(data, indent=2) + "\n")
    (out / "RESULTS.md").write_text(_results_md(data, note))
    return data
