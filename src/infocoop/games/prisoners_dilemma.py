from .base import Game


class PrisonersDilemma(Game):
    """Actions: 'C' (cooperate) and 'D' (defect). Requires T > R > P > S and 2R > T + S."""

    actions = ("C", "D")

    def __init__(self, T: float = 5, R: float = 3, P: float = 1, S: float = 0):
        if not (T > R > P > S):
            raise ValueError("Prisoner's dilemma requires T > R > P > S")
        if not (2 * R > T + S):
            raise ValueError("Requires 2R > T + S so mutual cooperation is socially optimal")
        self.T, self.R, self.P, self.S = T, R, P, S

    def payoffs(self, action_a: str, action_b: str) -> tuple[float, float]:
        table = {
            ("C", "C"): (self.R, self.R),
            ("C", "D"): (self.S, self.T),
            ("D", "C"): (self.T, self.S),
            ("D", "D"): (self.P, self.P),
        }
        return table[(action_a, action_b)]

    def max_joint_payoff(self) -> float:
        return 2 * self.R

    def describe(self) -> str:
        return (
            "Each round you and another player simultaneously choose COOPERATE or DEFECT.\n"
            f"- Both COOPERATE: you each get {self.R}.\n"
            f"- Both DEFECT: you each get {self.P}.\n"
            f"- You DEFECT, they COOPERATE: you get {self.T}, they get {self.S}.\n"
            f"- You COOPERATE, they DEFECT: you get {self.S}, they get {self.T}.\n"
            "Your goal is to maximize your own total payoff over all rounds."
        )
