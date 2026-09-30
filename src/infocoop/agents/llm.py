from __future__ import annotations

import re
from typing import Callable

from ..games.base import Game
from ..information.base import Observation
from .base import Agent
from .prompts import SYSTEM, build_user_prompt


def _ollama_chat(**kwargs):
    import ollama  # lazy import: only needed for real LLM runs

    return ollama.chat(**kwargs)


class OllamaAgent(Agent):
    """LLM agent backed by Ollama. Pass `chat_fn` to mock in tests."""

    def __init__(self, agent_id: int, model: str = "llama3.1:8b", temperature: float = 0.7,
                 seed: int | None = None, total_rounds: int | None = None,
                 fallback: str = "D", chat_fn: Callable | None = None):
        super().__init__(agent_id)
        self.model, self.temperature, self.seed = model, temperature, seed
        self.total_rounds, self.fallback = total_rounds, fallback
        self._chat = chat_fn or _ollama_chat
        self.parse_failures = 0
        self.transcript: list[dict] = []

    def act(self, obs: Observation, game: Game) -> str:
        prompt = build_user_prompt(obs, game, self.total_rounds)
        options = {"temperature": self.temperature}
        if self.seed is not None:
            options["seed"] = self.seed
        resp = self._chat(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            options=options,
        )
        text = resp["message"]["content"]
        action = self._parse(text)
        self.transcript.append({"round": obs.round, "opponent": obs.opponent_id,
                                "prompt": prompt, "response": text, "action": action})
        return action

    def _parse(self, text: str) -> str:
        has_c = re.search(r"\bcooperate\b", text, re.I) is not None
        has_d = re.search(r"\bdefect\b", text, re.I) is not None
        if has_c != has_d:
            return "C" if has_c else "D"
        self.parse_failures += 1
        return self.fallback
