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


def parse_model_output(text: str, communication: bool) -> tuple[int, int | None]:
    """Parse ``{"take": int, "claimed_take": int}`` out of model text.

    Returns ``(take, claimed_take)``; ``claimed_take`` is ``None`` when
    communication is off. Raises ``ParseError`` on anything invalid. Takes are
    NOT clamped here — the environment clamps to ``[0, pool]`` at resolution.
    """
    if not text:
        raise ParseError("empty output")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ParseError("no JSON object found")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or "take" not in data:
        raise ParseError("missing 'take' field")

    take = _as_nonneg_int(data["take"])
    if not communication:
        return take, None
    if "claimed_take" not in data:
        raise ParseError("missing 'claimed_take' field")
    claimed = _as_nonneg_int(data["claimed_take"])
    return take, claimed
