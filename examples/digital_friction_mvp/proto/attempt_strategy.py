from __future__ import annotations

import random

from .models import AttemptStrategy, StrategyDeliberationResult

_STRATEGY_KEYS = (
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
)


def _base_weights(helplessness: float) -> dict[str, float]:
    helplessness = float(helplessness)
    if helplessness < 40:
        return {
            "attempt_self": 0.75,
            "seek_help_then_attempt": 0.15,
            "avoid": 0.10,
        }
    if helplessness < 70:
        return {
            "attempt_self": 0.45,
            "seek_help_then_attempt": 0.40,
            "avoid": 0.15,
        }
    if helplessness < 85:
        return {
            "attempt_self": 0.20,
            "seek_help_then_attempt": 0.45,
            "avoid": 0.35,
        }
    return {
        "attempt_self": 0.10,
        "seek_help_then_attempt": 0.30,
        "avoid": 0.60,
    }


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    clipped = {key: max(0.05, float(weights.get(key, 0.0))) for key in _STRATEGY_KEYS}
    total = sum(clipped.values()) or 1.0
    return {key: clipped[key] / total for key in _STRATEGY_KEYS}


def compute_rule_strategy_weights(
    *,
    effective_helplessness: float,
    support_quality: int,
    task_difficulty: float,
    consecutive_failures: int,
    task_self_efficacy: float = 50.0,
    help_success_rate_smoothed: float = 0.5,
    recent_negative_feedback_ratio: float = 0.0,
    recent_same_task_failure_count: int = 0,
) -> dict[str, float]:
    effective_helplessness = float(effective_helplessness)
    support_quality = int(support_quality)
    task_difficulty = float(task_difficulty)
    consecutive_failures = int(consecutive_failures)
    task_self_efficacy = float(task_self_efficacy)
    help_success_rate_smoothed = float(help_success_rate_smoothed)
    recent_negative_feedback_ratio = float(recent_negative_feedback_ratio)
    recent_same_task_failure_count = int(recent_same_task_failure_count)
    help_confidence_bonus = (help_success_rate_smoothed - 0.5) * 0.20

    weights = _base_weights(effective_helplessness)

    if support_quality == 0:
        weights["seek_help_then_attempt"] -= 0.15
        if effective_helplessness < 70:
            weights["attempt_self"] += 0.05
            weights["avoid"] += 0.10
        else:
            weights["avoid"] += 0.15
    elif support_quality == 2:
        weights["seek_help_then_attempt"] += 0.10
        weights["attempt_self"] -= 0.05
        weights["avoid"] -= 0.05

    if task_difficulty >= 0.70:
        weights["avoid"] += 0.10
        weights["attempt_self"] -= 0.05
        weights["seek_help_then_attempt"] -= 0.05

    if consecutive_failures >= 2:
        weights["avoid"] += 0.10
        if support_quality > 0:
            weights["seek_help_then_attempt"] += 0.05
            weights["attempt_self"] -= 0.15
        else:
            weights["attempt_self"] -= 0.10

    if task_self_efficacy >= 60:
        weights["attempt_self"] += 0.10
    elif task_self_efficacy < 40:
        weights["attempt_self"] -= 0.10

    weights["seek_help_then_attempt"] += help_confidence_bonus
    if help_success_rate_smoothed < 0.35:
        weights["seek_help_then_attempt"] -= 0.10
    elif help_success_rate_smoothed > 0.65:
        weights["seek_help_then_attempt"] += 0.10

    weights["avoid"] += recent_negative_feedback_ratio * 0.15
    weights["avoid"] += recent_same_task_failure_count * 0.05
    return _normalize_weights(weights)


def compute_strategy_weights(
    *,
    effective_helplessness: float,
    support_quality: int,
    task_difficulty: float,
    consecutive_failures: int,
    task_self_efficacy: float = 50.0,
    help_success_rate_smoothed: float = 0.5,
    recent_negative_feedback_ratio: float = 0.0,
    recent_same_task_failure_count: int = 0,
    strategy_deliberation_result: StrategyDeliberationResult | None = None,
    precomputed_final_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    rule_weights = compute_rule_strategy_weights(
        effective_helplessness=effective_helplessness,
        support_quality=support_quality,
        task_difficulty=task_difficulty,
        consecutive_failures=consecutive_failures,
        task_self_efficacy=task_self_efficacy,
        help_success_rate_smoothed=help_success_rate_smoothed,
        recent_negative_feedback_ratio=recent_negative_feedback_ratio,
        recent_same_task_failure_count=recent_same_task_failure_count,
    )
    if precomputed_final_weights is not None:
        return _normalize_weights(precomputed_final_weights)
    if (
        strategy_deliberation_result is not None
        and strategy_deliberation_result.final_weights
    ):
        return _normalize_weights(strategy_deliberation_result.final_weights)
    return rule_weights


def choose_attempt_strategy(
    *,
    effective_helplessness: float,
    support_quality: int,
    task_difficulty: float,
    consecutive_failures: int,
    task_self_efficacy: float = 50.0,
    help_success_rate_smoothed: float = 0.5,
    recent_negative_feedback_ratio: float = 0.0,
    recent_same_task_failure_count: int = 0,
    strategy_deliberation_result: StrategyDeliberationResult | None = None,
    precomputed_final_weights: dict[str, float] | None = None,
    rng: random.Random | None = None,
) -> AttemptStrategy:
    rng = rng or random.Random()
    weights = compute_strategy_weights(
        effective_helplessness=effective_helplessness,
        support_quality=support_quality,
        task_difficulty=task_difficulty,
        consecutive_failures=consecutive_failures,
        task_self_efficacy=task_self_efficacy,
        help_success_rate_smoothed=help_success_rate_smoothed,
        recent_negative_feedback_ratio=recent_negative_feedback_ratio,
        recent_same_task_failure_count=recent_same_task_failure_count,
        strategy_deliberation_result=strategy_deliberation_result,
        precomputed_final_weights=precomputed_final_weights,
    )
    roll = rng.random()
    cumulative = 0.0
    selected = "avoid"
    for key in _STRATEGY_KEYS:
        cumulative += float(weights[key])
        if roll <= cumulative:
            selected = key
            break

    if strategy_deliberation_result is not None:
        rationale = (
            "weighted_strategy_sampling:"
            f"effective_h={effective_helplessness:.1f},"
            f"task_efficacy={task_self_efficacy:.1f},"
            f"help_rate={help_success_rate_smoothed:.3f},"
            f"recent_neg={recent_negative_feedback_ratio:.3f},"
            f"same_task_fail={recent_same_task_failure_count},"
            f"deliberation_status={strategy_deliberation_result.status},"
            f"deliberation_source={strategy_deliberation_result.source},"
            f"rule_self={float(strategy_deliberation_result.rule_weights.get('attempt_self', 0.0)):.3f},"
            f"rule_help={float(strategy_deliberation_result.rule_weights.get('seek_help_then_attempt', 0.0)):.3f},"
            f"rule_avoid={float(strategy_deliberation_result.rule_weights.get('avoid', 0.0)):.3f},"
            f"llm_self={float((strategy_deliberation_result.llm_weights or {}).get('attempt_self', 0.0)):.3f},"
            f"llm_help={float((strategy_deliberation_result.llm_weights or {}).get('seek_help_then_attempt', 0.0)):.3f},"
            f"llm_avoid={float((strategy_deliberation_result.llm_weights or {}).get('avoid', 0.0)):.3f},"
            f"final_self={weights['attempt_self']:.3f},"
            f"final_help={weights['seek_help_then_attempt']:.3f},"
            f"final_avoid={weights['avoid']:.3f}"
        )
    else:
        rationale = (
            "weighted_strategy_sampling:"
            f"effective_h={effective_helplessness:.1f},"
            f"task_efficacy={task_self_efficacy:.1f},"
            f"help_rate={help_success_rate_smoothed:.3f},"
            f"recent_neg={recent_negative_feedback_ratio:.3f},"
            f"same_task_fail={recent_same_task_failure_count},"
            f"self={weights['attempt_self']:.3f},"
            f"help={weights['seek_help_then_attempt']:.3f},"
            f"avoid={weights['avoid']:.3f}"
        )
    return AttemptStrategy(
        strategy_type=selected,  # type: ignore[arg-type]
        support_requested=selected == "seek_help_then_attempt",
        rationale=rationale,
        weights=weights,
    )
