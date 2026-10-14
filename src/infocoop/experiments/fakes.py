"""Fake environment + scripted agents, for testing the runner/metrics only.

Independent of the real game/agents (owned by teammates, not implemented
yet) -- this is not used by real experiments.
"""
from __future__ import annotations

from .interfaces import AgentRoundResult, RoundResult


class HonestAgent:
    """Requests a fixed amount each round and truthfully reports its take."""

    def __init__(self, request: int = 5):
        self.request = request

    def choose_request(self, pool: int) -> int:
        return self.request

    def broadcast(self, received: int) -> tuple[int, str]:
        return received, str(received)


class UnderReportingAgent:
    """Requests a fixed amount but always claims `under_by` less than it received."""

    def __init__(self, request: int = 5, under_by: int = 2):
        self.request = request
        self.under_by = under_by

    def choose_request(self, pool: int) -> int:
        return self.request

    def broadcast(self, received: int) -> tuple[int, str]:
        claimed = max(0, received - self.under_by)
        return claimed, str(claimed)


class FakeFishermansDilemmaEnv:
    """Minimal in-memory FishermansDilemmaEnv for tests: splits over-requests
    proportionally and doubles the remaining pool each round (see the
    defaults documented in configs.py)."""

    def __init__(self, agents: list, initial_pool: int, max_rounds: int):
        self.agents = agents
        self.initial_pool = initial_pool
        self.max_rounds = max_rounds
        self.pool = initial_pool
        self.round_num = 0

    def reset(self, seed: int) -> None:
        self.pool = self.initial_pool
        self.round_num = 0

    def run_round(self) -> RoundResult:
        pool_before = self.pool
        requests = [agent.choose_request(pool_before) for agent in self.agents]
        total_requested = sum(requests)

        if total_requested <= pool_before:
            received = requests
        else:
            received = [int(pool_before * r / total_requested) for r in requests]

        agent_results = []
        for agent_id, (agent, req, rec) in enumerate(zip(self.agents, requests, received)):
            claimed, raw = agent.broadcast(rec)
            agent_results.append(
                AgentRoundResult(
                    agent_id=agent_id,
                    requested_take=req,
                    received_take=rec,
                    claimed_take=claimed,
                    raw_broadcast=raw,
                )
            )

        self.pool = (pool_before - sum(received)) * 2
        self.round_num += 1
        return RoundResult(pool_before=pool_before, pool_after=self.pool, agents=agent_results)

    def is_over(self) -> bool:
        return self.round_num >= self.max_rounds or self.pool <= 0
