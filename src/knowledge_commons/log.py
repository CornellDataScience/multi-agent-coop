"""JSONL game log (ARCHITECTURE §3.8). Metrics read games only through
``load_game``, never from live objects."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import KCConfig
from .events import RoundRecord
from .observation import KCObservation
from .scoring import utilities

SCHEMA_VERSION = 1


def _str_keys(obj):
    """Recursively turn int dict keys into strings (JSON needs them anyway;
    doing it explicitly keeps the in-memory records equal to the file)."""
    if isinstance(obj, dict):
        return {str(k): _str_keys(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_str_keys(v) for v in obj]
    return obj


def _int_keys(obj):
    """Inverse of ``_str_keys`` for this schema: any dict whose keys are all
    digit strings is an agent-id map, so its keys become ints."""
    if isinstance(obj, dict):
        if obj and all(isinstance(k, str) and k.isdigit() for k in obj):
            return {int(k): _int_keys(v) for k, v in obj.items()}
        return {k: _int_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_int_keys(v) for v in obj]
    return obj


def _action_meta(action) -> dict:
    return {
        "raw_output": action.raw_output,
        "parse_status": action.parse_status,
        "served_by": action.served_by,
        "usage": dict(action.usage),
        "reason": action.reason,
    }


@dataclass
class KCGameLog:
    """Full ground truth of one game, owned by the environment."""

    config: KCConfig
    condition: str
    agents: list[dict]
    run_parameters: dict = field(default_factory=dict)
    rounds: list[RoundRecord] = field(default_factory=list)
    message_obs: list[dict[int, KCObservation]] = field(default_factory=list)
    guess_obs: list[dict[int, KCObservation]] = field(default_factory=list)
    comprehension: dict[int, dict] = field(default_factory=dict)  # agent id -> quiz result

    def add_round(self, rec: RoundRecord, message_obs: dict[int, KCObservation],
                  guess_obs: dict[int, KCObservation]) -> None:
        self.rounds.append(rec)
        self.message_obs.append(message_obs)
        self.guess_obs.append(guess_obs)

    def totals(self) -> dict[int, int]:
        totals = {i: 0 for i in range(self.config.n_agents)}
        for r in self.rounds:
            for i, p in r.points.items():
                totals[i] += p
        return totals

    def utilities(self) -> dict[int, float]:
        return utilities(self.totals(), self.config.alpha)

    def records(self) -> list[dict]:
        out = [{
            "record": "meta",
            "game": "knowledge_commons",
            "schema_version": SCHEMA_VERSION,
            "condition": self.condition,
            "seed": self.config.seed,
            "config": self.config.to_dict(),
            "agents": self.agents,
            "run_parameters": self.run_parameters,
        }]
        for i, quiz in sorted(self.comprehension.items()):
            out.append({"record": "comprehension", "agent": i, **quiz})
        for idx, r in enumerate(self.rounds):
            out.append({
                "record": "round",
                "round": r.round,
                "code": list(r.code),
                "sends": {i: a.sends for i, a in r.message_actions.items()},
                "guesses": {i: list(a.guess) for i, a in r.guess_actions.items()},
                "confidence": {i: a.confidence for i, a in r.guess_actions.items()},
                "solved": r.solved,
                "n_solvers": r.n_solvers,
                "bonus": r.bonus,
                "points": r.points,
                "actions": {
                    "message": {i: _action_meta(a) for i, a in r.message_actions.items()},
                    "guess": {i: _action_meta(a) for i, a in r.guess_actions.items()},
                },
                "observations": {
                    "message": {i: o.to_dict() for i, o in self.message_obs[idx].items()},
                    "guess": {i: o.to_dict() for i, o in self.guess_obs[idx].items()},
                },
            })
        out.append({"record": "end", "totals": self.totals(), "utilities": self.utilities()})
        return _str_keys(out)

    def write_jsonl(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for rec in self.records():
                fh.write(json.dumps(rec) + "\n")
        return path


def load_game(path: str | Path) -> dict:
    """Read a JSONL game. Returns ``{"meta", "comprehension", "rounds",
    "end"}`` with agent-id keys converted back to ints. ``comprehension`` maps
    agent id -> quiz record (empty for scripted agents and older logs).
    ``end`` is None for a truncated file."""
    meta: dict = {}
    comprehension: dict[int, dict] = {}
    rounds: list[dict] = []
    end: dict | None = None
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = _int_keys(json.loads(line))
            kind = rec.get("record")
            if kind == "meta":
                meta = rec
            elif kind == "comprehension":
                comprehension[rec["agent"]] = rec
            elif kind == "round":
                rounds.append(rec)
            elif kind == "end":
                end = rec
    return {"meta": meta, "comprehension": comprehension, "rounds": rounds, "end": end}
