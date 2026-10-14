from __future__ import annotations

from abc import ABC, abstractmethod

from ..game.events import Action
from ..information.observation import Observation


class Agent(ABC):
    """N-player, numeric agent. ``act`` may use ONLY the observation it is given,
    never the ground-truth log or another agent's true take."""

    def __init__(self, agent_id: int):
        self.agent_id = agent_id

    @abstractmethod
    def act(self, obs: Observation) -> Action:
        """Return an Action (take + optional claimed_take) for this round."""
