from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GameConfig:
    """All game parameters (specs.md §3.2) plus information flags.

    ``horizon_known`` stays False for v1: agents are never told ``max_rounds``.
    Every round is a pre-announce-with-revision round (see specs.md §3.1):
    announcements and the two-take mechanic are always on.
    """

    n_agents: int = 3
    max_rounds: int = 10
    initial_pool: int = 100
    growth_factor: int = 2
    pool_cap: int | None = None
    overdraw_rule: str = "proportional"
    horizon_known: bool = False
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_agents < 1:
            raise ValueError("n_agents must be >= 1")
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        if self.initial_pool < 0:
            raise ValueError("initial_pool must be >= 0")
        if self.growth_factor < 1:
            raise ValueError("growth_factor must be >= 1")
        if self.pool_cap is not None and self.pool_cap < 0:
            raise ValueError("pool_cap must be >= 0 or None")
        if self.overdraw_rule != "proportional":
            raise ValueError(f"unsupported overdraw_rule: {self.overdraw_rule!r}")
        if self.horizon_known:
            # v1 only implements the unknown-horizon condition end to end.
            raise ValueError("horizon_known=True is not supported in v1")

    def cooperative_optimum(self) -> int:
        """Experimenter-side optimum: wait, then take everything on the last
        round. Requires knowing the horizon, so agents cannot compute it."""
        return self.initial_pool * self.growth_factor ** (self.max_rounds - 1)

    def to_dict(self) -> dict:
        return asdict(self)
