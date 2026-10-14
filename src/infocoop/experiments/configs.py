# Defaults for unsettled game rules (not yet specified by teammates'
# src/infocoop/games / src/infocoop/information code). The real environment
# owns enforcing these; this is only what the harness assumes when
# interpreting logged rows and designing conditions:
#   - If total requests exceed the pool: split proportionally among requesters.
#   - The remaining pool doubles after broadcasts each round, with no cap.
#   - Agents can see the true pool size (full transparency).
#   - Broadcasts are simultaneous (no agent sees another's before its own).
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExperimentConfig:
    """Everything needed to run one experimental condition end-to-end.

    condition_settings is passed through untouched to the environment
    factory (e.g. which information policy the agents get); the runner
    never inspects it.
    """

    experiment_name: str
    condition_name: str
    condition_settings: dict[str, Any] = field(default_factory=dict)
    num_agents: int = 3
    max_rounds: int = 10
    initial_pool_size: int = 100
    model_name: str = "llama3.1:8b"
    temperature: float = 0.7
    num_trials: int = 10
    base_seed: int = 0
    output_dir: str = "results"


def trial_seed(config: ExperimentConfig, trial_id: int) -> int:
    """Deterministic per-trial seed derived from the config's base seed."""
    return config.base_seed + trial_id


# Experiment conditions to run. Add more here as information policies /
# game variants teammates build become available.
EXPERIMENTS: list[ExperimentConfig] = [
    ExperimentConfig(
        experiment_name="baseline",
        condition_name="full_information",
        condition_settings={},
    ),
    ExperimentConfig(
        experiment_name="baseline",
        condition_name="no_broadcast_history",
        condition_settings={"show_broadcast_history": False},
    ),
]
