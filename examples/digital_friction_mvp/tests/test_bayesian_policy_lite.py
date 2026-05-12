from __future__ import annotations

import copy
import inspect

import pytest

from proto.bayesian_policy_lite import (
    BAYESIAN_POLICY_LITE_VERSION,
    POLICY_LITE_ACTIONS,
    build_initial_bayesian_policy_memory,
    classify_policy_outcome_subtype,
    combine_bayesian_policy_audits,
    compute_bayesian_policy_shadow,
    compute_posterior_predictive_by_action,
    update_bayesian_policy_memory,
)


TASK_FAMILY = "payment_risk_confirmation"


def test_initial_memory_uses_action_specific_priors() -> None:
    memory = build_initial_bayesian_policy_memory()
    family = memory["families"][TASK_FAMILY]

    assert memory["version"] == BAYESIAN_POLICY_LITE_VERSION
    assert family["attempt_self"]["alpha"]["success_self"] == 1.0
    assert family["attempt_self"]["alpha"]["success_with_help"] == 0.01
    assert family["seek_help_then_attempt"]["alpha"]["success_with_help"] == 1.0
    assert family["seek_help_then_attempt"]["alpha"]["success_self"] == 0.01
    assert family["avoid"]["alpha"]["no_attempt"] == 1.0
    assert family["avoid"]["alpha"]["success_self"] == 0.01
    assert family["avoid"]["alpha"]["neutral_unknown"] == 0.05


def test_empty_or_malformed_memory_initializes_safely() -> None:
    memory, audit = compute_bayesian_policy_shadow(
        raw_memory={TASK_FAMILY: {"attempt_self": {"alpha": {"success_self": -9}}}},
        mode="shadow",
        task_family=TASK_FAMILY,
        strategy_reference={"attempt_self": 0.2, "seek_help_then_attempt": 0.5},
    )

    assert audit["status"] == "computed"
    assert TASK_FAMILY in memory["families"]
    for action in POLICY_LITE_ACTIONS:
        assert set(memory["families"][TASK_FAMILY][action]["alpha"])
        assert sum(memory["families"][TASK_FAMILY][action]["alpha"].values()) > 0.0


def test_policy_shadow_returns_valid_distributions_confidence_and_entropy() -> None:
    _, audit = compute_bayesian_policy_shadow(
        raw_memory={},
        mode="shadow",
        task_family=TASK_FAMILY,
        strategy_reference={
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.5,
            "avoid": 0.3,
        },
        task_difficulty=0.8,
        env={
            "risk_level": 2,
            "assist_level": 1,
            "accessibility_level": 1,
            "human_support_level": 1,
        },
        task_appraisal={"expected_help_effectiveness": 75.0},
        tau=0.7,
        confidence_k=4,
    )

    assert audit["uses_post_outcome_information_for_policy"] is False
    assert audit["utility_profile"] == "shadow_v1"
    assert audit["pre_update"] is True
    assert audit["strategy_unchanged"] is True
    assert sum(audit["pi_bayes_shadow"].values()) == pytest.approx(1.0)
    assert sum(audit["pi_prior"].values()) == pytest.approx(1.0)
    assert sum(audit["pi_strategy_reference"].values()) == pytest.approx(1.0)
    assert set(audit["q_bayes"]) == set(POLICY_LITE_ACTIONS)
    assert all(0.0 <= value <= 1.0 for value in audit["confidence_by_action"].values())
    assert all(
        0.0 <= value <= 1.0 for value in audit["posterior_entropy_by_action"].values()
    )
    assert "pi_final" not in audit
    assert audit["pi_ref"] == audit["pi_strategy_reference"]


def test_shadow_v1_default_matches_explicit_profile() -> None:
    kwargs = {
        "raw_memory": {},
        "mode": "shadow",
        "task_family": TASK_FAMILY,
        "strategy_reference": {
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.5,
            "avoid": 0.3,
        },
        "task_difficulty": 0.8,
        "env": {
            "risk_level": 2,
            "assist_level": 1,
            "accessibility_level": 1,
            "human_support_level": 1,
        },
        "task_appraisal": {
            "expected_help_effectiveness": 75.0,
            "task_value": 80.0,
        },
        "tau": 0.7,
    }

    _, default_audit = compute_bayesian_policy_shadow(**kwargs)
    _, explicit_audit = compute_bayesian_policy_shadow(
        **kwargs,
        utility_profile="shadow_v1",
    )

    assert default_audit["utility_profile"] == "shadow_v1"
    assert default_audit["q_bayes"] == explicit_audit["q_bayes"]
    assert default_audit["pi_bayes_shadow"] == explicit_audit["pi_bayes_shadow"]


def test_theory_v2_penalizes_high_value_no_attempt() -> None:
    base = {
        "raw_memory": {},
        "mode": "shadow",
        "task_family": TASK_FAMILY,
        "strategy_reference": {},
        "task_difficulty": 0.5,
        "env": {"risk_level": 1},
        "utility_profile": "theory_v2",
    }

    _, low_value_audit = compute_bayesian_policy_shadow(
        **base,
        task_appraisal={
            "task_value": 20.0,
            "perceived_task_risk": 50.0,
            "felt_control": 50.0,
        },
    )
    _, high_value_audit = compute_bayesian_policy_shadow(
        **base,
        task_appraisal={
            "task_value": 90.0,
            "perceived_task_risk": 50.0,
            "felt_control": 50.0,
        },
    )

    assert high_value_audit["q_bayes"]["avoid"] < low_value_audit["q_bayes"]["avoid"]
    assert high_value_audit["utility_profile_note"]


def test_theory_v2_rewards_expected_effective_help() -> None:
    base = {
        "raw_memory": {},
        "mode": "shadow",
        "task_family": TASK_FAMILY,
        "strategy_reference": {},
        "task_difficulty": 0.5,
        "env": {
            "assist_level": 1,
            "accessibility_level": 1,
            "human_support_level": 1,
        },
        "utility_profile": "theory_v2",
    }

    _, low_help_audit = compute_bayesian_policy_shadow(
        **base,
        task_appraisal={"expected_help_effectiveness": 20.0},
    )
    _, high_help_audit = compute_bayesian_policy_shadow(
        **base,
        task_appraisal={"expected_help_effectiveness": 90.0},
    )

    assert (
        high_help_audit["q_bayes"]["seek_help_then_attempt"]
        > low_help_audit["q_bayes"]["seek_help_then_attempt"]
    )


def test_shadow_policy_ignores_post_outcome_fields_in_context_dicts() -> None:
    base = {
        "raw_memory": {},
        "mode": "shadow",
        "task_family": TASK_FAMILY,
        "strategy_reference": {"attempt_self": 0.3, "avoid": 0.7},
        "task_difficulty": 0.5,
        "env": {"risk_level": 2},
        "task_appraisal": {
            "expected_help_effectiveness": 70.0,
            "task_value": 80.0,
            "perceived_task_risk": 60.0,
            "felt_control": 40.0,
        },
        "utility_profile": "theory_v2",
    }
    leaked = copy.deepcopy(base)
    leaked["env"] = {
        **base["env"],
        "support_mode": "enabling_support",
        "outcome_type": "success_with_help",
    }
    leaked["task_appraisal"] = {
        **base["task_appraisal"],
        "avoid_reason": "helpless_avoid",
        "event_attribution_locus": "internal",
        "event_attribution_stability": "stable",
        "event_attribution_scope": "global",
        "event_level_uncontrollability": 2,
    }

    _, base_audit = compute_bayesian_policy_shadow(**base)
    _, leaked_audit = compute_bayesian_policy_shadow(**leaked)

    assert base_audit["q_bayes"] == leaked_audit["q_bayes"]
    assert base_audit["pi_bayes_shadow"] == leaked_audit["pi_bayes_shadow"]
    assert leaked_audit["uses_post_outcome_information_for_policy"] is False
    assert set(leaked_audit["post_outcome_fields_ignored_for_policy"]) == {
        "avoid_reason",
        "event_attribution_locus",
        "event_attribution_scope",
        "event_attribution_stability",
        "event_level_uncontrollability",
        "outcome_type",
        "support_mode",
    }


def test_gated_lite_returns_final_policy_when_gate_opens() -> None:
    raw_memory = build_initial_bayesian_policy_memory()
    family = raw_memory["families"][TASK_FAMILY]
    family["attempt_self"]["update_count"] = 10
    family["seek_help_then_attempt"]["update_count"] = 10
    family["avoid"]["update_count"] = 10
    family["attempt_self"]["alpha"] = {
        outcome: 0.01 for outcome in family["attempt_self"]["alpha"]
    }
    family["attempt_self"]["alpha"]["success_self"] = 20.0
    family["seek_help_then_attempt"]["alpha"] = {
        outcome: 0.01 for outcome in family["seek_help_then_attempt"]["alpha"]
    }
    family["seek_help_then_attempt"]["alpha"]["failure_even_with_help"] = 20.0
    family["avoid"]["alpha"] = {
        outcome: 0.01 for outcome in family["avoid"]["alpha"]
    }
    family["avoid"]["alpha"]["no_attempt"] = 20.0

    _, audit = compute_bayesian_policy_shadow(
        raw_memory=raw_memory,
        mode="gated_lite",
        task_family=TASK_FAMILY,
        strategy_reference={
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.4,
            "avoid": 0.4,
        },
        utility_profile="theory_v2",
        gate_threshold=0.5,
        entropy_threshold=0.85,
        max_delta=0.05,
        prob_floor=0.05,
    )

    assert audit["mode"] == "gated_lite"
    assert audit["status"] == "computed"
    assert audit["strategy_unchanged"] is False
    assert audit["intervention_applied"] is True
    assert set(audit["pi_final"]) == set(POLICY_LITE_ACTIONS)
    assert sum(audit["pi_final"].values()) == pytest.approx(1.0)
    assert min(audit["pi_final"].values()) >= 0.05 - 1e-12
    assert audit["gate_by_action"]["attempt_self"] is True
    assert audit["delta_applied"]["attempt_self"] <= 0.05
    assert audit["delta_applied"]["attempt_self"] > 0.0
    assert audit["final_delta_after_floor"]["attempt_self"] == pytest.approx(
        audit["pi_final"]["attempt_self"] - audit["pi_ref"]["attempt_self"]
    )
    assert audit["max_abs_final_delta"] == pytest.approx(
        max(abs(value) for value in audit["final_delta_after_floor"].values())
    )


def test_gated_lite_does_not_intervene_when_confidence_is_low() -> None:
    _, audit = compute_bayesian_policy_shadow(
        raw_memory={},
        mode="gated_lite",
        task_family=TASK_FAMILY,
        strategy_reference={
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.4,
            "avoid": 0.4,
        },
        gate_threshold=0.5,
        entropy_threshold=0.85,
        max_delta=0.05,
    )

    assert audit["intervention_applied"] is False
    assert all(value == 0.0 for value in audit["delta_applied"].values())


def test_gated_lite_does_not_intervene_when_entropy_is_high() -> None:
    raw_memory = build_initial_bayesian_policy_memory()
    family = raw_memory["families"][TASK_FAMILY]
    for action in POLICY_LITE_ACTIONS:
        family[action]["update_count"] = 20

    _, audit = compute_bayesian_policy_shadow(
        raw_memory=raw_memory,
        mode="gated_lite",
        task_family=TASK_FAMILY,
        strategy_reference={
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.4,
            "avoid": 0.4,
        },
        gate_threshold=0.5,
        entropy_threshold=0.01,
        max_delta=0.05,
    )

    assert audit["intervention_applied"] is False
    assert all(value is False for value in audit["gate_by_action"].values())
    assert all(value == 0.0 for value in audit["delta_applied"].values())


def test_gated_lite_max_delta_zero_is_no_bayesian_intervention() -> None:
    raw_memory = build_initial_bayesian_policy_memory()
    family = raw_memory["families"][TASK_FAMILY]
    for action in POLICY_LITE_ACTIONS:
        family[action]["update_count"] = 20

    _, audit = compute_bayesian_policy_shadow(
        raw_memory=raw_memory,
        mode="gated_lite",
        task_family=TASK_FAMILY,
        strategy_reference={
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.4,
            "avoid": 0.4,
        },
        gate_threshold=0.1,
        entropy_threshold=1.0,
        max_delta=0.0,
    )

    assert audit["intervention_applied"] is False
    assert all(value == 0.0 for value in audit["delta_applied"].values())
    assert audit["pi_after_bayesian_shift"] == pytest.approx(audit["pi_ref"])


def test_posterior_predictive_probabilities_sum_to_one() -> None:
    predictive = compute_posterior_predictive_by_action(
        raw_memory={},
        task_family=TASK_FAMILY,
    )

    assert set(predictive) == set(POLICY_LITE_ACTIONS)
    for action_distribution in predictive.values():
        assert sum(action_distribution.values()) == pytest.approx(1.0)
        assert set(action_distribution)


def test_pre_outcome_shadow_signature_excludes_post_outcome_fields() -> None:
    parameters = set(inspect.signature(compute_bayesian_policy_shadow).parameters)

    assert "outcome_type" not in parameters
    assert "support_mode" not in parameters
    assert "avoid_reason" not in parameters
    assert "event_attribution_locus" not in parameters


def test_policy_outcome_subtype_uses_calibrated_uncontrollability_label() -> None:
    assert (
        classify_policy_outcome_subtype(
            outcome_type="failure_after_attempt",
            event_level_uncontrollability=2,
        )
        == "failure_after_attempt_high_uncontrollability"
    )
    assert (
        classify_policy_outcome_subtype(outcome_type="avoid_without_attempt")
        == "no_attempt"
    )


def test_update_only_observed_action() -> None:
    raw_memory = build_initial_bayesian_policy_memory()
    before = copy.deepcopy(raw_memory)

    memory_after, audit = update_bayesian_policy_memory(
        raw_memory=raw_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
        actual_strategy="seek_help_then_attempt",
        outcome_type="success_with_help",
        support_mode="enabling_support",
        day=3,
    )

    family_after = memory_after["families"][TASK_FAMILY]
    assert audit["status"] == "updated"
    assert audit["posterior_update_action"] == "seek_help_then_attempt"
    assert audit["policy_outcome_subtype"] == "success_with_help"
    assert family_after["seek_help_then_attempt"]["update_count"] == 1
    assert family_after["attempt_self"] == before["families"][TASK_FAMILY]["attempt_self"]
    assert family_after["avoid"] == before["families"][TASK_FAMILY]["avoid"]
    assert raw_memory == before


def test_gated_lite_updates_observed_action_like_shadow() -> None:
    raw_memory = build_initial_bayesian_policy_memory()

    memory_after, audit = update_bayesian_policy_memory(
        raw_memory=raw_memory,
        mode="gated_lite",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="success_self",
        day=6,
    )

    assert audit["mode"] == "gated_lite"
    assert audit["status"] == "updated"
    assert audit["posterior_update_action"] == "attempt_self"
    assert memory_after["families"][TASK_FAMILY]["attempt_self"]["update_count"] == 1


def test_avoid_updates_only_no_attempt_for_avoid_action() -> None:
    raw_memory = build_initial_bayesian_policy_memory()
    before = copy.deepcopy(raw_memory)

    memory_after, audit = update_bayesian_policy_memory(
        raw_memory=raw_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
        actual_strategy="avoid",
        outcome_type="avoid_without_attempt",
        avoid_reason="risk_avoid",
        day=4,
    )

    family_after = memory_after["families"][TASK_FAMILY]
    assert audit["policy_outcome_subtype"] == "no_attempt"
    assert audit["psychological_interpretation"] == "risk_avoid"
    assert family_after["avoid"]["alpha"]["no_attempt"] > (
        before["families"][TASK_FAMILY]["avoid"]["alpha"]["no_attempt"]
    )
    assert family_after["attempt_self"] == before["families"][TASK_FAMILY]["attempt_self"]
    assert family_after["seek_help_then_attempt"] == (
        before["families"][TASK_FAMILY]["seek_help_then_attempt"]
    )


def test_weight_zero_freezes_alpha_and_update_count() -> None:
    raw_memory = build_initial_bayesian_policy_memory()
    before_action = copy.deepcopy(raw_memory["families"][TASK_FAMILY]["attempt_self"])

    memory_after, audit = update_bayesian_policy_memory(
        raw_memory=raw_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="success_self",
        weight=0.0,
        day=5,
    )

    after_action = memory_after["families"][TASK_FAMILY]["attempt_self"]
    assert audit["weight"] == 0.0
    assert after_action["alpha"] == before_action["alpha"]
    assert after_action["update_count"] == before_action["update_count"]
    assert after_action["last_policy_outcome_subtype"] == "success_self"


def test_rho_zero_drops_prior_history_and_keeps_current_evidence_only() -> None:
    raw_memory = build_initial_bayesian_policy_memory()

    memory_after, audit = update_bayesian_policy_memory(
        raw_memory=raw_memory,
        mode="shadow",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="failure_after_attempt",
        event_level_uncontrollability=2,
        rho=0.0,
        weight=1.0,
    )

    alpha = memory_after["families"][TASK_FAMILY]["attempt_self"]["alpha"]
    assert audit["rho"] == 0.0
    assert alpha["failure_after_attempt_high_uncontrollability"] == 1.0
    assert (
        sum(
            value
            for key, value in alpha.items()
            if key != "failure_after_attempt_high_uncontrollability"
        )
        == 0.0
    )


def test_mode_off_returns_disabled_without_updating_memory() -> None:
    raw_memory = build_initial_bayesian_policy_memory()

    memory_after, audit = update_bayesian_policy_memory(
        raw_memory=raw_memory,
        mode="off",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="success_self",
    )

    assert audit["status"] == "disabled"
    assert memory_after == raw_memory


def test_combine_audits_marks_strategy_unchanged_and_merges_update_fields() -> None:
    _, pre_audit = compute_bayesian_policy_shadow(
        raw_memory={},
        mode="shadow",
        task_family=TASK_FAMILY,
        strategy_reference={"attempt_self": 1.0},
    )
    _, update_audit = update_bayesian_policy_memory(
        raw_memory={},
        mode="shadow",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="success_self",
    )

    combined = combine_bayesian_policy_audits(
        pre_audit=pre_audit,
        update_audit=update_audit,
        actual_strategy="attempt_self",
    )

    assert combined["status"] == "updated"
    assert combined["actual_strategy"] == "attempt_self"
    assert combined["strategy_unchanged"] is True
    assert combined["uses_post_outcome_information_for_policy"] is False
    assert combined["posterior_update_action"] == "attempt_self"


def test_combine_audits_marks_gated_lite_strategy_changed() -> None:
    _, pre_audit = compute_bayesian_policy_shadow(
        raw_memory={},
        mode="gated_lite",
        task_family=TASK_FAMILY,
        strategy_reference={"attempt_self": 1.0},
        max_delta=0.0,
    )
    _, update_audit = update_bayesian_policy_memory(
        raw_memory={},
        mode="gated_lite",
        task_family=TASK_FAMILY,
        actual_strategy="attempt_self",
        outcome_type="success_self",
    )

    combined = combine_bayesian_policy_audits(
        pre_audit=pre_audit,
        update_audit=update_audit,
        actual_strategy="attempt_self",
    )

    assert combined["mode"] == "gated_lite"
    assert combined["status"] == "updated"
    assert combined["strategy_unchanged"] is False
    assert combined["posterior_update_action"] == "attempt_self"
