from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BeautyContestObservation:
    agent_id: int
    round: int
    n_agents: int
    history: list[dict]


class BeautyContestAgent(Protocol):
    agent_id: int

    def choose(self, observation: BeautyContestObservation) -> int: ...


class FixedPickAgent:
    """Simple deterministic player, useful for baselines and examples."""

    def __init__(self, agent_id: int, pick: int = 50):
        self.agent_id = agent_id
        self.pick = pick

    def choose(self, observation: BeautyContestObservation) -> int:
        return self.pick


class OllamaBeautyContestAgent:
    """Ollama-backed player that chooses one number from 1 through 100."""

    def __init__(self, agent_id: int, model: str, temperature: float = 0.7,
                 seed: int | None = None, chat_fn=None):
        self.agent_id = agent_id
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self._chat = chat_fn or self._ollama_chat

    @staticmethod
    def _ollama_chat(**kwargs):
        import ollama
        return ollama.chat(**kwargs)

    def choose(self, observation: BeautyContestObservation) -> int:
        prompt = (
            "Play a Keynesian beauty contest. Choose one integer from 1 to 100. "
            "The player closest to 0.85 times the mean of all players' choices wins this round. "
            "You receive points by closeness rank: 10, 7, 5, 3, 0. Choose strategically to "
            "maximize your cumulative points over repeated rounds. Choices are simultaneous.\n"
            f"You are player {observation.agent_id}; this is round {observation.round} of 10.\n"
            f"Previous rounds: {json.dumps(observation.history)}\n"
            'Reply only as JSON: {"pick": 1}. /no_think'
        )
        last_content = ""
        for token_limit in (128, 256):
            options = {"temperature": self.temperature, "num_predict": token_limit}
            if self.seed is not None:
                options["seed"] = self.seed
            response = self._chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options=options,
                think=False,
                format={"type": "object", "properties": {"pick": {"type": "integer"}},
                        "required": ["pick"]},
            )
            try:
                message = response["message"]
                last_content = message["content"] or ""
            except (KeyError, TypeError):
                last_content = ""
            if last_content:
                match = re.search(r'\{\s*"pick"\s*:\s*(\d+)\s*\}', last_content)
                if match:
                    return int(match.group(1))
        raise ValueError(
            f"Ollama model {self.model!r} returned no valid JSON pick after retry; "
            f"last response content was {last_content!r}"
        )


@dataclass
class BeautyContestGame:
    n_agents: int = 5
    max_rounds: int = 10
    target_multiplier: float = 0.85
    points_by_rank: tuple[int, ...] = (10, 7, 5, 3, 0)
    min_pick: int = 1
    max_pick: int = 100

    def __post_init__(self) -> None:
        if self.n_agents < 2:
            raise ValueError("n_agents must be at least 2")
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        if len(self.points_by_rank) != self.n_agents:
            raise ValueError("points_by_rank must have one score per agent")
        if self.min_pick > self.max_pick:
            raise ValueError("min_pick must be <= max_pick")

    def run(self, agents: list[BeautyContestAgent], seed: int = 0,
            condition: str = "keynesian_beauty_contest", progress=None) -> dict:
        if len(agents) != self.n_agents:
            raise ValueError(f"expected {self.n_agents} agents, got {len(agents)}")
        if sorted(a.agent_id for a in agents) != list(range(self.n_agents)):
            raise ValueError("agent IDs must be unique and range from 0 to n_agents-1")
        ordered = sorted(agents, key=lambda a: a.agent_id)
        totals = {a.agent_id: 0 for a in ordered}
        rounds = []
        for round_no in range(1, self.max_rounds + 1):
            history = [dict(r) for r in rounds]
            obs = [BeautyContestObservation(a.agent_id, round_no, self.n_agents, history)
                   for a in ordered]
            picks = {}
            for agent, observation in zip(ordered, obs):
                if progress is not None:
                    progress(round_no, agent.agent_id)
                picks[agent.agent_id] = agent.choose(observation)
            if any(type(p) is not int or not self.min_pick <= p <= self.max_pick for p in picks.values()):
                raise ValueError(f"each pick must be an integer from {self.min_pick} to {self.max_pick}")
            mean = sum(picks.values()) / self.n_agents
            target = self.target_multiplier * mean
            # Exact ties share rank; deterministic player ID breaks ties for points.
            ranked = sorted(picks, key=lambda i: (abs(picks[i] - target), i))
            points = {i: self.points_by_rank[rank] for rank, i in enumerate(ranked)}
            for i, score in points.items():
                totals[i] += score
            rounds.append({"round": round_no, "picks": picks, "mean": mean,
                           "target": target, "distance": {i: abs(picks[i] - target) for i in picks},
                           "round_ranking": ranked, "points": points})
        ranking = sorted(totals, key=lambda i: (-totals[i], i))
        return {"meta": {"record": "meta", "condition": condition, "seed": seed,
                         "config": {"n_agents": self.n_agents, "max_rounds": self.max_rounds,
                                    "target_multiplier": self.target_multiplier,
                                    "points_by_rank": list(self.points_by_rank),
                                    "min_pick": self.min_pick, "max_pick": self.max_pick}},
                "rounds": rounds, "total_points": totals, "final_ranking": ranking,
                "winner": ranking[0]}

    @staticmethod
    def write_jsonl(result: dict, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            fh.write(json.dumps(result["meta"]) + "\n")
            for round_result in result["rounds"]:
                fh.write(json.dumps({"record": "round", **round_result}) + "\n")
            fh.write(json.dumps({"record": "final", "total_points": result["total_points"],
                                 "final_ranking": result["final_ranking"],
                                 "winner": result["winner"]}) + "\n")
        return path
