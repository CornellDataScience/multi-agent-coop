"""LLM-backed Knowledge Commons agent: prompt -> backend -> parse, with one
retry and the SPEC §6 fallback."""
from __future__ import annotations

from typing import Callable

from ...agents.backends import ChatResult
from ..events import ComprehensionAction, GuessAction, MessageAction
from ..observation import KCObservation, KCRulesObservation
from .base import KCAgent
from .parsing import (ParseError, extract_reason, parse_comprehension_output, parse_guess_output,
                      parse_message_output)
from .prompt_variants import DEFAULT_VARIANT, get_variant
from .prompts import build_prompts, build_quiz_prompts
from .scripted import trusting_guess

_BACKEND_TYPES = {"ClaudeBackend": "claude", "OllamaBackend": "ollama", "MockBackend": "mock",
                  "KCMockBackend": "mock"}


def _add_usage(total: dict, usage: dict) -> None:
    for k, v in (usage or {}).items():
        total[k] = total.get(k, 0) + v


class KCLLMAgent(KCAgent):
    """``backend`` is any callable ``(system, prompt) -> ChatResult``, e.g.
    ``ClaudeBackend``, ``OllamaBackend`` or ``MockBackend``. A refusal counts
    as a parse failure. Usage from every attempt is summed into the action.
    Backend exceptions (network errors, call budgets) propagate."""

    def __init__(self, agent_id: int, backend: Callable[[str, str], ChatResult],
                 prompt_variant: str = DEFAULT_VARIANT):
        super().__init__(agent_id)
        get_variant(prompt_variant)  # fail fast on an unknown name
        self.backend = backend
        self.prompt_variant = prompt_variant
        self.parse_failures = 0

    def describe(self) -> dict:
        backend = getattr(self.backend, "wrapped", self.backend)  # see runner.CallBudget
        name = type(backend).__name__
        return {
            "id": self.agent_id,
            "type": _BACKEND_TYPES.get(name, name.lower()),
            "model": getattr(backend, "model", None),
            "prompt_variant": self.prompt_variant,
        }

    def _ask(self, obs: KCObservation, parse):
        """Up to two attempts with the same prompt. Returns
        ``(value | None, status, raw_text, served_by, usage)``."""
        return self._attempt(*build_prompts(obs, self.prompt_variant), parse)

    def _attempt(self, system: str, prompt: str, parse, count_failures: bool = True):
        usage: dict = {}
        text, served_by = "", None
        for attempt in range(2):
            result = self.backend(system, prompt)
            _add_usage(usage, result.usage)
            text, served_by = result.text, result.served_by or served_by
            try:
                if result.refused:
                    raise ParseError("model refused")
                return parse(text), ("ok" if attempt == 0 else "retry_ok"), text, served_by, usage
            except ParseError:
                if count_failures:
                    self.parse_failures += 1
        return None, "fallback", text, served_by, usage

    def comprehension_check(self, obs: KCRulesObservation) -> ComprehensionAction:
        """One quiz call (plus one retry on bad JSON). Stateless: nothing
        from the quiz is kept, so game prompts are unchanged by it."""
        answers, status, raw, served_by, usage = self._attempt(
            *build_quiz_prompts(obs, self.prompt_variant), parse_comprehension_output,
            count_failures=False)
        return ComprehensionAction(answers=answers, raw_output=raw,
                                   parse_status="failed" if status == "fallback" else status,
                                   served_by=served_by, usage=usage)

    def send_messages(self, obs: KCObservation) -> MessageAction:
        sends, status, raw, served_by, usage = self._ask(
            obs, lambda t: parse_message_output(t, obs.agent_id, obs.n_agents))
        if sends is None:  # SPEC §6 fallback: send nothing to anyone
            sends = {j: None for j in range(obs.n_agents) if j != obs.agent_id}
            reason = None
        else:
            reason = extract_reason(raw, "messages")
        return MessageAction(sends=sends, raw_output=raw, parse_status=status,
                             served_by=served_by, usage=usage, reason=reason)

    def make_guess(self, obs: KCObservation) -> GuessAction:
        parsed, status, raw, served_by, usage = self._ask(obs, lambda t: parse_guess_output(t, obs.n_agents))
        if parsed is None:  # SPEC §6 fallback: own digit + received digits, 0 elsewhere
            guess, confidence, reason = trusting_guess(obs), None, None
        else:
            (guess, confidence), reason = parsed, extract_reason(raw, "guess")
        return GuessAction(guess=guess, confidence=confidence, raw_output=raw, parse_status=status,
                           served_by=served_by, usage=usage, reason=reason)
