from abc import ABC, abstractmethod

from ..games.base import Game
from ..information.base import Observation


class Agent(ABC):
    def __init__(self, agent_id: int):
        self.agent_id = agent_id

    @abstractmethod
    def act(self, obs: Observation, game: Game) -> str:
        """Choose an action using ONLY the observation (never the ground-truth log)."""
