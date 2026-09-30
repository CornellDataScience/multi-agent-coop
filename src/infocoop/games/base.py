from abc import ABC, abstractmethod


class Game(ABC):
    """A symmetric two-player simultaneous-move stage game."""

    actions: tuple[str, ...]

    @abstractmethod
    def payoffs(self, action_a: str, action_b: str) -> tuple[float, float]:
        """Return (payoff_a, payoff_b)."""

    @abstractmethod
    def max_joint_payoff(self) -> float:
        """Socially optimal total payoff for a single stage game."""

    @abstractmethod
    def describe(self) -> str:
        """Natural-language rules, used in LLM prompts."""
