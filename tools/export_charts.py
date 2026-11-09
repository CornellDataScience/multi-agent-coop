"""Export a run's headline charts as PNGs for the results report.

Usage: .venv/bin/python tools/export_charts.py <run_id> <out_dir>

Style follows the project's validated palette and chart conventions: fixed
categorical slots (control = reference gray), thin bars, hairline grid on the
value axis only, ink-colored CI whiskers, no chartjunk.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from asymbench import db  # noqa: E402

# Light-mode tokens from the validated reference palette
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_DIM = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
GRAY_REF = "#898781"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 10,
    "text.color": INK, "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_DIM, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "svg.fonttype": "none",
})

CP_SHORT = {"meta-llama/llama-3.1-8b-instruct": "Llama 3.1 8B",
            "openai/gpt-oss-20b": "gpt-oss-20b"}


def style(ax, ylabel=None, zero_line=False):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.xaxis.grid(False)
    ax.tick_params(length=0)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    if zero_line:
        ax.axhline(0, color=BASELINE, linewidth=1)


def whisker(ax, x, lo, hi):
    if lo is None or hi is None:
        return
    ax.plot([x, x], [lo, hi], color=INK_DIM, linewidth=1.1, zorder=5)
    for v in (lo, hi):
        ax.plot([x - 0.06, x + 0.06], [v, v], color=INK_DIM, linewidth=1.1, zorder=5)


def save(fig, out_dir: Path, name: str):
    path = out_dir / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


def main(run_id: str, out: str) -> None:
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run = db.get_run(run_id)
    agg = run["aggregates"]
    contrasts = agg["contrasts"]
    cells = agg["cells"]
    cps = sorted({c["counterpart"] for c in contrasts})
    labels = [CP_SHORT.get(c, c) for c in cps]

    def task_mean(cp, key):
        vals = [c[key]["mean"] for c in contrasts
                if c["counterpart"] == cp and c.get(key) and c[key].get("mean") is not None]
        return sum(vals) / len(vals) if vals else None

    def pooled_ci(cp, key):
        """When one contrast per task exists, pool by averaging means; whiskers
        only when a single pooled CI is well-defined (per-task shown in tables)."""
        cs = [c[key] for c in contrasts
              if c["counterpart"] == cp and c.get(key) and c[key].get("mean") is not None]
        if len(cs) == 1:
            return cs[0]["mean"], cs[0]["lo"], cs[0]["hi"]
        if not cs:
            return None, None, None
        return sum(c["mean"] for c in cs) / len(cs), None, None

    # ---- 1. Integrity shifts (attempt / success) per counterpart, per task ----
    tasks = sorted({c["task"] for c in contrasts})
    fig, axes = plt.subplots(1, len(tasks), figsize=(2.6 * len(tasks), 3.1), sharey=True)
    for ax, task in zip(axes, tasks):
        tc = [c for c in contrasts if c["task"] == task]
        xs = range(len(tc))
        for i, c in enumerate(sorted(tc, key=lambda c: c["counterpart"])):
            v = c["attempt_shift"]
            ax.bar(i, v["mean"], width=0.5, color=S1, zorder=3)
            whisker(ax, i, v["lo"], v["hi"])
        ax.set_xticks(list(xs))
        ax.set_xticklabels([CP_SHORT.get(c["counterpart"], "?").split()[0]
                            for c in sorted(tc, key=lambda c: c["counterpart"])], fontsize=8)
        ax.set_title(task, fontsize=10)
        style(ax, zero_line=True)
    axes[0].set_ylabel("attempt shift vs control", fontsize=9)
    fig.suptitle("Attempt shift by task (scored exploitative events per episode, weak − control)",
                 fontsize=11, y=1.03)
    save(fig, out_dir, "attempt_shift_by_task.png")

    # ---- 2. Recognition: rate + survey rating (two panels, one axis each) ----
    def cell_mean(cp_sel, field):
        sel = [c for c in cells if
               (c["is_control"] if cp_sel == "control" else c["counterpart"] == cp_sel
                and not c["is_control"])]
        vals = [c["fields"][field]["mean"] for c in sel
                if c["fields"][field].get("mean") is not None]
        return sum(vals) / len(vals) if vals else None

    groups = cps + ["control"]
    glabels = labels + ["control"]
    colors = [S1] * len(cps) + [GRAY_REF]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.0))
    a1.bar(range(len(groups)), [cell_mean(g, "recognized") for g in groups],
           width=0.5, color=colors, zorder=3)
    a1.set_xticks(range(len(groups)))
    a1.set_xticklabels(glabels, fontsize=8)
    a1.set_ylim(0, 1)
    a1.set_title("Recognition rate", fontsize=10)
    style(a1)
    a2.bar(range(len(groups)), [cell_mean(g, "survey_rating") for g in groups],
           width=0.5, color=colors, zorder=3)
    a2.set_xticks(range(len(groups)))
    a2.set_xticklabels(glabels, fontsize=8)
    a2.set_ylim(0, 5)
    a2.set_title("Post-episode survey rating (1–5)", fontsize=10)
    style(a2)
    fig.suptitle("Did the test agent notice weaker counterparts?", fontsize=11, y=1.04)
    save(fig, out_dir, "recognition.png")

    # ---- 3. Advantage captured per counterpart (pooled over tasks) ----
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    for i, cp in enumerate(cps):
        m, lo, hi = pooled_ci(cp, "advantage_captured")
        ax.bar(i, m, width=0.45, color=S1, zorder=3)
        whisker(ax, i, lo, hi)
    ax.set_xticks(range(len(cps)))
    ax.set_xticklabels(labels, fontsize=9)
    style(ax, ylabel="share of value, weak − control", zero_line=True)
    ax.set_title("Advantage captured (not evidence of wrongdoing by itself)", fontsize=10)
    save(fig, out_dir, "advantage_captured.png")

    # ---- 4. Commons pool trajectory ----
    commons = [c for c in cells if c["task"] == "commons"]
    if commons:
        fig, ax = plt.subplots(figsize=(6.2, 3.2))
        si = 0
        for c in sorted(commons, key=lambda c: (c["is_control"], c["counterpart"])):
            traj = (c.get("extras") or {}).get("pool_by_round") or []
            if not traj:
                continue
            if c["is_control"]:
                color, label = GRAY_REF, "control"
            else:
                color = [S1, S2, S3][si % 3]
                label = CP_SHORT.get(c["counterpart"], c["counterpart"])
                si += 1
            ax.plot(range(1, len(traj) + 1), traj, color=color, linewidth=2,
                    marker="o", markersize=4, markeredgecolor=SURFACE,
                    markeredgewidth=1.2, label=label)
        ax.set_ylim(0, 105)
        ax.set_xlabel("round", fontsize=9)
        style(ax, ylabel="lake size at round start")
        ax.legend(frameon=False, fontsize=8)
        ax.set_title("Commons: average lake size per round", fontsize=10)
        save(fig, out_dir, "commons_pool.png")

    # ---- 5. Harm per counterpart (pooled) ----
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    for i, cp in enumerate(cps):
        m, lo, hi = pooled_ci(cp, "harm_shift")
        ax.bar(i, m, width=0.45, color=S1, zorder=3)
        whisker(ax, i, lo, hi)
    ax.set_xticks(range(len(cps)))
    ax.set_xticklabels(labels, fontsize=9)
    style(ax, ylabel="harm shift vs control (0–1)", zero_line=True)
    ax.set_title("Harm to the counterpart, weak − control", fontsize=10)
    save(fig, out_dir, "harm_shift.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
