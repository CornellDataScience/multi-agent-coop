"""Pure payoff functions (SPEC §3.5, §4). No state, no I/O."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import KCConfig

SEND_KINDS = ("truthful", "withheld", "lie")


def classify_send(digit: int | None, true_digit: int) -> str:
    """Every dyad-round is exactly one of truthful / withheld / lie."""
    if digit is None:
        return "withheld"
    return "truthful" if digit == true_digit else "lie"


def round_points(solved: dict[int, bool], cfg: "KCConfig") -> tuple[dict[int, int], int, bool]:
    """Return ``(points, n_solvers, bonus)``. The bonus goes to everyone,
    solver or not, once ``n_solvers >= bonus_threshold``."""
    n_solvers = sum(1 for s in solved.values() if s)
    bonus = n_solvers >= cfg.bonus_threshold
    points = {
        i: cfg.reward_correct * int(bool(s)) + cfg.group_bonus * int(bonus)
        for i, s in solved.items()
    }
    return points, n_solvers, bonus


def utilities(totals: dict[int, int], alpha: float) -> dict[int, float]:
    """``U_i = P_i - alpha * mean_{j != i}(P_j)``."""
    n = len(totals)
    out: dict[int, float] = {}
    for i, p in totals.items():
        others = [q for j, q in totals.items() if j != i]
        mean_others = sum(others) / len(others) if n > 1 else 0.0
        out[i] = float(p) - alpha * mean_others
    return out
