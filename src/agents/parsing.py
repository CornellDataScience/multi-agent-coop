from __future__ import annotations

import json
import re


class ParseError(ValueError):
    """Raised when model output cannot be parsed into a valid action."""


def _as_nonneg_int(value) -> int:
    if isinstance(value, bool):  # bool is an int subclass; reject it
        raise ParseError(f"expected integer, got bool: {value!r}")
    if isinstance(value, int):
        n = value
    elif isinstance(value, float) and value.is_integer():
        n = int(value)
    elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        n = int(value.strip())
    else:
        raise ParseError(f"expected integer, got {value!r}")
    if n < 0:
        raise ParseError(f"expected non-negative integer, got {n}")
    return n


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v == "yes":
            return True
        if v == "no":
            return False
    raise ParseError(f"expected 'yes' or 'no', got {value!r}")


def _extract_json_object(text: str) -> dict:
    if not text:
        raise ParseError("empty output")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ParseError("no JSON object found")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError("expected a JSON object")
    return data


def parse_first_phase_output(text: str) -> tuple[int, int]:
    """Parse ``{"first_announcement": int, "first_take": int}`` out of model
    text. Returns ``(first_announcement, first_take)``. Raises ``ParseError``
    on anything invalid. Neither value is clamped here -- the environment
    clamps ``first_take`` to ``[0, pool]`` at resolution.
    """
    data = _extract_json_object(text)
    if "first_announcement" not in data:
        raise ParseError("missing 'first_announcement' field")
    if "first_take" not in data:
        raise ParseError("missing 'first_take' field")
    return _as_nonneg_int(data["first_announcement"]), _as_nonneg_int(data["first_take"])


def parse_second_phase_output(text: str) -> tuple[bool, int, int]:
    """Parse ``{"revise": "yes"|"no", "second_announcement": int,
    "final_take": int}`` out of model text. Returns
    ``(revise, second_announcement, final_take)``. Raises ``ParseError`` on
    anything invalid. ``final_take`` is NOT clamped here -- the environment
    clamps to ``[0, pool]`` and applies the overdraw rule at resolution.
    """
    data = _extract_json_object(text)
    for field_name in ("revise", "second_announcement", "final_take"):
        if field_name not in data:
            raise ParseError(f"missing {field_name!r} field")
    revise = _as_bool(data["revise"])
    second_announcement = _as_nonneg_int(data["second_announcement"])
    final_take = _as_nonneg_int(data["final_take"])
    return revise, second_announcement, final_take
