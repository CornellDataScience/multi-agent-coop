"""Run one full episode: generate -> play -> survey -> score -> judge ->
indicators -> normalized fields. Used by the runner and by tests.

Mock episodes go through exactly the same path as real ones; only the model
call is swapped (agent.py routes mock/* ids to mock.py)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from . import metrics as metrics_mod
from .agent import AgentRole, EpisodeContext
from .judge import judge_episode, split_events
from .tasks import TASKS
from .tasks.base import DEFAULT_CONDITION, run_capability_survey


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_agents(task, scenario: dict, test_model: str, counterpart_model: str,
                 condition: dict) -> dict[str, AgentRole]:
    """AgentRole per participant. T1 has two counterpart agents (cp_1, cp_2);
    the two-party tasks have one (cp_1)."""
    names = task.role_names(scenario)
    agents = {}
    for key, role in names.items():
        model = test_model if key == "test" else counterpart_model
        agents[key] = AgentRole(
            agent_key=key, role=role, model_id=model,
            system_prompt=task.system_prompt(scenario, key, condition),
        )
    return agents


def assemble_analysis(task, scenario: dict, outcome: dict, turns: list[dict],
                      survey: dict | None, judge_result: dict) -> dict:
    """Everything derived from the played episode + judge output: metrics,
    events, success indicators, counterpart indicators, normalized fields.
    Pure (no model calls), so re-judge and recompute can reuse it."""
    scored = task.score(scenario, outcome, turns)
    metrics = scored["metrics"]
    det_events = scored["events"]
    judge_out = judge_result.get("judge_out") or {}

    metrics.update(task.judge_metrics(scenario, outcome, judge_out))
    judge_scored, judge_gray = split_events(task.id, judge_out) if judge_out else ([], [])
    extra_gray = (task.extra_gray_events(scenario, outcome, turns, judge_out)
                  if hasattr(task, "extra_gray_events") else [])

    events = {
        "deterministic_test": det_events.get("deterministic_test", []),
        "deterministic_cp": det_events.get("deterministic_cp", []),
        "judge_test_scored": judge_scored,
        "judge_test_gray": judge_gray,
        "judge_counterpart": judge_out.get("counterpart_events", []) if judge_out else [],
        "extra_gray": extra_gray,
        "dropped": judge_result.get("dropped", []),
    }
    success = task.success_indicators(scenario, outcome, metrics, judge_out)
    events["success"] = success
    cp_indicators = task.counterpart_indicators(scenario, outcome, turns, judge_out)

    counts: dict[str, int] = {}
    for e in events["deterministic_test"] + events["judge_test_scored"]:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    for e in events["judge_test_gray"] + events["extra_gray"]:
        counts[f"gray:{e['type']}"] = counts.get(f"gray:{e['type']}", 0) + 1
    for e in events["deterministic_cp"] + events["judge_counterpart"]:
        counts[f"cp:{e['type']}"] = counts.get(f"cp:{e['type']}", 0) + 1
    for s in success:
        counts[f"success:{s['type']}"] = counts.get(f"success:{s['type']}", 0) + 1
    metrics["event_type_counts"] = counts

    fields = metrics_mod.episode_fields(task, metrics, events, success, cp_indicators,
                                        survey, judge_result, turns)
    return {
        "metrics": metrics,
        "events": events,
        "fields": fields,
        "detection": judge_out.get("detection") if judge_out else None,
        "eval_awareness": judge_out.get("eval_awareness") if judge_out else None,
    }


async def run_episode(task_id: str, seed: int, test_model: str, counterpart_model: str,
                      condition: dict | None = None, judge_model: str = "mock/judge",
                      episode_id: str | None = None, run_id: str | None = None) -> dict:
    """Returns a complete episode record (benchmark spec section 10.2)."""
    task = TASKS[task_id]
    condition = dict(condition or DEFAULT_CONDITION)
    episode_id = episode_id or f"ep_{uuid.uuid4().hex[:12]}"
    is_control = counterpart_model == test_model
    started = _now()

    ctx = EpisodeContext(
        episode_id=episode_id, task_id=task_id, seed=seed, condition=condition,
        counterpart_model=counterpart_model, is_control=is_control,
    )

    scenario = task.generate(seed)
    agents = build_agents(task, scenario, test_model, counterpart_model, condition)

    outcome = await task.play(scenario, agents, ctx)
    survey = await run_capability_survey(task, scenario, outcome, agents["test"], ctx)

    judge_result = await judge_episode(task, scenario, outcome, ctx.turns, judge_model)
    ctx.tokens_in += judge_result.get("tokens_in", 0)
    ctx.tokens_out += judge_result.get("tokens_out", 0)
    ctx.cost_usd += judge_result.get("cost_usd", 0.0)

    analysis = assemble_analysis(task, scenario, outcome, ctx.turns, survey, judge_result)

    system_prompts = {a.system_prompt_hash: a.system_prompt for a in agents.values()}
    return {
        "episode_id": episode_id,
        "run_id": run_id,
        "task": task_id,
        "seed": seed,
        "test_model": test_model,
        "counterpart_model": counterpart_model,
        "is_control": is_control,
        "condition": condition,
        "scenario": scenario,
        "turns": ctx.turns,
        "system_prompts": system_prompts,
        "outcome": outcome,
        "metrics": analysis["metrics"],
        "events": analysis["events"],
        "fields": analysis["fields"],
        "survey": survey,
        "detection": analysis["detection"],
        "eval_awareness": analysis["eval_awareness"],
        "judge_model": judge_model,
        "judge_raw": judge_result.get("judge_raw"),
        "judge_out": judge_result.get("judge_out"),
        "judge_dropped": judge_result.get("dropped", []),
        "judge_failed": bool(judge_result.get("judge_failed")),
        "excluded": analysis["fields"]["excluded"],
        "tokens_in": ctx.tokens_in,
        "tokens_out": ctx.tokens_out,
        "cost_usd": ctx.cost_usd,
        "status": "done",
        "error": None,
        "started_at": started,
        "finished_at": _now(),
    }
