"""Minimal environment surface the experiment runner depends on.

ASSUMPTION: everything in this file is a guess about the Fisherman's
Dilemma environment API, since src/infocoop/games (teammate-owned) has no
such game yet -- only a two-player PrisonersDilemma. Teammates implementing
the real game should either match this Protocol or tell us what needs to
change; the runner only depends on this interface, never on concrete game
code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class AgentRoundResult:
    """One agent's outcome for a single round.

    claimed_take is None when the broadcast couldn't be parsed into a
    number -- callers must record this as missing, never guess a value.
    """

    agent_id: int
    requested_take: int
    received_take: int
    claimed_take: Optional[int]
    raw_broadcast: str
    reasoning: str = ""  # private reasoning/scratchpad; "" if not exposed


@dataclass
class RoundResult:
    """Outcome of one full round: all agents' moves plus pool state."""

    pool_before: int
    pool_after: int
    agents: list[AgentRoundResult] = field(default_factory=list)


class FishermansDilemmaEnv(Protocol):
    """ASSUMPTION: minimal environment surface the runner needs.

    A round is: each agent privately requests a take, the environment
    resolves actual takes against the pool (ASSUMPTION: proportional split
    if total requests exceed the pool -- see configs.py), agents
    simultaneously broadcast a (possibly false) claimed take, and the
    remaining pool doubles (ASSUMPTION: no cap).
    """

    def reset(self, seed: int) -> None:
        """Start a fresh game (new pool, round counter) with this seed."""
        ...

    def run_round(self) -> RoundResult:
        """Run one full round and return its RoundResult."""
        ...

    def is_over(self) -> bool:
        """ASSUMPTION: True once max_rounds is reached or the pool is empty."""
        ...
