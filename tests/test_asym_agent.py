"""take_turn behavior: parsing ladder integration, field rules, one retry,
safe defaults, clamping, truncation. All with scripted model calls."""

import json

from asym_helpers import run, script_calls

from asymbench.agent import (ActionError, ActionSpec, AgentRole, EpisodeContext,
                             take_turn)
from asymbench.tasks.base import clamp_value, coerce_int_field, require_type

LEGAL = [ActionSpec('{"type": "take", "amount": <integer 0 to 20>} (example: {"type": "take", "amount": 5})',
                    {"type": "take", "amount": 5})]
SAFE = {"type": "take", "amount": 0}


def validate(action):
    require_type(action, ["take"])
    amount = coerce_int_field(action, "amount")
    amount, clamped = clamp_value(amount, 0, 20)
    return {"type": "take", "amount": amount}, clamped


def make(monkeypatch, replies):
    """replies: list of raw model texts, one per call."""
    calls = {"n": 0}

    def fn(agent, user_message, obs, ctx, attempt):
        text = replies[min(calls["n"], len(replies) - 1)]
        calls["n"] += 1
        return text
    script_calls(monkeypatch, fn)
    agent = AgentRole("test", "fisher", "s/x", "You are a fisher.")
    ctx = EpisodeContext(episode_id="a1", task_id="commons", seed=0, condition={})
    return agent, ctx, calls


def turn(agent, ctx):
    return run(take_turn(agent, "obs", LEGAL, validate, SAFE, ctx, phase="harvest"))


def test_happy_path(monkeypatch):
    agent, ctx, calls = make(monkeypatch, [
        '{"private_notes": "n", "message": "m", "action": {"type": "take", "amount": 7}}'])
    rec = turn(agent, ctx)
    assert rec["action"] == {"type": "take", "amount": 7}
    assert not rec["invalid"] and not rec["retried"] and rec["parse_stage"] == 2
    assert ctx.turns == [rec] and ctx.next_turn == 2


def test_number_as_string_coerced(monkeypatch):
    agent, ctx, _ = make(monkeypatch, [
        '{"message": "m", "action": {"type": "take", "amount": "12"}}'])
    rec = turn(agent, ctx)
    assert rec["action"]["amount"] == 12 and not rec["invalid"] and not rec["clamped"]
    assert rec["private_notes"] == ""  # missing field -> empty, not invalid


def test_clamped_out_of_range(monkeypatch):
    agent, ctx, _ = make(monkeypatch, [
        '{"action": {"type": "take", "amount": 50}}'])
    rec = turn(agent, ctx)
    assert rec["action"]["amount"] == 20 and rec["clamped"] and not rec["invalid"]


def test_message_truncated(monkeypatch):
    agent, ctx, _ = make(monkeypatch, [json.dumps(
        {"message": "x" * 1500, "action": {"type": "take", "amount": 1}})])
    rec = turn(agent, ctx)
    assert len(rec["message"]) == 1200 and rec["message_truncated"]


def test_retry_then_success(monkeypatch):
    agent, ctx, calls = make(monkeypatch, [
        "gibberish with no json at all",
        '{"action": {"type": "take", "amount": 3}}'])
    rec = turn(agent, ctx)
    assert calls["n"] == 2 and rec["retried"] and not rec["invalid"]
    assert rec["action"]["amount"] == 3
    assert rec["raw_output_first_attempt"] == "gibberish with no json at all"


def test_retry_prompt_contains_error_and_example(monkeypatch):
    seen = []

    def fn(agent, user_message, obs, ctx, attempt):
        seen.append(user_message)
        return "still broken" if attempt == 0 else '{"action": {"type": "take", "amount": 2}}'
    script_calls(monkeypatch, fn)
    agent = AgentRole("test", "fisher", "s/x", "p")
    ctx = EpisodeContext(episode_id="a2", task_id="commons", seed=0, condition={})
    run(take_turn(agent, "obs", LEGAL, validate, SAFE, ctx))
    assert "could not be used" in seen[1]
    assert '"take"' in seen[1]  # the valid example action appears


def test_double_failure_applies_safe_default(monkeypatch):
    agent, ctx, calls = make(monkeypatch, ["nope", "still nope"])
    rec = turn(agent, ctx)
    assert calls["n"] == 2
    assert rec["invalid"] and rec["action"] == SAFE and rec["message"] == ""
    assert rec["error"]


def test_illegal_action_type_is_invalid(monkeypatch):
    agent, ctx, _ = make(monkeypatch, [
        '{"action": {"type": "fly", "amount": 3}}'])
    rec = turn(agent, ctx)
    assert rec["invalid"] and rec["action"] == SAFE


def test_missing_action_is_invalid(monkeypatch):
    agent, ctx, _ = make(monkeypatch, ['{"message": "hello"}'])
    rec = turn(agent, ctx)
    assert rec["invalid"]


def test_format_block_in_observation(monkeypatch):
    seen = []

    def fn(agent, user_message, obs, ctx, attempt):
        seen.append(user_message)
        return '{"action": {"type": "take", "amount": 1}}'
    script_calls(monkeypatch, fn)
    agent = AgentRole("test", "fisher", "s/x", "p")
    ctx = EpisodeContext(episode_id="a3", task_id="commons", seed=0, condition={})
    run(take_turn(agent, "my observation", LEGAL, validate, SAFE, ctx))
    assert seen[0].startswith("my observation")
    assert "RESPONSE FORMAT" in seen[0]
    assert "Legal actions right now:" in seen[0]
    assert "private_notes" in seen[0]
