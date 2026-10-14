from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game.config import GameConfig
    from .log import GameLog


@dataclass(frozen=True)
class Observation:
    """Everything agent ``agent_id`` may see entering a round.

    The information firewall lives here: ``history`` carries the agent's OWN
    true takes and grants, plus OTHER agents' broadcast claims only — never
    another agent's true take. There is no ``max_rounds`` or horizon hint
    anywhere, by design (specs.md: unknown horizon).
    """

    agent_id: int
    round: int
    pool: int
    n_agents: int
    growth_factor: int
    communication: bool
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_observation(
    log: "GameLog", agent_id: int, config: "GameConfig", pool: int, round: int
) -> Observation:
    """The ONLY path from the ground-truth log to an agent. Any information
    policy change (control condition, a future hidden-pool condition) lives
    here, not in the agents."""
    history: list[dict] = []
    for past in log.rounds:
        entry = {
            "round": past.round,
            "pool_before": past.pool_before,
            "your_take": past.takes[agent_id],
            "your_granted": past.granted[agent_id],
        }
        if config.communication:
            # Other agents' public claims (attribution is visible, but their
            # true takes are not). The total actually removed from the pool is
            # inferable from consecutive pool sizes, so we surface it directly.
            entry["claims"] = {
                other: past.claims[other] for other in sorted(past.claims) if other != agent_id
            }
            entry["inferred_total_take"] = past.pool_before - past.pool_after
        history.append(entry)

    return Observation(
        agent_id=agent_id,
        round=round,
        pool=pool,
        n_agents=config.n_agents,
        growth_factor=config.growth_factor,
        communication=config.communication,
        history=history,
    )
