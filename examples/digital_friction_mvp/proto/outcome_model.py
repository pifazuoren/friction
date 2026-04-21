from __future__ import annotations

import random
from typing import Any

from .models import AttemptOutcome, AttemptStrategy, DigitalTask


def clamp_probability(value: float) -> float:
    return max(0.01, min(0.99, float(value)))


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def support_quality_from_env(env: dict[str, Any]) -> int:
    total = int(float(env.get("assist_level", 0))) + int(
        float(env.get("human_support_level", 0))
    ) + int(float(env.get("accessibility_level", 0)))
    if total <= 1:
        return 0
    if total <= 5:
        return 1
    return 2


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
    }
    ranking = sorted(scores.items(), key=lambda item: (item[1], item[0]), reverse=True)
    label, top_score = ranking[0]
    second_score = ranking[1][1]
    confidence = max(0.55, min(0.95, 0.62 + 0.15 * (top_score - second_score)))
    if label == "helpless_avoid":
        note = "low_control_or_repeat_failure_dominates"
    elif label == "risk_avoid":
        note = "risk_signal_dominates"
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
) -> dict[str, Any]:
    if outcome_type not in {"success_with_help", "failure_even_with_help", "abandon_midway"}:
        return {
            "label": "not_applicable",
            "source": "not_applicable",
            "confidence": 0.0,
            "note": "",
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


def resolve_attempt_outcome(
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
