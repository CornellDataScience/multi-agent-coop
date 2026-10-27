from __future__ import annotations

import re

from ..information.observation import Observation
from .prompt_variants import DEFAULT_VARIANT, get_variant

# Prompt wording lives in prompt_variants.py; this module only fills it in.

_PLACEHOLDER = re.compile(r"\{(round|pool|n_agents|agent_id|growth|pool_if_untouched)\}")


def _fill(template: str, obs: Observation) -> str:
    values = {
        "round": obs.round,
        "pool": obs.pool,
        "n_agents": obs.n_agents,
        "agent_id": obs.agent_id,
        "growth": obs.growth_factor,
        "pool_if_untouched": obs.pool * obs.growth_factor,
    }
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)


def _history_lines(obs: Observation) -> str:
    if not obs.history:
        return "No rounds have been played yet."
    lines = []
    for h in obs.history:
        line = f"- Round {h['round']}: pool was {h['pool_before']}; you took {h['your_take']}"
        if obs.communication and "claims" in h:
            claims = ", ".join(f"fisherman {k} claimed {v}" for k, v in h["claims"].items())
            line += f"; others announced: {claims or 'none'}"
            line += f"; total actually taken from the pool: {h['inferred_total_take']}"
        lines.append(line)
    return "\n".join(lines)


def build_system_prompt(obs: Observation, variant: str = DEFAULT_VARIANT) -> str:
    return _fill(get_variant(variant)["system"], obs)


def build_user_prompt(obs: Observation, variant: str = DEFAULT_VARIANT) -> str:
    t = get_variant(variant)
    rules = t["rules"]
    if obs.communication:
        rules += t["comm"]
    schema = t["schema_comm"] if obs.communication else t["schema_nocomm"]

    return _fill(
        f"{rules}\n\n{t['state']}\n\nHistory so far:\n{_history_lines(obs)}\n\n{schema}",
        obs,
    )
