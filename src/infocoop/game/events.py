from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Action:
    """One agent's move for a round.

    ``take`` is the real, private choice (the "true take"). ``claimed_take`` is
    the public broadcast and may differ; it is ``None`` when communication is
    off. The remaining fields are for the ground-truth log.
    """

    take: int
    claimed_take: int | None = None
    raw_output: str | None = None
    message: str = ""
    parse_status: str = "ok"  # "ok" | "retry_ok" | "fallback"

    def to_dict(self) -> dict:
        return {
            "take": self.take,
            "claimed_take": self.claimed_take,
            "raw_output": self.raw_output,
            "message": self.message,
            "parse_status": self.parse_status,
        }


@dataclass(frozen=True)
class RoundResult:
    """Ground-truth record of one resolved round.

    ``takes`` are the requested (true) takes; ``granted`` are what was actually
    applied after the overdraw rule (and what counts toward score). They differ
    only in an over-request round.
    """

    round: int
    pool_before: int
    takes: dict[int, int]
    granted: dict[int, int]
    claims: dict[int, int | None]
    pool_after: int  # after takes, before growth
    pool_next: int  # after growth (0 => collapse)
    actions: dict[int, Action] = field(default_factory=dict)

    def total_take(self) -> int:
        return sum(self.granted.values())

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "pool_before": self.pool_before,
            "pool_after": self.pool_after,
            "pool_next": self.pool_next,
            "takes": dict(self.takes),
            "granted": dict(self.granted),
            "claims": dict(self.claims),
            "actions": {i: a.to_dict() for i, a in self.actions.items()},
        }
