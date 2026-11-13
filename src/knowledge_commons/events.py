from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MessageAction:
    """What one agent sends this round: recipient id -> digit, or None to
    send nothing. Every other agent must be present (the environment fills
    gaps with None)."""

    sends: dict[int, int | None]
    raw_output: str | None = None
    parse_status: str = "scripted"  # scripted | ok | retry_ok | fallback
    served_by: str | None = None
    usage: dict = field(default_factory=dict)


@dataclass
class GuessAction:
    """One agent's full guess of the code, plus optional confidence that the
    guess is fully correct (used only for calibration metrics)."""

    guess: tuple[int, ...]
    confidence: float | None = None
    raw_output: str | None = None
    parse_status: str = "scripted"
    served_by: str | None = None
    usage: dict = field(default_factory=dict)


@dataclass
class RoundRecord:
    """Ground truth for one resolved round. Lives in the log only; agents
    see slices of it through ``observation.py``."""

    round: int
    code: tuple[int, ...]
    message_actions: dict[int, MessageAction]
    guess_actions: dict[int, GuessAction]
    solved: dict[int, bool]
    n_solvers: int
    bonus: bool
    points: dict[int, int]
