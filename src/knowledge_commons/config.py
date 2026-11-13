from __future__ import annotations

from dataclasses import asdict, dataclass

INFO_CONDITIONS = ("no_memory", "private_memory", "public_reputation")


@dataclass(frozen=True)
class KCConfig:
    """Parameters of one Knowledge Commons game (SPEC §2, §4).

    The code has ``n_agents`` digits, each 0-9; agent ``i`` holds digit ``i``.
    ``max_rounds`` is known to the engine only; agents are never told it.
    """

    n_agents: int = 4
    max_rounds: int = 8
    reward_correct: int = 10
    group_bonus: int = 10
    bonus_threshold: int = 3
    alpha: float = 0.5
    info_condition: str = "private_memory"
    horizon_known: bool = False  # v1: must stay False (unknown horizon)
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_agents < 2:
            raise ValueError("n_agents must be at least 2")
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        if not 1 <= self.bonus_threshold <= self.n_agents:
            raise ValueError("bonus_threshold must be between 1 and n_agents")
        if self.alpha < 0:
            raise ValueError("alpha must be non-negative")
        if self.info_condition not in INFO_CONDITIONS:
            raise ValueError(f"unknown info_condition {self.info_condition!r}; known: {INFO_CONDITIONS}")
        if self.horizon_known:
            raise ValueError("horizon_known=True is out of scope for v1")

    def max_welfare(self) -> int:
        """Group points if every agent solves every round."""
        return self.n_agents * (self.reward_correct + self.group_bonus) * self.max_rounds

    def to_dict(self) -> dict:
        return asdict(self)
