from __future__ import annotations

from typing import Callable

from ..game.events import Action
from ..information.observation import Observation
from .base import Agent
from .parsing import ParseError, parse_model_output
from .prompts import SYSTEM, build_user_prompt


def _ollama_chat(**kwargs):
    import ollama  # lazy import: only needed for real LLM runs

    return ollama.chat(**kwargs)


class OllamaAgent(Agent):
    """LLM agent backed by Ollama.

    Inject ``chat_fn`` to mock the model in tests (it receives the same keyword
    arguments as ``ollama.chat`` and must return ``{"message": {"content": ...}}``).
    On parse failure the output is retried once, then falls back to ``take=0``
    (logged as ``parse_status="fallback"``).
    """

    def __init__(
        self,
        agent_id: int,
        model: str = "llama3.1:8b",
        temperature: float = 0.7,
        seed: int | None = None,
        communication: bool = True,
        fallback_take: int = 0,
        chat_fn: Callable | None = None,
    ):
        super().__init__(agent_id)
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.communication = communication
        self.fallback_take = fallback_take
        self._chat = chat_fn or _ollama_chat
        self.parse_failures = 0

    def _call(self, prompt: str) -> str:
        options = {"temperature": self.temperature}
        if self.seed is not None:
            options["seed"] = self.seed
        resp = self._chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            options=options,
        )
        return resp["message"]["content"]

    def act(self, obs: Observation) -> Action:
        prompt = build_user_prompt(obs)
        last_text = ""
        for attempt in range(2):  # initial try + one retry
            try:
                last_text = self._call(prompt)
                take, claimed = parse_model_output(last_text, self.communication)
                status = "ok" if attempt == 0 else "retry_ok"
                return Action(
                    take=take,
                    claimed_take=claimed,
                    raw_output=last_text,
                    parse_status=status,
                )
            except (ParseError, KeyError, TypeError):
                self.parse_failures += 1

        claimed = self.fallback_take if self.communication else None
        return Action(
            take=self.fallback_take,
            claimed_take=claimed,
            raw_output=last_text,
            parse_status="fallback",
        )
