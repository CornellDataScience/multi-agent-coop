"""Model call layer shared by every game.

A backend turns ``(system, prompt)`` into a ``ChatResult``. Agents own prompt
building, parsing and retries; backends own the API call, the model that
actually answered, and token usage. Every backend accepts an injected
``chat_fn`` so tests never touch the network.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_claude_client = None


def _claude_chat(**kwargs):
    global _claude_client
    if _claude_client is None:
        import anthropic  # lazy import: only needed for real Claude runs

        _claude_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _claude_client.beta.messages.create(**kwargs)


def _ollama_chat(**kwargs):
    import ollama  # lazy import: only needed for real Ollama runs

    return ollama.chat(**kwargs)


class OpenRouterError(RuntimeError):
    """Missing key, HTTP failure or error payload from OpenRouter."""


def _openrouter_post(payload: dict, api_key: str, timeout: float = 300) -> dict:
    """POST ``payload`` with urllib (no extra dependency) and return the JSON body."""
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500] if e.fp is not None else ""
        raise OpenRouterError(f"OpenRouter HTTP {e.code} for model {payload.get('model')!r}: {detail}") from e
    except urllib.error.URLError as e:
        raise OpenRouterError(f"OpenRouter request failed: {e.reason}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise OpenRouterError(f"OpenRouter returned non-JSON: {body[:200]!r}") from e


def _openrouter_chat(**payload) -> dict:
    """Default ``chat_fn``: reads the key at call time so a missing key fails
    on the first real call, with a message that says what to set."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set (add it to .env; see .env.example)")
    return _openrouter_post(payload, api_key)


def _get(obj, name, default=None):
    """Read ``name`` from an attribute-style or dict-style response."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class ChatResult:
    text: str
    served_by: str | None = None
    usage: dict = field(default_factory=dict)  # {"input_tokens", "output_tokens"}; {} if unknown
    refused: bool = False


class ClaudeBackend:
    """Claude API backend. No temperature or seed (the API takes neither);
    reasoning depth is set with ``effort``. ``fallbacks=True`` lets the API
    re-run a refused request on another Claude model."""

    def __init__(
        self,
        model: str = "claude-sonnet-5-5",
        effort: str = "medium",
        fallbacks: bool = False,
        chat_fn: Callable | None = None,
    ):
        self.model = model
        self.effort = effort
        self.fallbacks = fallbacks
        self._chat = chat_fn or _claude_chat

    def __call__(self, system: str, prompt: str) -> ChatResult:
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
        text = "".join(
            _get(b, "text", "") for b in (_get(resp, "content") or []) if _get(b, "type") == "text"
        )
        raw_usage = _get(resp, "usage")
        usage = {}
        if raw_usage is not None:
            usage = {
                "input_tokens": int(_get(raw_usage, "input_tokens", 0) or 0),
                "output_tokens": int(_get(raw_usage, "output_tokens", 0) or 0),
            }
        return ChatResult(
            text=text,
            served_by=_get(resp, "model"),
            usage=usage,
            refused=_get(resp, "stop_reason") == "refusal",
        )


class OllamaBackend:
    """Local Ollama backend with deterministic per-agent seeds."""

    def __init__(
        self,
        model: str = "llama3.1:8b",
        temperature: float = 0.7,
        seed: int | None = None,
        chat_fn: Callable | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self._chat = chat_fn or _ollama_chat

    def __call__(self, system: str, prompt: str) -> ChatResult:
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
        usage = {}
        if _get(resp, "prompt_eval_count") is not None or _get(resp, "eval_count") is not None:
            usage = {
                "input_tokens": int(_get(resp, "prompt_eval_count", 0) or 0),
                "output_tokens": int(_get(resp, "eval_count", 0) or 0),
            }
        return ChatResult(text=_get(_get(resp, "message"), "content", ""), served_by=None, usage=usage)


class OpenRouterBackend:
    """OpenRouter chat-completions backend (OpenAI-style messages).

    ``model`` is the OpenRouter ID without the ``openrouter/`` routing prefix,
    e.g. ``deepseek/deepseek-v4-pro``. ``temperature`` is sent only when set,
    so each provider's default applies otherwise. Needs ``OPENROUTER_API_KEY``.
    """

    def __init__(self, model: str, temperature: float | None = None, chat_fn: Callable | None = None):
        self.model = model
        self.temperature = temperature
        self._chat = chat_fn or _openrouter_chat

    def __call__(self, system: str, prompt: str) -> ChatResult:
        kwargs: dict = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        resp = self._chat(**kwargs)
        error = _get(resp, "error")
        if error:  # OpenRouter can report upstream failures inside a 200 body
            msg = _get(error, "message", error)
            raise OpenRouterError(f"OpenRouter error for model {self.model!r}: {msg}")
        choices = _get(resp, "choices") or []
        if not choices:
            raise OpenRouterError(f"OpenRouter returned no choices for model {self.model!r}")
        text = _get(_get(choices[0], "message"), "content") or ""
        raw_usage = _get(resp, "usage")
        usage = {}
        if raw_usage is not None:
            usage = {
                "input_tokens": int(_get(raw_usage, "prompt_tokens", 0) or 0),
                "output_tokens": int(_get(raw_usage, "completion_tokens", 0) or 0),
            }
        return ChatResult(text=text, served_by=_get(resp, "model"), usage=usage)


class MockBackend:
    """Network-free backend for tests and ``--model mock`` runs.

    ``responder(system, prompt) -> str`` produces each reply. Without one, the
    backend cycles through ``replies``. Every call is recorded in ``calls``.
    """

    def __init__(
        self,
        responder: Callable[[str, str], str] | None = None,
        replies: list[str] | None = None,
        model: str = "mock",
    ):
        if responder is None and not replies:
            raise ValueError("MockBackend needs a responder or at least one reply")
        self.responder = responder
        self.replies = list(replies or [])
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, prompt: str) -> ChatResult:
        self.calls.append((system, prompt))
        if self.responder is not None:
            text = self.responder(system, prompt)
        else:
            text = self.replies[(len(self.calls) - 1) % len(self.replies)]
        return ChatResult(text=text, served_by=self.model, usage={})
