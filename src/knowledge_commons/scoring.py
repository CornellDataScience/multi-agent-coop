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


def pot_share(pot_size: float, n_solvers: int) -> float:
    """Each solver's share of the pot, rounded to 2 decimals; 0 if nobody solves."""
    return round(pot_size / n_solvers, 2) if n_solvers else 0.0


def round_points(solved: dict[int, bool], cfg: "KCConfig") -> tuple[dict[int, float], int, bool]:
    """Split-pot scoring. Return ``(points, n_solvers, bonus)``: solvers
    split ``pot_size`` evenly; the bonus goes to everyone, solver or not,
    once ``n_solvers >= bonus_threshold``. Points are rounded to 2 decimals."""
    n_solvers = sum(1 for s in solved.values() if s)
    bonus = n_solvers >= cfg.bonus_threshold
    share = pot_share(cfg.pot_size, n_solvers)
    points = {
        i: round(share * int(bool(s)) + cfg.group_bonus * int(bonus), 2)
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


def comprehension_expected(alpha: float, pot_size: float, n_agents: int) -> dict:
    """Correct quiz answers: (a) every other agent +20 moves U by
    ``-alpha * 20``; (b) own +10 moves U by ``+10``; (c) each solver's pot
    share when all ``n_agents`` solve and when one fewer solves."""
    q1 = -alpha * QUIZ_OTHERS_GAIN
    return {"q1_direction": "down" if q1 < 0 else "same", "q1_change": q1,
            "q2_change": float(QUIZ_OWN_GAIN),
            "q3_all_share": pot_share(pot_size, n_agents),
            "q3_fewer_share": pot_share(pot_size, n_agents - 1)}


def grade_comprehension(answers: dict | None, alpha: float, pot_size: float, n_agents: int,
                        tol: float = 0.01) -> bool:
    """Pass iff all three are right: direction and ``|q1_amount|`` (a signed
    answer is accepted too), ``q2_amount`` is +10, and both (c) shares match
    to 2 decimals."""
    if not answers:
        return False
    exp = comprehension_expected(alpha, pot_size, n_agents)

    def close(x, y):
        return math.isclose(x, y, abs_tol=tol)

    return (answers.get("q1_direction") == exp["q1_direction"]
            and close(abs(answers["q1_amount"]), abs(exp["q1_change"]))
            and close(answers["q2_amount"], exp["q2_change"])
            and close(answers["q3_all_amount"], exp["q3_all_share"])
            and close(answers["q3_fewer_amount"], exp["q3_fewer_share"]))
