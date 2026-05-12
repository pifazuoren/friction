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
