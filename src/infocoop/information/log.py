from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..game.config import GameConfig
from ..game.events import RoundResult

if TYPE_CHECKING:
    from .observation import Observation


@dataclass
class GameLog:
    """Full ground-truth history of one game, owned by the environment.

    Serialized as JSONL: the first line is a ``meta`` record (config, seed,
    condition, cooperative optimum); each subsequent line is one round,
    including every agent's observation entering that round.
    """

    config: GameConfig
    seed: int
    condition: str = "unnamed"
    rounds: list[RoundResult] = field(default_factory=list)
    observations: list[dict[int, "Observation"]] = field(default_factory=list)

    def add_round(self, result: RoundResult, observations: dict[int, "Observation"]) -> None:
        self.rounds.append(result)
        self.observations.append(observations)

    @property
    def scores(self) -> dict[int, int]:
        totals = {i: 0 for i in range(self.config.n_agents)}
        for r in self.rounds:
            for i, g in r.granted.items():
                totals[i] += g
        return totals

    def meta_record(self) -> dict:
        return {
            "record": "meta",
            "condition": self.condition,
            "seed": self.seed,
            "config": self.config.to_dict(),
            "cooperative_optimum": self.config.cooperative_optimum(),
        }

    def round_records(self) -> list[dict]:
        records = []
        for idx, r in enumerate(self.rounds):
            rec = {"record": "round", **r.to_dict()}
            obs = self.observations[idx] if idx < len(self.observations) else {}
            rec["observations"] = {i: o.to_dict() for i, o in obs.items()}
            records.append(rec)
        return records

    def write_jsonl(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            fh.write(json.dumps(self.meta_record()) + "\n")
            for rec in self.round_records():
                fh.write(json.dumps(rec) + "\n")
        return path


def _int_keys(d: dict | None) -> dict:
    if not d:
        return {}
    return {int(k): v for k, v in d.items()}


def load_game(path: str | Path) -> tuple[dict, list[dict]]:
    """Read a JSONL game file. Returns ``(meta, rounds)`` with agent-keyed dicts
    converted back to int keys. Metrics read games through this, never live
    state."""
    meta: dict = {}
    rounds: list[dict] = []
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("record") == "meta":
                meta = rec
                continue
            rec["takes"] = _int_keys(rec.get("takes"))
            rec["granted"] = _int_keys(rec.get("granted"))
            rec["claims"] = _int_keys(rec.get("claims"))
            rec["actions"] = _int_keys(rec.get("actions"))
            rounds.append(rec)
    return meta, rounds
