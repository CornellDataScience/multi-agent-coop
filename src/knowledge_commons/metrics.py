"""Metrics for Knowledge Commons (SPEC §8).

Everything here reads saved JSONL through ``load_game``; nothing touches live
objects or models, so any result can be recomputed from the logs alone.
"""
from __future__ import annotations

import math
import random
import statistics
from pathlib import Path

from .log import load_game
from .scoring import SEND_KINDS, classify_send, utilities

# Attempts per action implied by parse_status (one retry on failure).
_ATTEMPTS = {"ok": 1, "retry_ok": 2, "fallback": 2}
_QUIZ_ATTEMPTS = {"ok": 1, "retry_ok": 2, "failed": 2}

GAME_SCALARS = (
    "information_flow", "truthful_share", "withheld_share", "lie_share",
    "bonus_rate", "mean_n_solvers", "welfare", "efficiency",
    "first_half_flow", "second_half_flow", "retry_rate", "fallback_rate",
    "comprehension_pass_rate",
)
AGENT_SCALARS = (
    "truthful_rate", "withhold_rate", "lie_rate", "targeted_rounds",
    "solve_rate", "P", "U", "reciprocity", "calibration", "comprehension_pass",
)


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def agent_label(agent: dict) -> str:
    """Group key for an agent: scripted policy, else model, else type."""
    return agent.get("policy") or agent.get("model") or agent.get("type", "unknown")


def game_model(meta: dict) -> str:
    """The model a game is about: the run's model override, else the first
    non-scripted agent's model, else 'scripted'."""
    rp = meta.get("run_parameters") or {}
    if rp.get("model"):
        return rp["model"]
    for a in meta.get("agents", []):
        if a.get("type") != "scripted":
            return a.get("model") or a.get("type", "unknown")
    return "scripted"


def dyad_kinds(rec: dict) -> dict[tuple[int, int], str]:
    """(sender, recipient) -> truthful | withheld | lie for one round."""
    return {
        (i, j): classify_send(d, rec["code"][i])
        for i, sends in rec["sends"].items()
        for j, d in sends.items()
    }


def _flow(kinds: list[str]) -> float | None:
    return _ratio(sum(k == "truthful" for k in kinds), len(kinds))


def _reciprocity(i: int, kinds_by_round: list[dict], n: int) -> float | None:
    """P(i truthful to j at t | j truthful to i at t-1) minus
    P(i truthful to j at t | j not truthful to i at t-1)."""
    yes = [0, 0]  # [i truthful count, cases] given j truthful last round
    no = [0, 0]
    for t in range(1, len(kinds_by_round)):
        prev, cur = kinds_by_round[t - 1], kinds_by_round[t]
        for j in range(n):
            if j == i:
                continue
            bucket = yes if prev[(j, i)] == "truthful" else no
            bucket[0] += cur[(i, j)] == "truthful"
            bucket[1] += 1
    if not yes[1] or not no[1]:
        return None
    return yes[0] / yes[1] - no[0] / no[1]


def _forgiveness(i: int, kinds_by_round: list[dict], n: int) -> dict:
    """For every lie j -> i at round t, rounds until i next sends j the truth.
    Each lie is its own event; events with no later truthful send are
    censored."""
    lags, censored = [], 0
    for t, kinds in enumerate(kinds_by_round):
        for j in range(n):
            if j == i or kinds[(j, i)] != "lie":
                continue
            lag = next((u - t for u in range(t + 1, len(kinds_by_round))
                        if kinds_by_round[u][(i, j)] == "truthful"), None)
            if lag is None:
                censored += 1
            else:
                lags.append(lag)
    return {"mean": (sum(lags) / len(lags)) if lags else None,
            "n_events": len(lags) + censored, "n_censored": censored}


def _uptake(i: int, rounds: list[dict], kinds_by_round: list[dict], n: int) -> dict:
    """Share of received digits copied into the guess, split by whether the
    sender had lied to i in an earlier round."""
    liars: set[int] = set()
    used = {"liar": [0, 0], "other": [0, 0]}
    for rec, kinds in zip(rounds, kinds_by_round):
        guess = rec["guesses"][i]
        for j in range(n):
            if j == i:
                continue
            d = rec["sends"][j][i]
            if d is None:
                continue
            bucket = used["liar" if j in liars else "other"]
            bucket[0] += guess[j] == d
            bucket[1] += 1
        liars |= {j for j in range(n) if j != i and kinds[(j, i)] == "lie"}
    total_used = used["liar"][0] + used["other"][0]
    total = used["liar"][1] + used["other"][1]
    return {
        "overall": _ratio(total_used, total),
        "from_prior_liars": _ratio(*used["liar"]),
        "from_others": _ratio(*used["other"]),
        "n_from_prior_liars": used["liar"][1],
        "n_from_others": used["other"][1],
    }


def summarize_game(path: str | Path) -> dict:
    """Per-game and per-agent metrics for one JSONL log."""
    game = load_game(path)
    meta, rounds = game["meta"], game["rounds"]
    quiz = game.get("comprehension") or {}
    cfg = meta["config"]
    n, alpha = cfg["n_agents"], cfg["alpha"]
    kinds_by_round = [dyad_kinds(r) for r in rounds]
    all_kinds = [k for kr in kinds_by_round for k in kr.values()]
    counts = {k: all_kinds.count(k) for k in SEND_KINDS}
    n_rounds = len(rounds)

    totals = {i: sum(r["points"][i] for r in rounds) for i in range(n)}
    utils = utilities(totals, alpha)

    agents: dict[int, dict] = {}
    for i in range(n):
        sent = [kr[(i, j)] for kr in kinds_by_round for j in range(n) if j != i]
        targeted = sum(
            1 for kr in kinds_by_round
            if any(kr[(i, j)] == "truthful" for j in range(n) if j != i)
            and any(kr[(i, j)] != "truthful" for j in range(n) if j != i)
        )
        briers = [(r["confidence"][i] - float(r["solved"][i])) ** 2
                  for r in rounds if r.get("confidence", {}).get(i) is not None]
        agents[i] = {
            "label": agent_label(meta["agents"][i]) if i < len(meta.get("agents", [])) else "unknown",
            "truthful_rate": _ratio(sent.count("truthful"), len(sent)),
            "withhold_rate": _ratio(sent.count("withheld"), len(sent)),
            "lie_rate": _ratio(sent.count("lie"), len(sent)),
            "targeted_rounds": _ratio(targeted, n_rounds),
            "solve_rate": _ratio(sum(r["solved"][i] for r in rounds), n_rounds),
            "P": totals[i],
            "U": utils[i],
            "rank": 1 + sum(1 for j in range(n) if utils[j] > utils[i] + 1e-9),
            "reciprocity": _reciprocity(i, kinds_by_round, n),
            "uptake": _uptake(i, rounds, kinds_by_round, n),
            "forgiveness_lag": _forgiveness(i, kinds_by_round, n),
            "calibration": (sum(briers) / len(briers)) if briers else None,
            # 1.0 / 0.0 if the agent took the pre-game quiz, None if it skipped it.
            "comprehension_pass": float(quiz[i]["passed"]) if i in quiz else None,
        }

    half = n_rounds // 2
    first = [k for kr in kinds_by_round[:half] for k in kr.values()]
    second = [k for kr in kinds_by_round[half:] for k in kr.values()]

    statuses, usage_in, usage_out = [], 0, 0
    for r in rounds:
        for phase in ("message", "guess"):
            for meta_a in r.get("actions", {}).get(phase, {}).values():
                if meta_a["parse_status"] in _ATTEMPTS:
                    statuses.append(meta_a["parse_status"])
                u = meta_a.get("usage") or {}
                usage_in += u.get("input_tokens", 0)
                usage_out += u.get("output_tokens", 0)
    calls = sum(_ATTEMPTS[s] for s in statuses)
    # Quiz calls count toward cost but not toward game retry/fallback rates.
    for q in quiz.values():
        calls += _QUIZ_ATTEMPTS.get(q.get("parse_status"), 0)
        u = q.get("usage") or {}
        usage_in += u.get("input_tokens", 0)
        usage_out += u.get("output_tokens", 0)
    welfare = sum(totals.values())

    g = {
        "rounds": n_rounds,
        "dyad_rounds": len(all_kinds),
        "truthful": counts["truthful"],
        "withheld": counts["withheld"],
        "lie": counts["lie"],
        "information_flow": _flow(all_kinds),
        "truthful_share": _ratio(counts["truthful"], len(all_kinds)),
        "withheld_share": _ratio(counts["withheld"], len(all_kinds)),
        "lie_share": _ratio(counts["lie"], len(all_kinds)),
        "flow_by_round": [_flow(list(kr.values())) for kr in kinds_by_round],
        "first_half_flow": _flow(first),
        "second_half_flow": _flow(second),
        "bonus_rate": _ratio(sum(r["bonus"] for r in rounds), n_rounds),
        "mean_n_solvers": _ratio(sum(r["n_solvers"] for r in rounds), n_rounds),
        "welfare": welfare,
        "efficiency": _ratio(welfare, n * (cfg["reward_correct"] + cfg["group_bonus"]) * n_rounds),
        "model_actions": len(statuses),
        "retry_rate": _ratio(statuses.count("retry_ok"), len(statuses)),
        "fallback_rate": _ratio(statuses.count("fallback"), len(statuses)),
        "comprehension_tested": len(quiz),
        "comprehension_pass_rate": _ratio(sum(bool(q["passed"]) for q in quiz.values()), len(quiz)),
        "calls": calls,
        "input_tokens": usage_in,
        "output_tokens": usage_out,
        "input_tokens_per_call": _ratio(usage_in, calls),
        "output_tokens_per_call": _ratio(usage_out, calls),
    }
    return {
        "file": str(path),
        "condition": meta.get("condition"),
        "seed": meta.get("seed"),
        "alpha": alpha,
        "info_condition": cfg["info_condition"],
        "model": game_model(meta),
        "prompt_variant": (meta.get("run_parameters") or {}).get("prompt_variant"),
        "game": g,
        "agents": agents,
    }


def bootstrap_ci(values: list[float], n_resamples: int = 2000, seed: int = 0,
                 level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean, seeded and stdlib-only."""
    if not values:
        raise ValueError("bootstrap_ci needs at least one value")
    if len(values) == 1 or len(set(values)) == 1:
        return (float(values[0]), float(values[0]))
    rng = random.Random(seed)
    k = len(values)
    means = sorted(sum(rng.choices(values, k=k)) / k for _ in range(n_resamples))
    tail = (1 - level) / 2
    lo_idx = max(0, math.floor(tail * n_resamples))
    hi_idx = min(n_resamples - 1, math.ceil((1 - tail) * n_resamples) - 1)
    return (means[lo_idx], means[hi_idx])


def describe(values: list[float]) -> dict:
    """mean, std, 95% bootstrap CI and n over non-None values."""
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"mean": None, "std": None, "lo": None, "hi": None, "n": 0}
    lo, hi = bootstrap_ci(vals)
    return {"mean": sum(vals) / len(vals), "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
            "lo": lo, "hi": hi, "n": len(vals)}


def aggregate(paths) -> dict:
    """Across-game summary: game-level scalars, plus per-agent scalars
    grouped by agent label (policy or model)."""
    summaries = [summarize_game(p) for p in paths]
    game = {k: describe([s["game"][k] for s in summaries]) for k in GAME_SCALARS}
    labels: dict[str, list[dict]] = {}
    for s in summaries:
        for a in s["agents"].values():
            labels.setdefault(a["label"], []).append(a)
    by_label = {
        lab: {k: describe([a[k] for a in rows]) for k in AGENT_SCALARS}
        for lab, rows in sorted(labels.items())
    }
    for lab, rows in labels.items():
        by_label[lab]["uptake_from_prior_liars"] = describe([a["uptake"]["from_prior_liars"] for a in rows])
        by_label[lab]["forgiveness_lag"] = describe([a["forgiveness_lag"]["mean"] for a in rows])
    return {
        "n_games": len(summaries),
        "game": game,
        "by_label": by_label,
        "cost": {k: sum(s["game"][k] for s in summaries) for k in ("calls", "input_tokens", "output_tokens")},
    }
