import random

from proto.attempt_strategy import choose_attempt_strategy, compute_strategy_weights
from proto.models import StrategyDeliberationResult


def test_strategy_weights_favor_self_when_helplessness_low() -> None:
    weights = compute_strategy_weights(
        effective_helplessness=35,
        support_quality=2,
        task_difficulty=0.40,
        consecutive_failures=0,
        task_self_efficacy=68,
        help_success_rate_smoothed=0.55,
        recent_negative_feedback_ratio=0.0,
        recent_same_task_failure_count=0,
    )
    assert weights["attempt_self"] > weights["seek_help_then_attempt"]
    assert weights["attempt_self"] > weights["avoid"]


def test_strategy_weights_keep_avoid_below_one_when_helplessness_high() -> None:
    weights = compute_strategy_weights(
        effective_helplessness=92,
        support_quality=2,
        task_difficulty=0.65,
        consecutive_failures=3,
        task_self_efficacy=32,
        help_success_rate_smoothed=0.60,
        recent_negative_feedback_ratio=0.50,
        recent_same_task_failure_count=2,
    )
    assert weights["avoid"] > weights["attempt_self"]
    assert weights["avoid"] > weights["seek_help_then_attempt"]
    assert weights["avoid"] < 1.0
    assert weights["seek_help_then_attempt"] >= 0.05


def test_high_support_raises_help_weight() -> None:
    low_support = compute_strategy_weights(
        effective_helplessness=78,
        support_quality=0,
        task_difficulty=0.55,
        consecutive_failures=2,
        task_self_efficacy=48,
        help_success_rate_smoothed=0.55,
        recent_negative_feedback_ratio=0.25,
        recent_same_task_failure_count=1,
    )
    high_support = compute_strategy_weights(
        effective_helplessness=78,
        support_quality=2,
        task_difficulty=0.55,
        consecutive_failures=2,
        task_self_efficacy=48,
        help_success_rate_smoothed=0.55,
        recent_negative_feedback_ratio=0.25,
        recent_same_task_failure_count=1,
    )
    assert high_support["seek_help_then_attempt"] > low_support["seek_help_then_attempt"]


def test_high_task_self_efficacy_boosts_attempt_self() -> None:
    low_efficacy = compute_strategy_weights(
        effective_helplessness=58,
        support_quality=1,
        task_difficulty=0.55,
        consecutive_failures=1,
        task_self_efficacy=35,
        help_success_rate_smoothed=0.50,
        recent_negative_feedback_ratio=0.0,
        recent_same_task_failure_count=0,
    )
    high_efficacy = compute_strategy_weights(
        effective_helplessness=58,
        support_quality=1,
        task_difficulty=0.55,
        consecutive_failures=1,
        task_self_efficacy=68,
        help_success_rate_smoothed=0.50,
        recent_negative_feedback_ratio=0.0,
        recent_same_task_failure_count=0,
    )
    assert high_efficacy["attempt_self"] > low_efficacy["attempt_self"]


def test_good_help_history_raises_help_weight() -> None:
    weak_help_history = compute_strategy_weights(
        effective_helplessness=72,
        support_quality=2,
        task_difficulty=0.62,
        consecutive_failures=2,
        task_self_efficacy=45,
        help_success_rate_smoothed=0.30,
        recent_negative_feedback_ratio=0.25,
        recent_same_task_failure_count=1,
    )
    strong_help_history = compute_strategy_weights(
        effective_helplessness=72,
        support_quality=2,
        task_difficulty=0.62,
        consecutive_failures=2,
        task_self_efficacy=45,
        help_success_rate_smoothed=0.75,
        recent_negative_feedback_ratio=0.25,
        recent_same_task_failure_count=1,
    )
    assert (
        strong_help_history["seek_help_then_attempt"]
        > weak_help_history["seek_help_then_attempt"]
    )


def test_recent_negative_feedback_raises_avoid_weight() -> None:
    calm_history = compute_strategy_weights(
        effective_helplessness=68,
        support_quality=1,
        task_difficulty=0.55,
        consecutive_failures=1,
        task_self_efficacy=48,
        help_success_rate_smoothed=0.50,
        recent_negative_feedback_ratio=0.0,
        recent_same_task_failure_count=0,
    )
    rough_history = compute_strategy_weights(
        effective_helplessness=68,
        support_quality=1,
        task_difficulty=0.55,
        consecutive_failures=1,
        task_self_efficacy=48,
        help_success_rate_smoothed=0.50,
        recent_negative_feedback_ratio=0.75,
        recent_same_task_failure_count=2,
    )
    assert rough_history["avoid"] > calm_history["avoid"]


def test_strategy_sampling_is_reproducible_for_fixed_rng() -> None:
    strategy_a = choose_attempt_strategy(
        effective_helplessness=82,
        support_quality=2,
        task_difficulty=0.60,
        consecutive_failures=2,
        task_self_efficacy=38,
        help_success_rate_smoothed=0.72,
        recent_negative_feedback_ratio=0.50,
        recent_same_task_failure_count=2,
        rng=random.Random(7),
    )
    strategy_b = choose_attempt_strategy(
        effective_helplessness=82,
        support_quality=2,
        task_difficulty=0.60,
        consecutive_failures=2,
        task_self_efficacy=38,
        help_success_rate_smoothed=0.72,
        recent_negative_feedback_ratio=0.50,
        recent_same_task_failure_count=2,
        rng=random.Random(7),
    )
    assert strategy_a.strategy_type == strategy_b.strategy_type
    assert strategy_a.weights == strategy_b.weights


def test_strategy_deliberation_defaults_do_not_change_weights() -> None:
    plain = compute_strategy_weights(
        effective_helplessness=70,
        support_quality=1,
        task_difficulty=0.58,
        consecutive_failures=1,
        task_self_efficacy=46,
        help_success_rate_smoothed=0.58,
        recent_negative_feedback_ratio=0.25,
        recent_same_task_failure_count=1,
    )
    disabled = compute_strategy_weights(
        effective_helplessness=70,
        support_quality=1,
        task_difficulty=0.58,
        consecutive_failures=1,
        task_self_efficacy=46,
        help_success_rate_smoothed=0.58,
        recent_negative_feedback_ratio=0.25,
        recent_same_task_failure_count=1,
        strategy_deliberation_result=StrategyDeliberationResult(
            mode="off",
            status="disabled",
            source="rule",
            confidence=0.0,
            reason="",
            cache_hit=False,
            rule_weights=plain,
            final_weights=plain,
        ),
    )
    assert plain == disabled


def test_strategy_deliberation_uses_precomputed_final_weights_without_changing_contract() -> None:
    strategy = choose_attempt_strategy(
        effective_helplessness=74,
        support_quality=2,
        task_difficulty=0.64,
        consecutive_failures=2,
        task_self_efficacy=42,
        help_success_rate_smoothed=0.66,
        recent_negative_feedback_ratio=0.30,
        recent_same_task_failure_count=1,
        strategy_deliberation_result=StrategyDeliberationResult(
            mode="hybrid",
            status="ok",
            source="hybrid_blended",
            confidence=0.88,
            reason="test",
            cache_hit=False,
            dominant_strategy="seek_help_then_attempt",
            attempt_self_score=0.18,
            seek_help_score=0.57,
            avoid_score=0.25,
            rule_weights={
                "attempt_self": 0.20,
                "seek_help_then_attempt": 0.50,
                "avoid": 0.30,
            },
            llm_weights={
                "attempt_self": 0.18,
                "seek_help_then_attempt": 0.57,
                "avoid": 0.25,
            },
            final_weights={
                "attempt_self": 0.195,
                "seek_help_then_attempt": 0.5175,
                "avoid": 0.2875,
            },
        ),
        rng=random.Random(3),
    )
    assert set(strategy.weights) == {"attempt_self", "seek_help_then_attempt", "avoid"}
    assert abs(sum(strategy.weights.values()) - 1.0) < 1e-9
    assert "rule_self=" in strategy.rationale
    assert "final_help=" in strategy.rationale
