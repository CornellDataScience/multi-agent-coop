"""Run a condition over seeds and write one JSONL log per game."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from ..agents.backends import ClaudeBackend, OllamaBackend, OpenRouterBackend
from .agents.base import KCAgent
from .agents.llm import KCLLMAgent
from .agents.mock import KCMockBackend, mock_responder
from .agents.prompt_variants import get_variant
from .agents.scripted import make_scripted
from .configs import DEFAULT_LLM_MODEL, KCCondition
from .environment import KCEnvironment


class CallBudgetExceeded(RuntimeError):
    """Raised by ``CallBudget`` when the run hits ``--max-calls``."""


class CallBudget:
    """Shared counter of model calls for one run. ``wrap`` returns a backend
    that refuses to make call ``limit + 1``."""

    def __init__(self, limit: int | None = None):
        self.limit = limit
        self.calls = 0

    def wrap(self, backend):
        return _Budgeted(backend, self)


class _Budgeted:
    def __init__(self, backend, budget: CallBudget):
        self.wrapped = backend
        self.budget = budget
        self.model = getattr(backend, "model", None)

    def __call__(self, system: str, prompt: str):
        b = self.budget
        if b.limit is not None and b.calls >= b.limit:
            raise CallBudgetExceeded(f"reached --max-calls {b.limit}")
        b.calls += 1
        return self.wrapped(system, prompt)


@dataclass
class RunResult:
    paths: list[Path] = field(default_factory=list)
    calls: int = 0
    aborted: bool = False
    message: str = ""


OPENROUTER_PREFIX = "openrouter/"


def _tag(value: str) -> str:
    """Model IDs can contain ':' or '/', which are awkward in filenames."""
    return "".join(c if c.isalnum() or c in ".-" else "-" for c in value)


def expand_lineup(specs: list[dict], n: int) -> list[dict]:
    """Resize a lineup to ``n`` agents: keep the first spec (the LLM in probe
    conditions) and repeat the rest cyclically, so a probe keeps one LLM."""
    if n <= len(specs):
        return specs[:n]
    rest = specs[1:] or specs[:1]
    return [specs[0]] + [rest[i % len(rest)] for i in range(n - 1)]


def make_backend(model: str, agent_id: int, game_seed: int, effort: str | None = None,
                 temperature: float | None = None, chat_fn: Callable | None = None):
    """``mock`` -> network-free mock; ``claude-*`` -> Claude API;
    ``openrouter/<id>`` -> OpenRouter with ``<id>``; else Ollama."""
    if model == "mock":
        return KCMockBackend(responder=mock_responder(game_seed * 1000 + agent_id))
    if model.startswith(OPENROUTER_PREFIX):
        model_id = model[len(OPENROUTER_PREFIX):]
        if not model_id:
            raise ValueError("--model openrouter/ needs a model ID, e.g. openrouter/deepseek/deepseek-v4-pro")
        return OpenRouterBackend(model=model_id, temperature=temperature, chat_fn=chat_fn)
    if model.startswith("claude"):
        return ClaudeBackend(model=model, effort=effort or "medium", chat_fn=chat_fn)
    return OllamaBackend(model=model, temperature=0.7 if temperature is None else temperature,
                         seed=game_seed * 1000 + agent_id, chat_fn=chat_fn)


def run_condition(
    cond: KCCondition,
    out_dir: str | Path = "results/kc",
    *,
    model: str | None = None,
    seeds: list[int] | None = None,
    prompt_variant: str | None = None,
    alpha: float | None = None,
    info: str | None = None,
    n_agents: int | None = None,
    rounds: int | None = None,
    pot_size: float | None = None,
    must_send: bool = False,
    effort: str | None = None,
    temperature: float | None = None,
    max_calls: int | None = None,
    chat_fn: Callable | None = None,
) -> RunResult:
    """Run ``cond`` once per seed. Completed games are written as they
    finish; if ``max_calls`` is reached mid-game, that game is dropped and
    the run stops with ``aborted=True``."""
    out_dir = Path(out_dir)
    variant = prompt_variant or cond.prompt_variant
    get_variant(variant)
    overrides = {k: v for k, v in {"alpha": alpha, "info_condition": info, "n_agents": n_agents,
                                   "max_rounds": rounds, "pot_size": pot_size}.items() if v is not None}
    if must_send:
        overrides["allow_withhold"] = False
    base = replace(cond.config, **overrides)  # validates via __post_init__
    specs = expand_lineup(cond.agent_specs, base.n_agents)
    uses_llm = any(s["type"] == "llm" for s in specs)
    llm_model = model or next((s.get("model") for s in specs if s["type"] == "llm"), DEFAULT_LLM_MODEL)

    tags = [cond.name, _tag(llm_model) if uses_llm else "scripted", f"a{base.alpha:g}", base.info_condition]
    if not base.allow_withhold:
        tags.append("mustsend")
    if uses_llm:
        tags.append(variant)
        if effort:
            tags.append(effort)
        if temperature is not None:
            tags.append(f"temp{temperature:g}")
    if n_agents is not None:
        tags.append(f"n{n_agents}")
    if rounds is not None:
        tags.append(f"r{rounds}")
    if pot_size is not None:
        tags.append(f"pot{pot_size:g}")
    stem = "_".join(tags)

    budget = CallBudget(max_calls)
    result = RunResult()
    for seed in seeds if seeds is not None else cond.seeds:
        cfg = replace(base, seed=seed)
        agents: list[KCAgent] = []
        for i, spec in enumerate(specs):
            if spec["type"] == "scripted":
                extra = {k: v for k, v in spec.items() if k not in ("type", "policy")}
                agents.append(make_scripted(spec["policy"], i, **extra))
            elif spec["type"] == "llm":
                backend = make_backend(model or spec.get("model", DEFAULT_LLM_MODEL), i, seed,
                                       effort, temperature, chat_fn)
                agents.append(KCLLMAgent(i, budget.wrap(backend), prompt_variant=variant))
            else:
                raise ValueError(f"unknown agent type {spec['type']!r}")
        env = KCEnvironment(cfg, agents, cond.name, run_parameters={
            "model": llm_model if uses_llm else None,
            "prompt_variant": variant if uses_llm else None,
            "effort": effort,
            "temperature": temperature,
            "max_calls": max_calls,
            "must_send": not cfg.allow_withhold,
        })
        try:
            log = env.run()
        except CallBudgetExceeded as exc:
            result.aborted = True
            result.message = f"stopped before finishing seed {seed}: {exc}"
            break
        result.paths.append(log.write_jsonl(out_dir / f"{stem}_seed{seed}.jsonl"))
    result.calls = budget.calls
    return result
