from __future__ import annotations

from dataclasses import dataclass, field

from ..agents.prompt_variants import DEFAULT_VARIANT
from ..game.config import GameConfig


@dataclass(frozen=True)
class ExperimentConfig:
    """One experimental condition: a base game config + an agent lineup + the
    seeds to run. Each seed is one full game (run). ``prompt_variant`` names the
    LLM prompt wording; scripted agents ignore it."""

    name: str
    game: GameConfig
    agent_specs: list[dict] = field(default_factory=list)
    seeds: list[int] = field(default_factory=lambda: [0])
    prompt_variant: str = DEFAULT_VARIANT  # see agents/prompt_variants.py

def _scripted(take: str, claim: str = "honest") -> dict:
    return {"type": "scripted", "take_policy": take, "claim_policy": claim}


def _llm(**kwargs) -> dict:
    return {"type": "llm", **kwargs}


def _claude(**kwargs) -> dict:
    return {"type": "claude", **kwargs}


_BASE = GameConfig()  # defaults from specs.md §3.2


def _build() -> dict[str, ExperimentConfig]:
    conds: dict[str, ExperimentConfig] = {}

    # --- Main LLM conditions -------------------------------------------------
    conds["broadcast_unverified"] = ExperimentConfig(
        name="broadcast_unverified",
        game=_BASE,
        agent_specs=[_llm() for _ in range(_BASE.n_agents)],
        seeds=list(range(20)),  # LLM: repeat to capture variance (specs.md §5)
    )

    # Claude API (needs ANTHROPIC_API_KEY; billed per request).
    conds["broadcast_unverified_claude"] = ExperimentConfig(
        name="broadcast_unverified_claude",
        game=_BASE,
        agent_specs=[_claude() for _ in range(_BASE.n_agents)],
        seeds=list(range(20)),
    )

    # --- Scripted sanity checks (deterministic => 1 seed) --------------------
    conds["all_greedy"] = ExperimentConfig(
        name="all_greedy",
        game=_BASE,
        agent_specs=[_scripted("greedy", "honest") for _ in range(_BASE.n_agents)],
        seeds=[0],
    )
    conds["all_sustainable"] = ExperimentConfig(
        name="all_sustainable",
        game=_BASE,
        agent_specs=[_scripted("sustainable", "honest") for _ in range(_BASE.n_agents)],
        seeds=[0],
    )
    conds["all_honest"] = ExperimentConfig(
        name="all_honest",
        game=_BASE,
        agent_specs=[_scripted("fair", "honest") for _ in range(_BASE.n_agents)],
        seeds=[0],
    )
    conds["all_lie"] = ExperimentConfig(
        name="all_lie",
        game=_BASE,
        agent_specs=[_scripted("greedy", "always_lie") for _ in range(_BASE.n_agents)],
        seeds=[0],
    )
    # One greedy liar among sustainable honest agents.
    conds["one_defector"] = ExperimentConfig(
        name="one_defector",
        game=_BASE,
        agent_specs=(
            [_scripted("greedy", "underreport")]
            + [_scripted("sustainable", "honest") for _ in range(_BASE.n_agents - 1)]
        ),
        seeds=[0],
    )

    return conds


CONDITIONS = _build()


def get_condition(name: str) -> ExperimentConfig:
    if name not in CONDITIONS:
        raise KeyError(f"unknown condition {name!r}; known: {sorted(CONDITIONS)}")
    return CONDITIONS[name]
