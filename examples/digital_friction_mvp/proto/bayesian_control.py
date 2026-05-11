from __future__ import annotations

import copy
from typing import Any

from .experience_memory import TASK_FAMILIES


BAYESIAN_CONTROL_VERSION = "beta_v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp_rho(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.98)))


def clamp_weight(value: Any) -> float:
    return max(0.0, _safe_float(value, 1.0))


def _default_family_state() -> dict[str, Any]:
    return {
        "alpha": 1.0,
        "beta": 1.0,
        "belief": 0.5,
        "last_evidence_z": None,
        "last_evidence_reason": "",
        "last_updated_day": -1,
        "update_count": 0,
    }


def build_initial_bayesian_control_memory() -> dict[str, dict[str, Any]]:
    return {task_family: _default_family_state() for task_family in TASK_FAMILIES}


def _normalize_family_state(raw_state: Any) -> dict[str, Any]:
    state = _default_family_state()
    if not isinstance(raw_state, dict):
        return state

    alpha = max(0.0, _safe_float(raw_state.get("alpha"), state["alpha"]))
    beta = max(0.0, _safe_float(raw_state.get("beta"), state["beta"]))
    denominator = alpha + beta
    if denominator <= 0.0:
        alpha = 1.0
        beta = 1.0
        belief = 0.5
    else:
        belief = alpha / denominator

    state.update(
        {
            "alpha": alpha,
            "beta": beta,
            "belief": belief,
            "last_evidence_z": (
                None
                if raw_state.get("last_evidence_z") is None
                else _safe_float(raw_state.get("last_evidence_z"), 0.5)
            ),
            "last_evidence_reason": str(
                raw_state.get("last_evidence_reason", "")
            ),
            "last_updated_day": _safe_int(raw_state.get("last_updated_day"), -1),
            "update_count": max(0, _safe_int(raw_state.get("update_count"), 0)),
        }
    )
    return state


def normalize_bayesian_control_memory(
    raw_memory: Any,
    *,
    task_family: str | None = None,
) -> dict[str, dict[str, Any]]:
    source = raw_memory if isinstance(raw_memory, dict) else {}
    families = list(TASK_FAMILIES)
    if task_family and task_family not in families:
        families.append(task_family)
    return {
        family: _normalize_family_state(source.get(family))
        for family in families
    }


def evidence_from_outcome(
    *,
    outcome_type: Any,
    support_mode: Any = "not_applicable",
    avoid_reason: Any = "not_applicable",
    event_level_uncontrollability: Any = 0,
) -> tuple[float, str]:
    outcome = str(outcome_type or "")
    support = str(support_mode or "not_applicable")
    avoid = str(avoid_reason or "not_applicable")
    uncontrollability = max(
        0,
        min(2, _safe_int(event_level_uncontrollability, 0)),
    )

    if outcome == "success_self":
        return 1.0, "success_self"
    if outcome == "success_with_help" and support == "enabling_support":
        return 0.75, "success_with_help_enabling_support"
    if outcome == "success_with_help" and support == "substituting_support":
        return 0.45, "success_with_help_substituting_support"
    if outcome == "failure_after_attempt":
        return (
            {0: 0.45, 1: 0.25, 2: 0.05}[uncontrollability],
            f"failure_after_attempt_uncontrollability_{uncontrollability}",
        )
    if outcome == "failure_even_with_help":
        return 0.0, "failure_even_with_help"
    if outcome == "abandon_midway":
        return 0.15, "abandon_midway"
    if outcome == "avoid_without_attempt" and avoid == "helpless_avoid":
        return 0.10, "avoid_without_attempt_helpless_avoid"
    if outcome == "avoid_without_attempt" and avoid == "risk_avoid":
        return 0.50, "avoid_without_attempt_risk_avoid"
    if outcome == "avoid_without_attempt" and avoid == "low_value_avoid":
        return 0.55, "avoid_without_attempt_low_value_avoid"
    return 0.50, "neutral_unknown"


def update_bayesian_control_memory(
    *,
    raw_memory: Any,
    enabled: bool,
    task_family: Any,
    outcome_type: Any,
    support_mode: Any = "not_applicable",
    avoid_reason: Any = "not_applicable",
    event_level_uncontrollability: Any = 0,
    uncontrollability_source: Any = "not_applicable",
    rho: Any = 0.98,
    weight: Any = 1.0,
    day: Any = -1,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not enabled:
        return copy.deepcopy(raw_memory if isinstance(raw_memory, dict) else {}), {
            "version": BAYESIAN_CONTROL_VERSION,
            "enabled": False,
            "status": "disabled",
        }

    family = str(task_family or "")
    memory = normalize_bayesian_control_memory(raw_memory, task_family=family)
    if not family:
        return memory, {
            "version": BAYESIAN_CONTROL_VERSION,
            "enabled": True,
            "status": "missing_task_family",
        }

    state_before = _normalize_family_state(memory.get(family))
    alpha_before = float(state_before["alpha"])
    beta_before = float(state_before["beta"])
    belief_before = float(state_before["belief"])
    evidence_z, evidence_reason = evidence_from_outcome(
        outcome_type=outcome_type,
        support_mode=support_mode,
        avoid_reason=avoid_reason,
        event_level_uncontrollability=event_level_uncontrollability,
    )
    bounded_rho = clamp_rho(rho)
    bounded_weight = clamp_weight(weight)
    if bounded_weight == 0.0:
        alpha_after = alpha_before
        beta_after = beta_before
    else:
        alpha_after = bounded_rho * alpha_before + bounded_weight * evidence_z
        beta_after = bounded_rho * beta_before + bounded_weight * (1.0 - evidence_z)
    denominator = alpha_after + beta_after
    belief_after = 0.5 if denominator <= 0.0 else alpha_after / denominator
    update_count_after = int(state_before["update_count"]) + 1
    updated_state = {
        "alpha": float(alpha_after),
        "beta": float(beta_after),
        "belief": float(belief_after),
        "last_evidence_z": float(evidence_z),
        "last_evidence_reason": evidence_reason,
        "last_updated_day": _safe_int(day, -1),
        "update_count": update_count_after,
    }
    memory[family] = updated_state
    audit = {
        "version": BAYESIAN_CONTROL_VERSION,
        "enabled": True,
        "status": "updated",
        "task_family": family,
        "outcome_type": str(outcome_type or ""),
        "support_mode": str(support_mode or "not_applicable"),
        "avoid_reason": str(avoid_reason or "not_applicable"),
        "event_level_uncontrollability": max(
            0,
            min(2, _safe_int(event_level_uncontrollability, 0)),
        ),
        "uncontrollability_source": str(uncontrollability_source or "not_applicable"),
        "alpha_before": alpha_before,
        "beta_before": beta_before,
        "belief_before": belief_before,
        "evidence_z": float(evidence_z),
        "evidence_reason": evidence_reason,
        "alpha_after": float(alpha_after),
        "beta_after": float(beta_after),
        "belief_after": float(belief_after),
        "last_evidence_z": float(evidence_z),
        "last_evidence_reason": evidence_reason,
        "last_updated_day": _safe_int(day, -1),
        "update_count_after": update_count_after,
        "rho": bounded_rho,
        "weight": bounded_weight,
        "day": _safe_int(day, -1),
    }
    return memory, audit
