"""Controlled Day 4 login outcome and Day 5 strategy selection using production memory.

Both members start with a synthetic profile and no completed tasks on Days 1–3.
Only the separately dated Day 4 episode is exposed after the cutoff. All summary
statistics and psychological state supplied to the Day 5 decision are frozen
before that episode so that the contrast measures its direct prompt effect.
"""
from __future__ import annotations

import random
from typing import Any, Literal

from proto.attempt_strategy import choose_attempt_strategy, compute_rule_strategy_weights
from proto.experience_memory import (
    build_initial_help_effect_memory,
    build_initial_task_domain_memory,
    extract_memory_features,
    update_experience_memory,
)
from proto.llm_psychology import build_initial_digital_emotion_state, resolve_strategy_deliberation
from proto.memory.packet import build_task_relevant_memory_packet
from proto.models import AttemptOutcome, AttemptStrategy, DigitalTask, TaskAppraisalResult
from proto.outcome_model import infer_event_level_uncontrollability


class _PairedDraw(random.Random):
    def __init__(self, sample_u: float) -> None:
        super().__init__(0)
        self.sample_u = sample_u

    def random(self) -> float:
        return self.sample_u


def _login_task(day: int) -> DigitalTask:
    return DigitalTask(
        task_id=f"synthetic-login-day{day}", task_family="account_login_verification",
        friction_type="verification", difficulty=0.64, need_type="daily_task",
        support_sensitivity=0.7, assigned_tick=9 * 3600,
    )


async def run_pair_member(
    llm: Any, condition: Literal["success", "failure"], sample_u: float,
    *, prompt_format: Literal["scored_example", "field_rules", "field_rules_no_priors"] = "scored_example",
) -> dict[str, Any]:
    """Sample one Day 5 strategy. No help request or Day 5 outcome is executed."""
    if condition not in ("success", "failure"):
        raise ValueError("condition must be 'success' or 'failure'")
    if isinstance(sample_u, bool) or not isinstance(sample_u, (float, int)):
        raise ValueError("sample_u must be a number in [0, 1)")
    if not 0 <= sample_u < 1:
        raise ValueError("sample_u must be finite and in [0, 1)")

    profile = {"digital_experience": 0.4, "vision_limit": 0.3, "past_fraud_experience": 0.2}
    day4 = _login_task(4)
    day5 = _login_task(5)
    succeeded = condition == "success"
    outcome_type = "success_self" if succeeded else "failure_after_attempt"
    # For a first low-friction verification attempt, the production rule assigns
    # zero event-level uncontrollability to both a success and an ordinary failure.
    uncontrollability = infer_event_level_uncontrollability(
        task=day4, outcome_type=outcome_type, friction_tier=0,
        consecutive_failures_after_event=int(not succeeded),
    )
    outcome = AttemptOutcome(
        outcome_type=outcome_type, success=succeeded, help_used=False,
        negative_feedback=not succeeded, support_quality=1, friction_tier=0,
        event_level_uncontrollability=uncontrollability,
        rule_event_level_uncontrollability=uncontrollability,
        success_probability=0.5, abandon_probability=0.1,
    )
    appraisal = TaskAppraisalResult(
        mode="controlled", status="fixed", source="fixture", confidence=1.0,
        reason="", cache_hit=False, perceived_task_difficulty=64.0,
    ).to_dict()
    baseline_tasks = build_initial_task_domain_memory(**profile)
    baseline_help = build_initial_help_effect_memory()
    emotion = build_initial_digital_emotion_state(**profile)
    baseline = extract_memory_features(
        task=day5, helplessness_score=50.0, task_domain_memory=baseline_tasks,
        help_effect_memory=baseline_help, recent_episode_buffer=[],
        digital_emotion_state=emotion, task_appraisal_result=appraisal, psychology_mode="hybrid",
    )
    recent = {
        "recent_negative_feedback_ratio": baseline.recent_negative_feedback_ratio,
        "recent_avoid_ratio": baseline.recent_avoid_ratio,
        "recent_help_seek_ratio": baseline.recent_help_seek_ratio,
        "recent_same_task_failure_count": baseline.recent_same_task_failure_count,
        "recent_failure_pressure": baseline.recent_failure_pressure,
    }
    memory = update_experience_memory(
        task=day4, strategy=AttemptStrategy("attempt_self"), outcome=outcome,
        day=3, tick_seconds=day4.assigned_tick, helplessness_delta=0.0,
        task_domain_memory=baseline_tasks, help_effect_memory=baseline_help, recent_episode_buffer=[],
        rationale_memory=[], task_appraisal_result=appraisal,
        requested_strategy_type="attempt_self", support_delivery_status="not_requested",
    )
    packet = build_task_relevant_memory_packet(
        task=day5, task_domain_memory=baseline_tasks,
        help_effect_memory=baseline_help, recent_episode_summary=recent,
        recent_episode_buffer=memory["recent_episode_buffer"], event_log=[],
        simulation_day=4, tick_seconds=day5.assigned_tick,
    )
    packet["aggregate_memory_scope"] = (
        "All counts, summaries, psychological state and rule weights use the Day 1–3 "
        "baseline (no completed tasks). The Day 4 episode is excluded from those statistics."
    )
    packet["episode_memory_scope"] = (
        "recent_task_episodes separately records the Day 4 login attempt. Its event-level "
        "uncontrollability is held fixed at zero. The current login task occurs on Day 5."
    )
    baseline_inputs = {
        "effective_helplessness": baseline.effective_helplessness,
        "task_self_efficacy": baseline.task_self_efficacy,
        "help_success_rate_smoothed": baseline.help_success_rate_smoothed,
        "recent_negative_feedback_ratio": recent["recent_negative_feedback_ratio"],
        "recent_same_task_failure_count": recent["recent_same_task_failure_count"],
    }
    rule_weights = compute_rule_strategy_weights(
        **baseline_inputs, support_quality=1,
        task_difficulty=day5.difficulty, consecutive_failures=0,
    )
    deliberation = await resolve_strategy_deliberation(
        llm=llm, task=day5, task_appraisal=appraisal, rule_weights=rule_weights,
        profile_summary={"age": 67, **profile}, digital_emotion_state=emotion,
        daily_reflection={}, task_relevant_memory=packet, recent_episode_summary=recent,
        prompt_format=prompt_format, **baseline_inputs,
    )
    strategy = choose_attempt_strategy(
        **baseline_inputs, support_quality=1, task_difficulty=day5.difficulty,
        consecutive_failures=packet["same_task_failure_streak"],
        strategy_deliberation_result=deliberation, rng=_PairedDraw(float(sample_u)),
    )
    raw_scores = None
    if deliberation.llm_weights is not None:
        raw_scores = {
            "attempt_self": deliberation.attempt_self_score,
            "seek_help_then_attempt": deliberation.seek_help_score,
            "avoid": deliberation.avoid_score,
        }
    return {
        "condition": condition, "prompt_format": prompt_format, "day1_3_completed_tasks": 0,
        "day4_episode": memory["recent_episode_buffer"][-1], "day5_task": day5.to_dict(),
        "task_relevant_memory": packet, "recent_episode_summary": recent,
        "source": deliberation.source, "status": deliberation.status, "cache_hit": deliberation.cache_hit,
        "confidence": deliberation.confidence, "reason": deliberation.reason,
        "dominant_strategy": deliberation.dominant_strategy, "raw_scores": raw_scores,
        "llm_weights": deliberation.llm_weights, "rule_weights": deliberation.rule_weights,
        "blended_weights": deliberation.final_weights, "final_weights": strategy.weights,
        "sample_u": float(sample_u), "sampled_action": strategy.strategy_type,
        "support_requested_by_strategy": strategy.support_requested, "help_request_dispatched": False,
    }
