"""Shared helpers for the asymbench tests: scripted agents with no model calls."""

from __future__ import annotations

import asyncio
import json

import asymbench.agent as agent_mod
from asymbench.providers import ChatResult


def run(coro):
    return asyncio.run(coro)


def script_calls(monkeypatch, fn):
    """Patch asymbench.agent._call_model so every turn is served by fn.

    fn(agent, user_message, obs_data, ctx, attempt) -> str (the raw model text).
    """
    async def fake_call(agent, user_message, ctx, obs_data, attempt):
        text = fn(agent, user_message, obs_data or {}, ctx, attempt)
        return ChatResult(text=text, tokens_in=0, tokens_out=0, cost_usd=0.0,
                          latency_ms=0, raw_meta={"scripted": True})
    monkeypatch.setattr(agent_mod, "_call_model", fake_call)


def reply(action: dict, message: str = "", notes: str = "") -> str:
    return json.dumps({"private_notes": notes, "message": message, "action": action})


def make_episode_dict(task: str, seed: int, counterpart: str, is_control: bool,
                      fields: dict, test_model: str = "m", condition: dict | None = None,
                      status: str = "done", run_id: str = "r1", has_mock: bool = False) -> dict:
    """Synthetic episode row for metrics tests."""
    base_fields = {
        "share": 0.5, "principal_value": 0.5, "attempt_events": 0, "attempt_any": False,
        "success_any": False, "harm": 0.0, "gray_events": 0, "disclosure_rate": None,
        "counterpart_misconduct": False, "cp_indicators": {}, "survey_rating": 3,
        "detected": False, "detection_turn": None, "recognized": False,
        "attempts_before_recognition": None, "attempts_after_recognition": None,
        "turns_before_recognition": None, "turns_after_recognition": None,
        "eval_aware": False, "cp_invalid_rate": 0.0, "test_invalid_rate": 0.0,
        "excluded": False, "judge_failed": False,
    }
    base_fields.update(fields)
    return {
        "task": task, "seed": seed, "counterpart_model": counterpart,
        "is_control": is_control, "condition": condition or
        {"instruction": "neutral", "oversight": "none", "label": "none"},
        "status": status, "fields": base_fields, "test_model": test_model,
        "run_id": run_id, "has_mock": has_mock,
    }
