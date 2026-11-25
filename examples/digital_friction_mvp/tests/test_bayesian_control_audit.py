from __future__ import annotations

import copy
import inspect

from proto.bayesian_control import (
    BAYESIAN_CONTROL_VERSION,
    build_initial_bayesian_control_memory,
    evidence_from_outcome,
    update_bayesian_control_memory,
)


TASK_FAMILY = "payment_risk_confirmation"


def test_success_self_raises_belief_from_prior() -> None:
    memory_after, audit = update_bayesian_control_memory(
        raw_memory={},
        enabled=True,
        task_family=TASK_FAMILY,
        outcome_type="success_self",
        day=3,
    )

    assert audit["version"] == BAYESIAN_CONTROL_VERSION
    assert audit["status"] == "updated"
    assert audit["belief_before"] == 0.5
    assert audit["evidence_z"] == 1.0
    assert audit["belief_after"] > 0.5
    assert memory_after[TASK_FAMILY]["belief"] == audit["belief_after"]


def test_high_uncontrollability_failure_lowers_belief_from_prior() -> None:
    memory_after, audit = update_bayesian_control_memory(
        raw_memory={},
        enabled=True,
        task_family=TASK_FAMILY,
        outcome_type="failure_after_attempt",
        event_level_uncontrollability=2,
        uncontrollability_source="hybrid",
        day=4,
    )

    assert audit["evidence_z"] == 0.05
    assert audit["evidence_reason"] == "failure_after_attempt_uncontrollability_2"
    assert audit["uncontrollability_source"] == "hybrid"
    assert audit["belief_after"] < 0.5
    assert memory_after[TASK_FAMILY]["last_evidence_z"] == 0.05


def test_risk_and_low_value_avoid_are_not_strong_uncontrollable_evidence() -> None:
    risk_z, risk_reason = evidence_from_outcome(
        outcome_type="avoid_without_attempt",
        avoid_reason="risk_avoid",
    )
    low_value_z, low_value_reason = evidence_from_outcome(
        outcome_type="avoid_without_attempt",
        avoid_reason="low_value_avoid",
    )

    assert risk_z == 0.50
    assert risk_reason == "avoid_without_attempt_risk_avoid"
    assert low_value_z == 0.55
    assert low_value_reason == "avoid_without_attempt_low_value_avoid"


def test_empty_or_malformed_memory_initializes_safely() -> None:
    memory_after, audit = update_bayesian_control_memory(
        raw_memory={TASK_FAMILY: {"alpha": -9, "beta": "bad"}},
        enabled=True,
        task_family=TASK_FAMILY,
        outcome_type="abandon_midway",
        day=2,
    )

    assert audit["alpha_before"] == 0.0
    assert audit["beta_before"] == 1.0
    assert 0.0 <= audit["belief_after"] <= 1.0
    assert set(build_initial_bayesian_control_memory()).issubset(memory_after)


def test_debug_fields_update_with_each_event() -> None:
    memory_after, audit = update_bayesian_control_memory(
        raw_memory={},
        enabled=True,
        task_family=TASK_FAMILY,
        outcome_type="failure_after_attempt",
        event_level_uncontrollability=1,
        day=7,
    )

    state = memory_after[TASK_FAMILY]
    assert state["last_evidence_z"] == 0.25
    assert state["last_evidence_reason"] == (
        "failure_after_attempt_uncontrollability_1"
    )
    assert state["last_updated_day"] == 7
    assert state["update_count"] == 1
    assert audit["update_count_after"] == 1


def test_weight_zero_records_audit_but_freezes_belief_values() -> None:
    raw_memory = {
        TASK_FAMILY: {
            "alpha": 3.0,
            "beta": 1.0,
            "belief": 0.75,
            "last_evidence_z": 1.0,
            "last_evidence_reason": "previous",
            "last_updated_day": 2,
            "update_count": 5,
        }
    }

    memory_after, audit = update_bayesian_control_memory(
        raw_memory=raw_memory,
        enabled=True,
        task_family=TASK_FAMILY,
        outcome_type="failure_even_with_help",
        rho=0.1,
        weight=0.0,
        day=8,
    )

    state = memory_after[TASK_FAMILY]
    assert audit["weight"] == 0.0
    assert state["alpha"] == 3.0
    assert state["beta"] == 1.0
    assert state["belief"] == 0.75
    assert state["last_evidence_z"] == 0.0
    assert state["update_count"] == 6


def test_disabled_returns_disabled_audit_without_updating_memory() -> None:
    raw_memory = {TASK_FAMILY: {"alpha": 2.0, "beta": 2.0, "belief": 0.5}}

    memory_after, audit = update_bayesian_control_memory(
        raw_memory=raw_memory,
        enabled=False,
        task_family=TASK_FAMILY,
        outcome_type="success_self",
    )

    assert audit == {
        "version": BAYESIAN_CONTROL_VERSION,
        "enabled": False,
        "status": "disabled",
    }
    assert memory_after == raw_memory


def test_helper_does_not_mutate_input_memory_in_place() -> None:
    raw_memory = build_initial_bayesian_control_memory()
    before = copy.deepcopy(raw_memory)

    update_bayesian_control_memory(
        raw_memory=raw_memory,
        enabled=True,
        task_family=TASK_FAMILY,
        outcome_type="success_self",
    )

    assert raw_memory == before


def test_helper_signature_excludes_main_mechanism_objects() -> None:
    parameters = set(inspect.signature(update_bayesian_control_memory).parameters)

    assert "helplessness_after" not in parameters
    assert "strategy_weights" not in parameters
    assert "task_domain_memory" not in parameters
    assert "scope_spillover_total" not in parameters
