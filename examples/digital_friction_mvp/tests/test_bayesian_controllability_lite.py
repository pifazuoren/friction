from __future__ import annotations

import copy

import pytest

from proto.bayesian_controllability_lite import (
    ACTIVE_HUYS_DAYAN_LITE_MODES,
    OUTCOME_BIN_BY_SUBTYPE,
    apply_controllability_gated_modulation,
    build_initial_controllability_lite_memory,
    combine_huys_dayan_lite_audits,
    compute_family_controllability_diagnostic,
    compute_huys_dayan_lite_after_event_audit,
    compute_huys_dayan_lite_before_event_audit,
    normalize_controllability_mode,
    normalize_controllability_lite_memory,
)
from proto.bayesian_policy_lite import (
    build_initial_bayesian_policy_memory,
    update_bayesian_policy_memory,
)


TASK_FAMILY = "payment_risk_confirmation"


def _policy_memory_with_balanced_evidence() -> dict:
    memory = build_initial_bayesian_policy_memory()
    family = memory["families"][TASK_FAMILY]
    for action in ("attempt_self", "seek_help_then_attempt", "avoid"):
        family[action]["update_count"] = 10
        family[action]["alpha"] = {outcome: 0.01 for outcome in family[action]["alpha"]}
    family["attempt_self"]["alpha"]["success_self"] = 20.0
    family["seek_help_then_attempt"]["alpha"]["success_with_help"] = 20.0
    family["avoid"]["alpha"]["no_attempt"] = 20.0
    return memory


def _before_audit(c_family: float, confidence: float = 1.0) -> dict:
    return {
        "before_event": {
            "shrunk_c_family": c_family,
            "family_confidence": confidence,
        },
        "uses_post_outcome_information_for_controllability_policy": False,
    }


def test_control_centered_modulate_is_active_mode() -> None:
    assert normalize_controllability_mode("control_centered_modulate") == (
        "control_centered_modulate"
    )
    assert "control_centered_modulate" in ACTIVE_HUYS_DAYAN_LITE_MODES


def test_outcome_bins_keep_controllable_failure_separate_from_success() -> None:
    assert OUTCOME_BIN_BY_SUBTYPE["success_self"] == "success"
    assert OUTCOME_BIN_BY_SUBTYPE["success_with_help"] == "success"
    assert (
        OUTCOME_BIN_BY_SUBTYPE["failure_after_attempt_low_uncontrollability"]
        == "controllable_failure"
    )
    assert (
        OUTCOME_BIN_BY_SUBTYPE["failure_after_attempt_high_uncontrollability"]
        == "uncontrollable_failure"
    )


def test_empty_or_malformed_memory_initializes_safely() -> None:
    memory = normalize_controllability_lite_memory(
        {"global": {"global_controllability_trace": 9}, "families": {"x": "bad"}},
        task_family=TASK_FAMILY,
    )

    assert memory["version"]
    assert memory["global"]["global_controllability_trace"] == 1.0
    assert TASK_FAMILY in memory["families"]
    assert memory["families"][TASK_FAMILY]["shrunk_c_family"] == 0.5


def test_family_diagnostic_uses_balanced_attempt_help_evidence() -> None:
    memory = _policy_memory_with_balanced_evidence()

    diagnostic = compute_family_controllability_diagnostic(
        raw_policy_memory=memory,
        task_family=TASK_FAMILY,
        min_action_updates=2,
        confidence_k=6,
        utility_profile="theory_v2",
    )

    assert diagnostic["status"] == "computed"
    assert diagnostic["excluded_actions"]["avoid"]
    assert diagnostic["family_confidence"] > 0.0
    assert diagnostic["action_contrast_control"] >= 0.0
    assert diagnostic["reward_control_chi_lite"] >= 0.0
    assert 0.0 <= diagnostic["shrunk_c_family"] <= 1.0


def test_avoid_no_attempt_does_not_inflate_main_c_family() -> None:
    memory = build_initial_bayesian_policy_memory()
    family = memory["families"][TASK_FAMILY]
    family["avoid"]["update_count"] = 50
    family["avoid"]["alpha"] = {outcome: 0.01 for outcome in family["avoid"]["alpha"]}
    family["avoid"]["alpha"]["no_attempt"] = 100.0

    diagnostic = compute_family_controllability_diagnostic(
        raw_policy_memory=memory,
        task_family=TASK_FAMILY,
        min_action_updates=2,
        confidence_k=6,
    )

    assert diagnostic["family_confidence"] == pytest.approx(0.0)
    assert diagnostic["shrunk_c_family"] == pytest.approx(0.5)


def test_low_c_flattens_policy_toward_uniform_without_directional_help_rule() -> None:
    pi_base = {"attempt_self": 0.8, "seek_help_then_attempt": 0.1, "avoid": 0.1}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="gated_modulate",
        pi_base=pi_base,
        before_event_audit=_before_audit(0.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
        prob_floor=0.05,
    )

    assert audit["modulation_family"] == "flatten_low_c"
    assert audit["low_c_directional_help_shift_enabled"] is False
    assert audit["extreme_low_c_avoid_shift_enabled"] is False
    assert audit["uniform_mix_gamma"] == pytest.approx(0.10)
    assert pi_final is not None
    assert pi_final["attempt_self"] < pi_base["attempt_self"]
    assert pi_final["seek_help_then_attempt"] > pi_base["seek_help_then_attempt"]
    assert pi_final["avoid"] > pi_base["avoid"]


def test_low_c_does_not_directly_increase_avoid_when_uniform_is_lower() -> None:
    pi_base = {"attempt_self": 0.1, "seek_help_then_attempt": 0.1, "avoid": 0.8}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="gated_modulate",
        pi_base=pi_base,
        before_event_audit=_before_audit(0.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
    )

    assert audit["modulation_family"] == "flatten_low_c"
    assert pi_final is not None
    assert pi_final["avoid"] < pi_base["avoid"]


def test_control_centered_low_c_shrinks_policy_toward_pi_ref() -> None:
    pi_base = {"attempt_self": 0.8, "seek_help_then_attempt": 0.1, "avoid": 0.1}
    pi_ref = {"attempt_self": 0.2, "seek_help_then_attempt": 0.7, "avoid": 0.1}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="control_centered_modulate",
        pi_base=pi_base,
        pi_ref=pi_ref,
        before_event_audit=_before_audit(0.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
        prob_floor=0.05,
    )

    assert audit["modulation_status"] == "modulated"
    assert audit["modulation_status"] != "not_gated_modulate"
    assert audit["modulation_family"] == "shrink_to_reference_low_c"
    assert audit["control_centered_low_c_target"] == "pi_ref"
    assert audit["reference_mix_gamma"] == pytest.approx(0.10)
    assert audit["uniform_mix_gamma"] == pytest.approx(0.0)
    assert audit["pi_reference_for_control_centered"] == pytest.approx(pi_ref)
    assert pi_final is not None
    assert pi_final["attempt_self"] < pi_base["attempt_self"]
    assert pi_final["seek_help_then_attempt"] > pi_base["seek_help_then_attempt"]
    assert pi_final["avoid"] == pytest.approx(pi_base["avoid"])


def test_low_c_modulation_scales_with_sqrt_family_confidence() -> None:
    pi_base = {"attempt_self": 0.8, "seek_help_then_attempt": 0.1, "avoid": 0.1}
    pi_ref = {"attempt_self": 0.2, "seek_help_then_attempt": 0.7, "avoid": 0.1}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="control_centered_modulate",
        pi_base=pi_base,
        pi_ref=pi_ref,
        before_event_audit=_before_audit(0.0, 0.25),
        gate_threshold=0.1,
        max_delta=0.20,
        low_c_threshold=0.50,
        high_c_threshold=0.60,
        prob_floor=0.05,
    )

    assert audit["modulation_family"] == "shrink_to_reference_low_c"
    assert audit["reference_mix_gamma"] == pytest.approx(0.10)
    assert pi_final is not None
    assert pi_final["attempt_self"] == pytest.approx(0.74)
    assert pi_final["seek_help_then_attempt"] == pytest.approx(0.16)


@pytest.mark.parametrize(
    "bad_pi_ref",
    [
        None,
        {"attempt_self": 0.0, "seek_help_then_attempt": 0.0, "avoid": 0.0},
        {"attempt_self": 0.4, "avoid": 0.6},
        {"attempt_self": 0.5, "seek_help_then_attempt": -0.1, "avoid": 0.6},
        {"attempt_self": 0.5, "seek_help_then_attempt": float("nan"), "avoid": 0.5},
    ],
)
def test_control_centered_low_c_invalid_pi_ref_noops_without_uniform_fallback(
    bad_pi_ref,
) -> None:
    pi_base = {"attempt_self": 0.7, "seek_help_then_attempt": 0.2, "avoid": 0.1}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="control_centered_modulate",
        pi_base=pi_base,
        pi_ref=bad_pi_ref,
        before_event_audit=_before_audit(0.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
        prob_floor=0.05,
    )

    assert audit["modulation_status"] == "reference_policy_unavailable"
    assert audit["modulation_family"] == "none"
    assert audit["reference_mix_gamma"] == pytest.approx(0.0)
    assert audit["intervention_applied"] is False
    assert audit["pi_reference_for_control_centered"] == {}
    assert pi_final == pytest.approx(pi_base)


def test_high_c_reduces_avoid_and_uses_best_nonavoid_from_phase4_policy() -> None:
    pi_base = {"attempt_self": 0.2, "seek_help_then_attempt": 0.5, "avoid": 0.3}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="gated_modulate",
        pi_base=pi_base,
        before_event_audit=_before_audit(1.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
    )

    assert audit["modulation_family"] == "reduce_avoid_high_c"
    assert audit["best_nonavoid_action"] == "seek_help_then_attempt"
    assert audit["best_nonavoid_source"] == "phase4_pi_final"
    assert pi_final is not None
    assert pi_final["avoid"] < pi_base["avoid"]
    assert pi_final["seek_help_then_attempt"] > pi_base["seek_help_then_attempt"]


def test_high_c_can_give_mass_to_attempt_when_attempt_is_stronger() -> None:
    pi_base = {"attempt_self": 0.55, "seek_help_then_attempt": 0.2, "avoid": 0.25}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="gated_modulate",
        pi_base=pi_base,
        before_event_audit=_before_audit(1.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
    )

    assert audit["best_nonavoid_action"] == "attempt_self"
    assert pi_final is not None
    assert pi_final["attempt_self"] > pi_base["attempt_self"]


def test_high_c_modulation_scales_with_sqrt_family_confidence() -> None:
    pi_base = {"attempt_self": 0.2, "seek_help_then_attempt": 0.5, "avoid": 0.3}

    pi_final, audit = apply_controllability_gated_modulation(
        mode="control_centered_modulate",
        pi_base=pi_base,
        before_event_audit=_before_audit(1.0, 0.25),
        gate_threshold=0.1,
        max_delta=0.20,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
    )

    assert audit["modulation_family"] == "reduce_avoid_high_c"
    assert audit["removed_avoid_mass"] == pytest.approx(0.10)
    assert pi_final is not None
    assert pi_final["avoid"] == pytest.approx(0.20)
    assert pi_final["seek_help_then_attempt"] == pytest.approx(0.60)


@pytest.mark.parametrize(
    ("pi_base", "expected_action", "other_action"),
    [
        (
            {"attempt_self": 0.2, "seek_help_then_attempt": 0.5, "avoid": 0.3},
            "seek_help_then_attempt",
            "attempt_self",
        ),
        (
            {"attempt_self": 0.55, "seek_help_then_attempt": 0.2, "avoid": 0.25},
            "attempt_self",
            "seek_help_then_attempt",
        ),
    ],
)
def test_control_centered_high_c_reuses_best_nonavoid_from_phase4_policy(
    pi_base: dict[str, float],
    expected_action: str,
    other_action: str,
) -> None:
    pi_final, audit = apply_controllability_gated_modulation(
        mode="control_centered_modulate",
        pi_base=pi_base,
        before_event_audit=_before_audit(1.0, 1.0),
        gate_threshold=0.5,
        max_delta=0.10,
        low_c_threshold=0.45,
        high_c_threshold=0.60,
    )

    assert audit["modulation_family"] == "reduce_avoid_high_c"
    assert audit["best_nonavoid_action"] == expected_action
    assert audit["best_nonavoid_source"] == "phase4_pi_final"
    assert pi_final is not None
    assert pi_final["avoid"] < pi_base["avoid"]
    assert pi_final[expected_action] > pi_base[expected_action]
    assert pi_final[other_action] == pytest.approx(pi_base[other_action])


def test_modulation_gate_closed_or_base_missing_does_not_intervene() -> None:
    gated_final, gated_audit = apply_controllability_gated_modulation(
        mode="gated_modulate",
        pi_base={"attempt_self": 0.6, "seek_help_then_attempt": 0.2, "avoid": 0.2},
        before_event_audit=_before_audit(1.0, 0.1),
        gate_threshold=0.5,
    )
    missing_final, missing_audit = apply_controllability_gated_modulation(
        mode="gated_modulate",
        pi_base=None,
        q_bayes=None,
        before_event_audit=_before_audit(1.0, 1.0),
    )

    assert gated_final is not None
    assert gated_audit["intervention_applied"] is False
    assert gated_audit["modulation_status"] == "gate_closed_low_confidence"
    assert missing_final is None
    assert missing_audit["modulation_status"] == "base_policy_unavailable"


def test_before_event_audit_ignores_post_outcome_fields() -> None:
    memory = _policy_memory_with_balanced_evidence()

    _, audit = compute_huys_dayan_lite_before_event_audit(
        raw_policy_memory=memory,
        raw_controllability_memory={},
        mode="shadow",
        task_family=TASK_FAMILY,
        env={"support_mode": "enabling_support", "outcome_type": "success_self"},
        task_appraisal={
            "avoid_reason": "helpless_avoid",
            "event_attribution_locus": "internal",
            "helplessness_after": 99,
        },
    )

    assert audit["uses_post_outcome_information_for_controllability_policy"] is False
    assert set(audit["post_outcome_fields_ignored_for_controllability"]) == {
        "avoid_reason",
        "event_attribution_locus",
        "helplessness_after",
        "outcome_type",
        "support_mode",
    }


def test_after_event_updates_trace_but_is_marked_post_update() -> None:
    policy_memory = _policy_memory_with_balanced_evidence()
    controllability_memory = build_initial_controllability_lite_memory()

    updated_memory, after_audit = compute_huys_dayan_lite_after_event_audit(
        raw_policy_memory=policy_memory,
        raw_controllability_memory=controllability_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
        confidence_k=1,
        min_action_updates=1,
        day=3,
    )

    assert after_audit["after_event"]["post_update"] is True
    assert after_audit["after_event"]["post_update_memory_status"] == "updated"
    assert TASK_FAMILY in updated_memory["families"]


def test_helper_does_not_mutate_inputs() -> None:
    policy_memory = _policy_memory_with_balanced_evidence()
    controllability_memory = build_initial_controllability_lite_memory()
    pi_base = {"attempt_self": 0.4, "seek_help_then_attempt": 0.4, "avoid": 0.2}
    pi_ref = {"attempt_self": 0.2, "seek_help_then_attempt": 0.7, "avoid": 0.1}
    before_audit = _before_audit(0.0, 1.0)
    before = (
        copy.deepcopy(policy_memory),
        copy.deepcopy(controllability_memory),
        copy.deepcopy(pi_base),
        copy.deepcopy(pi_ref),
        copy.deepcopy(before_audit),
    )

    compute_huys_dayan_lite_before_event_audit(
        raw_policy_memory=policy_memory,
        raw_controllability_memory=controllability_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
    )
    apply_controllability_gated_modulation(
        mode="control_centered_modulate",
        pi_base=pi_base,
        pi_ref=pi_ref,
        before_event_audit=before_audit,
    )

    assert policy_memory == before[0]
    assert controllability_memory == before[1]
    assert pi_base == before[2]
    assert pi_ref == before[3]
    assert before_audit == before[4]


def test_combine_audits_keeps_before_and_after_separate() -> None:
    before = {
        "enabled": True,
        "before_event": {"shrunk_c_family": 0.4, "global_controllability_trace": 0.5},
    }
    modulation = {"intervention_applied": True}
    after = {
        "after_event": {
            "shrunk_c_family": 0.6,
            "global_controllability_trace_after": 0.55,
        }
    }

    combined = combine_huys_dayan_lite_audits(
        before_audit=before,
        modulation_audit=modulation,
        after_audit=after,
    )

    assert combined["C_family_before_event"] == 0.4
    assert combined["C_family_after_event"] == 0.6
    assert combined["intervention_applied"] is True


def test_update_policy_memory_can_feed_after_event_diagnostic() -> None:
    policy_memory = build_initial_bayesian_policy_memory()
    policy_memory, _ = update_bayesian_policy_memory(
        raw_memory=policy_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="success_self",
        day=1,
    )

    diagnostic = compute_family_controllability_diagnostic(
        raw_policy_memory=policy_memory,
        task_family=TASK_FAMILY,
    )

    assert diagnostic["update_counts_by_action"]["attempt_self"] == 1
