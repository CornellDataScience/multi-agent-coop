from __future__ import annotations

from abc import abstractmethod
from typing import Callable

from ..game.events import Action
from ..information.observation import Observation
from .base import Agent
from .parsing import ParseError, parse_model_output
from .prompt_variants import DEFAULT_VARIANT, get_variant
from .prompts import build_system_prompt, build_user_prompt


class LLMAgent(Agent):
    """Shared prompt -> call -> parse loop for model-backed agents.

    Subclasses implement ``_call(system, prompt) -> str``. On parse failure the
    output is retried once, then falls back to ``take=fallback_take`` (logged as
    ``parse_status="fallback"``).
    """

    def __init__(
        self,
        agent_id: int,
        model: str,
        communication: bool = True,
        fallback_take: int = 0,
        prompt_variant: str = DEFAULT_VARIANT,
    ):
        super().__init__(agent_id)
        self.model = model
        self.communication = communication
        self.fallback_take = fallback_take
        get_variant(prompt_variant)  # fail fast on an unknown name
        self.prompt_variant = prompt_variant
        self.parse_failures = 0
        self._served_by: str | None = None  # set by _call when the backend reports it

    @abstractmethod
    def _call(self, system: str, prompt: str) -> str:
        """Send one request and return the model's text reply."""

    def act(self, obs: Observation) -> Action:
        system = build_system_prompt(obs, self.prompt_variant)
        prompt = build_user_prompt(obs, self.prompt_variant)
        last_text = ""
        for attempt in range(2):  # initial try + one retry
            try:
                last_text = self._call(system, prompt)
                take, claimed = parse_model_output(last_text, self.communication)
                status = "ok" if attempt == 0 else "retry_ok"
                return Action(
                    take=take,
                    claimed_take=claimed,
                    raw_output=last_text,
                    parse_status=status,
                    served_by=self._served_by,
                )
            except (ParseError, KeyError, TypeError):
                self.parse_failures += 1

        claimed = self.fallback_take if self.communication else None
        return Action(
            take=self.fallback_take,
            claimed_take=claimed,
            raw_output=last_text,
            parse_status="fallback",
            served_by=self._served_by,
        )


def _ollama_chat(**kwargs):
    import ollama  # lazy import: only needed for real LLM runs

    return ollama.chat(**kwargs)


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
        communication: bool = True,
        fallback_take: int = 0,
        prompt_variant: str = DEFAULT_VARIANT,
        chat_fn: Callable | None = None,
    ):
        super().__init__(agent_id, model, communication, fallback_take, prompt_variant)
        self.temperature = temperature
        self.seed = seed
        self._chat = chat_fn or _ollama_chat

    def _call(self, system: str, prompt: str) -> str:
        options = {"temperature": self.temperature}
        if self.seed is not None:
            options["seed"] = self.seed
        resp = self._chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            options=options,
        )
        return resp["message"]["content"]
