"""Round loop. Owns the code and all ground truth (SPEC §3, ARCHITECTURE §3.7)."""
from __future__ import annotations

import random

from .agents.base import KCAgent
from .config import KCConfig
from .events import GuessAction, MessageAction, RoundRecord
from .log import KCGameLog
from .observation import build_guess_obs, build_message_obs
from .scoring import round_points


def draw_codes(cfg: KCConfig) -> list[tuple[int, ...]]:
    """All codes for the game, drawn up front from the per-game RNG so the
    sequence depends only on the seed (not on agents, alpha, or info)."""
    rng = random.Random(cfg.seed)
    return [tuple(rng.randrange(10) for _ in range(cfg.n_agents)) for _ in range(cfg.max_rounds)]


def _is_digit(d) -> bool:
    return isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 9


def _sanitize_message(action: MessageAction, agent_id: int, n: int) -> MessageAction:
    """Drop sends to self, fill missing recipients with None, and turn any
    non-digit into None. LLM output is validated earlier, in parsing.py."""
    sends = {}
    for j in range(n):
        if j == agent_id:
            continue
        d = action.sends.get(j)
        sends[j] = d if _is_digit(d) else None
    action.sends = sends
    return action


def _sanitize_guess(action: GuessAction, n: int) -> GuessAction:
    """Pad/truncate to length n; any non-digit becomes 0."""
    g = list(action.guess)[:n] + [0] * max(0, n - len(action.guess))
    action.guess = tuple(d if _is_digit(d) else 0 for d in g)
    return action


class KCEnvironment:
    def __init__(self, cfg: KCConfig, agents: list[KCAgent], condition: str,
                 run_parameters: dict | None = None,
                 codes: list[tuple[int, ...]] | None = None):
        if len(agents) != cfg.n_agents:
            raise ValueError(f"expected {cfg.n_agents} agents, got {len(agents)}")
        if [a.agent_id for a in agents] != list(range(cfg.n_agents)):
            raise ValueError("agent ids must be 0..n_agents-1 in order")
        if codes is not None:  # tests only: hand-computable golden games
            if len(codes) < cfg.max_rounds:
                raise ValueError("codes override must cover every round")
            if any(len(c) != cfg.n_agents or not all(_is_digit(d) for d in c) for c in codes):
                raise ValueError("each code must have n_agents digits 0-9")
            self.codes = [tuple(c) for c in codes[: cfg.max_rounds]]
        else:
            self.codes = draw_codes(cfg)
        self.cfg = cfg
        self.agents = agents
        self.log = KCGameLog(config=cfg, condition=condition,
                             agents=[a.describe() for a in agents],
                             run_parameters=dict(run_parameters or {}))

    def play_round(self, round_no: int) -> RoundRecord:
        cfg, n = self.cfg, self.cfg.n_agents
        code = self.codes[round_no - 1]
        past = self.log.rounds

        # Message phase: build every observation before collecting any action.
        m_obs = {i: build_message_obs(cfg, round_no, i, code, past) for i in range(n)}
        m_act = {i: _sanitize_message(self.agents[i].send_messages(m_obs[i]), i, n) for i in range(n)}
        sends = {i: dict(a.sends) for i, a in m_act.items()}

        # Guess phase: same discipline.
        g_obs = {i: build_guess_obs(cfg, round_no, i, code, past, sends) for i in range(n)}
        g_act = {i: _sanitize_guess(self.agents[i].make_guess(g_obs[i]), n) for i in range(n)}

        solved = {i: g_act[i].guess == code for i in range(n)}
        points, n_solvers, bonus = round_points(solved, cfg)
        rec = RoundRecord(round=round_no, code=code, message_actions=m_act, guess_actions=g_act,
                          solved=solved, n_solvers=n_solvers, bonus=bonus, points=points)
        self.log.add_round(rec, m_obs, g_obs)
        return rec

    def run(self) -> KCGameLog:
        for round_no in range(len(self.log.rounds) + 1, self.cfg.max_rounds + 1):
            self.play_round(round_no)
        return self.log
