from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from ..agents.base import Agent
from ..agents.llm import OllamaAgent
from ..agents.prompt_variants import DEFAULT_VARIANT
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
    prompt_variant: str = DEFAULT_VARIANT,
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
            prompt_variant=prompt_variant,
            chat_fn=chat_fn,
        )
    raise ValueError(f"unknown agent type: {kind!r}")


def run_condition(
    exp: ExperimentConfig,
    out_dir: str | Path = "results",
    model_override: str | None = None,
    chat_fn: Callable | None = None,
    seeds: list[int] | None = None,
    prompt_variant: str | None = None,
) -> list[Path]:
    """Run one condition over its seeds, writing one JSONL game per seed.

    ``chat_fn`` is forwarded to LLM agents (inject a mock in tests).
    ``prompt_variant`` overrides the condition's prompt wording. Returns the
    list of written log paths.
    """
    out_dir = Path(out_dir)
    variant = prompt_variant or exp.prompt_variant
    uses_llm = any(s.get("type") == "llm" for s in exp.agent_specs)
    # Tag non-default prompts in the filename so variants don't overwrite each other.
    stem = f"{exp.name}_{variant}" if uses_llm and variant != DEFAULT_VARIANT else exp.name
    paths: list[Path] = []
    for seed in seeds if seeds is not None else exp.seeds:
        game = replace(exp.game, seed=seed)
        agents = [
            build_agent(i, exp.agent_specs[i], game, model_override, chat_fn, variant)
            for i in range(game.n_agents)
        ]
        log = Environment(
            game, agents, condition=exp.name, prompt_variant=variant if uses_llm else None
        ).run()
        path = log.write_jsonl(out_dir / f"{stem}_seed{seed}.jsonl")
        paths.append(path)
    return paths
