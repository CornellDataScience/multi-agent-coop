from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GameState:
    """Mutable pool and round counter owned by the environment."""

    pool: int
    round: int = 1

    @classmethod
    def initial(cls, initial_pool: int) -> "GameState":
        return cls(pool=initial_pool)
