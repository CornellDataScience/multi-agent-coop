"""Parse and validate model JSON for each phase (SPEC §6). Anything invalid
raises ``ParseError``; the agent retries once and then falls back."""
from __future__ import annotations

import json
import re


class ParseError(ValueError):
    """Model output could not be turned into a valid action."""


_DECODER = json.JSONDecoder()


def extract_json_object(text: str, key: str) -> dict:
    """First JSON object in ``text`` that has ``key``. Scans every ``{`` so
    JSON wrapped in prose or code fences still parses."""
    if not text or not text.strip():
        raise ParseError("empty output")
    first_obj = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = _DECODER.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            if key in obj:
                return obj
            first_obj = first_obj or obj
    if first_obj is None:
        raise ParseError("no JSON object found")
    raise ParseError(f"missing {key!r} field")


def _as_digit(value) -> int:
    """0-9 as int; also accepts a digit string or an integral float."""
    if isinstance(value, bool):
        raise ParseError(f"expected a digit, got bool {value!r}")
    if isinstance(value, int):
        n = value
    elif isinstance(value, float) and value.is_integer():
        n = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\s*\d\s*", value):
        n = int(value)
    else:
        raise ParseError(f"expected a digit 0-9, got {value!r}")
    if not 0 <= n <= 9:
        raise ParseError(f"digit out of range: {n}")
    return n


def parse_message_output(text: str, agent_id: int, n_agents: int) -> dict[int, int | None]:
    """``{"messages": {"<id>": digit | null, ...}}`` with every other agent
    exactly once. Returns recipient id -> digit or None."""
    data = extract_json_object(text, "messages")
    msgs = data["messages"]
    if not isinstance(msgs, dict):
        raise ParseError("'messages' must be an object")
    out: dict[int, int | None] = {}
    for k, v in msgs.items():
        if not re.fullmatch(r"\s*\d+\s*", str(k)):
            raise ParseError(f"bad recipient key {k!r}")
        j = int(k)
        if j in out:
            raise ParseError(f"recipient {j} listed twice")
        out[j] = None if v is None else _as_digit(v)
    expected = {j for j in range(n_agents) if j != agent_id}
    if set(out) != expected:
        raise ParseError(f"recipients {sorted(out)} != expected {sorted(expected)}")
    return {j: out[j] for j in sorted(out)}


def parse_guess_output(text: str, n_agents: int) -> tuple[tuple[int, ...], float | None]:
    """``{"guess": [d, ...], "confidence": p}``. ``confidence`` is optional;
    a missing or invalid one becomes None rather than failing the guess."""
    data = extract_json_object(text, "guess")
    guess = data["guess"]
    if not isinstance(guess, list):
        raise ParseError("'guess' must be a list")
    if len(guess) != n_agents:
        raise ParseError(f"guess has {len(guess)} digits, expected {n_agents}")
    digits = tuple(_as_digit(d) for d in guess)
    conf = data.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        conf = None
    return digits, (float(conf) if conf is not None else None)
