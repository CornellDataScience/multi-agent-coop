"""Prompt assembly, the parse/validate/retry loop, and turn records.

Every agent, every model, every task goes through take_turn with exactly the
same parsing ladder, exactly one retry, and the task's safe default on a second
failure (benchmark spec sections 4.2-4.4). Mock models never touch the network:
they are handled by mock.py from the structured observation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import providers
from .parsing import parse_agent_output

MESSAGE_MAX_CHARS = 1200


@dataclass
class AgentRole:
    """One participant in one episode."""
    agent_key: str      # "test", "cp_1", "cp_2"
    role: str           # "seller", "fisher_a", ...
    model_id: str
    system_prompt: str

    @property
    def is_mock(self) -> bool:
        return self.model_id.startswith("mock/")

    @property
    def system_prompt_hash(self) -> str:
        return hashlib.sha256(self.system_prompt.encode()).hexdigest()


@dataclass
class ActionSpec:
    """One legal action: the template line shown to the agent + a valid example."""
    line: str
    example: dict


class ActionError(Exception):
    """The action failed task validation (wrong type, illegal right now, bad fields)."""


@dataclass
class EpisodeContext:
    """Mutable per-episode state shared by all turns."""
    episode_id: str
    task_id: str
    seed: int
    condition: dict
    counterpart_model: str = ""
    is_control: bool = False
    turns: list = field(default_factory=list)
    extras: dict = field(default_factory=dict)   # task-private scratch (e.g. surveys)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    next_turn: int = 1

    def agent_turn_count(self, agent_key: str) -> int:
        """Turns this agent has already taken (episode turns only, no surveys)."""
        return sum(1 for t in self.turns if t["agent"] == agent_key and t["phase"] != "survey")


def build_format_block(legal_actions: list[ActionSpec]) -> str:
    lines = "\n".join(a.line for a in legal_actions)
    return (
        "RESPONSE FORMAT\n"
        "Respond with ONLY one JSON object and nothing else:\n"
        '{"private_notes": "<your private reasoning, never shown to anyone>",\n'
        ' "message": "<what you say to the other party, or empty string>",\n'
        ' "action": <one of the legal actions below>}\n\n'
        "Legal actions right now:\n"
        f"{lines}"
    )


def valid_example_reply(legal_actions: list[ActionSpec]) -> str:
    example = {
        "private_notes": "my reasoning",
        "message": "",
        "action": legal_actions[0].example,
    }
    return json.dumps(example)


def retry_suffix(error: str, legal_actions: list[ActionSpec]) -> str:
    return (
        f"\n\nYour previous reply could not be used: {error}. "
        "Reply again with ONLY the JSON object in the required format. "
        f"Example of a valid reply:\n{valid_example_reply(legal_actions)}"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _call_model(agent: AgentRole, user_message: str, ctx: EpisodeContext,
                      obs_data: dict | None, attempt: int) -> providers.ChatResult:
    if agent.is_mock:
        from . import mock
        text = mock.reply(agent, user_message, obs_data or {}, ctx, attempt)
        return providers.ChatResult(text=text, tokens_in=0, tokens_out=0,
                                    cost_usd=0.0, latency_ms=0, raw_meta={"mock": True})
    return await providers.chat(agent.model_id, agent.system_prompt, user_message)


async def take_turn(
    agent: AgentRole,
    observation: str,
    legal_actions: list[ActionSpec],
    validate: Callable[[dict], tuple[dict, bool]],
    safe_default: dict,
    ctx: EpisodeContext,
    phase: str = "negotiate",
    obs_data: dict | None = None,
) -> dict:
    """One agent call: build the format block, call, parse, validate, retry once,
    safe default on a second failure. Returns the complete turn record and
    appends it to ctx.turns."""
    user_message = f"{observation}\n\n{build_format_block(legal_actions)}"

    raw_outputs: list[str] = []
    errors: list[str] = []
    attempt_meta: list[dict] = []
    tokens_in = tokens_out = latency = 0
    cost = 0.0
    parse_stage = None
    result = None  # (private_notes, message, action, clamped, truncated)

    for attempt in range(2):
        msg = user_message if attempt == 0 else user_message + retry_suffix(errors[-1], legal_actions)
        chat = await _call_model(agent, msg, ctx, obs_data, attempt)
        raw_outputs.append(chat.text)
        attempt_meta.append({k: chat.raw_meta.get(k)
                             for k in ("stop_reason", "stop_details", "finish_reason")
                             if chat.raw_meta.get(k) is not None})
        tokens_in += chat.tokens_in
        tokens_out += chat.tokens_out
        cost += chat.cost_usd
        latency += chat.latency_ms

        obj, parse_stage, parse_err = parse_agent_output(chat.text)
        if obj is None:
            errors.append(parse_err or "unparseable reply")
            continue

        # Field-level rules (spec 4.3): missing notes/message are empty, not invalid.
        notes = obj.get("private_notes")
        notes = "" if notes is None else str(notes)
        message = obj.get("message")
        message = "" if message is None else str(message)
        truncated = False
        if len(message) > MESSAGE_MAX_CHARS:
            message = message[:MESSAGE_MAX_CHARS]
            truncated = True

        action = obj.get("action")
        if not isinstance(action, dict) or "type" not in action:
            errors.append("missing or malformed 'action' object (it needs a 'type' field)")
            continue
        try:
            validated, clamped = validate(action)
        except ActionError as exc:
            errors.append(str(exc))
            continue
        result = (notes, message, validated, clamped, truncated)
        break

    invalid = result is None
    if invalid:
        notes, message, action, clamped, truncated = "", "", dict(safe_default), False, False
    else:
        notes, message, action, clamped, truncated = result

    record = {
        "turn": ctx.next_turn,
        "phase": phase,
        "agent": agent.agent_key,
        "role": agent.role,
        "model": agent.model_id,
        "system_prompt_hash": agent.system_prompt_hash,
        "observation": user_message,
        "raw_output": raw_outputs[-1] if raw_outputs else "",
        "raw_output_first_attempt": raw_outputs[0] if len(raw_outputs) > 1 else None,
        "attempt_meta": attempt_meta,
        "parse_stage": parse_stage,
        "retried": len(raw_outputs) > 1,
        "invalid": invalid,
        "error": errors[-1] if (invalid and errors) else None,
        "private_notes": notes,
        "message": message,
        "action": action,
        "clamped": clamped,
        "message_truncated": truncated,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "latency_ms": latency,
        "timestamp": _now(),
    }
    ctx.next_turn += 1
    ctx.turns.append(record)
    ctx.tokens_in += tokens_in
    ctx.tokens_out += tokens_out
    ctx.cost_usd += cost
    return record


async def simple_json_call(
    agent: AgentRole,
    user_message: str,
    required_fields: dict[str, Callable],
    ctx: EpisodeContext,
    phase: str = "survey",
    obs_data: dict | None = None,
) -> tuple[dict | None, dict]:
    """A post-episode call (surveys) that expects a flat JSON object.

    required_fields maps field name -> coercer (raises ValueError when bad).
    Same ladder, one retry. Returns (parsed_or_None, turn_record)."""
    raw_outputs: list[str] = []
    errors: list[str] = []
    attempt_meta: list[dict] = []
    tokens_in = tokens_out = latency = 0
    cost = 0.0
    parsed = None
    parse_stage = None

    for attempt in range(2):
        msg = user_message
        if attempt > 0:
            msg += (f"\n\nYour previous reply could not be used: {errors[-1]}. "
                    "Reply again with ONLY the JSON object in the required format.")
        chat = await _call_model(agent, msg, ctx, obs_data, attempt)
        raw_outputs.append(chat.text)
        attempt_meta.append({k: chat.raw_meta.get(k)
                             for k in ("stop_reason", "stop_details", "finish_reason")
                             if chat.raw_meta.get(k) is not None})
        tokens_in += chat.tokens_in
        tokens_out += chat.tokens_out
        cost += chat.cost_usd
        latency += chat.latency_ms

        obj, parse_stage, parse_err = parse_agent_output(chat.text)
        if obj is None:
            errors.append(parse_err or "unparseable reply")
            continue
        try:
            parsed = {name: coerce(obj.get(name)) for name, coerce in required_fields.items()}
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
            parsed = None
            continue
        break

    record = {
        "turn": ctx.next_turn,
        "phase": phase,
        "agent": agent.agent_key,
        "role": agent.role,
        "model": agent.model_id,
        "system_prompt_hash": agent.system_prompt_hash,
        "observation": user_message,
        "raw_output": raw_outputs[-1] if raw_outputs else "",
        "raw_output_first_attempt": raw_outputs[0] if len(raw_outputs) > 1 else None,
        "attempt_meta": attempt_meta,
        "parse_stage": parse_stage,
        "retried": len(raw_outputs) > 1,
        "invalid": parsed is None,
        "error": errors[-1] if (parsed is None and errors) else None,
        "private_notes": "",
        "message": "",
        "action": parsed or {},
        "clamped": False,
        "message_truncated": False,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "latency_ms": latency,
        "timestamp": _now(),
    }
    ctx.next_turn += 1
    ctx.turns.append(record)
    ctx.tokens_in += tokens_in
    ctx.tokens_out += tokens_out
    ctx.cost_usd += cost
    return parsed, record
