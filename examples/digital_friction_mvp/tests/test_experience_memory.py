from __future__ import annotations

from proto.experience_memory import (
    TASK_FAMILIES,
    _TASK_FAMILY_SIMILARITY,
    _gaussian_weights,
    build_initial_help_effect_memory,
    build_initial_task_domain_memory,
    extract_memory_features,
    update_experience_memory,
    update_help_effect_memory,
    update_recent_episode_buffer,
    update_task_domain_memory,
)
from proto.models import AttemptOutcome, AttemptStrategy, DigitalTask
from proto.support_protocol import SupportResponse


def _make_task(task_family: str = "account_login_verification") -> DigitalTask:
    friction_map = {
        "navigation_service_location": "information_overload",
        "account_login_verification": "verification",
        "information_search_judgment": "information_overload",
        "profile_form_upload": "form_complexity",
        "service_application_submission": "form_complexity",
        "payment_risk_confirmation": "payment_risk_popup",
    }
    difficulty_map = {
        "navigation_service_location": 0.58,
        "account_login_verification": 0.64,
        "information_search_judgment": 0.56,
        "profile_form_upload": 0.61,
        "service_application_submission": 0.63,
        "payment_risk_confirmation": 0.67,
    }
    return DigitalTask(
        task_id=f"{task_family}-task",
        task_family=task_family,  # type: ignore[arg-type]
        friction_type=friction_map[task_family],  # type: ignore[arg-type]
        difficulty=difficulty_map[task_family],
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=1,
    )


def _make_outcome(
    outcome_type: str,
    *,
    help_used: bool = False,
    negative_feedback: bool = False,
    avoid_reason: str = "not_applicable",
    support_quality: int = 1,
    support_mode: str = "not_applicable",
    event_attribution_stability: str = "not_applicable",
    event_attribution_scope_amplitude: float = 0.0,
) -> AttemptOutcome:
    if event_attribution_scope_amplitude < 0.20:
        event_attribution_scope = "task_specific"
    elif event_attribution_scope_amplitude < 0.60:
        event_attribution_scope = "mixed"
    else:
        event_attribution_scope = "family_generalizing"
    event_attribution_status = (
        "ok"
        if (
            event_attribution_stability != "not_applicable"
            or event_attribution_scope_amplitude > 0.0
        )
        else "not_applicable"
    )
    return AttemptOutcome(
        outcome_type=outcome_type,  # type: ignore[arg-type]
        success=outcome_type in {"success_self", "success_with_help"},
        help_used=help_used,
        negative_feedback=negative_feedback,
        support_quality=support_quality,
        event_level_uncontrollability=1 if negative_feedback else 0,
        friction_tier=1,
        success_probability=0.5,
        abandon_probability=0.1,
        note="test",
        rule_event_level_uncontrollability=1 if negative_feedback else 0,
        avoid_reason=avoid_reason,
        support_mode=support_mode,
        event_attribution_stability=event_attribution_stability,
        event_attribution_scope=event_attribution_scope,
        event_attribution_scope_amplitude=event_attribution_scope_amplitude,
        event_attribution_status=event_attribution_status,
    )


def test_initial_task_domain_memory_has_all_families() -> None:
    memory = build_initial_task_domain_memory(
        digital_experience=0.6,
        vision_limit=0.2,
        past_fraud_experience=0.1,
    )
    assert set(memory) == {
        "navigation_service_location",
        "account_login_verification",
        "information_search_judgment",
        "profile_form_upload",
        "service_application_submission",
        "payment_risk_confirmation",
    }


def test_task_family_similarity_matrix_covers_six_families() -> None:
    assert set(TASK_FAMILIES) == set(_TASK_FAMILY_SIMILARITY)
    for source_family, row in _TASK_FAMILY_SIMILARITY.items():
        assert set(row) == set(TASK_FAMILIES)
        assert row[source_family] == 1.0
        for target_family in TASK_FAMILIES:
            assert row[target_family] == _TASK_FAMILY_SIMILARITY[target_family][source_family]


def test_gaussian_scope_weights_are_normalized_and_exclude_source() -> None:
    weights = _gaussian_weights(
        source_task_family="navigation_service_location",
        sigma=0.45,
    )
    assert "navigation_service_location" not in weights
    assert set(weights) == set(TASK_FAMILIES) - {"navigation_service_location"}
    assert round(sum(weights.values()), 10) == 1.0


def test_profile_changes_initial_task_self_efficacy() -> None:
    high_profile = build_initial_task_domain_memory(
        digital_experience=0.9,
        vision_limit=0.1,
        past_fraud_experience=0.0,
    )
    low_profile = build_initial_task_domain_memory(
        digital_experience=0.2,
        vision_limit=0.6,
        past_fraud_experience=0.6,
    )
    assert (
        high_profile["account_login_verification"]["task_self_efficacy"]
        > low_profile["account_login_verification"]["task_self_efficacy"]
    )


def test_same_task_failures_reduce_efficacy_and_grow_streak() -> None:
    task = _make_task()
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    after_first = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("failure_after_attempt", negative_feedback=True),
        day=0,
        task_domain_memory=memory,
    )
    after_second = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("failure_after_attempt", negative_feedback=True),
        day=0,
        task_domain_memory=after_first,
    )
    assert (
        after_second["account_login_verification"]["task_self_efficacy"]
        < after_first["account_login_verification"]["task_self_efficacy"]
    )
    assert after_second["account_login_verification"]["same_task_failure_streak"] == 2


def test_success_clears_same_task_failure_streak() -> None:
    task = _make_task()
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    failed = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("failure_after_attempt", negative_feedback=True),
        day=0,
        task_domain_memory=memory,
    )
    recovered = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("success_self"),
        day=0,
        task_domain_memory=failed,
    )
    assert recovered["account_login_verification"]["same_task_failure_streak"] == 0


def test_non_helpless_avoid_hurts_task_efficacy_less() -> None:
    task = _make_task()
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    helpless_avoid = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("avoid_without_attempt", avoid_reason="helpless_avoid"),
        day=0,
        task_domain_memory=memory,
    )
    low_value_avoid = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("avoid_without_attempt", avoid_reason="low_value_avoid"),
        day=0,
        task_domain_memory=memory,
    )
    assert (
        helpless_avoid["account_login_verification"]["task_self_efficacy"]
        < low_value_avoid["account_login_verification"]["task_self_efficacy"]
    )


def test_controllable_success_memory_grows_more_for_self_success() -> None:
    task = _make_task()
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    self_success = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("success_self"),
        day=0,
        task_domain_memory=memory,
        task_appraisal_result={"felt_control": 72.0},
    )
    help_success = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "success_with_help",
            help_used=True,
            support_quality=2,
            support_mode="enabling_support",
        ),
        day=0,
        task_domain_memory=memory,
        task_appraisal_result={
            "felt_control": 72.0,
            "expected_help_effectiveness": 72.0,
        },
    )
    assert (
        self_success["account_login_verification"]["controllable_success_memory"]
        > help_success["account_login_verification"]["controllable_success_memory"]
    )
    assert self_success["account_login_verification"]["controllable_success_memory"] > 0.0


def test_controllable_success_memory_decays_slowly_across_days() -> None:
    task = _make_task()
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    memory["account_login_verification"]["controllable_success_memory"] = 0.4
    memory["account_login_verification"]["last_updated_day"] = 0
    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("avoid_without_attempt", avoid_reason="low_value_avoid"),
        day=3,
        task_domain_memory=memory,
    )
    value = updated["account_login_verification"]["controllable_success_memory"]
    assert value < 0.4
    assert value > 0.35


def test_negative_attribution_updates_task_family_summary() -> None:
    task = _make_task("payment_risk_confirmation")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_even_with_help",
            help_used=True,
            negative_feedback=True,
            support_mode="substituting_support",
            event_attribution_stability="stable",
            event_attribution_scope_amplitude=0.85,
        ),
        day=0,
        task_domain_memory=memory,
    )
    state = updated["payment_risk_confirmation"]
    assert state["recent_stable_attribution_ratio"] > 0.0
    assert state["recent_scope_amplitude_ema"] > 0.0
    assert state["dominant_attribution_stability"] in {"mixed", "stable"}
    assert state["dominant_attribution_scope"] in {"mixed", "family_generalizing"}
    assert state["attribution_summary"] != ""


def test_mixed_attribution_pulls_summary_toward_center() -> None:
    task = _make_task("payment_risk_confirmation")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    memory["payment_risk_confirmation"]["recent_stable_attribution_ratio"] = 1.0
    memory["payment_risk_confirmation"]["recent_scope_amplitude_ema"] = 1.0
    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_after_attempt",
            negative_feedback=True,
            event_attribution_stability="mixed",
            event_attribution_scope_amplitude=0.5,
        ),
        day=0,
        task_domain_memory=memory,
    )
    state = updated["payment_risk_confirmation"]
    assert state["recent_stable_attribution_ratio"] < 1.0
    assert state["recent_scope_amplitude_ema"] < 1.0


def test_stable_attribution_history_slows_success_recovery() -> None:
    task = _make_task("payment_risk_confirmation")
    baseline_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    stable_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    stable_memory["payment_risk_confirmation"]["recent_stable_attribution_ratio"] = 1.0

    baseline = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("success_self"),
        day=0,
        task_domain_memory=baseline_memory,
        task_appraisal_result={"felt_control": 70.0},
    )
    slowed = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("success_self"),
        day=0,
        task_domain_memory=stable_memory,
        task_appraisal_result={"felt_control": 70.0},
    )
    assert (
        slowed["payment_risk_confirmation"]["task_self_efficacy"]
        < baseline["payment_risk_confirmation"]["task_self_efficacy"]
    )


def test_high_quality_mastery_pulls_attribution_toward_recovery() -> None:
    task = _make_task("payment_risk_confirmation")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    memory["payment_risk_confirmation"]["recent_stable_attribution_ratio"] = 1.0
    memory["payment_risk_confirmation"]["recent_scope_amplitude_ema"] = 1.0

    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome("success_self"),
        day=0,
        task_domain_memory=memory,
        task_appraisal_result={"felt_control": 72.0},
    )
    state = updated["payment_risk_confirmation"]
    assert state["recent_stable_attribution_ratio"] < 1.0
    assert state["recent_scope_amplitude_ema"] < 1.0
    assert state["dominant_attribution_stability"] in {"mixed", "transient"}
    assert state["dominant_attribution_scope"] in {"mixed", "task_specific"}


def test_family_generalizing_attribution_drags_neighbor_task_family() -> None:
    task = _make_task("navigation_service_location")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    baseline_neighbor = memory["service_application_submission"]["task_self_efficacy"]

    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_after_attempt",
            negative_feedback=True,
            event_attribution_stability="stable",
            event_attribution_scope_amplitude=0.85,
        ),
        day=0,
        task_domain_memory=memory,
    )
    assert updated["service_application_submission"]["task_self_efficacy"] < baseline_neighbor


def test_mixed_scope_generalization_is_weaker_than_family_generalizing() -> None:
    task = _make_task("navigation_service_location")
    mixed_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    broad_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )

    mixed = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_after_attempt",
            negative_feedback=True,
            event_attribution_stability="mixed",
            event_attribution_scope_amplitude=0.35,
        ),
        day=0,
        task_domain_memory=mixed_memory,
    )
    broad = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_after_attempt",
            negative_feedback=True,
            event_attribution_stability="stable",
            event_attribution_scope_amplitude=0.85,
        ),
        day=0,
        task_domain_memory=broad_memory,
    )
    assert (
        mixed["service_application_submission"]["task_self_efficacy"]
        > broad["service_application_submission"]["task_self_efficacy"]
    )


def test_scope_spillover_weights_follow_similarity_order() -> None:
    task = _make_task("navigation_service_location")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_after_attempt",
            negative_feedback=True,
            event_attribution_stability="stable",
            event_attribution_scope_amplitude=0.85,
        ),
        day=0,
        task_domain_memory=memory,
    )
    service_drop = (
        memory["service_application_submission"]["task_self_efficacy"]
        - updated["service_application_submission"]["task_self_efficacy"]
    )
    payment_drop = (
        memory["payment_risk_confirmation"]["task_self_efficacy"]
        - updated["payment_risk_confirmation"]["task_self_efficacy"]
    )
    profile_drop = (
        memory["profile_form_upload"]["task_self_efficacy"]
        - updated["profile_form_upload"]["task_self_efficacy"]
    )
    assert service_drop > payment_drop
    assert service_drop > profile_drop


def test_account_spillover_prefers_profile_upload_over_information_search() -> None:
    task = _make_task("account_login_verification")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    updated = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "failure_after_attempt",
            negative_feedback=True,
            event_attribution_stability="stable",
            event_attribution_scope_amplitude=0.85,
        ),
        day=0,
        task_domain_memory=memory,
    )
    profile_drop = (
        memory["profile_form_upload"]["task_self_efficacy"]
        - updated["profile_form_upload"]["task_self_efficacy"]
    )
    information_drop = (
        memory["information_search_judgment"]["task_self_efficacy"]
        - updated["information_search_judgment"]["task_self_efficacy"]
    )
    assert profile_drop > information_drop


def test_scope_spillover_tracks_total_and_targets() -> None:
    task = _make_task("navigation_service_location")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    outcome = _make_outcome(
        "failure_after_attempt",
        negative_feedback=True,
        event_attribution_stability="stable",
        event_attribution_scope_amplitude=0.85,
    )
    update_task_domain_memory(
        task=task,
        outcome=outcome,
        day=0,
        task_domain_memory=memory,
    )
    assert outcome.scope_spillover_total > 0.0
    assert "service_application_submission" in outcome.scope_spillover_targets_json


def test_zero_scope_amplitude_does_not_trigger_spillover() -> None:
    task = _make_task("navigation_service_location")
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    baseline_neighbor = memory["service_application_submission"]["task_self_efficacy"]
    outcome = _make_outcome(
        "failure_after_attempt",
        negative_feedback=True,
        event_attribution_stability="stable",
        event_attribution_scope_amplitude=0.0,
    )
    updated = update_task_domain_memory(
        task=task,
        outcome=outcome,
        day=0,
        task_domain_memory=memory,
    )
    assert updated["service_application_submission"]["task_self_efficacy"] == baseline_neighbor
    assert outcome.scope_spillover_total == 0.0


def test_enabling_support_builds_more_self_efficacy_than_substituting_support() -> None:
    task = _make_task()
    memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    enabling = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "success_with_help",
            help_used=True,
            support_quality=2,
            support_mode="enabling_support",
        ),
        day=0,
        task_domain_memory=memory,
        task_appraisal_result={
            "felt_control": 65.0,
            "expected_help_effectiveness": 72.0,
        },
    )
    substituting = update_task_domain_memory(
        task=task,
        outcome=_make_outcome(
            "success_with_help",
            help_used=True,
            support_quality=2,
            support_mode="substituting_support",
        ),
        day=0,
        task_domain_memory=memory,
        task_appraisal_result={
            "felt_control": 42.0,
            "expected_help_effectiveness": 48.0,
        },
    )
    assert (
        enabling["account_login_verification"]["task_self_efficacy"]
        > substituting["account_login_verification"]["task_self_efficacy"]
    )
    assert (
        enabling["account_login_verification"]["controllable_success_memory"]
        > substituting["account_login_verification"]["controllable_success_memory"]
    )
    assert substituting["account_login_verification"]["controllable_success_memory"] == 0.0


def test_help_success_rate_is_smoothed() -> None:
    help_memory = build_initial_help_effect_memory()
    updated = update_help_effect_memory(
        task=_make_task("payment_risk_confirmation"),
        strategy=AttemptStrategy(strategy_type="seek_help_then_attempt"),
        outcome=_make_outcome("success_with_help", help_used=True),
        help_effect_memory=help_memory,
    )
    assert updated["overall"]["help_success_rate_smoothed"] == 2.0 / 3.0
    assert updated["overall"]["help_success_rate_smoothed"] < 1.0


def test_support_response_is_recorded_in_help_memory_audit() -> None:
    response = SupportResponse(
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
    updated = update_help_effect_memory(
        task=_make_task("payment_risk_confirmation"),
        strategy=AttemptStrategy(strategy_type="seek_help_then_attempt"),
        outcome=_make_outcome("success_with_help", help_used=True),
        help_effect_memory=build_initial_help_effect_memory(),
        support_response=response,
    )
    audit = updated["support_response_audit"]
    assert audit["style_counts"]["enabling"] == 1
    assert audit["latest"]["instruction_quality"] == "high"
    assert "helplessness_delta" not in audit["latest"]


def test_recent_episode_buffer_caps_at_eight() -> None:
    buffer: list[dict] = []
    task = _make_task("information_search_judgment")
    strategy = AttemptStrategy(strategy_type="attempt_self")
    outcome = _make_outcome("failure_after_attempt", negative_feedback=True)
    for day in range(9):
        buffer = update_recent_episode_buffer(
            task=task,
            strategy=strategy,
            outcome=outcome,
            day=day,
            helplessness_delta=4.0,
            recent_episode_buffer=buffer,
        )
    assert len(buffer) == 8
    assert buffer[0]["day"] == 1


def test_recent_episode_records_support_response_audit_fields() -> None:
    response = SupportResponse(
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
    )
    buffer = update_recent_episode_buffer(
        task=_make_task("service_application_submission"),
        strategy=AttemptStrategy(strategy_type="seek_help_then_attempt"),
        outcome=_make_outcome("success_with_help", help_used=True),
        day=0,
        helplessness_delta=-1.0,
        recent_episode_buffer=[],
        support_response=response,
    )
    assert buffer[-1]["support_style"] == "substituting"
    assert buffer[-1]["proxy_completion_level"] == "full"


def test_recent_failure_pressure_uses_weaker_formula() -> None:
    task = _make_task("payment_risk_confirmation")
    buffer = [
        {
            "day": 0,
            "task_family": "payment_risk_confirmation",
            "strategy_type": "attempt_self",
            "outcome_type": "failure_after_attempt",
            "avoid_reason": "not_applicable",
            "help_used": False,
            "help_source": "none",
            "negative_feedback": True,
            "event_level_uncontrollability": 2,
            "helplessness_delta": 4.0,
        },
        {
            "day": 0,
            "task_family": "payment_risk_confirmation",
            "strategy_type": "avoid",
            "outcome_type": "avoid_without_attempt",
            "avoid_reason": "helpless_avoid",
            "help_used": False,
            "help_source": "none",
            "negative_feedback": False,
            "event_level_uncontrollability": 2,
            "helplessness_delta": 0.5,
        },
        {
            "day": 0,
            "task_family": "payment_risk_confirmation",
            "strategy_type": "seek_help_then_attempt",
            "outcome_type": "failure_even_with_help",
            "avoid_reason": "not_applicable",
            "help_used": True,
            "help_source": "generic",
            "negative_feedback": True,
            "event_level_uncontrollability": 2,
            "helplessness_delta": 5.0,
        },
        {
            "day": 0,
            "task_family": "information_search_judgment",
            "strategy_type": "attempt_self",
            "outcome_type": "success_self",
            "avoid_reason": "not_applicable",
            "help_used": False,
            "help_source": "none",
            "negative_feedback": False,
            "event_level_uncontrollability": 0,
            "helplessness_delta": -2.0,
        },
    ]
    features = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=buffer,
        psychology_mode="off",
    )
    assert features.recent_failure_pressure == 5.0


def test_non_helpless_avoid_does_not_enter_recent_failure_pressure() -> None:
    task = _make_task("payment_risk_confirmation")
    risk_buffer = [
        {
            "day": 0,
            "task_family": "payment_risk_confirmation",
            "strategy_type": "avoid",
            "outcome_type": "avoid_without_attempt",
            "avoid_reason": "risk_avoid",
            "help_used": False,
            "help_source": "none",
            "negative_feedback": False,
            "event_level_uncontrollability": 1,
            "helplessness_delta": 0.2,
        }
    ]
    helpless_buffer = [
        {
            "day": 0,
            "task_family": "payment_risk_confirmation",
            "strategy_type": "avoid",
            "outcome_type": "avoid_without_attempt",
            "avoid_reason": "helpless_avoid",
            "help_used": False,
            "help_source": "none",
            "negative_feedback": False,
            "event_level_uncontrollability": 1,
            "helplessness_delta": 0.2,
        }
    ]
    risk_features = extract_memory_features(
        task=task,
        helplessness_score=40.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=risk_buffer,
        psychology_mode="off",
    )
    helpless_features = extract_memory_features(
        task=task,
        helplessness_score=40.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=helpless_buffer,
        psychology_mode="off",
    )
    assert risk_features.recent_avoid_ratio == 0.0
    assert helpless_features.recent_avoid_ratio > 0.0
    assert helpless_features.recent_failure_pressure > risk_features.recent_failure_pressure


def test_effective_helplessness_rises_when_task_efficacy_is_low() -> None:
    task = _make_task("payment_risk_confirmation")
    baseline_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    strained_memory = build_initial_task_domain_memory(
        digital_experience=0.5,
        vision_limit=0.3,
        past_fraud_experience=0.2,
    )
    strained_memory["payment_risk_confirmation"]["task_self_efficacy"] = 20.0

    baseline_features = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=baseline_memory,
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        psychology_mode="off",
    )
    strained_features = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=strained_memory,
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        psychology_mode="off",
    )
    assert strained_features.effective_helplessness > baseline_features.effective_helplessness


def test_help_success_history_no_longer_changes_effective_helplessness_directly() -> None:
    task = _make_task("payment_risk_confirmation")
    base_kwargs = dict(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        recent_episode_buffer=[],
        psychology_mode="off",
    )
    default_features = extract_memory_features(
        help_effect_memory=build_initial_help_effect_memory(),
        **base_kwargs,
    )
    strong_help_memory = build_initial_help_effect_memory()
    strong_help_memory["by_task_family"]["payment_risk_confirmation"] = {
        "help_attempt_count": 8,
        "help_success_count": 7,
        "help_failure_count": 1,
        "help_success_rate_smoothed": 0.8,
    }
    strong_help_features = extract_memory_features(
        help_effect_memory=strong_help_memory,
        **base_kwargs,
    )
    assert (
        strong_help_features.effective_helplessness
        == default_features.effective_helplessness
    )


def test_emotion_pressure_only_applies_in_hybrid_mode() -> None:
    task = _make_task("payment_risk_confirmation")
    features_off = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={
            "anxiety": 8.0,
            "frustration": 7.0,
            "relief": 1.0,
            "confidence": 2.0,
            "last_updated_day": 0,
        },
        psychology_mode="off",
    )
    features_hybrid = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={
            "anxiety": 8.0,
            "frustration": 7.0,
            "relief": 1.0,
            "confidence": 2.0,
            "last_updated_day": 0,
        },
        psychology_mode="hybrid",
    )
    assert features_off.emotion_pressure == 0.0
    assert features_hybrid.emotion_pressure > 0.0
    assert features_hybrid.effective_helplessness == features_off.effective_helplessness


def test_frustration_and_relief_do_not_change_core_emotion_pressure() -> None:
    task = _make_task("payment_risk_confirmation")
    low_secondary = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={
            "anxiety": 7.0,
            "frustration": 1.0,
            "relief": 1.0,
            "confidence": 3.0,
            "last_updated_day": 0,
        },
        psychology_mode="hybrid",
    )
    high_secondary = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={
            "anxiety": 7.0,
            "frustration": 9.0,
            "relief": 9.0,
            "confidence": 3.0,
            "last_updated_day": 0,
        },
        psychology_mode="hybrid",
    )
    assert low_secondary.emotion_pressure == high_secondary.emotion_pressure
    assert (
        low_secondary.effective_helplessness == high_secondary.effective_helplessness
    )


def test_task_appraisal_shift_no_longer_enters_effective_helplessness() -> None:
    task = _make_task("payment_risk_confirmation")
    neutral = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={"anxiety": 4.0, "confidence": 5.0},
        task_appraisal_result={},
        psychology_mode="hybrid",
    )
    strained = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={"anxiety": 4.0, "confidence": 5.0},
        task_appraisal_result={
            "perceived_task_difficulty": 80.0,
            "perceived_task_risk": 75.0,
            "felt_control": 25.0,
            "expected_help_effectiveness": 40.0,
            "task_value": 65.0,
        },
        psychology_mode="hybrid",
    )
    assert neutral.task_appraisal_shift == 0.0
    assert strained.task_appraisal_shift > 0.0
    assert strained.effective_helplessness == neutral.effective_helplessness


def test_control_and_help_expectation_no_longer_enter_effective_helplessness() -> None:
    task = _make_task("payment_risk_confirmation")
    low_agency = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        task_appraisal_result={
            "perceived_task_difficulty": 75.0,
            "felt_control": 25.0,
            "expected_help_effectiveness": 35.0,
        },
        psychology_mode="off",
    )
    high_agency = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        task_appraisal_result={
            "perceived_task_difficulty": 75.0,
            "felt_control": 80.0,
            "expected_help_effectiveness": 80.0,
        },
        psychology_mode="off",
    )
    assert low_agency.task_appraisal_shift == high_agency.task_appraisal_shift
    assert (
        low_agency.effective_helplessness
        == high_agency.effective_helplessness
    )


def test_task_appraisal_shift_ignores_risk_and_value_direct_push() -> None:
    task = _make_task("payment_risk_confirmation")
    low_risk_value = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={"anxiety": 4.0, "confidence": 5.0},
        task_appraisal_result={
            "perceived_task_difficulty": 75.0,
            "perceived_task_risk": 20.0,
            "felt_control": 30.0,
            "expected_help_effectiveness": 35.0,
            "task_value": 20.0,
        },
        psychology_mode="hybrid",
    )
    high_risk_value = extract_memory_features(
        task=task,
        helplessness_score=55.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.5,
            vision_limit=0.3,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        digital_emotion_state={"anxiety": 4.0, "confidence": 5.0},
        task_appraisal_result={
            "perceived_task_difficulty": 75.0,
            "perceived_task_risk": 90.0,
            "felt_control": 30.0,
            "expected_help_effectiveness": 35.0,
            "task_value": 90.0,
        },
        psychology_mode="hybrid",
    )
    assert low_risk_value.task_appraisal_shift == high_risk_value.task_appraisal_shift
    assert (
        low_risk_value.effective_helplessness
        == high_risk_value.effective_helplessness
    )


def test_update_experience_memory_exposes_audit_snapshots() -> None:
    result = update_experience_memory(
        task=_make_task("service_application_submission"),
        strategy=AttemptStrategy(strategy_type="seek_help_then_attempt"),
        outcome=_make_outcome(
            "failure_even_with_help",
            help_used=True,
            negative_feedback=True,
        ),
        day=1,
        helplessness_delta=5.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.4,
            vision_limit=0.4,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        rationale_memory=[],
    )
    assert "task_domain_snapshot" in result
    assert "help_effect_snapshot" in result
    assert "recent_episode_summary" in result
    assert "rationale_snapshot" in result


def test_update_experience_memory_keeps_support_response_as_audit_only() -> None:
    response = SupportResponse(
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
    result = update_experience_memory(
        task=_make_task("service_application_submission"),
        strategy=AttemptStrategy(strategy_type="seek_help_then_attempt"),
        outcome=_make_outcome(
            "success_with_help",
            help_used=True,
            support_mode="enabling_support",
        ),
        day=1,
        helplessness_delta=-2.0,
        task_domain_memory=build_initial_task_domain_memory(
            digital_experience=0.4,
            vision_limit=0.4,
            past_fraud_experience=0.2,
        ),
        help_effect_memory=build_initial_help_effect_memory(),
        recent_episode_buffer=[],
        rationale_memory=[],
        support_response=response,
    )
    assert result["support_response_snapshot"]["support_style"] == "enabling"
    assert (
        result["help_effect_snapshot"]["support_response_audit"]["latest"][
            "autonomy_preservation"
        ]
        == "high"
    )
    assert "helplessness_delta" not in result["support_response_snapshot"]
