from __future__ import annotations

from typing import Callable

from .backends import ClaudeBackend
from .llm import LLMAgent
from .parsing import ParseError
from .prompt_variants import DEFAULT_VARIANT

class ClaudeAgent(LLMAgent):
    """LLM agent backed by the Claude API.

    Needs ``ANTHROPIC_API_KEY`` (see ``.env.example``). The Claude API takes no
    ``temperature`` or ``seed``, so runs are not reproducible the way seeded
    Ollama runs are; reasoning depth is set with ``effort`` instead.

    A refusal counts as a parse failure. ``fallbacks=True`` instead lets the API
    re-run a refused request on another Claude model (only on models that
    support server-side fallback; Haiku does not). The model that actually
    answered is logged per action as ``served_by``.

    Inject ``chat_fn`` to mock the API in tests (it receives the keyword
    arguments of ``client.beta.messages.create`` and must return an object with
    ``.content``, ``.stop_reason`` and ``.model``).
    """

    def __init__(
        self,
        agent_id: int,
        model: str = "claude-sonnet-5-5",
        effort: str = "medium",
        fallbacks: bool = False,
        fallback_take: int = 0,
        prompt_variant: str = DEFAULT_VARIANT,
        chat_fn: Callable | None = None,
    ):
        super().__init__(agent_id, model, fallback_take, prompt_variant)
        self.effort = effort
        self.fallbacks = fallbacks
        self._backend = ClaudeBackend(model=model, effort=effort, fallbacks=fallbacks, chat_fn=chat_fn)

    def _call(self, system: str, prompt: str) -> str:
        result = self._backend(system, prompt)
        self._served_by = result.served_by
        self.last_usage = result.usage
        if result.refused:
            raise ParseError("model refused")
        return result.text
