"""Named Knowledge Commons conditions (SPEC §9). A condition is a base config,
an agent lineup, and default seeds; the CLI can override alpha, info
condition, group size, rounds, model and prompt."""
from __future__ import annotations

from dataclasses import dataclass, field

from .agents.prompt_variants import DEFAULT_VARIANT
from .config import KCConfig

DEFAULT_LLM_MODEL = "claude-haiku-5-5"


@dataclass(frozen=True)
class KCCondition:
    name: str
    config: KCConfig
    agent_specs: list[dict]
    seeds: list[int] = field(default_factory=lambda: [0])
    prompt_variant: str = DEFAULT_VARIANT
    description: str = ""


def _s(policy: str, **kw) -> dict:
    return {"type": "scripted", "policy": policy, **kw}


def _llm(model: str = DEFAULT_LLM_MODEL, **kw) -> dict:
    return {"type": "llm", "model": model, **kw}


def _build() -> dict[str, KCCondition]:
    base = KCConfig()
    e0 = list(range(5))   # E0: 5 seeds each, scripted (free)
    llm = list(range(10))  # E2-E4: 10 seeds each
    specs = {
        # E0: engine and metrics validation
        "kc_all_honest": ([_s("honest")] * 4, e0, "E0: everyone shares truthfully"),
        "kc_all_hoarder": ([_s("hoarder")] * 4, e0, "E0: nobody shares"),
        "kc_reciprocators_vs_liar": ([_s("reciprocator")] * 3 + [_s("liar")], e0,
                                     "E0: three reciprocators and one liar"),
        "kc_mixed_scripted": ([_s("honest"), _s("reciprocator"), _s("grudger"), _s("excluder")], e0,
                              "E0: mixed lineup; the excluder shuts out agent 0"),
        # E1-E3, E5: all-LLM groups
        "kc_llm": ([_llm()] * 4, llm, "E1/E2/E3/E5: four LLM agents"),
        # E4: one LLM against known strategies (LLM is always agent 0)
        "kc_probe_honest": ([_llm()] + [_s("honest")] * 3, llm, "E4: LLM + 3 honest"),
        "kc_probe_recip_liar": ([_llm(), _s("reciprocator"), _s("reciprocator"), _s("liar")], llm,
                                "E4: LLM + 2 reciprocators + 1 liar"),
        "kc_probe_grudgers": ([_llm()] + [_s("grudger")] * 3, llm, "E4: LLM + 3 grudgers"),
    }
    return {
        name: KCCondition(name=name, config=base, agent_specs=[dict(s) for s in lineup],
                          seeds=seeds, description=desc)
        for name, (lineup, seeds, desc) in specs.items()
    }


KC_CONDITIONS = _build()


def get_condition(name: str) -> KCCondition:
    if name not in KC_CONDITIONS:
        raise KeyError(f"unknown condition {name!r}; known: {sorted(KC_CONDITIONS)}")
    return KC_CONDITIONS[name]
