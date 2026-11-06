from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..game.config import GameConfig
    from .log import GameLog


@dataclass(frozen=True)
class Observation:
    """Everything agent ``agent_id`` may see at one step of a round.

    The information firewall lives here: ``history`` carries the agent's OWN
    true first/final takes, revision choice, and grant, plus every agent's
    PUBLIC first and second announcements for past rounds -- never another
    agent's true take or revision choice. There is no ``max_rounds`` or
    horizon hint anywhere, by design (specs.md: unknown horizon).

    ``phase`` is ``"first"`` (choosing the first announcement + first take,
    before anyone's first announcement is visible) or ``"second"`` (choosing
    the revision decision + second announcement + final take, after seeing
    every agent's first announcement). The ``own_first_announcement`` /
    ``own_first_take`` / ``other_first_announcements`` fields are only set in
    the ``"second"`` phase.
    """

    agent_id: int
    round: int
    pool: int
    n_agents: int
    growth_factor: int
    phase: str
    history: list[dict] = field(default_factory=list)
    own_first_announcement: int | None = None
    own_first_take: int | None = None
    other_first_announcements: dict[int, int] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _history(log: "GameLog", agent_id: int) -> list[dict]:
    history: list[dict] = []
    for past in log.rounds:
        history.append(
            {
                "round": past.round,
                "pool_before": past.pool_before,
                "pool_after": past.pool_after,
                "first_announcements": dict(past.first_announcements),
                "second_announcements": dict(past.second_announcements),
                "your_first_take": past.first_takes[agent_id],
                "your_final_take": past.final_takes[agent_id],
                "your_revision": past.revisions[agent_id],
                "your_granted": past.granted[agent_id],
            }
        )
    return history


def build_first_observation(
    log: "GameLog", agent_id: int, config: "GameConfig", pool: int, round: int
) -> Observation:
    """The observation entering the first-phase call: own history only, no
    agent has announced anything yet this round."""
    return Observation(
        agent_id=agent_id,
        round=round,
        pool=pool,
        n_agents=config.n_agents,
        growth_factor=config.growth_factor,
        phase="first",
        history=_history(log, agent_id),
    )


def build_second_observation(
    log: "GameLog",
    agent_id: int,
    config: "GameConfig",
    pool: int,
    round: int,
    first_announcements: dict[int, int],
    first_takes: dict[int, int],
) -> Observation:
    """The observation entering the second-phase call: every agent's first
    announcement is now public, plus this agent's own first take (restated,
    since this is a fresh call and not a continued conversation). No agent's
    first take, and no pool result of the first take, is visible here."""
    others = {other: v for other, v in first_announcements.items() if other != agent_id}
    return Observation(
        agent_id=agent_id,
        round=round,
        pool=pool,
        n_agents=config.n_agents,
        growth_factor=config.growth_factor,
        phase="second",
        history=_history(log, agent_id),
        own_first_announcement=first_announcements[agent_id],
        own_first_take=first_takes[agent_id],
        other_first_announcements=others,
    )
