"""The parsing ladder (benchmark spec section 4.3) as pure functions.

parse_agent_output(text) -> (obj | None, stage | None, error | None)

Stages (stop at the first success):
  1. strip <think>/<thinking> blocks (always applied, not a stage by itself)
  2. json.loads on the whole stripped text
  3. remove markdown code fences, try again
  4. extract the first balanced {...} object (string-aware), try again
  5. light repair on that object only (trailing commas, smart quotes), try again

Steps 6 (one retry) and 7 (safe default) live in agent.py, not here.
"""

from __future__ import annotations

import json
import re

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*[ \t]*\n?")
_SMART_QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'"}
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def strip_think_blocks(text: str) -> str:
    return _THINK_RE.sub("", text)


def remove_code_fences(text: str) -> str:
    return _FENCE_RE.sub("", text)


def first_balanced_object(text: str) -> str | None:
    """Return the first balanced {...} substring using string-aware brace matching."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def light_repair(text: str) -> str:
    for smart, straight in _SMART_QUOTES.items():
        text = text.replace(smart, straight)
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _try_load(text: str) -> dict | None:
    try:
        # strict=False accepts raw control characters (e.g. newlines) inside
        # strings, a very common weak-model artifact. Applied identically to
        # every model (DECISIONS.md #27).
        obj = json.loads(text, strict=False)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def parse_agent_output(text: str) -> tuple[dict | None, int | None, str | None]:
    """Parse one model reply into a JSON object. Never raises."""
    if not text or not text.strip():
        return None, None, "empty output"

    stripped = strip_think_blocks(text).strip()
    if not stripped:
        return None, None, "output contained only a thinking block"

    obj = _try_load(stripped)
    if obj is not None:
        return obj, 2, None

    unfenced = remove_code_fences(stripped).strip()
    obj = _try_load(unfenced)
    if obj is not None:
        return obj, 3, None

    candidate = first_balanced_object(unfenced)
    if candidate is None:
        return None, None, "no JSON object found in the reply"
    obj = _try_load(candidate)
    if obj is not None:
        return obj, 4, None

    obj = _try_load(light_repair(candidate))
    if obj is not None:
        return obj, 5, None

    return None, None, "the reply's JSON object could not be parsed even after repair"


def coerce_number(value) -> float | None:
    """Coerce a JSON value to a number. Handles '20', '$450', '1,200'. None if impossible."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
