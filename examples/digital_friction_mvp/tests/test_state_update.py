import pytest

from proto.models import HelplessnessUpdateInput
from proto.state_update import apply_helplessness_update


def make_input(**overrides: float | int | str) -> HelplessnessUpdateInput:
    payload: dict[str, float | int | str] = {
        "helplessness_now": 40,
        "outcome_type": "failure_after_attempt",
        "consecutive_failures": 1,
        "support_quality": 0,
        "event_level_uncontrollability": 1,
        "task_self_efficacy": 55,
        "felt_control": 50,
        "expected_help_effectiveness": 50,
        "avoid_reason": "not_applicable",
        "controllable_success_memory": 0.0,
        "support_mode": "not_applicable",
    }
    payload.update(overrides)
    return HelplessnessUpdateInput(**payload)  # type: ignore[arg-type]


def test_failure_update_grows_helplessness_and_increments_streak() -> None:
    result = apply_helplessness_update(make_input())
    assert result.helplessness_after > 40
    assert result.next_consecutive_failures == 2
    assert result.delta > 0


def test_higher_uncontrollability_increases_negative_delta() -> None:
    low = apply_helplessness_update(make_input(event_level_uncontrollability=0))
    high = apply_helplessness_update(make_input(event_level_uncontrollability=2))
    assert high.delta > low.delta
    assert high.uncontrollability_delta > low.uncontrollability_delta


def test_failure_streak_no_longer_directly_adds_helplessness() -> None:
    early = apply_helplessness_update(
        make_input(
            outcome_type="failure_after_attempt",
            consecutive_failures=1,
            event_level_uncontrollability=0,
            task_self_efficacy=55,
            felt_control=50,
        )
    )
    late = apply_helplessness_update(
        make_input(
            outcome_type="failure_after_attempt",
            consecutive_failures=4,
            event_level_uncontrollability=0,
            task_self_efficacy=55,
            felt_control=50,
        )
    )
    assert late.raw_delta_before_damping == early.raw_delta_before_damping
    assert late.delta == early.delta


def test_lower_task_self_efficacy_increases_negative_delta() -> None:
    low_efficacy = apply_helplessness_update(make_input(task_self_efficacy=25))
    high_efficacy = apply_helplessness_update(make_input(task_self_efficacy=65))
    assert low_efficacy.delta > high_efficacy.delta
    assert low_efficacy.efficacy_loss_term > high_efficacy.efficacy_loss_term


def test_felt_control_no_longer_directly_changes_negative_delta() -> None:
    low_control = apply_helplessness_update(
        make_input(
            outcome_type="failure_after_attempt",
            event_level_uncontrollability=1,
            task_self_efficacy=55,
            felt_control=20,
        )
    )
    high_control = apply_helplessness_update(
        make_input(
            outcome_type="failure_after_attempt",
            event_level_uncontrollability=1,
            task_self_efficacy=55,
            felt_control=70,
        )
    )
    assert low_control.raw_delta_before_damping == high_control.raw_delta_before_damping
    assert low_control.delta == high_control.delta


def test_high_helplessness_reduces_negative_delta_via_damping() -> None:
    low_helplessness = apply_helplessness_update(make_input(helplessness_now=20))
    high_helplessness = apply_helplessness_update(make_input(helplessness_now=85))
    assert high_helplessness.raw_delta_before_damping == low_helplessness.raw_delta_before_damping
    assert high_helplessness.damping_factor < low_helplessness.damping_factor
    assert high_helplessness.delta < low_helplessness.delta


def test_success_self_recovers_more_than_success_with_help() -> None:
    self_result = apply_helplessness_update(
        make_input(
            helplessness_now=60,
            outcome_type="success_self",
            consecutive_failures=2,
            support_quality=0,
            event_level_uncontrollability=0,
            felt_control=70,
        )
    )
    help_result = apply_helplessness_update(
        make_input(
            helplessness_now=60,
            outcome_type="success_with_help",
            consecutive_failures=2,
            support_quality=2,
            event_level_uncontrollability=0,
            felt_control=50,
            expected_help_effectiveness=70,
            support_mode="enabling_support",
        )
    )
    assert self_result.delta < help_result.delta
    assert self_result.mastery_recovery_term > help_result.mastery_recovery_term


def test_success_that_ends_failure_streak_recovers_more() -> None:
    boosted = apply_helplessness_update(
        make_input(
            helplessness_now=60,
            outcome_type="success_self",
            consecutive_failures=2,
            event_level_uncontrollability=0,
            felt_control=70,
        )
    )
    plain = apply_helplessness_update(
        make_input(
            helplessness_now=60,
            outcome_type="success_self",
            consecutive_failures=0,
            event_level_uncontrollability=0,
            felt_control=50,
        )
    )
    assert boosted.delta < plain.delta
    assert boosted.mastery_recovery_term > plain.mastery_recovery_term


def test_success_recovery_no_longer_directly_depends_on_felt_control() -> None:
    low_control = apply_helplessness_update(
        make_input(
            helplessness_now=58,
            outcome_type="success_self",
            consecutive_failures=1,
            event_level_uncontrollability=0,
            felt_control=35,
        )
    )
    high_control = apply_helplessness_update(
        make_input(
            helplessness_now=58,
            outcome_type="success_self",
            consecutive_failures=1,
            event_level_uncontrollability=0,
            felt_control=75,
        )
    )
    assert low_control.mastery_recovery_term == high_control.mastery_recovery_term
    assert low_control.delta == high_control.delta


def test_avoid_does_not_reset_failure_streak() -> None:
    result = apply_helplessness_update(
        make_input(
            helplessness_now=70,
            outcome_type="avoid_without_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=0,
            avoid_reason="helpless_avoid",
        )
    )
    assert result.next_consecutive_failures == 2


def test_helpless_avoid_hits_harder_than_other_avoid_reasons() -> None:
    helpless = apply_helplessness_update(
        make_input(
            helplessness_now=65,
            outcome_type="avoid_without_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=1,
            task_self_efficacy=30,
            felt_control=28,
            avoid_reason="helpless_avoid",
        )
    )
    risk = apply_helplessness_update(
        make_input(
            helplessness_now=65,
            outcome_type="avoid_without_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=1,
            task_self_efficacy=30,
            felt_control=28,
            avoid_reason="risk_avoid",
        )
    )
    low_value = apply_helplessness_update(
        make_input(
            helplessness_now=65,
            outcome_type="avoid_without_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=1,
            task_self_efficacy=30,
            felt_control=28,
            avoid_reason="low_value_avoid",
        )
    )
    assert helpless.delta > risk.delta > low_value.delta
    assert helpless.avoid_reason_multiplier > risk.avoid_reason_multiplier


def test_theory_update_v2_records_mode_and_attribution_terms() -> None:
    result = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            event_attribution_locus="self",
            event_attribution_stability="stable",
            event_attribution_scope="family_generalizing",
            event_attribution_confidence=0.8,
        )
    )

    assert result.mode == "theory_update_v2"
    assert result.status == "ok"
    assert result.base_failure_signal > 0.0
    assert result.noncontingency_harm == result.uncontrollability_delta
    assert result.self_efficacy_harm == result.efficacy_loss_term
    assert result.affective_distress_harm == 0.0
    assert result.attribution_multiplier > 1.0
    assert result.calibration_mode_effective == "original_v2"
    assert result.negative_scale == 1.0
    assert result.daily_cap_applied is False
    assert result.delta_before_daily_cap == result.delta_after_daily_cap == result.delta


def test_theory_update_v2_attribution_multiplier_changes_failure_delta() -> None:
    harmful = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            event_level_uncontrollability=1,
            task_self_efficacy=45,
            event_attribution_locus="self",
            event_attribution_stability="stable",
            event_attribution_scope="family_generalizing",
            event_attribution_confidence=0.8,
        )
    )
    buffered = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            event_level_uncontrollability=1,
            task_self_efficacy=45,
            event_attribution_locus="situation",
            event_attribution_stability="transient",
            event_attribution_scope="task_specific",
            event_attribution_confidence=0.8,
        )
    )

    assert harmful.attribution_multiplier > buffered.attribution_multiplier
    assert harmful.delta > buffered.delta


def test_rule_v1_ignores_h_update_calibration_mode() -> None:
    baseline = apply_helplessness_update(
        make_input(
            helplessness_update_mode="rule_v1",
            helplessness_now=85,
            event_level_uncontrollability=2,
            task_self_efficacy=30,
        )
    )
    configured = apply_helplessness_update(
        make_input(
            helplessness_update_mode="rule_v1",
            helplessness_now=85,
            event_level_uncontrollability=2,
            task_self_efficacy=30,
            h_update_calibration_mode="scaled_nonlinear_daily_cap",
            h_update_negative_scale=0.1,
            h_update_daily_harm_cap=0.1,
            h_update_daily_harm_used_before=0.1,
        )
    )

    assert configured.delta == baseline.delta
    assert configured.helplessness_after == baseline.helplessness_after
    assert configured.calibration_mode_effective == "not_applicable"


def test_scaled_nonlinear_reduces_negative_delta_and_records_audit() -> None:
    original = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=85,
            event_level_uncontrollability=2,
            task_self_efficacy=30,
            h_update_calibration_mode="original_v2",
        )
    )
    scaled = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=85,
            event_level_uncontrollability=2,
            task_self_efficacy=30,
            h_update_calibration_mode="scaled_nonlinear",
            h_update_negative_scale=0.60,
            h_update_damping_strength=0.80,
            h_update_damping_power=1.25,
            h_update_damping_floor=0.20,
        )
    )

    assert scaled.calibration_mode_effective == "scaled_nonlinear"
    assert scaled.damping_formula == "nonlinear_v1"
    assert scaled.negative_scale == 0.60
    assert scaled.damping_factor < 0.55
    assert scaled.delta < original.delta
    assert scaled.delta_before_daily_cap == scaled.delta


def test_scaled_nonlinear_does_not_change_success_recovery() -> None:
    original = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=85,
            outcome_type="success_self",
            consecutive_failures=2,
            h_update_calibration_mode="original_v2",
        )
    )
    scaled = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=85,
            outcome_type="success_self",
            consecutive_failures=2,
            h_update_calibration_mode="scaled_nonlinear",
            h_update_negative_scale=0.1,
            h_update_damping_floor=0.9,
        )
    )

    assert scaled.delta == original.delta
    assert scaled.helplessness_after == original.helplessness_after


def test_daily_cap_is_applied_inside_state_update_result() -> None:
    result = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=40,
            event_level_uncontrollability=2,
            task_self_efficacy=20,
            h_update_calibration_mode="scaled_nonlinear_daily_cap",
            h_update_negative_scale=1.0,
            h_update_daily_harm_cap=1.0,
            h_update_daily_harm_used_before=0.8,
        )
    )

    assert result.daily_cap_applied is True
    assert result.daily_harm_remaining_before == pytest.approx(0.2)
    assert result.delta_after_daily_cap == pytest.approx(0.2)
    assert result.delta == pytest.approx(0.2)
    assert result.helplessness_after == pytest.approx(40.2)
    assert result.daily_harm_used_after == pytest.approx(1.0)


def test_success_recovery_does_not_refund_daily_harm_budget() -> None:
    result = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=60,
            outcome_type="success_self",
            consecutive_failures=2,
            h_update_calibration_mode="scaled_nonlinear_daily_cap",
            h_update_daily_harm_cap=5.0,
            h_update_daily_harm_used_before=4.0,
        )
    )

    assert result.delta < 0
    assert result.daily_cap_applied is False
    assert result.daily_harm_used_after == pytest.approx(4.0)


def test_theory_update_v2_low_attribution_confidence_uses_neutral_multiplier() -> None:
    result = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            event_attribution_locus="self",
            event_attribution_stability="stable",
            event_attribution_scope="family_generalizing",
            event_attribution_confidence=0.3,
        )
    )

    assert result.attribution_multiplier == 1.0


def test_invalid_helplessness_update_mode_raises() -> None:
    with pytest.raises(ValueError):
        apply_helplessness_update(make_input(helplessness_update_mode="full_llm_delta"))


def test_rational_security_avoid_has_zero_harm_and_keeps_failure_streak() -> None:
    result = apply_helplessness_update(
        make_input(
            helplessness_update_mode="theory_update_v2",
            helplessness_now=65,
            outcome_type="avoid_without_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=2,
            task_self_efficacy=25,
            avoid_reason="rational_security_avoid",
        )
    )

    assert result.avoid_reason_multiplier == 0.0
    assert result.raw_delta_before_damping == 0.0
    assert result.delta == 0.0
    assert result.next_consecutive_failures == 2


def test_controllable_success_memory_reduces_negative_delta() -> None:
    no_memory = apply_helplessness_update(
        make_input(
            helplessness_now=62,
            outcome_type="failure_after_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=2,
            task_self_efficacy=35,
            felt_control=30,
            controllable_success_memory=0.0,
        )
    )
    strong_memory = apply_helplessness_update(
        make_input(
            helplessness_now=62,
            outcome_type="failure_after_attempt",
            consecutive_failures=2,
            event_level_uncontrollability=2,
            task_self_efficacy=35,
            felt_control=30,
            controllable_success_memory=0.8,
        )
    )
    assert strong_memory.controllable_success_protection > 0.0
    assert strong_memory.delta < no_memory.delta


def test_support_no_longer_directly_reduces_negative_delta() -> None:
    enabling = apply_helplessness_update(
        make_input(
            helplessness_now=62,
            outcome_type="failure_even_with_help",
            consecutive_failures=2,
            support_quality=2,
            event_level_uncontrollability=2,
            task_self_efficacy=35,
            support_mode="enabling_support",
        )
    )
    substituting = apply_helplessness_update(
        make_input(
            helplessness_now=62,
            outcome_type="failure_even_with_help",
            consecutive_failures=2,
            support_quality=2,
            event_level_uncontrollability=2,
            task_self_efficacy=35,
            support_mode="substituting_support",
        )
    )
    assert enabling.raw_delta_before_damping == substituting.raw_delta_before_damping
    assert enabling.delta == substituting.delta


def test_enabling_support_recovers_more_than_substituting_support() -> None:
    enabling = apply_helplessness_update(
        make_input(
            helplessness_now=58,
            outcome_type="success_with_help",
            consecutive_failures=1,
            support_quality=2,
            event_level_uncontrollability=0,
            felt_control=60,
            expected_help_effectiveness=72,
            support_mode="enabling_support",
        )
    )
    substituting = apply_helplessness_update(
        make_input(
            helplessness_now=58,
            outcome_type="success_with_help",
            consecutive_failures=1,
            support_quality=2,
            event_level_uncontrollability=0,
            felt_control=42,
            expected_help_effectiveness=48,
            support_mode="substituting_support",
        )
    )
    assert enabling.mastery_recovery_term > substituting.mastery_recovery_term
    assert enabling.delta < substituting.delta
