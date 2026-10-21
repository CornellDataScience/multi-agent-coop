from __future__ import annotations

import math


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def apportion(takes: dict[int, int], pool: int, rule: str = "proportional") -> dict[int, int]:
    """Resolve requested takes against the pool.

    If the total requested fits, everyone gets their take. Otherwise grant the
    *entire* pool split proportionally to requested takes, converted to integers
    by largest-remainder apportionment with ascending-agent-id tie-break. This
    conserves fish exactly (sum(granted) == pool) and is deterministic.

    Assumes each ``takes[i]`` is already clamped to ``[0, pool]``.
    """
    if rule != "proportional":
        raise ValueError(f"unsupported overdraw_rule: {rule!r}")

    ids = sorted(takes)
    total = sum(takes[i] for i in ids)

    if total <= pool:
        return {i: takes[i] for i in ids}
    if total == 0 or pool <= 0:
        return {i: 0 for i in ids}

    raw = {i: takes[i] * pool / total for i in ids}
    granted = {i: int(math.floor(raw[i])) for i in ids}
    remaining = pool - sum(granted.values())

    # Hand out the leftover units to the largest fractional parts; break ties by
    # ascending agent id so the result is reproducible.
    order = sorted(ids, key=lambda i: (-(raw[i] - math.floor(raw[i])), i))
    for i in order[:remaining]:
        granted[i] += 1
    return granted
