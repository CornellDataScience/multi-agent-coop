from __future__ import annotations

from abc import abstractmethod
from typing import Callable

from ..game.events import FirstPhaseAction, SecondPhaseAction
from ..information.observation import Observation
from .backends import OllamaBackend
from .base import Agent
from .parsing import ParseError, parse_first_phase_output, parse_second_phase_output
from .prompt_variants import DEFAULT_VARIANT, get_variant
from .prompts import build_first_user_prompt, build_second_user_prompt, build_system_prompt


class LLMAgent(Agent):
    """Shared prompt -> call -> parse loop for model-backed agents.

    Subclasses implement ``_call(system, prompt) -> str``. On parse failure the
    output is retried once, then falls back (logged as ``parse_status="fallback"``):
    the first-phase fallback uses ``fallback_take`` for both the announcement and
    the take; the second-phase fallback keeps the agent's first announcement
    (no revision) and uses ``fallback_take`` for the final take.
    """

    def __init__(
        self,
        agent_id: int,
        model: str,
        fallback_take: int = 0,
        prompt_variant: str = DEFAULT_VARIANT,
    ):
        super().__init__(agent_id)
        self.model = model
        self.fallback_take = fallback_take
        get_variant(prompt_variant)  # fail fast on an unknown name
        self.prompt_variant = prompt_variant
        self.parse_failures = 0
        self._served_by: str | None = None  # set by _call when the backend reports it

    @abstractmethod
    def _call(self, system: str, prompt: str) -> str:
        """Send one request and return the model's text reply."""

    def act_first(self, obs: Observation) -> FirstPhaseAction:
        system = build_system_prompt(obs, self.prompt_variant)
        prompt = build_first_user_prompt(obs, self.prompt_variant)
        last_text = ""
        for attempt in range(2):  # initial try + one retry
            try:
                last_text = self._call(system, prompt)
                first_announcement, first_take = parse_first_phase_output(last_text)
                status = "ok" if attempt == 0 else "retry_ok"
                return FirstPhaseAction(
                    first_announcement=first_announcement,
                    first_take=first_take,
                    raw_output=last_text,
                    parse_status=status,
                    served_by=self._served_by,
                )
            except (ParseError, KeyError, TypeError):
                self.parse_failures += 1

        return FirstPhaseAction(
            first_announcement=self.fallback_take,
            first_take=self.fallback_take,
            raw_output=last_text,
            parse_status="fallback",
            served_by=self._served_by,
        )

    def act_second(self, obs: Observation) -> SecondPhaseAction:
        system = build_system_prompt(obs, self.prompt_variant)
        prompt = build_second_user_prompt(obs, self.prompt_variant)
        last_text = ""
        for attempt in range(2):  # initial try + one retry
            try:
                last_text = self._call(system, prompt)
                revise, second_announcement, final_take = parse_second_phase_output(last_text)
                status = "ok" if attempt == 0 else "retry_ok"
                return SecondPhaseAction(
                    revise=revise,
                    second_announcement=second_announcement,
                    final_take=final_take,
                    raw_output=last_text,
                    parse_status=status,
                    served_by=self._served_by,
                )
            except (ParseError, KeyError, TypeError):
                self.parse_failures += 1

        return SecondPhaseAction(
            revise=False,
            second_announcement=obs.own_first_announcement or 0,
            final_take=self.fallback_take,
            raw_output=last_text,
            parse_status="fallback",
            served_by=self._served_by,
        )


class OllamaAgent(LLMAgent):
    """LLM agent backed by Ollama.

    Inject ``chat_fn`` to mock the model in tests (it receives the same keyword
    arguments as ``ollama.chat`` and must return ``{"message": {"content": ...}}``).
    """

    def __init__(
        self,
        agent_id: int,
        model: str = "llama3.1:8b",
        temperature: float = 0.7,
        seed: int | None = None,
        fallback_take: int = 0,
        prompt_variant: str = DEFAULT_VARIANT,
        chat_fn: Callable | None = None,
    ):
        super().__init__(agent_id, model, fallback_take, prompt_variant)
        self.temperature = temperature
        self.seed = seed
        self._backend = OllamaBackend(model=model, temperature=temperature, seed=seed, chat_fn=chat_fn)

    def _call(self, system: str, prompt: str) -> str:
        result = self._backend(system, prompt)
        self.last_usage = result.usage
        return result.text
