"""Async chat() over Anthropic / OpenRouter with retries, timeouts and cost tracking.

- Model lookup goes through settings.resolve_model (models.yaml + prefix routing).
- Anthropic: messages.create with `system` and one user message; only text blocks
  are collected (thinking blocks ignored); no temperature; no tool use.
- OpenRouter: chat.completions.create with a system and a user message and
  extra_body={"usage": {"include": True}}; the reported cost is used when present.
- Timeouts: 120 s per call. Retries: up to 4 attempts, exponential backoff with
  jitter, on 429 / 5xx / timeouts / connection errors only.
- API keys are read by the SDKs from the environment and are never logged,
  stored or returned by anything in this module.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field

from .settings import ModelSpec, resolve_model

CALL_TIMEOUT_S = 120
MAX_ATTEMPTS = 4
CONCURRENCY = {"anthropic": 8, "openrouter": 8}

_NO_RETRY_STATUSES = {400, 401, 403, 404, 422}


class ProviderError(Exception):
    """A provider call failed in a way that should not be retried."""


@dataclass
class ChatResult:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    raw_meta: dict = field(default_factory=dict)


_anthropic_client = None
_openrouter_client = None
# Semaphores are per event loop (tests create several loops in one process).
_semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}


def _get_semaphore(provider: str) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = (provider, id(loop))
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(CONCURRENCY.get(provider, 8))
    return _semaphores[key]


def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        _anthropic_client = anthropic.AsyncAnthropic(timeout=CALL_TIMEOUT_S, max_retries=0)
    return _anthropic_client


def _openrouter():
    global _openrouter_client
    if _openrouter_client is None:
        import openai

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError("OPENROUTER_API_KEY is not set")
        _openrouter_client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1", api_key=key,
            timeout=CALL_TIMEOUT_S, max_retries=0,
        )
    return _openrouter_client


def compute_cost(spec: ModelSpec, tokens_in: int, tokens_out: int) -> float:
    return tokens_in * spec.price_in / 1e6 + tokens_out * spec.price_out / 1e6


def _status_code(exc: Exception) -> int | None:
    return getattr(exc, "status_code", None)


def _is_retryable(exc: Exception) -> bool:
    status = _status_code(exc)
    if status is not None:
        if status in _NO_RETRY_STATUSES:
            return False
        return status == 429 or status >= 500
    # Timeouts and connection errors from either SDK (both subclass their
    # APIConnectionError from APIError without a status code), plus asyncio timeouts.
    name = type(exc).__name__
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "Timeout" in name or "Connection" in name


async def _call_anthropic(spec: ModelSpec, system: str, user: str, max_tokens: int) -> ChatResult:
    client = _anthropic()
    t0 = time.monotonic()
    resp = await client.messages.create(
        model=spec.id,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    latency = int((time.monotonic() - t0) * 1000)
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    tokens_in = getattr(resp.usage, "input_tokens", 0) or 0
    tokens_out = getattr(resp.usage, "output_tokens", 0) or 0
    stop_details = getattr(resp, "stop_details", None)
    if stop_details is not None:
        try:
            stop_details = stop_details.model_dump()
        except AttributeError:
            stop_details = str(stop_details)
    return ChatResult(
        text=text, tokens_in=tokens_in, tokens_out=tokens_out,
        cost_usd=compute_cost(spec, tokens_in, tokens_out), latency_ms=latency,
        raw_meta={"response_id": getattr(resp, "id", None),
                  "stop_reason": getattr(resp, "stop_reason", None),
                  "stop_details": stop_details,
                  "model": getattr(resp, "model", spec.id)},
    )


async def _call_openrouter(spec: ModelSpec, system: str, user: str, max_tokens: int) -> ChatResult:
    client = _openrouter()
    t0 = time.monotonic()
    resp = await client.chat.completions.create(
        model=spec.id,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        extra_body={"usage": {"include": True}},
    )
    latency = int((time.monotonic() - t0) * 1000)
    choice = resp.choices[0] if resp.choices else None
    text = (choice.message.content or "") if choice and choice.message else ""
    usage = resp.usage
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    # OpenRouter reports the actual charge in usage.cost when usage.include is set.
    reported = None
    if usage is not None:
        reported = getattr(usage, "cost", None)
        if reported is None and getattr(usage, "model_extra", None):
            reported = usage.model_extra.get("cost")
    cost = float(reported) if reported is not None else compute_cost(spec, tokens_in, tokens_out)
    return ChatResult(
        text=text, tokens_in=tokens_in, tokens_out=tokens_out,
        cost_usd=cost, latency_ms=latency,
        raw_meta={"response_id": getattr(resp, "id", None),
                  "finish_reason": getattr(choice, "finish_reason", None) if choice else None,
                  "model": getattr(resp, "model", spec.id)},
    )


async def chat(model_id: str, system: str, user: str, max_tokens: int | None = None) -> ChatResult:
    """One chat call with per-provider concurrency limits, retries and cost."""
    spec = resolve_model(model_id)
    if spec.provider == "mock":
        raise ProviderError("mock models never reach providers.chat (handled in agent.py)")
    limit = max_tokens or spec.max_tokens
    call = _call_anthropic if spec.provider == "anthropic" else _call_openrouter

    last_exc: Exception | None = None
    async with _get_semaphore(spec.provider):
        for attempt in range(MAX_ATTEMPTS):
            try:
                result = await asyncio.wait_for(call(spec, system, user, limit), CALL_TIMEOUT_S + 10)
                # A fully empty response (no text, zero output tokens) is a
                # transient service failure, not a model reply: retry it like a
                # 5xx, identically for every provider. If it is still empty on
                # the last attempt, return it and let the parsing ladder's
                # normal retry/safe-default path handle it (DECISIONS.md #37).
                if not result.text and result.tokens_out == 0 and attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep((2 ** attempt) + random.random())
                    continue
                return result
            except Exception as exc:  # noqa: BLE001 - classified below
                last_exc = exc
                if isinstance(exc, ProviderError) or not _is_retryable(exc):
                    break
                if attempt < MAX_ATTEMPTS - 1:
                    delay = (2 ** attempt) + random.random()
                    await asyncio.sleep(delay)
    if last_exc is None:
        return result  # empty on every attempt; parse ladder takes over
    status = _status_code(last_exc) if last_exc else None
    raise ProviderError(
        f"{spec.provider} call for {spec.id} failed"
        + (f" with status {status}" if status else "")
        + f": {type(last_exc).__name__}: {last_exc}"
    ) from last_exc


async def check_openrouter_ids(model_ids: list[str]) -> dict[str, bool]:
    """Check ids against OpenRouter's /models endpoint. Returns id -> available."""
    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get("https://openrouter.ai/api/v1/models")
        resp.raise_for_status()
        available = {m["id"] for m in resp.json().get("data", [])}
    return {mid: mid in available for mid in model_ids}
