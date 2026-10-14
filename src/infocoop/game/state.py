from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GameState:
    """Mutable live state of a single game. The environment owns this; agents
    never see it directly (only an Observation built from the log)."""

    pool: int
    round: int = 1
    scores: dict[int, int] = field(default_factory=dict)

    @classmethod
    def initial(cls, n_agents: int, initial_pool: int) -> "GameState":
        return cls(pool=initial_pool, round=1, scores={i: 0 for i in range(n_agents)})
