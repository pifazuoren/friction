import random

from proto.attempt_strategy import choose_attempt_strategy
from proto.outcome_model import (
    _resolve_attempt_outcome_rule_v1,
    build_rule_outcome_distribution_v2,
    derive_effective_support_features,
    fuse_rule_and_trajectory_distribution,
    infer_avoid_reason,
    infer_support_mode,
    resolve_attempt_outcome,
    support_quality_from_env,
)
from proto.models import AttemptStrategy, DigitalTask, MemoryFeatures, TaskAppraisalResult
from proto.support_protocol import SupportResponse
from proto.task_assignment import select_task_for_agent

TASK_WINDOW_MORNING = 9 * 60 * 60


def _payment_task() -> DigitalTask:
    return DigitalTask(
        task_id="task-payment",
        task_family="payment_risk_confirmation",
        friction_type="payment_risk_popup",
        difficulty=0.62,
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=TASK_WINDOW_MORNING,
    )


def _task_appraisal() -> TaskAppraisalResult:
    return TaskAppraisalResult(
        mode="hybrid",
        status="ok",
        source="llm",
        confidence=0.82,
        reason="bounded test appraisal",
        cache_hit=False,
        perceived_task_difficulty=64,
        perceived_task_risk=72,
        felt_control=44,
        expected_help_effectiveness=58,
        task_value=70,
    )


def _memory_features() -> MemoryFeatures:
    return MemoryFeatures(
        effective_helplessness=61,
        task_self_efficacy=46,
        controllable_success_memory=0.18,
        task_specific_pressure=0.2,
        help_success_rate_smoothed=0.55,
        help_confidence_bonus=0.05,
        recent_negative_feedback_ratio=0.25,
        recent_avoid_ratio=0.1,
        recent_help_seek_ratio=0.2,
        recent_same_task_failure_count=1,
        recent_failure_pressure=0.25,
    )


def test_rule_v1_wrapper_matches_existing_logic() -> None:
    task = _payment_task()
    strategy = AttemptStrategy("attempt_self")
    env = {
        "friction_level": 2,
        "malicious_friction_level": 2,
        "complexity_level": 1,
        "risk_level": 3,
        "assist_level": 0,
        "human_support_level": 0,
        "accessibility_level": 0,
    }
    legacy = _resolve_attempt_outcome_rule_v1(
        task=task,
        strategy=strategy,
        helplessness=63,
        env=env,
        consecutive_failures=1,
        rng=random.Random(19),
    )
    public = resolve_attempt_outcome(
        task=task,
        strategy=strategy,
        helplessness=63,
        env=env,
        consecutive_failures=1,
        rng=random.Random(19),
        outcome_model_mode="rule_v1",
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
        trajectory_result={"trajectory_confidence": 1.0},
    )
    assert public.to_dict() == legacy.to_dict()


def test_appraisal_rule_v2_distribution_is_normalized_and_strategy_specific() -> None:
    _, distribution = build_rule_outcome_distribution_v2(
        task=_payment_task(),
        strategy=AttemptStrategy("seek_help_then_attempt", support_requested=True),
        helplessness=61,
        env={
            "friction_level": 2,
            "malicious_friction_level": 2,
            "complexity_level": 1,
            "risk_level": 3,
            "assist_level": 2,
            "human_support_level": 1,
            "accessibility_level": 1,
        },
        consecutive_failures=1,
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
    )
    assert set(distribution) == {
        "success_with_help",
        "failure_even_with_help",
        "failure_after_attempt",
        "abandon_midway",
    }
    assert abs(sum(distribution.values()) - 1.0) < 0.000001


def test_structured_support_features_are_bounded_and_ordered() -> None:
    enabling = SupportResponse(
        support_style="enabling",
        instruction_quality="high",
        autonomy_preservation="high",
        proxy_completion_level="none",
        emotional_tone="patient",
        response_delay="immediate",
        confidence=0.9,
        responded=True,
        source="llm_family_helper",
        audit_status="ok",
    )
    substituting = SupportResponse(
        support_style="substituting",
        instruction_quality="medium",
        autonomy_preservation="low",
        proxy_completion_level="full",
        emotional_tone="neutral",
        response_delay="immediate",
        confidence=0.9,
        responded=True,
        source="llm_family_helper",
        audit_status="ok",
    )
    unavailable = SupportResponse.unavailable(audit_status="request_error")
    env = {"assist_level": 1, "human_support_level": 1, "accessibility_level": 1}

    enabling_features = derive_effective_support_features(enabling, env)
    substituting_features = derive_effective_support_features(substituting, env)
    unavailable_features = derive_effective_support_features(unavailable, env)

    assert (
        enabling_features["effective_support_quality"]
        > substituting_features["effective_support_quality"]
    )
    assert (
        substituting_features["substitution_pressure"]
        > enabling_features["substitution_pressure"]
    )
    assert unavailable_features["support_unavailability"] == 1.0


def test_support_response_lightly_modulates_help_distribution() -> None:
    task = _payment_task()
    strategy = AttemptStrategy("seek_help_then_attempt", support_requested=True)
    env = {
        "friction_level": 1,
        "malicious_friction_level": 1,
        "complexity_level": 1,
        "risk_level": 1,
        "assist_level": 1,
        "human_support_level": 1,
        "accessibility_level": 1,
    }
    task_appraisal = TaskAppraisalResult(
        mode="hybrid",
        status="ok",
        source="llm",
        confidence=0.82,
        reason="lower pressure support modulation test",
        cache_hit=False,
        perceived_task_difficulty=45,
        perceived_task_risk=40,
        felt_control=60,
        expected_help_effectiveness=65,
        task_value=75,
    )
    memory_features = MemoryFeatures(
        effective_helplessness=45,
        task_self_efficacy=60,
        controllable_success_memory=0.2,
        task_specific_pressure=0.0,
        help_success_rate_smoothed=0.55,
        help_confidence_bonus=0.0,
        recent_negative_feedback_ratio=0.0,
        recent_avoid_ratio=0.0,
        recent_help_seek_ratio=0.0,
        recent_same_task_failure_count=0,
        recent_failure_pressure=0.0,
    )
    enabling = SupportResponse(
        support_style="enabling",
        instruction_quality="high",
        autonomy_preservation="high",
        proxy_completion_level="none",
        emotional_tone="patient",
        response_delay="immediate",
        confidence=0.9,
        responded=True,
        source="llm_family_helper",
        audit_status="ok",
    )
    unavailable = SupportResponse.unavailable(audit_status="request_error")

    _, dist_enabling = build_rule_outcome_distribution_v2(
        task=task,
        strategy=strategy,
        helplessness=50,
        env=env,
        consecutive_failures=0,
        task_appraisal=task_appraisal,
        memory_features=memory_features,
        support_response=enabling,
    )
    _, dist_unavailable = build_rule_outcome_distribution_v2(
        task=task,
        strategy=strategy,
        helplessness=50,
        env=env,
        consecutive_failures=0,
        task_appraisal=task_appraisal,
        memory_features=memory_features,
        support_response=unavailable,
    )

    assert dist_enabling["success_with_help"] > dist_unavailable["success_with_help"]
    assert dist_unavailable["abandon_midway"] > dist_enabling["abandon_midway"]


def test_infer_support_mode_prioritizes_structured_response() -> None:
    result = infer_support_mode(
        outcome_type="success_with_help",
        support_quality=2,
        felt_control=80,
        expected_help_effectiveness=80,
        support_response=SupportResponse(
            support_style="substituting",
            instruction_quality="medium",
            autonomy_preservation="low",
            proxy_completion_level="full",
            emotional_tone="neutral",
            response_delay="immediate",
            confidence=0.8,
            responded=True,
            source="llm_family_helper",
            audit_status="ok",
        ),
    )
    assert result["label"] == "substituting_support"
    assert result["source"] == "support_response"


def test_appraisal_rule_v2_avoid_remains_direct_avoid_outcome() -> None:
    outcome = resolve_attempt_outcome(
        task=_payment_task(),
        strategy=AttemptStrategy("avoid"),
        helplessness=70,
        env={},
        consecutive_failures=2,
        rng=random.Random(1),
        outcome_model_mode="appraisal_rule_v2",
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
    )
    assert outcome.outcome_type == "avoid_without_attempt"
    assert outcome.trajectory_status == "not_called_strategy_avoid"


def test_bounded_fusion_alpha_zero_returns_rule_distribution() -> None:
    rule_distribution = {
        "success_self": 0.60,
        "failure_after_attempt": 0.25,
        "abandon_midway": 0.15,
    }
    trajectory_distribution = {
        "success_self": 0.10,
        "failure_after_attempt": 0.60,
        "abandon_midway": 0.30,
    }
    final_distribution, audit = fuse_rule_and_trajectory_distribution(
        rule_distribution=rule_distribution,
        trajectory_distribution=trajectory_distribution,
        allowed_keys=("success_self", "failure_after_attempt", "abandon_midway"),
        trajectory_confidence=1.0,
        alpha=0.0,
        max_outcome_shift=0.08,
        max_tvd=0.10,
    )
    assert final_distribution == rule_distribution
    assert audit["tvd_from_rule"] == 0.0


def test_bounded_fusion_uses_alpha_as_direct_residual_weight() -> None:
    rule_distribution = {
        "success_self": 0.60,
        "failure_after_attempt": 0.25,
        "abandon_midway": 0.15,
    }
    trajectory_distribution = {
        "success_self": 0.10,
        "failure_after_attempt": 0.60,
        "abandon_midway": 0.30,
    }
    final_distribution, audit = fuse_rule_and_trajectory_distribution(
        rule_distribution=rule_distribution,
        trajectory_distribution=trajectory_distribution,
        allowed_keys=("success_self", "failure_after_attempt", "abandon_midway"),
        trajectory_confidence=0.50,
        alpha=0.20,
        max_outcome_shift=1.0,
        max_tvd=1.0,
    )
    assert final_distribution == {
        "success_self": 0.50,
        "failure_after_attempt": 0.32,
        "abandon_midway": 0.18,
    }
    assert audit["alpha_effective"] == 0.20
    assert audit["trajectory_confidence"] == 0.50
    assert audit["fusion_rule"] == "rule_plus_alpha_trajectory_residual"


def test_bounded_fusion_obeys_shift_and_tvd_caps() -> None:
    rule_distribution = {
        "success_self": 0.80,
        "failure_after_attempt": 0.15,
        "abandon_midway": 0.05,
    }
    trajectory_distribution = {
        "success_self": 0.05,
        "failure_after_attempt": 0.45,
        "abandon_midway": 0.50,
    }
    final_distribution, audit = fuse_rule_and_trajectory_distribution(
        rule_distribution=rule_distribution,
        trajectory_distribution=trajectory_distribution,
        allowed_keys=("success_self", "failure_after_attempt", "abandon_midway"),
        trajectory_confidence=1.0,
        alpha=1.0,
        max_outcome_shift=0.08,
        max_tvd=0.10,
    )
    assert abs(sum(final_distribution.values()) - 1.0) < 0.000001
    assert audit["max_abs_shift_from_rule"] <= 0.080001
    assert audit["tvd_from_rule"] <= 0.100001


def test_trajectory_shadow_records_audit_without_changing_rule_outcome() -> None:
    task = _payment_task()
    strategy = AttemptStrategy("attempt_self")
    env = {"risk_level": 2, "friction_level": 2, "malicious_friction_level": 2}
    rule_outcome = resolve_attempt_outcome(
        task=task,
        strategy=strategy,
        helplessness=61,
        env=env,
        consecutive_failures=1,
        rng=random.Random(101),
        outcome_model_mode="appraisal_rule_v2",
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
    )
    shadow_outcome = resolve_attempt_outcome(
        task=task,
        strategy=strategy,
        helplessness=61,
        env=env,
        consecutive_failures=1,
        rng=random.Random(101),
        outcome_model_mode="trajectory_shadow",
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
        trajectory_result={
            "status": "ok",
            "trajectory_confidence": 0.9,
            "selected_friction_points": [
                {"point": "risk_popup_anxiety", "severity": 0.5, "step_id": 1}
            ],
            "trajectory_outcome_tendency": {
                "success_self": 0.1,
                "failure_after_attempt": 0.7,
                "abandon_midway": 0.2,
            },
            "prompt_version": "trajectory_v1",
            "taxonomy_version": "friction_taxonomy_v1",
        },
    )
    assert shadow_outcome.outcome_type == rule_outcome.outcome_type
    assert shadow_outcome.final_distribution_json == rule_outcome.final_distribution_json
    assert shadow_outcome.trajectory_status == "ok"


def test_trajectory_bounded_online_mc_uses_bounded_fusion_only() -> None:
    outcome = resolve_attempt_outcome(
        task=_payment_task(),
        strategy=AttemptStrategy("attempt_self"),
        helplessness=61,
        env={"risk_level": 2, "friction_level": 2, "malicious_friction_level": 2},
        consecutive_failures=1,
        rng=random.Random(11),
        outcome_model_mode="trajectory_bounded_online_mc",
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
        trajectory_result={
            "status": "ok",
            "trajectory_confidence": 1.0,
            "selected_friction_points": [],
            "trajectory_outcome_tendency": {
                "success_self": 0.05,
                "failure_after_attempt": 0.75,
                "abandon_midway": 0.20,
            },
            "prompt_version": "trajectory_v1",
            "taxonomy_version": "friction_taxonomy_v1",
        },
        trajectory_config={
            "alpha": 1.0,
            "max_outcome_shift": 0.08,
            "max_tvd": 0.10,
            "min_confidence": 0.65,
        },
    )
    assert outcome.outcome_model_mode == "trajectory_bounded_online_mc"
    assert outcome.trajectory_tvd_from_rule <= 0.100001
    assert outcome.trajectory_alpha_effective > 0


def test_trajectory_bounded_online_mc_avoid_does_not_require_trajectory() -> None:
    outcome = resolve_attempt_outcome(
        task=_payment_task(),
        strategy=AttemptStrategy("avoid"),
        helplessness=70,
        env={},
        consecutive_failures=2,
        rng=random.Random(1),
        outcome_model_mode="trajectory_bounded_online_mc",
        task_appraisal=_task_appraisal(),
        memory_features=_memory_features(),
        trajectory_result=None,
    )
    assert outcome.outcome_type == "avoid_without_attempt"
    assert outcome.outcome_model_mode == "trajectory_bounded_online_mc"
    assert outcome.trajectory_status == "not_called_strategy_avoid"


def test_trajectory_bounded_online_mc_rejects_low_confidence() -> None:
    try:
        resolve_attempt_outcome(
            task=_payment_task(),
            strategy=AttemptStrategy("attempt_self"),
            helplessness=61,
            env={"risk_level": 2},
            consecutive_failures=1,
            rng=random.Random(11),
            outcome_model_mode="trajectory_bounded_online_mc",
            task_appraisal=_task_appraisal(),
            memory_features=_memory_features(),
            trajectory_result={
                "status": "low_confidence",
                "trajectory_confidence": 0.2,
                "trajectory_outcome_tendency": {
                    "success_self": 0.4,
                    "failure_after_attempt": 0.4,
                    "abandon_midway": 0.2,
                },
            },
            trajectory_config={"min_confidence": 0.65},
        )
    except ValueError as exc:
        assert "confidence" in str(exc)
    else:
        raise AssertionError("low-confidence trajectory should fail run")


def test_support_quality_mapping() -> None:
    assert support_quality_from_env(
        {"assist_level": 0, "human_support_level": 0, "accessibility_level": 0}
    ) == 0
    assert support_quality_from_env(
        {"assist_level": 2, "human_support_level": 1, "accessibility_level": 1}
    ) == 1
    assert support_quality_from_env(
        {"assist_level": 3, "human_support_level": 3, "accessibility_level": 3}
    ) == 2


def test_high_help_can_flip_outcome_toward_success() -> None:
    task = select_task_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=TASK_WINDOW_MORNING,
        env={
            "friction_level": 3,
            "malicious_friction_level": 3,
            "complexity_level": 3,
            "risk_level": 3,
            "assist_level": 0,
            "human_support_level": 0,
            "accessibility_level": 0,
        },
    )
    assert task is not None
    low_help_outcome = resolve_attempt_outcome(
        task=task,
        strategy=choose_attempt_strategy(
            effective_helplessness=60,
            support_quality=0,
            task_difficulty=task.difficulty,
            consecutive_failures=1,
            task_self_efficacy=45,
            help_success_rate_smoothed=0.50,
            recent_negative_feedback_ratio=0.25,
            recent_same_task_failure_count=1,
            rng=random.Random(11),
        ),
        helplessness=60,
        env={
            "friction_level": 3,
            "malicious_friction_level": 3,
            "complexity_level": 3,
            "risk_level": 3,
            "assist_level": 0,
            "human_support_level": 0,
            "accessibility_level": 0,
        },
        consecutive_failures=1,
        rng=random.Random(5),
    )
    high_help_outcome = resolve_attempt_outcome(
        task=task,
        strategy=choose_attempt_strategy(
            effective_helplessness=60,
            support_quality=2,
            task_difficulty=task.difficulty,
            consecutive_failures=1,
            task_self_efficacy=45,
            help_success_rate_smoothed=0.65,
            recent_negative_feedback_ratio=0.25,
            recent_same_task_failure_count=1,
            rng=random.Random(11),
        ),
        helplessness=60,
        env={
            "friction_level": 3,
            "malicious_friction_level": 3,
            "complexity_level": 3,
            "risk_level": 3,
            "assist_level": 3,
            "human_support_level": 3,
            "accessibility_level": 3,
        },
        consecutive_failures=1,
        rng=random.Random(5),
    )
    assert high_help_outcome.success_probability > low_help_outcome.success_probability
    assert (
        high_help_outcome.rule_event_level_uncontrollability
        == high_help_outcome.event_level_uncontrollability
    )
    assert high_help_outcome.uncontrollability_source == "rule"
    assert high_help_outcome.uncontrollability_llm_value is None


def test_infer_avoid_reason_detects_helpless_avoid() -> None:
    task = select_task_for_agent(
        agent_id=1,
        day=0,
        tick_seconds=TASK_WINDOW_MORNING,
        env={
            "friction_level": 3,
            "malicious_friction_level": 2,
            "complexity_level": 3,
            "risk_level": 1,
            "assist_level": 0,
            "human_support_level": 0,
            "accessibility_level": 0,
        },
    )
    assert task is not None
    result = infer_avoid_reason(
        task=task,
        env={"risk_level": 1},
        helplessness=82,
        recent_same_task_failure_count=2,
        task_self_efficacy=28,
        felt_control=25,
        perceived_task_risk=42,
        task_value=66,
    )
    assert result["label"] == "helpless_avoid"


def test_infer_avoid_reason_detects_risk_and_low_value_paths() -> None:
    risk_task = select_task_for_agent(
        agent_id=2,
        day=0,
        tick_seconds=TASK_WINDOW_MORNING,
        env={
            "friction_level": 2,
            "malicious_friction_level": 2,
            "complexity_level": 1,
            "risk_level": 3,
            "assist_level": 0,
            "human_support_level": 0,
            "accessibility_level": 0,
        },
    )
    assert risk_task is not None
    risk_result = infer_avoid_reason(
        task=risk_task,
        env={"risk_level": 3},
        helplessness=48,
        recent_same_task_failure_count=0,
        task_self_efficacy=62,
        felt_control=58,
        perceived_task_risk=85,
        task_value=62,
    )
    low_value_result = infer_avoid_reason(
        task=risk_task,
        env={"risk_level": 1},
        helplessness=45,
        recent_same_task_failure_count=0,
        task_self_efficacy=58,
        felt_control=52,
        perceived_task_risk=30,
        task_value=24,
    )
    assert risk_result["label"] == "risk_avoid"
    assert low_value_result["label"] == "low_value_avoid"


def test_infer_avoid_reason_detects_rational_security_avoid() -> None:
    result = infer_avoid_reason(
        task=_payment_task(),
        env={"risk_level": 3, "malicious_friction_level": 3},
        helplessness=42,
        recent_same_task_failure_count=0,
        task_self_efficacy=62,
        felt_control=58,
        perceived_task_risk=88,
        task_value=62,
    )

    assert result["label"] == "rational_security_avoid"
    assert result["scores"]["rational_security_avoid"] > result["scores"]["risk_avoid"]


def test_infer_support_mode_splits_enabling_and_substituting() -> None:
    enabling = infer_support_mode(
        outcome_type="success_with_help",
        support_quality=2,
        felt_control=64,
        expected_help_effectiveness=72,
    )
    substituting = infer_support_mode(
        outcome_type="success_with_help",
        support_quality=2,
        felt_control=40,
        expected_help_effectiveness=46,
    )
    assert enabling["label"] == "enabling_support"
    assert substituting["label"] == "substituting_support"
