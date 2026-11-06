from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FirstPhaseAction:
    """One agent's first-phase move: a public first announcement plus an
    independent private first take. The overdraw rule is never applied to
    ``first_take`` and it never affects the pool or scores -- it exists only
    so the environment can measure how first takes diverge from first
    announcements.
    """

    first_announcement: int
    first_take: int
    raw_output: str | None = None
    parse_status: str = "ok"  # "ok" | "retry_ok" | "fallback"
    served_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "first_announcement": self.first_announcement,
            "first_take": self.first_take,
            "raw_output": self.raw_output,
            "parse_status": self.parse_status,
            "served_by": self.served_by,
        }


@dataclass(frozen=True)
class SecondPhaseAction:
    """One agent's second-phase move, made after seeing every agent's first
    announcement (but no first takes and no pool result from the first take).

    ``revise`` is the agent's explicit yes/no decision. ``second_announcement``
    is made regardless of that decision. ``final_take`` is the private take
    that actually counts; the overdraw rule applies to it.
    """

    revise: bool
    second_announcement: int
    final_take: int
    raw_output: str | None = None
    parse_status: str = "ok"
    served_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "revise": self.revise,
            "second_announcement": self.second_announcement,
            "final_take": self.final_take,
            "raw_output": self.raw_output,
            "parse_status": self.parse_status,
            "served_by": self.served_by,
        }


@dataclass(frozen=True)
class RoundResult:
    """Ground-truth record of one resolved round.

    ``first_takes`` never affect the pool or scores. ``final_takes`` are the
    requested (true) takes that count; ``granted`` is what was actually
    applied after the overdraw rule. They differ only in an over-request round.
    """

    round: int
    pool_before: int
    first_announcements: dict[int, int]
    first_takes: dict[int, int]
    revisions: dict[int, bool]
    second_announcements: dict[int, int]
    final_takes: dict[int, int]
    granted: dict[int, int]
    pool_after: int  # after final takes, before growth
    pool_next: int  # after growth (0 => collapse)
    first_actions: dict[int, FirstPhaseAction] = field(default_factory=dict)
    second_actions: dict[int, SecondPhaseAction] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "pool_before": self.pool_before,
            "pool_after": self.pool_after,
            "pool_next": self.pool_next,
            "first_announcements": dict(self.first_announcements),
            "first_takes": dict(self.first_takes),
            "revisions": dict(self.revisions),
            "second_announcements": dict(self.second_announcements),
            "final_takes": dict(self.final_takes),
            "granted": dict(self.granted),
            "first_actions": {i: a.to_dict() for i, a in self.first_actions.items()},
            "second_actions": {i: a.to_dict() for i, a in self.second_actions.items()},
        }
