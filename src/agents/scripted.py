from __future__ import annotations

from ..game.events import FirstPhaseAction, SecondPhaseAction
from ..information.observation import Observation
from .base import Agent

# --- take policies: how many fish to actually take -------------------------


def _greedy(obs: Observation) -> int:
    """Grab the whole visible pool."""
    return obs.pool


def _sustainable(obs: Observation) -> int:
    """Steady-state share that leaves the pool unchanged after doubling:
    all N agents together take half the pool."""
    return obs.pool // (2 * obs.n_agents)


def _fair(obs: Observation) -> int:
    """Equal split of the current pool."""
    return obs.pool // obs.n_agents


TAKE_POLICIES = {"greedy": _greedy, "sustainable": _sustainable, "fair": _fair}

# --- claim policies: what to announce ---------------------------------------


def _honest(take: int, obs: Observation, underreport_k: int) -> int:
    return take


def _underreport(take: int, obs: Observation, underreport_k: int) -> int:
    return max(0, take - underreport_k)


def _always_lie(take: int, obs: Observation, underreport_k: int) -> int:
    """Announce a fair-looking share regardless of the true take."""
    fair = obs.pool // obs.n_agents
    return fair if fair != take else max(0, fair - 1)


CLAIM_POLICIES = {"honest": _honest, "underreport": _underreport, "always_lie": _always_lie}


class ScriptedAgent(Agent):
    """Deterministic baseline = a take-policy x a claim-policy. No LLM. Used to
    validate the environment and metrics (specs.md §5).

    The take-policy sets both ``first_take`` and ``final_take`` (it is a
    static function of the visible pool, so it does not change within a
    round). The claim-policy sets both announcements the same way, so
    ``revise`` is ``False`` unless the policy itself is non-deterministic.
    """

    def __init__(
        self,
        agent_id: int,
        take_policy: str = "fair",
        claim_policy: str = "honest",
        underreport_k: int = 1,
    ):
        super().__init__(agent_id)
        if take_policy not in TAKE_POLICIES:
            raise ValueError(f"unknown take_policy: {take_policy!r}")
        if claim_policy not in CLAIM_POLICIES:
            raise ValueError(f"unknown claim_policy: {claim_policy!r}")
        self.take_policy = take_policy
        self.claim_policy = claim_policy
        self.underreport_k = underreport_k

    def _take_and_announcement(self, obs: Observation) -> tuple[int, int]:
        take = max(0, TAKE_POLICIES[self.take_policy](obs))
        announcement = CLAIM_POLICIES[self.claim_policy](take, obs, self.underreport_k)
        return take, announcement

    def act_first(self, obs: Observation) -> FirstPhaseAction:
        take, announcement = self._take_and_announcement(obs)
        return FirstPhaseAction(first_announcement=announcement, first_take=take, parse_status="ok")

    def act_second(self, obs: Observation) -> SecondPhaseAction:
        take, announcement = self._take_and_announcement(obs)
        revise = announcement != obs.own_first_announcement
        return SecondPhaseAction(
            revise=revise, second_announcement=announcement, final_take=take, parse_status="ok"
        )
