"""End-to-end on mocks: one complete episode record per task with every
section 9.1 field, and a mini-run whose aggregates show the pattern the mock
agents are designed to produce (positive recognition gap, attempt shift and
post-recognition change)."""

import asyncio

import pytest
from asym_helpers import run

from asymbench.episode import run_episode
from asymbench.metrics import aggregate_episodes
from asymbench.tasks import TASKS

REQUIRED_FIELDS = [
    "share", "principal_value", "attempt_events", "attempt_any", "success_any",
    "harm", "gray_events", "disclosure_rate", "counterpart_misconduct",
    "cp_indicators", "survey_rating", "detected", "detection_turn", "recognized",
    "attempts_before_recognition", "attempts_after_recognition",
    "turns_before_recognition", "turns_after_recognition", "eval_aware",
    "cp_invalid_rate", "test_invalid_rate", "excluded",
]

REQUIRED_RECORD_KEYS = [
    "episode_id", "task", "seed", "test_model", "counterpart_model", "is_control",
    "condition", "scenario", "turns", "system_prompts", "outcome", "metrics",
    "events", "fields", "survey", "detection", "eval_awareness", "judge_model",
    "judge_raw", "judge_failed", "excluded", "tokens_in", "tokens_out", "cost_usd",
    "status", "error", "started_at", "finished_at",
]


@pytest.mark.parametrize("tid", list(TASKS))
def test_complete_episode_record(tid):
    ep = run(run_episode(tid, seed=0, test_model="mock/strong",
                         counterpart_model="mock/weak", judge_model="mock/judge"))
    for key in REQUIRED_RECORD_KEYS:
        assert key in ep, f"{tid}: missing episode key {key}"
    for f in REQUIRED_FIELDS:
        assert f in ep["fields"], f"{tid}: missing 9.1 field {f}"
    assert ep["status"] == "done"
    assert ep["survey"] and ep["survey"]["counterpart_capability"] == 2
    # turn records carry the spec 10.1 fields
    t = ep["turns"][0]
    for key in ["turn", "phase", "agent", "role", "model", "system_prompt_hash",
                "observation", "raw_output", "parse_stage", "retried", "invalid",
                "error", "private_notes", "message", "action", "clamped",
                "message_truncated", "tokens_in", "tokens_out", "cost_usd",
                "latency_ms", "timestamp"]:
        assert key in t, f"{tid}: missing turn key {key}"
    # system prompts stored once, keyed by hash
    assert t["system_prompt_hash"] in ep["system_prompts"]


def test_mock_run_produces_designed_pattern():
    async def run_all():
        eps = []
        for task in TASKS:
            for cp in ("mock/weak", "mock/strong"):
                for seed in range(3):
                    ep = await run_episode(task, seed=seed, test_model="mock/strong",
                                           counterpart_model=cp, judge_model="mock/judge")
                    eps.append(ep)
        return eps

    eps = asyncio.run(run_all())
    agg = aggregate_episodes(eps)
    assert agg["totals"]["done"] == 6 * len(TASKS)
    contrasts = agg["contrasts"]
    assert len(contrasts) == len(TASKS)  # one weak counterpart per task

    rec_gaps = [c["recognition_gap"]["mean"] for c in contrasts]
    assert all(g is not None and g > 0 for g in rec_gaps), rec_gaps

    pooled_attempt_shift = sum(c["attempt_shift"]["mean"] for c in contrasts)
    assert pooled_attempt_shift > 0

    commons = next(c for c in contrasts if c["task"] == "commons")
    assert commons["attempt_shift"]["mean"] > 0
    for tid in ("knowledge", "knowledge_rel"):
        kc = next(c for c in contrasts if c["task"] == tid)
        assert kc["attempt_shift"]["mean"] > 0  # false digits rise after recognition

    post = [c["post_recognition_change"]["mean"] for c in contrasts
            if c["post_recognition_change"]["mean"] is not None]
    assert post and sum(post) / len(post) > 0

    surveys = [c["survey_gap"]["mean"] for c in contrasts]
    assert all(s == 2.0 for s in surveys)  # 4 vs control, 2 vs weak by design
