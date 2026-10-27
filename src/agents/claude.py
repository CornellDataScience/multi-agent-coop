from __future__ import annotations

from typing import Callable

from .llm import LLMAgent
from .parsing import ParseError
from .prompt_variants import DEFAULT_VARIANT

_client = None


def _claude_chat(**kwargs):
    global _client
    if _client is None:
        import anthropic  # lazy import: only needed for real Claude runs

        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client.beta.messages.create(**kwargs)


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
        communication: bool = True,
        fallback_take: int = 0,
        prompt_variant: str = DEFAULT_VARIANT,
        chat_fn: Callable | None = None,
    ):
        super().__init__(agent_id, model, communication, fallback_take, prompt_variant)
        self.effort = effort
        self.fallbacks = fallbacks
        self._chat = chat_fn or _claude_chat

    def _call(self, system: str, prompt: str) -> str:
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.effort},
        )
        if self.fallbacks:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        resp = self._chat(**kwargs)
        self._served_by = resp.model
        if resp.stop_reason == "refusal":
            raise ParseError("model refused")
        return "".join(b.text for b in resp.content if b.type == "text")
