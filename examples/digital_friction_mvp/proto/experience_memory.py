from __future__ import annotations

import copy
from typing import Any

from .models import (
    AttemptOutcome,
    AttemptStrategy,
    DigitalTask,
    DigitalEmotionState,
    HelpEffectState,
    MemoryFeatures,
    RecentEpisode,
    TaskAppraisalResult,
    TaskDomainState,
)
from .llm_psychology import normalize_digital_emotion_state
from .task_assignment import TASK_LIBRARY

TASK_FAMILIES: tuple[str, ...] = tuple(
    str(template["task_family"]) for template in TASK_LIBRARY
)
_TASK_DEFAULT_DIFFICULTIES = {
    str(template["task_family"]): float(template["difficulty"])
    for template in TASK_LIBRARY
}
_FAILURE_OUTCOMES = {
    "failure_after_attempt",
    "failure_even_with_help",
    "abandon_midway",
}
_TASK_SELF_EFFICACY_DELTAS = {
    "success_self": 6.0,
    "success_with_help": 4.0,
    "failure_after_attempt": -5.0,
    "failure_even_with_help": -6.0,
    "abandon_midway": -4.0,
    "avoid_without_attempt": -2.0,
}
_AVOID_SELF_EFFICACY_DELTAS = {
    "helpless_avoid": -2.0,
    "risk_avoid": -0.5,
    "low_value_avoid": 0.0,
}
_CONTROLLABLE_SUCCESS_DECAY_PER_DAY = 0.985
_ATTRIBUTION_EMA_KEEP = 0.7
_TASK_FAMILY_NEIGHBORS = {
    "login_verification": ("payment_checkout",),
    "payment_checkout": ("login_verification",),
    "appointment_registration": ("health_info_lookup",),
    "health_info_lookup": ("appointment_registration",),
}


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _copy_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def _blank_help_bucket() -> dict[str, Any]:
    return HelpEffectState().to_dict()


def _dominant_stability_label(ratio: float) -> str:
    if ratio >= 0.6:
        return "stable"
    if ratio < 0.3:
        return "transient"
    return "mixed"


def _dominant_scope_label(ratio: float) -> str:
    if ratio >= 0.6:
        return "family_generalizing"
    if ratio < 0.3:
        return "task_specific"
    return "mixed"


def _attribution_summary_text(stability: str, scope: str) -> str:
    return f"recent attribution tends toward {stability}/{scope}"


def _stable_recovery_multiplier(ratio: float) -> float:
    return _clamp(1.0 - 0.45 * float(ratio), 0.55, 1.0)


def _refresh_attribution_summary(state: TaskDomainState) -> None:
    state.dominant_attribution_stability = _dominant_stability_label(
        state.recent_stable_attribution_ratio
    )
    state.dominant_attribution_scope = _dominant_scope_label(
        state.recent_generalizing_attribution_ratio
    )
    state.attribution_summary = _attribution_summary_text(
        state.dominant_attribution_stability,
        state.dominant_attribution_scope,
    )


def _update_attribution_summary(state: TaskDomainState, outcome: AttemptOutcome) -> None:
    if outcome.outcome_type not in _FAILURE_OUTCOMES:
        return

    if str(getattr(outcome, "event_attribution_status", "")) != "ok":
        return

    stability = str(getattr(outcome, "event_attribution_stability", "not_applicable"))
    scope = str(getattr(outcome, "event_attribution_scope", "not_applicable"))
    if stability == "not_applicable" or scope == "not_applicable":
        return

    stable_target = 1.0 if stability == "stable" else 0.5 if stability == "mixed" else 0.0
    generalizing_target = (
        1.0 if scope == "family_generalizing" else 0.5 if scope == "mixed" else 0.0
    )
    state.recent_stable_attribution_ratio = _clamp_unit(
        _ATTRIBUTION_EMA_KEEP * state.recent_stable_attribution_ratio
        + (1.0 - _ATTRIBUTION_EMA_KEEP) * stable_target
    )
    state.recent_generalizing_attribution_ratio = _clamp_unit(
        _ATTRIBUTION_EMA_KEEP * state.recent_generalizing_attribution_ratio
        + (1.0 - _ATTRIBUTION_EMA_KEEP) * generalizing_target
    )
    _refresh_attribution_summary(state)


def _rewrite_attribution_after_mastery(
    state: TaskDomainState,
    *,
    outcome: AttemptOutcome,
    mastery_gain: float,
) -> None:
    if mastery_gain <= 0.0:
        return

    if outcome.outcome_type == "success_self":
        rewrite_strength = _clamp_unit(0.18 + 2.4 * mastery_gain)
    elif str(getattr(outcome, "support_mode", "")) == "enabling_support":
        rewrite_strength = _clamp_unit(0.06 + 2.0 * mastery_gain)
    else:
        return

    state.recent_stable_attribution_ratio = _clamp_unit(
        state.recent_stable_attribution_ratio * (1.0 - rewrite_strength)
    )
    state.recent_generalizing_attribution_ratio = _clamp_unit(
        state.recent_generalizing_attribution_ratio * (1.0 - rewrite_strength)
    )
    _refresh_attribution_summary(state)


def _apply_task_family_generalization(
    normalized: dict[str, dict[str, Any]],
    *,
    source_task_family: str,
    outcome: AttemptOutcome,
) -> None:
    if outcome.outcome_type not in _FAILURE_OUTCOMES:
        return

    scope = str(getattr(outcome, "event_attribution_scope", "not_applicable"))
    if scope == "family_generalizing":
        penalty = 1.2
    elif scope == "mixed":
        penalty = 0.5
    else:
        return

    for neighbor_family in _TASK_FAMILY_NEIGHBORS.get(str(source_task_family), ()):
        payload = normalized.get(neighbor_family)
        if not isinstance(payload, dict):
            continue
        neighbor_state = TaskDomainState.from_dict(payload)
        neighbor_state.task_self_efficacy = _clamp(
            neighbor_state.task_self_efficacy - penalty
        )
        normalized[neighbor_family] = neighbor_state.to_dict()


def _task_self_efficacy_delta(outcome: AttemptOutcome) -> float:
    if outcome.outcome_type == "success_with_help":
        return (
            4.5 if str(getattr(outcome, "support_mode", "")) == "enabling_support" else 1.5
        )
    if outcome.outcome_type == "failure_even_with_help":
        return (
            -4.5
            if str(getattr(outcome, "support_mode", "")) == "enabling_support"
            else -6.0
        )
    if outcome.outcome_type != "avoid_without_attempt":
        return float(_TASK_SELF_EFFICACY_DELTAS.get(outcome.outcome_type, 0.0))
    return float(
        _AVOID_SELF_EFFICACY_DELTAS.get(
            str(getattr(outcome, "avoid_reason", "not_applicable")),
            -1.0,
        )
    )


def _controllable_success_gain(
    *,
    task: DigitalTask,
    outcome: AttemptOutcome,
    task_appraisal_result: Any,
    previous_failure_streak: int,
) -> float:
    appraisal = TaskAppraisalResult.from_dict(
        task_appraisal_result if isinstance(task_appraisal_result, dict) else None
    )
    felt_control = float(appraisal.felt_control)
    uncontrollability = int(outcome.event_level_uncontrollability)
    difficulty_weight = _clamp(0.85 + (float(task.difficulty) - 0.5) * 0.8, 0.75, 1.15)

    if outcome.outcome_type == "success_self":
        if felt_control < 55.0 or uncontrollability > 1:
            return 0.0
        gain = 0.12 if uncontrollability == 0 else 0.08
        if previous_failure_streak >= 1:
            gain += 0.03
        return gain * difficulty_weight

    if outcome.outcome_type != "success_with_help":
        return 0.0

    if str(getattr(outcome, "support_mode", "")) != "enabling_support":
        return 0.0
    if felt_control < 55.0 or uncontrollability > 1:
        return 0.0

    gain = 0.045 if uncontrollability == 0 else 0.03
    if previous_failure_streak >= 2:
        gain += 0.01
    return gain * difficulty_weight


def build_initial_task_domain_memory(
    *,
    digital_experience: float,
    vision_limit: float,
    past_fraud_experience: float,
) -> dict[str, dict[str, Any]]:
    base_profile = (
        35.0
        + 40.0 * float(digital_experience)
        - 12.0 * float(vision_limit)
        - 10.0 * float(past_fraud_experience)
    )
    memory: dict[str, dict[str, Any]] = {}
    for task_family in TASK_FAMILIES:
        difficulty = _TASK_DEFAULT_DIFFICULTIES.get(task_family, 0.5)
        initial_task_self_efficacy = _clamp(
            base_profile - 12.0 * (difficulty - 0.5),
            15.0,
            85.0,
        )
        memory[task_family] = TaskDomainState(
            task_self_efficacy=initial_task_self_efficacy
        ).to_dict()
    return memory


def build_initial_help_effect_memory() -> dict[str, Any]:
    return {
        "overall": _blank_help_bucket(),
        "by_task_family": {
            task_family: _blank_help_bucket() for task_family in TASK_FAMILIES
        },
        "by_source": {
            "generic": _blank_help_bucket(),
        },
    }


def build_initial_recent_episode_buffer() -> list[dict[str, Any]]:
    return []


def build_initial_rationale_memory() -> list[dict[str, Any]]:
    return []


def _normalize_task_domain_memory(raw_value: Any) -> dict[str, dict[str, Any]]:
    default_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    if not isinstance(raw_value, dict):
        return _copy_dict(default_memory)
    normalized: dict[str, dict[str, Any]] = {}
    for task_family in TASK_FAMILIES:
        payload = raw_value.get(task_family)
        if isinstance(payload, dict):
            normalized[task_family] = TaskDomainState.from_dict(payload).to_dict()
        else:
            normalized[task_family] = TaskDomainState.from_dict(
                default_memory[task_family]
            ).to_dict()
    return normalized


def _normalize_help_effect_memory(raw_value: Any) -> dict[str, Any]:
    default_memory = build_initial_help_effect_memory()
    if not isinstance(raw_value, dict):
        return _copy_dict(default_memory)

    overall_payload = raw_value.get("overall")
    by_task_family_payload = raw_value.get("by_task_family")
    by_source_payload = raw_value.get("by_source")

    normalized = {
        "overall": HelpEffectState.from_dict(
            overall_payload if isinstance(overall_payload, dict) else None
        ).to_dict(),
        "by_task_family": {},
        "by_source": {
            "generic": HelpEffectState.from_dict(
                by_source_payload.get("generic")
                if isinstance(by_source_payload, dict)
                and isinstance(by_source_payload.get("generic"), dict)
                else None
            ).to_dict()
        },
    }
    for task_family in TASK_FAMILIES:
        payload = (
            by_task_family_payload.get(task_family)
            if isinstance(by_task_family_payload, dict)
            else None
        )
        normalized["by_task_family"][task_family] = HelpEffectState.from_dict(
            payload if isinstance(payload, dict) else None
        ).to_dict()
    return normalized


def _normalize_recent_episode_buffer(raw_value: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list):
        return []
    episodes = [
        RecentEpisode.from_dict(item).to_dict()
        for item in raw_value
        if isinstance(item, dict)
    ]
    return episodes[-8:]


def _normalize_rationale_memory(raw_value: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_value, list):
        return []
    rationales = [copy.deepcopy(item) for item in raw_value if isinstance(item, dict)]
    return rationales[-3:]


def _update_help_bucket(
    bucket_payload: dict[str, Any],
    *,
    success: bool,
) -> dict[str, Any]:
    bucket = HelpEffectState.from_dict(bucket_payload)
    bucket.help_attempt_count += 1
    if success:
        bucket.help_success_count += 1
    else:
        bucket.help_failure_count += 1
    bucket.help_success_rate_smoothed = (
        bucket.help_success_count + 1.0
    ) / (bucket.help_attempt_count + 2.0)
    return bucket.to_dict()


def _summarize_recent_episode_buffer(
    *,
    task_family: str,
    recent_episode_buffer: list[dict[str, Any]],
) -> dict[str, Any]:
    episodes = [
        RecentEpisode.from_dict(item)
        for item in _normalize_recent_episode_buffer(recent_episode_buffer)
    ]
    total = len(episodes)
    if total == 0:
        return {
            "buffer_size": 0,
            "recent_negative_feedback_ratio": 0.0,
            "recent_avoid_ratio": 0.0,
            "recent_help_seek_ratio": 0.0,
            "recent_same_task_failure_count": 0,
            "recent_failure_pressure": 0.0,
        }

    recent_negative_feedback_ratio = sum(
        1 for episode in episodes if episode.negative_feedback
    ) / float(total)
    recent_avoid_ratio = sum(
        1
        for episode in episodes
        if (
            episode.outcome_type == "avoid_without_attempt"
            and str(episode.avoid_reason) == "helpless_avoid"
        )
    ) / float(total)
    recent_help_seek_ratio = sum(
        1 for episode in episodes if episode.strategy_type == "seek_help_then_attempt"
    ) / float(total)
    same_task_episodes = [
        episode
        for episode in reversed(episodes)
        if episode.task_family == task_family
    ][:3]
    recent_same_task_failure_count = sum(
        1 for episode in same_task_episodes if episode.negative_feedback
    )
    recent_failure_pressure = min(
        8.0,
        5.0 * recent_negative_feedback_ratio
        + 2.0 * recent_avoid_ratio
        + 1.0 * recent_same_task_failure_count,
    )
    return {
        "buffer_size": total,
        "recent_negative_feedback_ratio": recent_negative_feedback_ratio,
        "recent_avoid_ratio": recent_avoid_ratio,
        "recent_help_seek_ratio": recent_help_seek_ratio,
        "recent_same_task_failure_count": recent_same_task_failure_count,
        "recent_failure_pressure": recent_failure_pressure,
    }


def extract_memory_features(
    *,
    task: DigitalTask,
    helplessness_score: float,
    task_domain_memory: Any,
    help_effect_memory: Any,
    recent_episode_buffer: Any,
    digital_emotion_state: Any = None,
    task_appraisal_result: Any = None,
    psychology_mode: str = "off",
) -> MemoryFeatures:
    normalized_task_memory = _normalize_task_domain_memory(task_domain_memory)
    normalized_help_memory = _normalize_help_effect_memory(help_effect_memory)
    summary = _summarize_recent_episode_buffer(
        task_family=task.task_family,
        recent_episode_buffer=_normalize_recent_episode_buffer(recent_episode_buffer),
    )

    task_state = TaskDomainState.from_dict(normalized_task_memory.get(task.task_family))
    overall_help = HelpEffectState.from_dict(normalized_help_memory["overall"])
    family_help = HelpEffectState.from_dict(
        normalized_help_memory["by_task_family"].get(task.task_family)
    )
    generic_help = HelpEffectState.from_dict(
        normalized_help_memory["by_source"].get("generic")
    )
    if family_help.help_attempt_count > 0:
        help_success_rate_smoothed = family_help.help_success_rate_smoothed
    elif overall_help.help_attempt_count > 0:
        help_success_rate_smoothed = overall_help.help_success_rate_smoothed
    else:
        help_success_rate_smoothed = generic_help.help_success_rate_smoothed

    task_specific_pressure = max(0.0, 50.0 - task_state.task_self_efficacy) * 0.10
    help_confidence_bonus = (help_success_rate_smoothed - 0.5) * 0.20
    emotion_pressure = 0.0
    task_appraisal = TaskAppraisalResult.from_dict(
        task_appraisal_result if isinstance(task_appraisal_result, dict) else None
    )
    difficulty_shift = (
        float(task_appraisal.perceived_task_difficulty) - 50.0
    ) * 0.03
    # Appraisal signals remain available for audit/strategy interpretation, but no longer
    # get merged back into effective helplessness as if they were the same construct.
    task_appraisal_shift = _clamp(difficulty_shift, -1.5, 2.0)
    if str(psychology_mode).strip().lower() == "hybrid":
        emotion_state = normalize_digital_emotion_state(digital_emotion_state)
        emotion_pressure = _clamp(
            0.25 * float(emotion_state.anxiety)
            - 0.20 * float(emotion_state.confidence),
            -2.0,
            3.0,
        )
    effective_helplessness = _clamp(
        float(helplessness_score)
        + task_specific_pressure
        + float(summary["recent_failure_pressure"]),
        0.0,
        100.0,
    )
    return MemoryFeatures(
        effective_helplessness=effective_helplessness,
        task_self_efficacy=task_state.task_self_efficacy,
        controllable_success_memory=task_state.controllable_success_memory,
        task_specific_pressure=task_specific_pressure,
        help_success_rate_smoothed=help_success_rate_smoothed,
        help_confidence_bonus=help_confidence_bonus,
        recent_negative_feedback_ratio=float(
            summary["recent_negative_feedback_ratio"]
        ),
        recent_avoid_ratio=float(summary["recent_avoid_ratio"]),
        recent_help_seek_ratio=float(summary["recent_help_seek_ratio"]),
        recent_same_task_failure_count=int(summary["recent_same_task_failure_count"]),
        recent_failure_pressure=float(summary["recent_failure_pressure"]),
        emotion_pressure=emotion_pressure,
        task_appraisal_shift=task_appraisal_shift,
    )


def update_task_domain_memory(
    *,
    task: DigitalTask,
    outcome: AttemptOutcome,
    day: int,
    task_domain_memory: Any,
    task_appraisal_result: Any = None,
) -> dict[str, dict[str, Any]]:
    normalized = _normalize_task_domain_memory(task_domain_memory)
    state = TaskDomainState.from_dict(normalized.get(task.task_family))
    if state.last_updated_day >= 0 and day > state.last_updated_day:
        day_gap = day - state.last_updated_day
        state.recent_negative_feedback_ema *= 0.9 ** day_gap
        state.controllable_success_memory *= (
            _CONTROLLABLE_SUCCESS_DECAY_PER_DAY ** day_gap
        )

    if outcome.outcome_type != "avoid_without_attempt":
        state.attempt_count += 1
    else:
        state.avoid_count += 1

    previous_failure_streak = state.same_task_failure_streak
    delta = _task_self_efficacy_delta(outcome)
    mastery_gain = 0.0
    if outcome.success:
        state.success_count += 1
        delta *= _stable_recovery_multiplier(
            state.recent_stable_attribution_ratio
        )
        mastery_gain = _controllable_success_gain(
            task=task,
            outcome=outcome,
            task_appraisal_result=task_appraisal_result,
            previous_failure_streak=previous_failure_streak,
        )
        state.same_task_failure_streak = 0
    elif outcome.outcome_type in _FAILURE_OUTCOMES:
        state.failure_count += 1
        state.same_task_failure_streak += 1
        if state.same_task_failure_streak == 2:
            delta -= 1.0
        elif state.same_task_failure_streak >= 3:
            delta -= 2.0

    current_negative = 1.0 if outcome.negative_feedback else 0.0
    state.task_self_efficacy = _clamp(state.task_self_efficacy + delta)
    state.controllable_success_memory = _clamp_unit(
        state.controllable_success_memory + mastery_gain
    )
    _update_attribution_summary(state, outcome)
    _rewrite_attribution_after_mastery(
        state,
        outcome=outcome,
        mastery_gain=mastery_gain,
    )
    state.recent_negative_feedback_ema = (
        0.7 * state.recent_negative_feedback_ema + 0.3 * current_negative
    )
    state.last_outcome = outcome.outcome_type
    state.last_updated_day = int(day)
    normalized[task.task_family] = state.to_dict()
    _apply_task_family_generalization(
        normalized,
        source_task_family=task.task_family,
        outcome=outcome,
    )
    return normalized


def update_help_effect_memory(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    help_effect_memory: Any,
) -> dict[str, Any]:
    normalized = _normalize_help_effect_memory(help_effect_memory)
    if strategy.strategy_type != "seek_help_then_attempt":
        return normalized

    success = outcome.outcome_type == "success_with_help"
    failure = outcome.outcome_type in {"failure_even_with_help", "abandon_midway"}
    if not success and not failure:
        return normalized

    normalized["overall"] = _update_help_bucket(
        normalized["overall"], success=success
    )
    normalized["by_task_family"][task.task_family] = _update_help_bucket(
        normalized["by_task_family"][task.task_family],
        success=success,
    )
    normalized["by_source"]["generic"] = _update_help_bucket(
        normalized["by_source"]["generic"],
        success=success,
    )
    return normalized


def update_recent_episode_buffer(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    day: int,
    helplessness_delta: float,
    recent_episode_buffer: Any,
) -> list[dict[str, Any]]:
    normalized = _normalize_recent_episode_buffer(recent_episode_buffer)
    normalized.append(
        RecentEpisode(
            day=int(day),
            task_family=task.task_family,
            strategy_type=strategy.strategy_type,
            outcome_type=outcome.outcome_type,
            avoid_reason=str(getattr(outcome, "avoid_reason", "not_applicable")),
            help_used=outcome.help_used,
            help_source="generic" if outcome.help_used else "none",
            negative_feedback=outcome.negative_feedback,
            event_level_uncontrollability=outcome.event_level_uncontrollability,
            helplessness_delta=float(helplessness_delta),
        ).to_dict()
    )
    return normalized[-8:]


def update_rationale_memory(
    *,
    task: DigitalTask,
    outcome: AttemptOutcome,
    day: int,
    previous_task_failure_streak: int,
    current_task_failure_streak: int,
    rationale_memory: Any,
) -> list[dict[str, Any]]:
    normalized = _normalize_rationale_memory(rationale_memory)
    reason_type = ""
    text = ""

    if outcome.outcome_type == "failure_even_with_help":
        reason_type = "help_failure"
        text = "有人帮也没做成，我更没把握了"
    elif outcome.outcome_type == "avoid_without_attempt":
        reason_type = "avoid"
        avoid_reason = str(getattr(outcome, "avoid_reason", "not_applicable"))
        if avoid_reason == "risk_avoid":
            text = "这次风险太高，我先不想冒险"
        elif avoid_reason == "low_value_avoid":
            text = "这事现在对我不太值当，我先放一放"
        elif previous_task_failure_streak >= 2:
            text = "这类任务老失败，我有点不敢再试"
        else:
            text = "这次我先不想碰这个任务"
    elif outcome.outcome_type == "success_self" and previous_task_failure_streak >= 2:
        reason_type = "self_recovery"
        text = "这次自己做成了，感觉还能学会"
    elif (
        outcome.negative_feedback
        and current_task_failure_streak >= 2
        and outcome.outcome_type != "failure_even_with_help"
    ):
        reason_type = "repeated_failure"
        text = "这类任务总失败，我越来越没把握"

    if not text:
        return normalized

    normalized.append(
        {
            "day": int(day),
            "task_family": task.task_family,
            "reason_type": reason_type,
            "text": text[:30],
        }
    )
    return normalized[-3:]


def update_experience_memory(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    day: int,
    helplessness_delta: float,
    task_domain_memory: Any,
    help_effect_memory: Any,
    recent_episode_buffer: Any,
    rationale_memory: Any,
    task_appraisal_result: Any = None,
) -> dict[str, Any]:
    normalized_task_memory = _normalize_task_domain_memory(task_domain_memory)
    previous_task_state = TaskDomainState.from_dict(
        normalized_task_memory.get(task.task_family)
    )
    updated_task_memory = update_task_domain_memory(
        task=task,
        outcome=outcome,
        day=day,
        task_domain_memory=normalized_task_memory,
        task_appraisal_result=task_appraisal_result,
    )
    updated_task_state = TaskDomainState.from_dict(
        updated_task_memory.get(task.task_family)
    )
    updated_help_memory = update_help_effect_memory(
        task=task,
        strategy=strategy,
        outcome=outcome,
        help_effect_memory=help_effect_memory,
    )
    updated_recent_buffer = update_recent_episode_buffer(
        task=task,
        strategy=strategy,
        outcome=outcome,
        day=day,
        helplessness_delta=helplessness_delta,
        recent_episode_buffer=recent_episode_buffer,
    )
    updated_rationale_memory = update_rationale_memory(
        task=task,
        outcome=outcome,
        day=day,
        previous_task_failure_streak=previous_task_state.same_task_failure_streak,
        current_task_failure_streak=updated_task_state.same_task_failure_streak,
        rationale_memory=rationale_memory,
    )
    recent_summary = _summarize_recent_episode_buffer(
        task_family=task.task_family,
        recent_episode_buffer=updated_recent_buffer,
    )
    return {
        "task_domain_memory": updated_task_memory,
        "help_effect_memory": updated_help_memory,
        "recent_episode_buffer": updated_recent_buffer,
        "rationale_memory": updated_rationale_memory,
        "task_domain_snapshot": copy.deepcopy(updated_task_memory[task.task_family]),
        "help_effect_snapshot": {
            "overall": copy.deepcopy(updated_help_memory["overall"]),
            "task_family": copy.deepcopy(
                updated_help_memory["by_task_family"][task.task_family]
            ),
            "source": copy.deepcopy(updated_help_memory["by_source"]["generic"]),
        },
        "recent_episode_summary": recent_summary,
        "rationale_snapshot": copy.deepcopy(updated_rationale_memory),
    }
