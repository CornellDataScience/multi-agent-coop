from __future__ import annotations

from abc import ABC, abstractmethod

from ..events import ComprehensionAction, GuessAction, MessageAction
from ..observation import KCObservation, KCRulesObservation


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

    def comprehension_check(self, obs: KCRulesObservation) -> ComprehensionAction | None:
        """Answer the pre-game rules quiz. Default: skip (None). Must not
        change how the agent plays: the game never shows the quiz again."""
        return None

    def describe(self) -> dict:
        """Agent entry for the log's meta record."""
        return {"id": self.agent_id, "type": type(self).__name__}
