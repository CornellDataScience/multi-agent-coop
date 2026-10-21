from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from ..agents.base import Agent
from ..agents.llm import OllamaAgent
from ..agents.scripted import ScriptedAgent
from ..game.config import GameConfig
from ..game.environment import Environment
from .configs import ExperimentConfig


def build_agent(
    agent_id: int,
    spec: dict,
    game: GameConfig,
    model_override: str | None = None,
    chat_fn: Callable | None = None,
) -> Agent:
    kind = spec.get("type", "scripted")
    if kind == "scripted":
        return ScriptedAgent(
            agent_id,
            take_policy=spec.get("take_policy", "fair"),
            claim_policy=spec.get("claim_policy", "honest"),
            communication=game.communication,
            underreport_k=spec.get("underreport_k", 1),
        )
    if kind == "llm":
        return OllamaAgent(
            agent_id,
            model=model_override or spec.get("model", "llama3.1:8b"),
            temperature=spec.get("temperature", 0.7),
            seed=game.seed * 1000 + agent_id,  # distinct, reproducible per agent
            communication=game.communication,
            fallback_take=spec.get("fallback_take", 0),
            chat_fn=chat_fn,
        )
    raise ValueError(f"unknown agent type: {kind!r}")


def run_condition(
    exp: ExperimentConfig,
    out_dir: str | Path = "results",
    model_override: str | None = None,
    chat_fn: Callable | None = None,
    seeds: list[int] | None = None,
) -> list[Path]:
    """Run one condition over its seeds, writing one JSONL game per seed.

    ``chat_fn`` is forwarded to LLM agents (inject a mock in tests). Returns the
    list of written log paths.
    """
    out_dir = Path(out_dir)
    paths: list[Path] = []
    for seed in seeds if seeds is not None else exp.seeds:
        game = replace(exp.game, seed=seed)
        agents = [
            build_agent(i, exp.agent_specs[i], game, model_override, chat_fn)
            for i in range(game.n_agents)
        ]
        log = Environment(game, agents, condition=exp.name).run()
        path = log.write_jsonl(out_dir / f"{exp.name}_seed{seed}.jsonl")
        paths.append(path)
    return paths
