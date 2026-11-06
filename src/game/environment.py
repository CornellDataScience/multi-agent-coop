from __future__ import annotations

from typing import TYPE_CHECKING

from ..information.log import GameLog
from ..information.observation import build_first_observation, build_second_observation
from .config import GameConfig
from .events import RoundResult
from .payoff import apportion, clamp
from .state import GameState

if TYPE_CHECKING:
    from ..agents.base import Agent


class Environment:
    """Runs one game. Sole owner of ground truth.

    Each round is "pre-announce with revision": every agent first and
    simultaneously picks a public first announcement and a private first take
    (independent of each other, from an observation built only from COMPLETED
    rounds, so no agent sees the current round's announcements yet); the
    first take never touches the pool or scores. Once every first
    announcement is known, every agent simultaneously picks an explicit
    revision choice, a public second announcement, and the private final take
    that actually counts; the overdraw rule applies only to that final take.
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

            # --- Phase 1: first announcement + first take (uncounted) -------
            first_observations = {
                agent.agent_id: build_first_observation(
                    self.log, agent.agent_id, cfg, pool_before, state.round
                )
                for agent in self.agents
            }
            first_actions = {
                agent.agent_id: agent.act_first(first_observations[agent.agent_id])
                for agent in self.agents
            }
            first_announcements = {i: a.first_announcement for i, a in first_actions.items()}
            first_takes = {
                i: clamp(a.first_take, 0, pool_before) for i, a in first_actions.items()
            }

            # --- Phase 2: revision + second announcement + final take -------
            second_observations = {
                agent.agent_id: build_second_observation(
                    self.log,
                    agent.agent_id,
                    cfg,
                    pool_before,
                    state.round,
                    first_announcements,
                    first_takes,
                )
                for agent in self.agents
            }
            second_actions = {
                agent.agent_id: agent.act_second(second_observations[agent.agent_id])
                for agent in self.agents
            }
            revisions = {i: a.revise for i, a in second_actions.items()}
            second_announcements = {i: a.second_announcement for i, a in second_actions.items()}
            final_takes = {
                i: clamp(a.final_take, 0, pool_before) for i, a in second_actions.items()
            }

            granted = apportion(final_takes, pool_before, cfg.overdraw_rule)
            pool_after = pool_before - sum(granted.values())

            for i, g in granted.items():
                state.scores[i] += g

            pool_next = pool_after * cfg.growth_factor
            if cfg.pool_cap is not None:
                pool_next = min(pool_next, cfg.pool_cap)

            result = RoundResult(
                round=state.round,
                pool_before=pool_before,
                first_announcements=first_announcements,
                first_takes=first_takes,
                revisions=revisions,
                second_announcements=second_announcements,
                final_takes=final_takes,
                granted=granted,
                pool_after=pool_after,
                pool_next=pool_next,
                first_actions=first_actions,
                second_actions=second_actions,
            )
            self.log.add_round(result, first_observations, second_observations)

            if pool_next == 0 or state.round >= cfg.max_rounds:
                break

            state.pool = pool_next
            state.round += 1

        return self.log
