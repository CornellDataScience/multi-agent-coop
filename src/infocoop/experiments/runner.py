"""Runs experiments: loops over trials, logs one JSONL row per round/agent.

Never constructs an environment or calls an LLM itself -- it only drives
whatever FishermansDilemmaEnv an injected factory builds.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable

from .configs import ExperimentConfig, trial_seed
from .interfaces import FishermansDilemmaEnv

# ASSUMPTION: factory takes the config and returns one env, reused (via
# .reset()) across trials. src/infocoop/main.py (teammate-owned) supplies
# this; tell us if the real env needs a different construction signature.
EnvFactory = Callable[[ExperimentConfig], FishermansDilemmaEnv]


def run_experiment(config: ExperimentConfig, env_factory: EnvFactory) -> Path:
    """Run all trials for one condition, writing rows.jsonl and config.json.

    Returns the output directory used.
    """
    out_dir = Path(config.output_dir) / config.experiment_name / config.condition_name
    out_dir.mkdir(parents=True, exist_ok=True)

    config_path = out_dir / "config.json"
    config_path.write_text(json.dumps(dataclasses.asdict(config), indent=2))

    env = env_factory(config)
    rows_path = out_dir / "rows.jsonl"
    with rows_path.open("w") as f:
        for trial_id in range(config.num_trials):
            _run_trial(config, env, trial_id, f)

    return out_dir


def _run_trial(config: ExperimentConfig, env: FishermansDilemmaEnv, trial_id: int, f) -> None:
    env.reset(trial_seed(config, trial_id))
    running_totals = {agent_id: 0 for agent_id in range(config.num_agents)}

    round_num = 0
    while not env.is_over():
        result = env.run_round()
        for agent_result in result.agents:
            running_totals[agent_result.agent_id] += agent_result.received_take
            row = {
                "experiment_name": config.experiment_name,
                "condition_name": config.condition_name,
                "trial_id": trial_id,
                "round": round_num,
                "agent_id": agent_result.agent_id,
                "model": config.model_name,
                "pool_before": result.pool_before,
                "requested_take": agent_result.requested_take,
                "received_take": agent_result.received_take,
                # None (missing) if the environment couldn't parse the
                # broadcast -- we never guess a value here.
                "claimed_take": agent_result.claimed_take,
                "raw_broadcast": agent_result.raw_broadcast,
                "reasoning": agent_result.reasoning,
                "pool_after": result.pool_after,
                "running_total": running_totals[agent_result.agent_id],
            }
            f.write(json.dumps(row) + "\n")
        round_num += 1
