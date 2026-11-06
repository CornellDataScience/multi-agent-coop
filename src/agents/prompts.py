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


def _announcements_line(announcements: dict[int, int]) -> str:
    if not announcements:
        return "none"
    return ", ".join(f"fisherman {k} announced {v}" for k, v in sorted(announcements.items()))


def _history_lines(obs: Observation) -> str:
    if not obs.history:
        return "No rounds have been played yet."
    lines = []
    for h in obs.history:
        revised = "revised" if h["your_revision"] else "did not revise"
        lines.append(
            f"- Round {h['round']}: pool was {h['pool_before']} -> {h['pool_after']} after "
            f"final takes. First announcements: {_announcements_line(h['first_announcements'])}. "
            f"Second announcements: {_announcements_line(h['second_announcements'])}. "
            f"You took {h['your_first_take']} on your first (uncounted) take and "
            f"{h['your_final_take']} on your final take ({revised} your plan); "
            f"you received {h['your_granted']} fish."
        )
    return "\n".join(lines)


def build_system_prompt(obs: Observation, variant: str = DEFAULT_VARIANT) -> str:
    return _fill(get_variant(variant)["system"], obs)


def build_first_user_prompt(obs: Observation, variant: str = DEFAULT_VARIANT) -> str:
    t = get_variant(variant)
    return _fill(
        f"{t['rules']}\n\n{t['state']}\n\nHistory so far:\n{_history_lines(obs)}\n\n"
        f"{t['schema_first']}",
        obs,
    )


def build_second_user_prompt(obs: Observation, variant: str = DEFAULT_VARIANT) -> str:
    t = get_variant(variant)
    situation = (
        f"Your first announcement this round was {obs.own_first_announcement} fish. "
        "Your own actual first take (private; nobody saw it, and it did not count) "
        f"was {obs.own_first_take} fish. The other fishermen's first announcements "
        f"this round were: {_announcements_line(obs.other_first_announcements or {})}."
    )
    return _fill(
        f"{t['rules']}\n\n{t['state']}\n\n{situation}\n\nHistory so far:\n"
        f"{_history_lines(obs)}\n\n{t['schema_second']}",
        obs,
    )
