from __future__ import annotations

import random
import json
import math
from typing import Any

from .models import (
    AttemptOutcome,
    AttemptStrategy,
    DigitalTask,
    MemoryFeatures,
    OutcomeAppraisalResult,
    TaskAppraisalResult,
)
from .support_protocol import SupportResponse, support_style_to_support_mode


OUTCOME_MODEL_MODES = {
    "rule_v1",
    "appraisal_rule_v2",
    "trajectory_shadow",
    "trajectory_bounded_online_mc",
}
_ATTEMPT_SELF_OUTCOME_KEYS = (
    "success_self",
    "failure_after_attempt",
    "abandon_midway",
)
_HELP_OUTCOME_KEYS = (
    "success_with_help",
    "failure_even_with_help",
    "failure_after_attempt",
    "abandon_midway",
)


def clamp_probability(value: float) -> float:
    return max(0.01, min(0.99, float(value)))


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _round_distribution(distribution: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 6) for key, value in distribution.items()}


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _task_appraisal_from_any(value: Any) -> TaskAppraisalResult:
    if isinstance(value, TaskAppraisalResult):
        return value
    if isinstance(value, dict):
        return TaskAppraisalResult.from_dict(value)
    return TaskAppraisalResult(
        mode="off",
        status="missing",
        source="rule_default",
        confidence=0.0,
        reason="",
        cache_hit=False,
    )


def _memory_float(value: Any, field_name: str, default: float) -> float:
    if isinstance(value, MemoryFeatures):
        return float(getattr(value, field_name))
    if isinstance(value, dict):
        try:
            return float(value.get(field_name, default))
        except (TypeError, ValueError):
            return float(default)
    return float(default)


def _memory_int(value: Any, field_name: str, default: int) -> int:
    if isinstance(value, MemoryFeatures):
        return int(getattr(value, field_name))
    if isinstance(value, dict):
        try:
            return int(float(value.get(field_name, default)))
        except (TypeError, ValueError):
            return int(default)
    return int(default)


def allowed_outcome_keys_for_strategy(strategy: AttemptStrategy) -> tuple[str, ...]:
    if strategy.strategy_type == "attempt_self":
        return _ATTEMPT_SELF_OUTCOME_KEYS
    if strategy.strategy_type == "seek_help_then_attempt":
        return _HELP_OUTCOME_KEYS
    if strategy.strategy_type == "avoid":
        return ("avoid_without_attempt",)
    raise ValueError(f"unsupported strategy_type: {strategy.strategy_type}")


def validate_outcome_distribution(
    distribution: dict[str, float],
    *,
    allowed_keys: tuple[str, ...],
    tolerance: float = 0.000001,
) -> dict[str, float]:
    if not isinstance(distribution, dict) or not distribution:
        raise ValueError("outcome distribution must be a non-empty dict")
    allowed = set(allowed_keys)
    if set(distribution.keys()) != allowed:
        raise ValueError(
            "outcome distribution keys must exactly match allowed outcomes: "
            + ", ".join(sorted(allowed))
        )
    normalized: dict[str, float] = {}
    for key in allowed_keys:
        value = distribution.get(key)
        if isinstance(value, bool):
            raise ValueError("outcome distribution values must be numeric")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("outcome distribution values must be numeric") from exc
        if numeric < -tolerance or numeric > 1.0 + tolerance:
            raise ValueError("outcome distribution values must be in [0,1]")
        normalized[key] = max(0.0, min(1.0, numeric))
    total = sum(normalized.values())
    if abs(total - 1.0) > max(tolerance, 0.0001):
        raise ValueError("outcome distribution probabilities must sum to 1")
    if total <= 0:
        raise ValueError("outcome distribution total must be positive")
    return {key: normalized[key] / total for key in allowed_keys}


def _total_variation_distance(
    left: dict[str, float],
    right: dict[str, float],
    keys: tuple[str, ...],
) -> float:
    return 0.5 * sum(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) for key in keys)


def _normalize_distribution(
    distribution: dict[str, float],
    *,
    keys: tuple[str, ...],
) -> dict[str, float]:
    clipped = {key: max(0.0, float(distribution.get(key, 0.0))) for key in keys}
    total = sum(clipped.values())
    if total <= 0:
        return {key: 1.0 / float(len(keys)) for key in keys}
    return {key: clipped[key] / total for key in keys}


def _cap_residual_to_bounds(
    *,
    rule_distribution: dict[str, float],
    candidate_distribution: dict[str, float],
    keys: tuple[str, ...],
    max_shift: float,
    max_tvd: float,
) -> dict[str, float]:
    residual = {
        key: float(candidate_distribution.get(key, 0.0))
        - float(rule_distribution.get(key, 0.0))
        for key in keys
    }
    max_abs = max((abs(value) for value in residual.values()), default=0.0)
    tvd = 0.5 * sum(abs(value) for value in residual.values())
    scale = 1.0
    if max_shift >= 0 and max_abs > max_shift > 0:
        scale = min(scale, max_shift / max_abs)
    if max_tvd >= 0 and tvd > max_tvd > 0:
        scale = min(scale, max_tvd / tvd)
    if max_shift == 0 or max_tvd == 0:
        scale = 0.0
    adjusted = {
        key: float(rule_distribution.get(key, 0.0)) + residual[key] * scale
        for key in keys
    }
    return _normalize_distribution(adjusted, keys=keys)


def support_quality_from_env(env: dict[str, Any]) -> int:
    total = int(float(env.get("assist_level", 0))) + int(
        float(env.get("human_support_level", 0))
    ) + int(float(env.get("accessibility_level", 0)))
    if total <= 1:
        return 0
    if total <= 5:
        return 1
    return 2


def _support_response_from_any(value: Any) -> SupportResponse | None:
    if value is None:
        return None
    if isinstance(value, SupportResponse):
        return value
    if isinstance(value, dict):
        try:
            return SupportResponse.from_dict(value)
        except ValueError:
            return None
    return None


def derive_effective_support_features(
    support_response: Any,
    env: dict[str, Any] | None = None,
) -> dict[str, float | str]:
    response = _support_response_from_any(support_response)
    if response is None:
        return {
            "effective_support_quality": 0.0,
            "substitution_pressure": 0.0,
            "support_unavailability": 0.0,
            "support_style": "none",
            "source": "none",
        }

    style = response.support_style
    quality = 0.0
    substitution = 0.0
    unavailable = 0.0
    if style == "enabling":
        quality = 0.75
        substitution = 0.05
    elif style == "substituting":
        quality = 0.45
        substitution = 0.65
    elif style == "dismissive":
        quality = 0.10
        substitution = 0.35
        unavailable = 0.35
    else:
        quality = 0.0
        substitution = 0.0
        unavailable = 1.0

    instruction_bonus = {
        "none": -0.10,
        "low": -0.04,
        "medium": 0.04,
        "high": 0.12,
    }.get(response.instruction_quality, 0.0)
    autonomy_bonus = {
        "low": -0.10,
        "medium": 0.0,
        "high": 0.10,
        "not_applicable": 0.0,
    }.get(response.autonomy_preservation, 0.0)
    proxy_pressure = {
        "none": 0.0,
        "partial": 0.25,
        "full": 0.60,
        "not_applicable": 0.0,
    }.get(response.proxy_completion_level, 0.0)
    delay_penalty = {
        "immediate": 0.0,
        "delayed": 0.20,
        "no_response": 0.65,
    }.get(response.response_delay, 0.0)
    env_quality = 0.0
    if isinstance(env, dict):
        env_quality = float(support_quality_from_env(env)) / 2.0
    confidence_scale = 0.55 + 0.45 * _clamp_unit(response.confidence)
    quality = _clamp_unit(
        (0.78 * quality + 0.22 * env_quality + instruction_bonus + autonomy_bonus)
        * confidence_scale
    )
    substitution = _clamp_unit(substitution + proxy_pressure)
    unavailable = _clamp_unit(unavailable + delay_penalty)
    return {
        "effective_support_quality": float(quality),
        "substitution_pressure": float(substitution),
        "support_unavailability": float(unavailable),
        "support_style": style,
        "source": str(response.source),
    }


def friction_tier_from_env(task: DigitalTask, env: dict[str, Any]) -> int:
    friction = float(env.get("friction_level", 0))
    malicious = float(env.get("malicious_friction_level", 0))
    complexity = float(env.get("complexity_level", 0))
    risk = float(env.get("risk_level", 0))
    if task.friction_type == "verification":
        raw = (friction + malicious) / 2.0
    elif task.friction_type == "form_complexity":
        raw = (friction + complexity) / 2.0
    elif task.friction_type == "payment_risk_popup":
        raw = (risk + malicious) / 2.0
    else:
        raw = (friction + complexity) / 2.0
    if raw <= 1.0:
        return 0
    if raw <= 2.0:
        return 1
    return 2


def infer_event_level_uncontrollability(
    *,
    task: DigitalTask,
    outcome_type: str,
    friction_tier: int,
    consecutive_failures_after_event: int,
) -> int:
    if outcome_type in {"success_self", "success_with_help"}:
        return 0
    if outcome_type == "failure_even_with_help":
        return 2
    if consecutive_failures_after_event >= 3:
        return 2
    if friction_tier >= 2 and task.friction_type in {"verification", "payment_risk_popup"}:
        return 2
    if friction_tier >= 2:
        return 1
    if consecutive_failures_after_event == 2:
        return 1
    if friction_tier == 1:
        return 1
    if task.friction_type in {"form_complexity", "information_overload"}:
        return 1
    return 0


def infer_avoid_reason(
    *,
    task: DigitalTask,
    env: dict[str, Any],
    helplessness: float,
    recent_same_task_failure_count: int,
    task_self_efficacy: float,
    felt_control: float,
    perceived_task_risk: float,
    task_value: float,
) -> dict[str, Any]:
    helpless_score = (
        _clamp_unit((float(helplessness) - 62.0) / 18.0)
        + _clamp_unit((45.0 - float(task_self_efficacy)) / 18.0)
        + _clamp_unit((50.0 - float(felt_control)) / 18.0)
        + 0.35 * min(max(int(recent_same_task_failure_count), 0), 3)
    )
    if task.friction_type in {"verification", "form_complexity"}:
        helpless_score += 0.15

    risk_score = (
        _clamp_unit((float(perceived_task_risk) - 58.0) / 16.0)
        + 0.35 * max(0.0, min(2.0, float(env.get("risk_level", 0)) - 1.0))
    )
    if task.friction_type == "payment_risk_popup":
        risk_score += 0.45
    if float(felt_control) >= 45.0:
        risk_score += 0.10
    rational_security_score = 0.0
    if task.task_family == "payment_risk_confirmation":
        rational_security_score += 0.55
    if task.friction_type == "payment_risk_popup":
        rational_security_score += 0.45
    rational_security_score += _clamp_unit((float(perceived_task_risk) - 72.0) / 18.0)
    rational_security_score += 0.35 * max(
        0.0,
        min(2.0, float(env.get("risk_level", 0)) - 1.0),
    )
    rational_security_score += 0.30 * max(
        0.0,
        min(2.0, float(env.get("malicious_friction_level", 0)) - 1.0),
    )
    if float(task_value) >= 35.0:
        rational_security_score += 0.20
    else:
        rational_security_score -= 0.35
    if float(task_self_efficacy) < 45.0 or float(felt_control) < 35.0:
        rational_security_score -= 0.25

    value_score = _clamp_unit((42.0 - float(task_value)) / 15.0)
    if float(task_value) < 40.0:
        value_score += 0.35
    if float(perceived_task_risk) < 60.0:
        value_score += 0.10
    if int(recent_same_task_failure_count) == 0 and float(helplessness) < 70.0:
        value_score += 0.10

    scores = {
        "helpless_avoid": round(float(helpless_score), 4),
        "risk_avoid": round(float(risk_score), 4),
        "low_value_avoid": round(float(value_score), 4),
        "rational_security_avoid": round(float(rational_security_score), 4),
    }
    ranking = sorted(scores.items(), key=lambda item: (item[1], item[0]), reverse=True)
    label, top_score = ranking[0]
    second_score = ranking[1][1]
    confidence = max(0.55, min(0.95, 0.62 + 0.15 * (top_score - second_score)))
    if label == "helpless_avoid":
        note = "low_control_or_repeat_failure_dominates"
    elif label == "risk_avoid":
        note = "risk_signal_dominates"
    elif label == "rational_security_avoid":
        note = "rational_security_stop_dominates"
    else:
        note = "low_value_signal_dominates"
    return {
        "label": label,
        "source": "rule_task_appraisal",
        "confidence": round(confidence, 4),
        "note": note,
        "scores": scores,
    }


def infer_support_mode(
    *,
    outcome_type: str,
    support_quality: int,
    felt_control: float,
    expected_help_effectiveness: float,
    support_response: Any = None,
) -> dict[str, Any]:
    if outcome_type not in {"success_with_help", "failure_even_with_help", "abandon_midway"}:
        return {
            "label": "not_applicable",
            "source": "not_applicable",
            "confidence": 0.0,
            "note": "",
        }
    response = _support_response_from_any(support_response)
    if response is not None:
        label = support_style_to_support_mode(response.support_style)
        return {
            "label": label,
            "source": "support_response",
            "confidence": round(float(response.confidence), 4),
            "note": f"structured_support_style={response.support_style}",
        }

    support_signal = 0.0
    if int(support_quality) >= 1:
        support_signal += 0.20
    if int(support_quality) >= 2:
        support_signal += 0.25
    support_signal += _clamp_unit((float(felt_control) - 42.0) / 20.0)
    support_signal += _clamp_unit(
        (float(expected_help_effectiveness) - 50.0) / 20.0
    )
    if outcome_type == "success_with_help":
        support_signal += 0.10

    if support_signal >= 0.95:
        return {
            "label": "enabling_support",
            "source": "rule_task_appraisal",
            "confidence": round(min(0.92, 0.6 + 0.12 * support_signal), 4),
            "note": "help_keeps_agency_and_understanding",
        }
    return {
        "label": "substituting_support",
        "source": "rule_task_appraisal",
        "confidence": round(min(0.9, 0.64 + 0.08 * max(0.0, 1.1 - support_signal)), 4),
        "note": "help_finishes_more_than_it_teaches",
    }


def build_outcome_appraisal_rule_v2(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    env: dict[str, Any],
    consecutive_failures: int,
    task_appraisal: Any,
    memory_features: Any,
    support_response: Any = None,
) -> OutcomeAppraisalResult:
    appraisal = _task_appraisal_from_any(task_appraisal)
    support_quality = support_quality_from_env(env)
    friction_tier = friction_tier_from_env(task, env)
    effective_helplessness = _memory_float(
        memory_features,
        "effective_helplessness",
        float(helplessness),
    )
    task_self_efficacy = _memory_float(memory_features, "task_self_efficacy", 50.0)
    controllable_success_memory = _memory_float(
        memory_features,
        "controllable_success_memory",
        0.0,
    )
    recent_negative_feedback_ratio = _memory_float(
        memory_features,
        "recent_negative_feedback_ratio",
        0.0,
    )
    recent_same_task_failure_count = _memory_int(
        memory_features,
        "recent_same_task_failure_count",
        int(consecutive_failures),
    )
    recent_failure_pressure = _memory_float(
        memory_features,
        "recent_failure_pressure",
        min(max(float(consecutive_failures), 0.0), 3.0) / 3.0,
    )

    difficulty_pressure = _clamp_unit(
        0.55 * float(task.difficulty)
        + 0.45 * (float(appraisal.perceived_task_difficulty) / 100.0)
    )
    risk_pressure = _clamp_unit(
        0.55 * (float(appraisal.perceived_task_risk) / 100.0)
        + 0.45 * _clamp_unit(float(env.get("risk_level", 0)) / 3.0)
    )
    control_deficit = _clamp_unit(1.0 - float(appraisal.felt_control) / 100.0)
    efficacy_deficit = _clamp_unit(1.0 - float(task_self_efficacy) / 100.0)
    support_effective_quality = _clamp_unit(
        0.50 * (float(support_quality) / 2.0)
        + 0.35 * (float(appraisal.expected_help_effectiveness) / 100.0)
        + 0.15 * float(task.support_sensitivity)
    )
    support_features = derive_effective_support_features(
        support_response,
        env,
    )
    if strategy.strategy_type == "seek_help_then_attempt" and support_response is not None:
        support_effective_quality = _clamp_unit(
            0.78 * support_effective_quality
            + 0.22 * float(support_features["effective_support_quality"])
            - 0.10 * float(support_features["support_unavailability"])
            - 0.04 * float(support_features["substitution_pressure"])
        )
    if strategy.strategy_type != "seek_help_then_attempt":
        support_effective_quality *= 0.35
    abandonment_pressure = _clamp_unit(
        0.20 * difficulty_pressure
        + 0.16 * risk_pressure
        + 0.18 * control_deficit
        + 0.14 * efficacy_deficit
        + 0.10 * _clamp_unit(float(effective_helplessness) / 100.0)
        + 0.10 * recent_negative_feedback_ratio
        + 0.07 * min(max(float(recent_same_task_failure_count), 0.0), 3.0) / 3.0
        + 0.05 * recent_failure_pressure
    )

    return OutcomeAppraisalResult(
        mode="appraisal_rule_v2",
        status="ok",
        source="rule",
        confidence=1.0,
        reason="rule_appraisal_probability_inputs",
        cache_hit=False,
        perceived_task_difficulty=float(appraisal.perceived_task_difficulty),
        perceived_task_risk=float(appraisal.perceived_task_risk),
        felt_control=float(appraisal.felt_control),
        expected_help_effectiveness=float(appraisal.expected_help_effectiveness),
        task_value=float(appraisal.task_value),
        effective_helplessness=float(effective_helplessness),
        task_self_efficacy=float(task_self_efficacy),
        controllable_success_memory=float(controllable_success_memory),
        recent_negative_feedback_ratio=float(recent_negative_feedback_ratio),
        recent_same_task_failure_count=int(recent_same_task_failure_count),
        recent_failure_pressure=float(recent_failure_pressure),
        friction_tier=int(friction_tier),
        difficulty_pressure=float(difficulty_pressure),
        risk_pressure=float(risk_pressure),
        control_deficit=float(control_deficit),
        efficacy_deficit=float(efficacy_deficit),
        support_effective_quality=float(support_effective_quality),
        abandonment_pressure=float(abandonment_pressure),
    )


def build_rule_outcome_distribution_v2(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    env: dict[str, Any],
    consecutive_failures: int,
    task_appraisal: Any,
    memory_features: Any,
    support_response: Any = None,
) -> tuple[OutcomeAppraisalResult, dict[str, float]]:
    appraisal = build_outcome_appraisal_rule_v2(
        task=task,
        strategy=strategy,
        helplessness=helplessness,
        env=env,
        consecutive_failures=consecutive_failures,
        task_appraisal=task_appraisal,
        memory_features=memory_features,
        support_response=support_response,
    )
    if strategy.strategy_type == "avoid":
        return appraisal, {"avoid_without_attempt": 1.0}

    support_term = (
        appraisal.support_effective_quality
        if strategy.strategy_type == "seek_help_then_attempt"
        else 0.0
    )
    support_features = derive_effective_support_features(
        support_response,
        env,
    )
    substitution_pressure = (
        float(support_features["substitution_pressure"])
        if strategy.strategy_type == "seek_help_then_attempt"
        else 0.0
    )
    support_unavailability = (
        float(support_features["support_unavailability"])
        if strategy.strategy_type == "seek_help_then_attempt"
        else 0.0
    )
    abandon_logit = (
        -2.35
        + 1.25 * appraisal.difficulty_pressure
        + 0.95 * (float(appraisal.friction_tier) / 2.0)
        + 0.85 * appraisal.control_deficit
        + 0.75 * appraisal.efficacy_deficit
        + 0.65 * _clamp_unit(appraisal.effective_helplessness / 100.0)
        + 0.55 * appraisal.risk_pressure
        + 0.45 * appraisal.recent_negative_feedback_ratio
        + 0.22 * min(max(float(appraisal.recent_same_task_failure_count), 0.0), 3.0)
        + 0.30 * support_unavailability
        - 0.40 * _clamp_unit(appraisal.task_value / 100.0)
        - 0.55 * support_term
    )
    p_abandon = max(0.0, min(0.55, _sigmoid(abandon_logit)))

    success_logit = (
        1.10
        + 1.05 * _clamp_unit(appraisal.task_self_efficacy / 100.0)
        + 0.75 * _clamp_unit(appraisal.felt_control / 100.0)
        + 0.65 * appraisal.controllable_success_memory
        + 0.35 * _clamp_unit(appraisal.task_value / 100.0)
        + 0.90 * support_term
        - 1.30 * appraisal.difficulty_pressure
        - 0.85 * (float(appraisal.friction_tier) / 2.0)
        - 0.70 * _clamp_unit(appraisal.effective_helplessness / 100.0)
        - 0.45 * appraisal.risk_pressure
        - 0.45 * appraisal.recent_negative_feedback_ratio
        - 0.18 * min(max(float(appraisal.recent_same_task_failure_count), 0.0), 3.0)
        - 0.14 * support_unavailability
        - 0.06 * substitution_pressure
    )
    p_success_given_not_abandon = _sigmoid(success_logit)
    p_success = (1.0 - p_abandon) * p_success_given_not_abandon
    p_failure = max(0.0, 1.0 - p_abandon - p_success)

    if strategy.strategy_type == "attempt_self":
        distribution = {
            "success_self": p_success,
            "failure_after_attempt": p_failure,
            "abandon_midway": p_abandon,
        }
    elif strategy.strategy_type == "seek_help_then_attempt":
        effective_help_share = _clamp_unit(
            0.20
            + 0.70 * support_term
            + 0.15 * substitution_pressure
            - 0.20 * support_unavailability
        )
        distribution = {
            "success_with_help": p_success,
            "failure_even_with_help": p_failure * effective_help_share,
            "failure_after_attempt": p_failure * (1.0 - effective_help_share),
            "abandon_midway": p_abandon,
        }
    else:
        raise ValueError(f"unsupported strategy_type: {strategy.strategy_type}")
    allowed_keys = allowed_outcome_keys_for_strategy(strategy)
    return appraisal, validate_outcome_distribution(
        distribution,
        allowed_keys=allowed_keys,
        tolerance=0.0001,
    )


def fuse_rule_and_trajectory_distribution(
    *,
    rule_distribution: dict[str, float],
    trajectory_distribution: dict[str, float],
    allowed_keys: tuple[str, ...],
    trajectory_confidence: float,
    alpha: float,
    max_outcome_shift: float,
    max_tvd: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    p_rule = validate_outcome_distribution(
        rule_distribution,
        allowed_keys=allowed_keys,
        tolerance=0.0001,
    )
    p_traj = validate_outcome_distribution(
        trajectory_distribution,
        allowed_keys=allowed_keys,
        tolerance=0.02,
    )
    alpha_effective = _clamp_unit(float(alpha))
    candidate = {
        key: float(p_rule[key]) + alpha_effective * (float(p_traj[key]) - float(p_rule[key]))
        for key in allowed_keys
    }
    candidate = _normalize_distribution(candidate, keys=allowed_keys)
    p_final = _cap_residual_to_bounds(
        rule_distribution=p_rule,
        candidate_distribution=candidate,
        keys=allowed_keys,
        max_shift=max(0.0, float(max_outcome_shift)),
        max_tvd=max(0.0, float(max_tvd)),
    )
    max_abs_shift = max(
        (abs(float(p_final[key]) - float(p_rule[key])) for key in allowed_keys),
        default=0.0,
    )
    tvd = _total_variation_distance(p_final, p_rule, allowed_keys)
    audit = {
        "alpha_base": round(float(alpha), 6),
        "alpha_effective": round(float(alpha_effective), 6),
        "trajectory_confidence": round(_clamp_unit(float(trajectory_confidence)), 6),
        "fusion_rule": "rule_plus_alpha_trajectory_residual",
        "max_outcome_shift": round(float(max_outcome_shift), 6),
        "max_tvd": round(float(max_tvd), 6),
        "max_abs_shift_from_rule": round(float(max_abs_shift), 6),
        "tvd_from_rule": round(float(tvd), 6),
    }
    if max_abs_shift > float(max_outcome_shift) + 0.000001:
        raise ValueError("bounded fusion exceeded max outcome shift")
    if tvd > float(max_tvd) + 0.000001:
        raise ValueError("bounded fusion exceeded max TVD")
    return validate_outcome_distribution(
        p_final,
        allowed_keys=allowed_keys,
        tolerance=0.0001,
    ), audit


def sample_from_outcome_distribution(
    distribution: dict[str, float],
    *,
    allowed_keys: tuple[str, ...],
    rng: random.Random,
) -> tuple[str, float]:
    normalized = validate_outcome_distribution(
        distribution,
        allowed_keys=allowed_keys,
        tolerance=0.0001,
    )
    roll = rng.random()
    cumulative = 0.0
    selected = allowed_keys[-1]
    for key in allowed_keys:
        cumulative += float(normalized[key])
        if roll < cumulative:
            selected = key
            break
    return selected, roll


def _success_probability(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    support_quality: int,
    friction_tier: int,
    consecutive_failures: int,
) -> float:
    probability = 0.78
    probability -= task.difficulty * 0.32
    probability -= (helplessness / 100.0) * 0.28
    probability -= friction_tier * 0.10
    probability -= min(consecutive_failures, 3) * 0.04
    probability += support_quality * 0.08
    if strategy.strategy_type == "seek_help_then_attempt":
        probability += 0.10 + (task.support_sensitivity * 0.06)
    return clamp_probability(probability)


def _abandon_probability(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    support_quality: int,
    friction_tier: int,
) -> float:
    probability = 0.02
    probability += task.difficulty * 0.12
    probability += (helplessness / 100.0) * 0.18
    probability += friction_tier * 0.05
    probability -= support_quality * 0.04
    if strategy.strategy_type == "seek_help_then_attempt":
        probability -= 0.05
    return max(0.0, min(0.45, probability))


def _resolve_attempt_outcome_rule_v1(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    env: dict[str, Any],
    consecutive_failures: int,
    rng: random.Random | None = None,
) -> AttemptOutcome:
    rng = rng or random.Random()
    support_quality = support_quality_from_env(env)
    friction_tier = friction_tier_from_env(task, env)
    if strategy.strategy_type == "avoid":
        event_level_uncontrollability = infer_event_level_uncontrollability(
            task=task,
            outcome_type="avoid_without_attempt",
            friction_tier=friction_tier,
            consecutive_failures_after_event=consecutive_failures,
        )
        return AttemptOutcome(
            outcome_type="avoid_without_attempt",
            success=False,
            help_used=False,
            negative_feedback=False,
            support_quality=support_quality,
            event_level_uncontrollability=event_level_uncontrollability,
            friction_tier=friction_tier,
            success_probability=0.0,
            abandon_probability=0.0,
            note="avoided_before_attempt",
            rule_event_level_uncontrollability=event_level_uncontrollability,
        )

    success_probability = _success_probability(
        task=task,
        strategy=strategy,
        helplessness=helplessness,
        support_quality=support_quality,
        friction_tier=friction_tier,
        consecutive_failures=consecutive_failures,
    )
    abandon_probability = _abandon_probability(
        task=task,
        strategy=strategy,
        helplessness=helplessness,
        support_quality=support_quality,
        friction_tier=friction_tier,
    )
    roll = rng.random()
    if roll < abandon_probability:
        outcome_type = "abandon_midway"
    elif roll < abandon_probability + success_probability:
        outcome_type = (
            "success_with_help"
            if strategy.strategy_type == "seek_help_then_attempt"
            else "success_self"
        )
    else:
        outcome_type = (
            "failure_even_with_help"
            if strategy.strategy_type == "seek_help_then_attempt"
            else "failure_after_attempt"
        )

    failure_count_after = (
        consecutive_failures + 1
        if outcome_type
        in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"}
        else 0
    )
    event_level_uncontrollability = infer_event_level_uncontrollability(
        task=task,
        outcome_type=outcome_type,
        friction_tier=friction_tier,
        consecutive_failures_after_event=failure_count_after,
    )
    return AttemptOutcome(
        outcome_type=outcome_type,  # type: ignore[arg-type]
        success=outcome_type in {"success_self", "success_with_help"},
        help_used=strategy.strategy_type == "seek_help_then_attempt",
        negative_feedback=outcome_type
        in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"},
        support_quality=support_quality,
        event_level_uncontrollability=event_level_uncontrollability,
        friction_tier=friction_tier,
        success_probability=success_probability,
        abandon_probability=abandon_probability,
        note=f"roll={roll:.4f}",
        rule_event_level_uncontrollability=event_level_uncontrollability,
    )


def _trajectory_config_value(
    trajectory_config: dict[str, Any] | None,
    key: str,
    default: Any,
) -> Any:
    if not isinstance(trajectory_config, dict):
        return default
    return trajectory_config.get(key, default)


def _outcome_from_distribution(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    env: dict[str, Any],
    consecutive_failures: int,
    distribution: dict[str, float],
    rule_distribution: dict[str, float],
    rng: random.Random,
    outcome_model_mode: str,
    note_prefix: str,
    outcome_appraisal: OutcomeAppraisalResult | None = None,
    trajectory_result: dict[str, Any] | None = None,
    trajectory_audit: dict[str, Any] | None = None,
    support_response: Any = None,
) -> AttemptOutcome:
    support_quality = support_quality_from_env(env)
    response = _support_response_from_any(support_response)
    friction_tier = friction_tier_from_env(task, env)
    allowed_keys = allowed_outcome_keys_for_strategy(strategy)
    final_distribution = validate_outcome_distribution(
        distribution,
        allowed_keys=allowed_keys,
        tolerance=0.0001,
    )
    outcome_type, roll = sample_from_outcome_distribution(
        final_distribution,
        allowed_keys=allowed_keys,
        rng=rng,
    )
    failure_count_after = (
        consecutive_failures + 1
        if outcome_type
        in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"}
        else 0
    )
    event_level_uncontrollability = infer_event_level_uncontrollability(
        task=task,
        outcome_type=outcome_type,
        friction_tier=friction_tier,
        consecutive_failures_after_event=failure_count_after,
    )
    success_probability = sum(
        final_distribution.get(key, 0.0)
        for key in ("success_self", "success_with_help")
    )
    abandon_probability = float(final_distribution.get("abandon_midway", 0.0))
    trajectory_result = trajectory_result if isinstance(trajectory_result, dict) else {}
    trajectory_audit = trajectory_audit if isinstance(trajectory_audit, dict) else {}
    selected_friction_points = trajectory_result.get("selected_friction_points", [])
    if not isinstance(selected_friction_points, list):
        selected_friction_points = []
    trajectory_tendency = trajectory_result.get("trajectory_outcome_tendency", {})
    if not isinstance(trajectory_tendency, dict):
        trajectory_tendency = {}
    probability_audit = {
        "outcome_appraisal": (
            outcome_appraisal.to_dict() if outcome_appraisal is not None else {}
        ),
        "rule_distribution": _round_distribution(rule_distribution),
        "final_distribution": _round_distribution(final_distribution),
        "trajectory_audit": trajectory_audit,
        "support_response_features": derive_effective_support_features(
            response,
            env,
        ),
    }
    return AttemptOutcome(
        outcome_type=outcome_type,  # type: ignore[arg-type]
        success=outcome_type in {"success_self", "success_with_help"},
        help_used=outcome_type in {"success_with_help", "failure_even_with_help"},
        negative_feedback=outcome_type
        in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"},
        support_quality=support_quality,
        support_response_json=_json_dumps(response.to_dict() if response else {}),
        support_ecology_status=(
            str(response.audit_status) if response is not None else "not_called"
        ),
        helper_agent_id=int(response.helper_agent_id or -1) if response else -1,
        event_level_uncontrollability=event_level_uncontrollability,
        friction_tier=friction_tier,
        success_probability=float(success_probability),
        abandon_probability=float(abandon_probability),
        note=f"{note_prefix};roll={roll:.4f}",
        rule_event_level_uncontrollability=event_level_uncontrollability,
        outcome_model_mode=outcome_model_mode,
        trajectory_status=str(trajectory_result.get("status", "not_called")),
        trajectory_confidence=float(trajectory_result.get("trajectory_confidence", 0.0) or 0.0),
        trajectory_prompt_version=str(trajectory_result.get("prompt_version", "")),
        trajectory_taxonomy_version=str(trajectory_result.get("taxonomy_version", "")),
        trajectory_friction_points_json=_json_dumps(selected_friction_points),
        trajectory_tendency_json=_json_dumps(_round_distribution(trajectory_tendency)),
        rule_distribution_json=_json_dumps(_round_distribution(rule_distribution)),
        final_distribution_json=_json_dumps(_round_distribution(final_distribution)),
        trajectory_alpha_effective=float(trajectory_audit.get("alpha_effective", 0.0) or 0.0),
        trajectory_tvd_from_rule=float(trajectory_audit.get("tvd_from_rule", 0.0) or 0.0),
        trajectory_invalid_reason=str(trajectory_result.get("invalid_reason", "")),
        trajectory_json_attempts_configured=int(
            trajectory_result.get("trajectory_json_attempts_configured", 1) or 1
        ),
        trajectory_json_attempts_used=int(
            trajectory_result.get("trajectory_json_attempts_used", 1) or 1
        ),
        probability_audit_json=_json_dumps(probability_audit),
    )


def _resolve_attempt_outcome_appraisal_rule_v2(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    env: dict[str, Any],
    consecutive_failures: int,
    task_appraisal: Any,
    memory_features: Any,
    rng: random.Random,
    outcome_model_mode: str = "appraisal_rule_v2",
    trajectory_result: dict[str, Any] | None = None,
    support_response: Any = None,
) -> AttemptOutcome:
    outcome_appraisal, rule_distribution = build_rule_outcome_distribution_v2(
        task=task,
        strategy=strategy,
        helplessness=helplessness,
        env=env,
        consecutive_failures=consecutive_failures,
        task_appraisal=task_appraisal,
        memory_features=memory_features,
        support_response=support_response,
    )
    response = _support_response_from_any(support_response)
    if strategy.strategy_type == "avoid":
        support_quality = support_quality_from_env(env)
        friction_tier = friction_tier_from_env(task, env)
        event_level_uncontrollability = infer_event_level_uncontrollability(
            task=task,
            outcome_type="avoid_without_attempt",
            friction_tier=friction_tier,
            consecutive_failures_after_event=consecutive_failures,
        )
        return AttemptOutcome(
            outcome_type="avoid_without_attempt",
            success=False,
            help_used=False,
            negative_feedback=False,
            support_quality=support_quality,
            support_response_json=_json_dumps(response.to_dict() if response else {}),
            support_ecology_status=(
                str(response.audit_status) if response is not None else "not_called"
            ),
            helper_agent_id=int(response.helper_agent_id or -1) if response else -1,
            event_level_uncontrollability=event_level_uncontrollability,
            friction_tier=friction_tier,
            success_probability=0.0,
            abandon_probability=0.0,
            note="avoided_before_attempt",
            rule_event_level_uncontrollability=event_level_uncontrollability,
            outcome_model_mode=outcome_model_mode,
            trajectory_status="not_called_strategy_avoid",
            rule_distribution_json=_json_dumps(_round_distribution(rule_distribution)),
            final_distribution_json=_json_dumps(_round_distribution(rule_distribution)),
            probability_audit_json=_json_dumps(
                {
                    "outcome_appraisal": outcome_appraisal.to_dict(),
                    "rule_distribution": _round_distribution(rule_distribution),
                    "final_distribution": _round_distribution(rule_distribution),
                }
            ),
        )
    if trajectory_result is not None:
        trajectory_result = {
            **trajectory_result,
            "status": str(trajectory_result.get("status", "shadow_ok")),
        }
    return _outcome_from_distribution(
        task=task,
        strategy=strategy,
        env=env,
        consecutive_failures=consecutive_failures,
        distribution=rule_distribution,
        rule_distribution=rule_distribution,
        rng=rng,
        outcome_model_mode=outcome_model_mode,
        note_prefix="appraisal_rule_v2",
        outcome_appraisal=outcome_appraisal,
        trajectory_result=trajectory_result,
        support_response=response,
    )


def _resolve_attempt_outcome_trajectory_bounded_online_mc(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    env: dict[str, Any],
    consecutive_failures: int,
    task_appraisal: Any,
    memory_features: Any,
    trajectory_result: Any,
    trajectory_config: dict[str, Any] | None,
    rng: random.Random,
    support_response: Any = None,
) -> AttemptOutcome:
    if strategy.strategy_type == "avoid":
        return _resolve_attempt_outcome_appraisal_rule_v2(
            task=task,
            strategy=strategy,
            helplessness=helplessness,
            env=env,
            consecutive_failures=consecutive_failures,
            task_appraisal=task_appraisal,
            memory_features=memory_features,
            rng=rng,
            outcome_model_mode="trajectory_bounded_online_mc",
            support_response=support_response,
        )
    if not isinstance(trajectory_result, dict):
        raise ValueError("trajectory_bounded_online_mc requires trajectory_result")
    min_confidence = float(
        _trajectory_config_value(trajectory_config, "min_confidence", 0.65)
    )
    confidence = float(trajectory_result.get("trajectory_confidence", 0.0) or 0.0)
    if confidence < min_confidence:
        raise ValueError("trajectory confidence below configured threshold")
    outcome_appraisal, rule_distribution = build_rule_outcome_distribution_v2(
        task=task,
        strategy=strategy,
        helplessness=helplessness,
        env=env,
        consecutive_failures=consecutive_failures,
        task_appraisal=task_appraisal,
        memory_features=memory_features,
        support_response=support_response,
    )
    allowed_keys = allowed_outcome_keys_for_strategy(strategy)
    trajectory_distribution = trajectory_result.get("trajectory_outcome_tendency")
    if not isinstance(trajectory_distribution, dict):
        raise ValueError("trajectory_outcome_tendency is required")
    final_distribution, trajectory_audit = fuse_rule_and_trajectory_distribution(
        rule_distribution=rule_distribution,
        trajectory_distribution=trajectory_distribution,
        allowed_keys=allowed_keys,
        trajectory_confidence=confidence,
        alpha=float(_trajectory_config_value(trajectory_config, "alpha", 0.10)),
        max_outcome_shift=float(
            _trajectory_config_value(trajectory_config, "max_outcome_shift", 0.08)
        ),
        max_tvd=float(_trajectory_config_value(trajectory_config, "max_tvd", 0.10)),
    )
    trajectory_result = {
        **trajectory_result,
        "status": str(trajectory_result.get("status", "online_ok")),
    }
    return _outcome_from_distribution(
        task=task,
        strategy=strategy,
        env=env,
        consecutive_failures=consecutive_failures,
        distribution=final_distribution,
        rule_distribution=rule_distribution,
        rng=rng,
        outcome_model_mode="trajectory_bounded_online_mc",
        note_prefix="trajectory_bounded_online_mc",
        outcome_appraisal=outcome_appraisal,
        trajectory_result=trajectory_result,
        trajectory_audit=trajectory_audit,
        support_response=support_response,
    )


def resolve_attempt_outcome(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    helplessness: float,
    env: dict[str, Any],
    consecutive_failures: int,
    rng: random.Random | None = None,
    outcome_model_mode: str = "rule_v1",
    task_appraisal: Any = None,
    memory_features: Any = None,
    trajectory_result: Any = None,
    trajectory_config: dict[str, Any] | None = None,
    support_response: Any = None,
) -> AttemptOutcome:
    rng = rng or random.Random()
    mode = str(outcome_model_mode or "rule_v1").strip().lower()
    if mode not in OUTCOME_MODEL_MODES:
        raise ValueError(
            "outcome_model_mode must be one of: "
            + ", ".join(sorted(OUTCOME_MODEL_MODES))
        )
    if mode == "rule_v1":
        return _resolve_attempt_outcome_rule_v1(
            task=task,
            strategy=strategy,
            helplessness=helplessness,
            env=env,
            consecutive_failures=consecutive_failures,
            rng=rng,
        )
    if mode in {"appraisal_rule_v2", "trajectory_shadow"}:
        return _resolve_attempt_outcome_appraisal_rule_v2(
            task=task,
            strategy=strategy,
            helplessness=helplessness,
            env=env,
            consecutive_failures=consecutive_failures,
            task_appraisal=task_appraisal,
            memory_features=memory_features,
            rng=rng,
            outcome_model_mode=mode,
            trajectory_result=trajectory_result if mode == "trajectory_shadow" else None,
            support_response=support_response,
        )
    return _resolve_attempt_outcome_trajectory_bounded_online_mc(
        task=task,
        strategy=strategy,
        helplessness=helplessness,
        env=env,
        consecutive_failures=consecutive_failures,
        task_appraisal=task_appraisal,
        memory_features=memory_features,
        trajectory_result=trajectory_result,
        trajectory_config=trajectory_config,
        rng=rng,
        support_response=support_response,
    )
