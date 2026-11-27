"""One controlled D4 login outcome, carried to the D5 09:00 decision."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass

from probe_strategy_memory_pair import _PairedDraw
from proto.compat import apply_compatibility_updates
from proto.experience_memory import (
    build_initial_help_effect_memory,
    build_initial_task_domain_memory,
    extract_memory_features,
    update_experience_memory,
)
from proto.llm_psychology import (
    _apply_rule_emotion_update,
    _emotion_dict,
    build_initial_digital_emotion_state,
    prepare_digital_emotion_state_for_day,
)
from proto.logical_clock import monotonic_sim_hour
from proto.models import AttemptStrategy, HelplessnessUpdateInput, TaskAppraisalResult
from proto.outcome_model import resolve_attempt_outcome
from proto.state_update import apply_helplessness_update


@dataclass
class FeedbackState:
    condition: str
    helplessness: float
    trust: float
    avoidance: float
    consecutive_failures: int
    emotion: dict
    domain_memory: dict
    help_memory: dict
    episodes: list[dict]
    event_log: list[dict]
    rationale_memory: list[dict]
    audit: dict

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> FeedbackState:
        return cls(**deepcopy(payload))


def build_feedback_state(condition: str) -> FeedbackState:
    """Apply production rule updates once. No D4 or D5 model judgment is sampled."""
    # Both probe entry points can import FeedbackState for JSON replay.
    from probe_hourly_intention import (
        DAY,
        ENVIRONMENT,
        HOUR,
        PROFILE,
        PROFILE_ID,
        TICK,
        login_offer,
    )

    # The intervention is the draw in the D4 rule sampler. All its inputs are shared.
    # These quantiles are inside the corresponding outcome intervals for this fixture.
    draws = {
        "success": ("success_self", 0.4),
        "failure": ("failure_after_attempt", 0.95),
    }
    if condition not in draws:
        raise ValueError("condition must be 'success' or 'failure'")
    target_outcome, draw = draws[condition]
    event_day = DAY - 1
    task, _, _ = login_offer(day=event_day)
    strategy = AttemptStrategy(strategy_type="attempt_self")
    traits = {
        k: PROFILE[k]
        for k in ("digital_experience", "vision_limit", "past_fraud_experience")
    }
    domain = build_initial_task_domain_memory(**traits)
    help_memory = build_initial_help_effect_memory()
    start_emotion = prepare_digital_emotion_state_for_day(
        build_initial_digital_emotion_state(**traits), target_day=event_day
    )
    # Same synthetic, zero-completed-task baseline as the frozen hourly probe.
    before = {
        "helplessness": 50.0,
        "trust": 50.0,
        "avoidance": 50.0,
        "consecutive_failures": 0,
        "emotion": start_emotion.to_dict(),
        "task_domain": deepcopy(domain[task.task_family]),
        "help_overall": deepcopy(help_memory["overall"]),
        "episodes": [],
        "event_log": [],
    }
    appraisal = TaskAppraisalResult.from_dict(None)
    features = extract_memory_features(
        task=task,
        helplessness_score=before["helplessness"],
        task_domain_memory=domain,
        help_effect_memory=help_memory,
        recent_episode_buffer=before["episodes"],
        digital_emotion_state=start_emotion.to_dict(),
        task_appraisal_result=appraisal.to_dict(),
        psychology_mode="off",
    )
    outcome = resolve_attempt_outcome(
        task=task,
        strategy=strategy,
        helplessness=before["helplessness"],
        env=ENVIRONMENT,
        consecutive_failures=before["consecutive_failures"],
        rng=_PairedDraw(draw),
        outcome_model_mode="rule_v1",
    )
    if outcome.outcome_type != target_outcome:
        raise RuntimeError(
            f"D4 controlled draw returned {outcome.outcome_type}, expected {target_outcome}"
        )

    # This is the deterministic event update used inside resolve_event_appraisal.
    # Calling its rule directly keeps D4 independent of the live D5 hybrid configuration.
    rule_emotion = _apply_rule_emotion_update(
        state=start_emotion, outcome_type=outcome.outcome_type, day=event_day
    )
    post_event_emotion = {**_emotion_dict(rule_emotion), "last_updated_day": event_day}
    update_input = HelplessnessUpdateInput(
        helplessness_now=before["helplessness"],
        outcome_type=outcome.outcome_type,
        consecutive_failures=before["consecutive_failures"],
        support_quality=outcome.support_quality,
        event_level_uncontrollability=outcome.event_level_uncontrollability,
        task_self_efficacy=features.task_self_efficacy,
        felt_control=appraisal.felt_control,
        expected_help_effectiveness=appraisal.expected_help_effectiveness,
        avoid_reason=outcome.avoid_reason,
        controllable_success_memory=features.controllable_success_memory,
        support_mode=outcome.support_mode,
        helplessness_update_mode="rule_v1",
    )
    update = apply_helplessness_update(update_input)
    compatibility = apply_compatibility_updates(
        trust_now=before["trust"],
        avoidance_now=before["avoidance"],
        outcome_type=outcome.outcome_type,
        help_used=outcome.help_used,
        help_requested=strategy.support_requested,
        avoid_reason=outcome.avoid_reason,
    )
    memory = update_experience_memory(
        task=task,
        strategy=strategy,
        outcome=outcome,
        day=event_day,
        tick_seconds=TICK,
        helplessness_delta=update.delta,
        task_domain_memory=domain,
        help_effect_memory=help_memory,
        recent_episode_buffer=before["episodes"],
        rationale_memory=[],
        task_appraisal_result=appraisal.to_dict(),
        requested_strategy_type=strategy.strategy_type,
        support_delivery_status="not_requested",
    )
    # agent.forward writes this log inline. Keep its envelope and the decision
    # fields that memory.packet.extract_event_log_episodes reads. Both histories
    # refer to the same attempt by its production episode ID and timestamp.
    episode = memory["recent_episode_buffer"][-1]
    event_log = [
        {
            "day": episode["day"],
            "t": episode["tick_seconds"],
            "attempt_uid": task.task_id,
            "scenario": task.task_family,
            "outcome": "positive" if outcome.success else "negative",
            "message": f"{task.task_family}:{outcome.outcome_type}",
            "roll": outcome.success_probability,  # This production log field stores p(success).
            "decision": {
                "episode_id": episode["episode_id"],
                "requested_strategy_type": episode["requested_strategy_type"],
                "support_request_id": episode["support_request_id"],
                "support_delivery_status": episode["support_delivery_status"],
                "primary_reason": outcome.outcome_type,
                "task_family": task.task_family,
                "strategy_type": strategy.strategy_type,
                "help_used": outcome.help_used,
                "support_quality": outcome.support_quality,
                "event_level_uncontrollability": outcome.event_level_uncontrollability,
                "avoid_reason": outcome.avoid_reason,
                "support_mode": outcome.support_mode,
            },
        }
    ]
    next_emotion = prepare_digital_emotion_state_for_day(
        post_event_emotion, target_day=DAY
    )
    after = {
        "helplessness": update.helplessness_after,
        "trust": compatibility.trust_in_apps,
        "avoidance": compatibility.avoidance_tendency,
        "consecutive_failures": update.next_consecutive_failures,
        "emotion": next_emotion.to_dict(),
        "task_domain": deepcopy(memory["task_domain_snapshot"]),
        "help_overall": deepcopy(memory["help_effect_memory"]["overall"]),
        "episodes": deepcopy(memory["recent_episode_buffer"]),
        "event_log": deepcopy(event_log),
    }
    audit = {
        "before": before,
        "after": after,
        "profile_id": PROFILE_ID,
        "profile": dict(PROFILE),
        "environment": dict(ENVIRONMENT),
        "day1_3_completed_tasks": 0,
        "task": task.to_dict(),
        "strategy": strategy.to_dict(),
        "pre_event_appraisal": appraisal.to_dict(),
        "intervention": {
            "stage": "D4 resolve_attempt_outcome, rule_v1 sampler",
            "target_outcome": target_outcome,
            "controlled_draw": draw,
        },
        "outcome": outcome.to_dict(),
        "d4_post_outcome_modules": {
            "infer_event_attribution": {
                "called": False,
                "status": outcome.event_attribution_status,
                "attribution_confidence": outcome.event_attribution_confidence,
            },
            "calibrate_uncontrollability": {
                "called": False,
                "status": outcome.uncontrollability_status,
                "value_source": outcome.uncontrollability_source,
                "event_level_uncontrollability": outcome.event_level_uncontrollability,
            },
        },
        "helplessness_input": asdict(update_input),
        "helplessness_update": update.to_dict(),
        "compatibility_update": compatibility.to_dict(),
        "scores_range": [0, 100],
        "emotion_range": [0, 10],
        "post_event_emotion": post_event_emotion,
        "event_time": {
            "report_day": event_day + 1,
            "engine_day": event_day,
            "hour": HOUR,
            "tick_seconds": TICK,
            "sim_hour": monotonic_sim_hour(event_day, TICK),
        },
        "read_time": {
            "report_day": DAY + 1,
            "engine_day": DAY,
            "hour": HOUR,
            "tick_seconds": TICK,
            "sim_hour": monotonic_sim_hour(DAY, TICK),
        },
        "carry_forward": {
            "applied": ["prepare_digital_emotion_state_for_day"],
            "intervening_hourly_steps_executed": 0,
            "intervening_task_events": 0,
            "skipped": [
                "hourly_plans",
                "goal_retries",
                "stage_transitions",
                "daily_reflection",
                "stream_recording_and_retrieval",
                "bayesian_updates",
            ],
            "scope": "One scheduled D4 login, then one day of emotion decay. "
            "D5 starts at the matched new login opportunity.",
        },
        "d4_llm_calls": 0,
    }
    return FeedbackState(
        condition=condition,
        helplessness=update.helplessness_after,
        trust=compatibility.trust_in_apps,
        avoidance=compatibility.avoidance_tendency,
        consecutive_failures=update.next_consecutive_failures,
        emotion=next_emotion.to_dict(),
        domain_memory=memory["task_domain_memory"],
        help_memory=memory["help_effect_memory"],
        episodes=memory["recent_episode_buffer"],
        event_log=event_log,
        rationale_memory=memory["rationale_memory"],
        audit=audit,
    )
