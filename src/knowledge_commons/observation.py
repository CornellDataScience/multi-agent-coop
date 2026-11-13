"""The firewall: the ONLY path from ground truth to an agent.

Builders take the full truth (this round's code, past ``RoundRecord``s, this
round's sends) and return a ``KCObservation`` holding only what the agent may
know under its information condition (SPEC §5). Nothing here exposes
``max_rounds``, other agents' digits before the reveal, messages between
other pairs, other agents' guesses, or other agents' points. Under
``no_memory`` even the round number is hidden (``round`` is None).
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .scoring import SEND_KINDS, classify_send

if TYPE_CHECKING:
    from .config import KCConfig
    from .events import RoundRecord


@dataclass(frozen=True)
class KCObservation:
    agent_id: int
    phase: str  # "message" | "guess"
    round: int | None  # None under no_memory: every round looks like the first
    n_agents: int
    pot_size: float
    group_bonus: int
    bonus_threshold: int
    alpha: float
    allow_withhold: bool  # False: must send a digit to every other agent
    info_condition: str
    my_position: int  # == agent_id
    my_digit: int
    received: dict[int, int | None] | None  # guess phase only: sender -> digit
    history: list[dict]  # past rounds, filtered by info_condition
    reputation: dict[int, dict] | None  # public_reputation only

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KCRulesObservation:
    """What an agent sees for the pre-game comprehension check: the rules and
    payoff parameters only. No digit, no round, no history, no round limit."""

    agent_id: int
    n_agents: int
    pot_size: float
    group_bonus: int
    bonus_threshold: int
    alpha: float
    allow_withhold: bool

    def to_dict(self) -> dict:
        return asdict(self)


def build_rules_obs(cfg: "KCConfig", agent_id: int) -> KCRulesObservation:
    return KCRulesObservation(agent_id=agent_id, n_agents=cfg.n_agents,
                              pot_size=cfg.pot_size, group_bonus=cfg.group_bonus,
                              bonus_threshold=cfg.bonus_threshold, alpha=cfg.alpha,
                              allow_withhold=cfg.allow_withhold)


def _history_entry(rec: "RoundRecord", agent_id: int) -> dict:
    """One past round as this agent saw it: its own sends, what it received,
    its own guess and points, and the public reveal."""
    return {
        "round": rec.round,
        "code": list(rec.code),
        "sent": dict(rec.message_actions[agent_id].sends),
        "received": {j: act.sends.get(agent_id) for j, act in sorted(rec.message_actions.items())
                     if j != agent_id},
        "my_guess": list(rec.guess_actions[agent_id].guess),
        "solved": bool(rec.solved[agent_id]),
        "points": rec.points[agent_id],
        "n_solvers": rec.n_solvers,
        "bonus": rec.bonus,
    }


def compute_reputation(past_rounds: list["RoundRecord"], n_agents: int) -> dict[int, dict]:
    """Ground-truth share of each agent's past dyad-rounds (all recipients)
    that were truthful / withheld / lie. Rates are 0.0 when ``n == 0``."""
    rep: dict[int, dict] = {}
    for j in range(n_agents):
        counts = dict.fromkeys(SEND_KINDS, 0)
        for rec in past_rounds:
            for d in rec.message_actions[j].sends.values():
                counts[classify_send(d, rec.code[j])] += 1
        n = sum(counts.values())
        rep[j] = {k: (counts[k] / n if n else 0.0) for k in SEND_KINDS}
        rep[j]["n"] = n
    return rep


def _build(cfg: "KCConfig", phase: str, round_no: int, agent_id: int, code, past_rounds,
           received: dict[int, int | None] | None) -> KCObservation:
    info = cfg.info_condition
    if info == "no_memory":
        history: list[dict] = []
    else:
        history = [_history_entry(r, agent_id) for r in past_rounds]
    reputation = compute_reputation(past_rounds, cfg.n_agents) if info == "public_reputation" else None
    return KCObservation(
        agent_id=agent_id,
        phase=phase,
        round=None if info == "no_memory" else round_no,
        n_agents=cfg.n_agents,
        pot_size=cfg.pot_size,
        group_bonus=cfg.group_bonus,
        bonus_threshold=cfg.bonus_threshold,
        alpha=cfg.alpha,
        allow_withhold=cfg.allow_withhold,
        info_condition=info,
        my_position=agent_id,
        my_digit=int(code[agent_id]),
        received=received,
        # Deep copy so an agent mutating its observation can't touch the log.
        history=copy.deepcopy(history),
        reputation=reputation,
    )


def build_message_obs(cfg: "KCConfig", round_no: int, agent_id: int, code,
                      past_rounds: list["RoundRecord"]) -> KCObservation:
    return _build(cfg, "message", round_no, agent_id, code, past_rounds, None)


def build_guess_obs(cfg: "KCConfig", round_no: int, agent_id: int, code,
                    past_rounds: list["RoundRecord"],
                    sends_this_round: dict[int, dict[int, int | None]]) -> KCObservation:
    """``sends_this_round`` is the full sender -> {recipient -> digit} map;
    only the column addressed to ``agent_id`` is kept."""
    received = {j: sends.get(agent_id) for j, sends in sorted(sends_this_round.items()) if j != agent_id}
    return _build(cfg, "guess", round_no, agent_id, code, past_rounds, received)
