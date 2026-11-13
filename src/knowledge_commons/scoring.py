"""Pure payoff functions (SPEC §3.5, §4). No state, no I/O."""
from __future__ import annotations

import math
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


# Comprehension check (pre-game quiz): fixed point changes asked about.
QUIZ_OTHERS_GAIN = 20
QUIZ_OWN_GAIN = 10


def comprehension_expected(alpha: float) -> dict:
    """Correct quiz answers implied by ``utilities``: every other agent +20
    moves U by ``-alpha * 20``; own +10 moves U by ``+10``."""
    q1 = -alpha * QUIZ_OTHERS_GAIN
    return {"q1_direction": "down" if q1 < 0 else "same", "q1_change": q1,
            "q2_change": float(QUIZ_OWN_GAIN)}


def grade_comprehension(answers: dict | None, alpha: float, tol: float = 0.01) -> bool:
    """Pass iff the direction is right, ``|q1_amount|`` equals the size of
    the change (a signed answer is accepted too), and ``q2_amount`` is +10."""
    if not answers:
        return False
    exp = comprehension_expected(alpha)
    q1, q2 = answers.get("q1_amount"), answers.get("q2_amount")
    return (answers.get("q1_direction") == exp["q1_direction"]
            and math.isclose(abs(q1), abs(exp["q1_change"]), abs_tol=tol)
            and math.isclose(q2, exp["q2_change"], abs_tol=tol))
