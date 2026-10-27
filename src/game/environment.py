from __future__ import annotations

from typing import TYPE_CHECKING

from ..information.log import GameLog
from ..information.observation import build_observation
from .config import GameConfig
from .events import RoundResult
from .payoff import apportion, clamp
from .state import GameState

if TYPE_CHECKING:
    from ..agents.base import Agent


class Environment:
    """Runs one game. Sole owner of ground truth.

    Moves are simultaneous: every agent chooses ``(take, claimed_take)`` from an
    observation built only from COMPLETED rounds, then the environment resolves.
    An agent therefore never sees the current round's claims, only prior ones.
    """

    def __init__(
        self,
        config: GameConfig,
        agents: list["Agent"],
        condition: str = "unnamed",
        prompt_variant: str | None = None,
    ):
        if len(agents) != config.n_agents:
            raise ValueError(f"expected {config.n_agents} agents, got {len(agents)}")
        self.config = config
        self.agents = agents
        self.log = GameLog(
            config=config, seed=config.seed, condition=condition, prompt_variant=prompt_variant
        )

    def run(self) -> GameLog:
        cfg = self.config
        state = GameState.initial(cfg.n_agents, cfg.initial_pool)

        while True:
            pool_before = state.pool

            observations = {
                agent.agent_id: build_observation(
                    self.log, agent.agent_id, cfg, pool_before, state.round
                )
                for agent in self.agents
            }
            actions = {agent.agent_id: agent.act(observations[agent.agent_id]) for agent in self.agents}

            takes = {i: clamp(a.take, 0, pool_before) for i, a in actions.items()}
            granted = apportion(takes, pool_before, cfg.overdraw_rule)
            pool_after = pool_before - sum(granted.values())

            for i, g in granted.items():
                state.scores[i] += g

            claims = {
                i: (a.claimed_take if cfg.communication else None) for i, a in actions.items()
            }

            pool_next = pool_after * cfg.growth_factor
            if cfg.pool_cap is not None:
                pool_next = min(pool_next, cfg.pool_cap)

            result = RoundResult(
                round=state.round,
                pool_before=pool_before,
                takes=takes,
                granted=granted,
                claims=claims,
                pool_after=pool_after,
                pool_next=pool_next,
                actions=actions,
            )
            self.log.add_round(result, observations)

            if pool_next == 0 or state.round >= cfg.max_rounds:
                break

            state.pool = pool_next
            state.round += 1

        return self.log
