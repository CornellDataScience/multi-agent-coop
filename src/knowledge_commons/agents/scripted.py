"""Scripted baselines and probe opponents (SPEC §7).

Each policy reads only its observation. Memory-based policies (reciprocator,
grudger) read past rounds from ``obs.history``, so under ``no_memory`` they
behave as in round 1. That keeps them inside the same firewall as LLM agents.
"""
from __future__ import annotations

from ..events import GuessAction, MessageAction
from ..observation import KCObservation
from .base import KCAgent


def _others(obs: KCObservation) -> list[int]:
    return [j for j in range(obs.n_agents) if j != obs.agent_id]


def _liars(obs: KCObservation) -> set[int]:
    """Agents that have ever sent this agent a digit that the reveal showed
    was false."""
    out = set()
    for h in obs.history:
        for j, d in h["received"].items():
            if d is not None and d != h["code"][j]:
                out.add(j)
    return out


def trusting_guess(obs: KCObservation, ignore: set[int] = frozenset()) -> tuple[int, ...]:
    """Own digit in own position, received digits elsewhere, 0 for unknowns
    and for senders in ``ignore``."""
    guess = [0] * obs.n_agents
    for j, d in (obs.received or {}).items():
        if d is not None and j not in ignore:
            guess[j] = d
    guess[obs.agent_id] = obs.my_digit
    return tuple(guess)


class ScriptedAgent(KCAgent):
    policy = "scripted"

    def describe(self) -> dict:
        return {"id": self.agent_id, "type": "scripted", "policy": self.policy}

    def send_messages(self, obs: KCObservation) -> MessageAction:
        return MessageAction(sends={j: self._send_to(j, obs) for j in _others(obs)})

    def make_guess(self, obs: KCObservation) -> GuessAction:
        return GuessAction(guess=trusting_guess(obs))

    def _send_to(self, j: int, obs: KCObservation) -> int | None:
        raise NotImplementedError


class HonestAgent(ScriptedAgent):
    policy = "honest"

    def _send_to(self, j, obs):
        return obs.my_digit


class HoarderAgent(ScriptedAgent):
    policy = "hoarder"

    def _send_to(self, j, obs):
        return None


class LiarAgent(ScriptedAgent):
    policy = "liar"

    def _send_to(self, j, obs):
        return (obs.my_digit + 1) % 10


class ReciprocatorAgent(ScriptedAgent):
    """Truth to all in the first round it remembers; afterwards truth to
    ``j`` iff ``j`` told it the truth in the most recent remembered round."""

    policy = "reciprocator"

    def _send_to(self, j, obs):
        if not obs.history:
            return obs.my_digit
        last = obs.history[-1]
        return obs.my_digit if last["received"].get(j) == last["code"][j] else None


class GrudgerAgent(ScriptedAgent):
    """Truth to ``j`` until ``j`` lies once, then nothing forever; ignores
    digits from anyone who has lied to it."""

    policy = "grudger"

    def send_messages(self, obs):
        liars = _liars(obs)
        return MessageAction(sends={j: None if j in liars else obs.my_digit for j in _others(obs)})

    def make_guess(self, obs):
        return GuessAction(guess=trusting_guess(obs, ignore=_liars(obs)))


class ExcluderAgent(ScriptedAgent):
    """Truth to everyone except one fixed target, who gets nothing. Default
    target is the next agent id (wrapping)."""

    policy = "excluder"

    def __init__(self, agent_id: int, target: int | None = None):
        super().__init__(agent_id)
        if target is not None and target == agent_id:
            raise ValueError("excluder cannot target itself")
        self.target = target

    def _target(self, obs):
        return self.target if self.target is not None else (self.agent_id + 1) % obs.n_agents

    def _send_to(self, j, obs):
        return None if j == self._target(obs) else obs.my_digit

    def describe(self) -> dict:
        d = super().describe()
        if self.target is not None:
            d["target"] = self.target
        return d


SCRIPTED_POLICIES: dict[str, type[ScriptedAgent]] = {
    cls.policy: cls
    for cls in (HonestAgent, HoarderAgent, LiarAgent, ReciprocatorAgent, GrudgerAgent, ExcluderAgent)
}


def make_scripted(policy: str, agent_id: int, **kwargs) -> ScriptedAgent:
    if policy not in SCRIPTED_POLICIES:
        raise KeyError(f"unknown scripted policy {policy!r}; known: {sorted(SCRIPTED_POLICIES)}")
    return SCRIPTED_POLICIES[policy](agent_id, **kwargs)
