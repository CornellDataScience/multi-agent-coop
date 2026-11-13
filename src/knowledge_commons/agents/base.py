from __future__ import annotations

from abc import ABC, abstractmethod

from ..events import GuessAction, MessageAction
from ..observation import KCObservation


class KCAgent(ABC):
    """One player. Each round the environment calls ``send_messages`` and
    then ``make_guess``. An agent may use only the ``KCObservation`` it is
    given (and state it built from earlier observations), never the log."""

    def __init__(self, agent_id: int):
        self.agent_id = agent_id

    @abstractmethod
    def send_messages(self, obs: KCObservation) -> MessageAction:
        """Return a digit or None for every other agent."""

    @abstractmethod
    def make_guess(self, obs: KCObservation) -> GuessAction:
        """Return a full guess of the code."""

    def describe(self) -> dict:
        """Agent entry for the log's meta record."""
        return {"id": self.agent_id, "type": type(self).__name__}
