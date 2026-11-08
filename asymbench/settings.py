"""Configuration: model registry, presets, .env, storage paths.

Nothing outside this module reads models.yaml or environment variables for
provider keys. Keys are never logged or returned by any function here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent

load_dotenv(REPO_ROOT / ".env")


def db_path() -> Path:
    p = Path(os.environ.get("ASYMBENCH_DB", "data/asymbench.db"))
    return p if p.is_absolute() else REPO_ROOT / p


def runs_dir() -> Path:
    p = Path(os.environ.get("ASYMBENCH_RUNS_DIR", "runs"))
    return p if p.is_absolute() else REPO_ROOT / p


def key_available(provider: str) -> bool:
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    if provider == "mock":
        return True
    return False


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str  # anthropic | openrouter | mock
    label: str
    tier: str
    price_in: float   # USD per million input tokens
    price_out: float  # USD per million output tokens
    max_tokens: int = 1500
    registered: bool = True  # False when resolved by prefix routing

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _raw_config() -> dict:
    with open(PKG_DIR / "config" / "models.yaml") as fh:
        return yaml.safe_load(fh)


def registry() -> list[ModelSpec]:
    out = []
    for m in _raw_config()["models"]:
        out.append(ModelSpec(
            id=m["id"], provider=m["provider"], label=m.get("label", m["id"]),
            tier=str(m.get("tier", "?")), price_in=float(m.get("price_in", 0)),
            price_out=float(m.get("price_out", 0)),
            max_tokens=int(m.get("max_tokens", 1500)),
        ))
    return out


def defaults() -> dict:
    return dict(_raw_config().get("defaults", {}))


# Conservative (deliberately high) default prices for ids not in the registry,
# so budget estimates never undershoot. See DECISIONS.md.
_UNKNOWN_PRICES = {"anthropic": (15.0, 75.0), "openrouter": (5.0, 15.0), "mock": (0.0, 0.0)}


def resolve_model(model_id: str) -> ModelSpec:
    """Look up a model id; unknown ids are routed by prefix with conservative prices."""
    for spec in registry():
        if spec.id == model_id:
            return spec
    if model_id.startswith("mock/"):
        provider = "mock"
    elif model_id.startswith("claude-"):
        provider = "anthropic"
    elif "/" in model_id:
        provider = "openrouter"
    else:
        raise ValueError(
            f"cannot route model id {model_id!r}: not in the registry and no known prefix "
            "(claude-* -> anthropic, mock/* -> mock, anything with '/' -> openrouter)"
        )
    pin, pout = _UNKNOWN_PRICES[provider]
    max_toks = 4000 if provider == "anthropic" else 1500
    return ModelSpec(
        id=model_id, provider=provider, label=model_id, tier="custom",
        price_in=pin, price_out=pout, max_tokens=max_toks, registered=False,
    )


@lru_cache(maxsize=1)
def presets() -> dict:
    with open(PKG_DIR / "config" / "presets.yaml") as fh:
        return yaml.safe_load(fh)["presets"]
