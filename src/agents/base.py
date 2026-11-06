from __future__ import annotations

from abc import ABC, abstractmethod

from ..game.events import FirstPhaseAction, SecondPhaseAction
from ..information.observation import Observation


class Agent(ABC):
    """N-player, numeric agent for a pre-announce-with-revision round.

    Each round calls ``act_first`` (public first announcement + private first
    take, chosen with no visibility into any other agent's choice) and then,
    once every agent's first announcement is known, ``act_second`` (revision
    choice + second announcement + the final take that counts). Neither call
    may use anything but the ``Observation`` it is given -- never the
    ground-truth log or another agent's true take or revision choice.
    """

    def __init__(self, agent_id: int):
        self.agent_id = agent_id

    @abstractmethod
    def act_first(self, obs: Observation) -> FirstPhaseAction:
        """Return this agent's first announcement and first take."""

    @abstractmethod
    def act_second(self, obs: Observation) -> SecondPhaseAction:
        """Return this agent's revision choice, second announcement, and final take."""
