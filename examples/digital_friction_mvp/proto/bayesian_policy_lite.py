from __future__ import annotations

import copy
import math
from typing import Any

from .experience_memory import TASK_FAMILIES


BAYESIAN_POLICY_LITE_VERSION = "policy_lite_shadow_v1"
POLICY_LITE_ACTIONS = (
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
)
POLICY_OUTCOME_SUBTYPES = (
    "success_self",
    "success_with_help",
    "failure_after_attempt_low_uncontrollability",
    "failure_after_attempt_mid_uncontrollability",
    "failure_after_attempt_high_uncontrollability",
    "failure_even_with_help",
    "abandon_midway",
    "no_attempt",
    "neutral_unknown",
)

_PLAUSIBLE_OUTCOMES_BY_ACTION = {
    "attempt_self": {
        "success_self",
        "failure_after_attempt_low_uncontrollability",
        "failure_after_attempt_mid_uncontrollability",
        "failure_after_attempt_high_uncontrollability",
        "abandon_midway",
    },
    "seek_help_then_attempt": {
        "success_with_help",
        "failure_even_with_help",
        "abandon_midway",
    },
    "avoid": {
        "no_attempt",
    },
}
_UNLIKELY_OUTCOMES = {"neutral_unknown"}
_BASE_OUTCOME_UTILITY = {
    "success_self": 1.0,
    "success_with_help": 0.75,
    "failure_after_attempt_low_uncontrollability": -0.25,
    "failure_after_attempt_mid_uncontrollability": -0.60,
    "failure_after_attempt_high_uncontrollability": -1.0,
    "failure_even_with_help": -0.90,
    "abandon_midway": -0.70,
    "no_attempt": -0.15,
    "neutral_unknown": 0.0,
}


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


def clamp_tau(value: Any) -> float:
    return max(0.000001, _safe_float(value, 1.0))


def clamp_confidence_k(value: Any) -> int:
    return max(1, _safe_int(value, 4))


def clamp_rho(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 1.0)))


def clamp_weight(value: Any) -> float:
    return max(0.0, _safe_float(value, 1.0))


def _prior_alpha_for(action: str, outcome_subtype: str) -> float:
    if outcome_subtype in _PLAUSIBLE_OUTCOMES_BY_ACTION.get(action, set()):
        return 1.0
    if outcome_subtype in _UNLIKELY_OUTCOMES:
        return 0.05
    return 0.01


def _default_action_state(action: str) -> dict[str, Any]:
    return {
        "alpha": {
            outcome: _prior_alpha_for(action, outcome)
            for outcome in POLICY_OUTCOME_SUBTYPES
        },
        "update_count": 0,
        "last_policy_outcome_subtype": "",
        "last_process_modifier": "",
        "last_psychological_interpretation": "",
        "last_updated_day": -1,
    }


def _default_family_state() -> dict[str, dict[str, Any]]:
    return {action: _default_action_state(action) for action in POLICY_LITE_ACTIONS}


def build_initial_bayesian_policy_memory() -> dict[str, Any]:
    return {
        "version": BAYESIAN_POLICY_LITE_VERSION,
        "families": {
            task_family: _default_family_state() for task_family in TASK_FAMILIES
        },
    }


def _normalize_alpha(raw_alpha: Any, *, action: str) -> dict[str, float]:
    source = raw_alpha if isinstance(raw_alpha, dict) else {}
    alpha: dict[str, float] = {}
    for outcome in POLICY_OUTCOME_SUBTYPES:
        default = _prior_alpha_for(action, outcome)
        alpha[outcome] = max(0.0, _safe_float(source.get(outcome), default))
    if sum(alpha.values()) <= 0.0:
        return {
            outcome: _prior_alpha_for(action, outcome)
            for outcome in POLICY_OUTCOME_SUBTYPES
        }
    return alpha


def _normalize_action_state(raw_state: Any, *, action: str) -> dict[str, Any]:
    state = _default_action_state(action)
    if not isinstance(raw_state, dict):
        return state
    state.update(
        {
            "alpha": _normalize_alpha(raw_state.get("alpha"), action=action),
            "update_count": max(0, _safe_int(raw_state.get("update_count"), 0)),
            "last_policy_outcome_subtype": str(
                raw_state.get("last_policy_outcome_subtype", "")
            ),
            "last_process_modifier": str(raw_state.get("last_process_modifier", "")),
            "last_psychological_interpretation": str(
                raw_state.get("last_psychological_interpretation", "")
            ),
            "last_updated_day": _safe_int(raw_state.get("last_updated_day"), -1),
        }
    )
    return state


def normalize_bayesian_policy_memory(
    raw_memory: Any,
    *,
    task_family: str | None = None,
) -> dict[str, Any]:
    source = raw_memory if isinstance(raw_memory, dict) else {}
    raw_families = source.get("families")
    families_source = raw_families if isinstance(raw_families, dict) else source
    families = list(TASK_FAMILIES)
    if task_family and task_family not in families:
        families.append(task_family)

    normalized_families: dict[str, Any] = {}
    for family in families:
        raw_family = families_source.get(family) if isinstance(families_source, dict) else {}
        raw_family = raw_family if isinstance(raw_family, dict) else {}
        normalized_families[family] = {
            action: _normalize_action_state(raw_family.get(action), action=action)
            for action in POLICY_LITE_ACTIONS
        }
    return {
        "version": BAYESIAN_POLICY_LITE_VERSION,
        "families": normalized_families,
    }


def _normalize_distribution(weights: Any) -> dict[str, float]:
    source = weights if isinstance(weights, dict) else {}
    clipped = {
        action: max(0.0, _safe_float(source.get(action), 0.0))
        for action in POLICY_LITE_ACTIONS
    }
    total = sum(clipped.values())
    if total <= 0.0:
        return {action: 1.0 / len(POLICY_LITE_ACTIONS) for action in POLICY_LITE_ACTIONS}
    return {action: clipped[action] / total for action in POLICY_LITE_ACTIONS}


def _posterior_predictive(
    action_state: dict[str, Any],
    *,
    action: str,
) -> dict[str, float]:
    alpha = _normalize_alpha(action_state.get("alpha"), action=action)
    total = sum(alpha.values())
    if total <= 0.0:
        return {outcome: 1.0 / len(POLICY_OUTCOME_SUBTYPES) for outcome in POLICY_OUTCOME_SUBTYPES}
    return {outcome: alpha[outcome] / total for outcome in POLICY_OUTCOME_SUBTYPES}


def compute_posterior_predictive_by_action(
    *,
    raw_memory: Any,
    task_family: Any,
) -> dict[str, dict[str, float]]:
    family = str(task_family or "")
    memory = normalize_bayesian_policy_memory(raw_memory, task_family=family)
    if not family:
        return {}
    family_state = memory["families"][family]
    return {
        action: _posterior_predictive(family_state[action], action=action)
        for action in POLICY_LITE_ACTIONS
    }


def _entropy(probabilities: dict[str, float]) -> float:
    entropy = 0.0
    for probability in probabilities.values():
        if probability > 0.0:
            entropy -= probability * math.log(probability)
    max_entropy = math.log(max(1, len(probabilities)))
    return 0.0 if max_entropy <= 0.0 else entropy / max_entropy


def classify_policy_outcome_subtype(
    *,
    outcome_type: Any,
    event_level_uncontrollability: Any = 0,
) -> str:
    outcome = str(outcome_type or "")
    uncontrollability = max(0, min(2, _safe_int(event_level_uncontrollability, 0)))
    if outcome == "success_self":
        return "success_self"
    if outcome == "success_with_help":
        return "success_with_help"
    if outcome == "failure_after_attempt":
        label = {0: "low", 1: "mid", 2: "high"}[uncontrollability]
        return f"failure_after_attempt_{label}_uncontrollability"
    if outcome == "failure_even_with_help":
        return "failure_even_with_help"
    if outcome == "abandon_midway":
        return "abandon_midway"
    if outcome == "avoid_without_attempt":
        return "no_attempt"
    return "neutral_unknown"


def classify_process_modifier(
    *,
    actual_strategy: Any,
    support_mode: Any = "not_applicable",
) -> str:
    support = str(support_mode or "not_applicable")
    if support and support != "not_applicable":
        return support
    strategy = str(actual_strategy or "")
    if strategy == "attempt_self":
        return "no_help"
    if strategy == "avoid":
        return "no_attempt"
    if strategy == "seek_help_then_attempt":
        return "support_used_unknown"
    return "not_applicable"


def classify_psychological_interpretation(
    *,
    avoid_reason: Any = "not_applicable",
    event_attribution_locus: Any = "not_applicable",
    event_attribution_stability: Any = "not_applicable",
    event_attribution_scope: Any = "not_applicable",
) -> str:
    avoid = str(avoid_reason or "not_applicable")
    if avoid != "not_applicable":
        return avoid
    locus = str(event_attribution_locus or "not_applicable")
    stability = str(event_attribution_stability or "not_applicable")
    scope = str(event_attribution_scope or "not_applicable")
    if {locus, stability, scope} == {"not_applicable"}:
        return "not_applicable"
    return f"locus={locus};stability={stability};scope={scope}"


def _context_value(task_appraisal: Any, key: str, default: float) -> float:
    if isinstance(task_appraisal, dict):
        return _safe_float(task_appraisal.get(key), default)
    return _safe_float(getattr(task_appraisal, key, default), default)


def _pre_outcome_utility(
    *,
    outcome_subtype: str,
    action: str,
    task_difficulty: Any = 0.5,
    env: Any = None,
    task_appraisal: Any = None,
) -> float:
    utility = float(_BASE_OUTCOME_UTILITY.get(outcome_subtype, 0.0))
    difficulty = max(0.0, min(1.0, _safe_float(task_difficulty, 0.5)))
    env_source = env if isinstance(env, dict) else {}
    risk_level = max(0.0, _safe_float(env_source.get("risk_level"), 0.0))
    support_available = (
        _safe_float(env_source.get("assist_level"), 0.0)
        + _safe_float(env_source.get("accessibility_level"), 0.0)
        + _safe_float(env_source.get("human_support_level"), 0.0)
    )
    expected_help_effectiveness = max(
        0.0,
        min(
            100.0,
            _context_value(task_appraisal, "expected_help_effectiveness", 50.0),
        ),
    )

    if outcome_subtype.startswith("failure_after_attempt"):
        utility -= 0.10 * difficulty
    if outcome_subtype == "success_with_help":
        utility += 0.12 * ((expected_help_effectiveness - 50.0) / 50.0)
        utility += 0.03 * min(3.0, support_available)
    if action == "avoid" and outcome_subtype == "no_attempt":
        utility += 0.04 * min(3.0, risk_level)
    return utility


def compute_q_bayes(
    *,
    family_state: dict[str, Any],
    task_difficulty: Any = 0.5,
    env: Any = None,
    task_appraisal: Any = None,
) -> dict[str, float]:
    q_values: dict[str, float] = {}
    for action in POLICY_LITE_ACTIONS:
        predictive = _posterior_predictive(family_state[action], action=action)
        q_values[action] = sum(
            probability
            * _pre_outcome_utility(
                outcome_subtype=outcome_subtype,
                action=action,
                task_difficulty=task_difficulty,
                env=env,
                task_appraisal=task_appraisal,
            )
            for outcome_subtype, probability in predictive.items()
        )
    return q_values


def softmax_policy(q_values: dict[str, float], *, tau: Any = 1.0) -> dict[str, float]:
    bounded_tau = clamp_tau(tau)
    scaled = {
        action: _safe_float(q_values.get(action), 0.0) / bounded_tau
        for action in POLICY_LITE_ACTIONS
    }
    max_value = max(scaled.values()) if scaled else 0.0
    exp_values = {
        action: math.exp(max(-700.0, min(700.0, value - max_value)))
        for action, value in scaled.items()
    }
    total = sum(exp_values.values())
    if total <= 0.0:
        return {action: 1.0 / len(POLICY_LITE_ACTIONS) for action in POLICY_LITE_ACTIONS}
    return {action: exp_values[action] / total for action in POLICY_LITE_ACTIONS}


def compute_bayesian_policy_shadow(
    *,
    raw_memory: Any,
    mode: Any,
    task_family: Any,
    strategy_reference: Any = None,
    task_difficulty: Any = 0.5,
    env: Any = None,
    task_appraisal: Any = None,
    tau: Any = 1.0,
    confidence_k: Any = 4,
    rho: Any = 1.0,
    weight: Any = 1.0,
    day: Any = -1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_mode = str(mode or "off").strip().lower()
    if normalized_mode != "shadow":
        return copy.deepcopy(raw_memory if isinstance(raw_memory, dict) else {}), {
            "version": BAYESIAN_POLICY_LITE_VERSION,
            "mode": normalized_mode,
            "enabled": False,
            "status": "disabled",
            "uses_post_outcome_information_for_policy": False,
            "strategy_unchanged": True,
        }

    family = str(task_family or "")
    memory = normalize_bayesian_policy_memory(raw_memory, task_family=family)
    if not family:
        return memory, {
            "version": BAYESIAN_POLICY_LITE_VERSION,
            "mode": "shadow",
            "enabled": True,
            "status": "missing_task_family",
            "uses_post_outcome_information_for_policy": False,
            "strategy_unchanged": True,
        }

    family_state = memory["families"][family]
    predictive_by_action = {
        action: _posterior_predictive(family_state[action], action=action)
        for action in POLICY_LITE_ACTIONS
    }
    q_bayes = compute_q_bayes(
        family_state=family_state,
        task_difficulty=task_difficulty,
        env=env,
        task_appraisal=task_appraisal,
    )
    pi_bayes_shadow = softmax_policy(q_bayes, tau=tau)
    bounded_k = clamp_confidence_k(confidence_k)
    update_counts = {
        action: int(family_state[action]["update_count"])
        for action in POLICY_LITE_ACTIONS
    }
    alpha_total_by_action = {
        action: float(sum(family_state[action]["alpha"].values()))
        for action in POLICY_LITE_ACTIONS
    }
    audit = {
        "version": BAYESIAN_POLICY_LITE_VERSION,
        "mode": "shadow",
        "enabled": True,
        "status": "computed",
        "task_family": family,
        "actual_strategy": "",
        "pre_update": True,
        "uses_post_outcome_information_for_policy": False,
        "pi_prior": {
            action: 1.0 / len(POLICY_LITE_ACTIONS)
            for action in POLICY_LITE_ACTIONS
        },
        "pi_strategy_reference": _normalize_distribution(strategy_reference),
        "q_bayes": q_bayes,
        "pi_bayes_shadow": pi_bayes_shadow,
        "confidence_by_action": {
            action: update_counts[action] / (update_counts[action] + bounded_k)
            for action in POLICY_LITE_ACTIONS
        },
        "alpha_total_by_action": alpha_total_by_action,
        "posterior_entropy_by_action": {
            action: _entropy(predictive_by_action[action])
            for action in POLICY_LITE_ACTIONS
        },
        "posterior_update_count_before": update_counts,
        "posterior_update_count_after": copy.deepcopy(update_counts),
        "posterior_update_action": "",
        "policy_outcome_subtype": "",
        "process_modifier": "",
        "psychological_interpretation": "",
        "strategy_unchanged": True,
        "tau": clamp_tau(tau),
        "rho": clamp_rho(rho),
        "weight": clamp_weight(weight),
        "confidence_k": bounded_k,
        "day": _safe_int(day, -1),
    }
    return memory, audit


def update_bayesian_policy_memory(
    *,
    raw_memory: Any,
    mode: Any,
    task_family: Any,
    actual_strategy: Any,
    outcome_type: Any,
    event_level_uncontrollability: Any = 0,
    support_mode: Any = "not_applicable",
    avoid_reason: Any = "not_applicable",
    event_attribution_locus: Any = "not_applicable",
    event_attribution_stability: Any = "not_applicable",
    event_attribution_scope: Any = "not_applicable",
    rho: Any = 1.0,
    weight: Any = 1.0,
    day: Any = -1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_mode = str(mode or "off").strip().lower()
    if normalized_mode != "shadow":
        return copy.deepcopy(raw_memory if isinstance(raw_memory, dict) else {}), {
            "version": BAYESIAN_POLICY_LITE_VERSION,
            "mode": normalized_mode,
            "enabled": False,
            "status": "disabled",
        }

    family = str(task_family or "")
    action = str(actual_strategy or "")
    memory = normalize_bayesian_policy_memory(raw_memory, task_family=family)
    if not family:
        return memory, {
            "version": BAYESIAN_POLICY_LITE_VERSION,
            "mode": "shadow",
            "enabled": True,
            "status": "missing_task_family",
        }
    if action not in POLICY_LITE_ACTIONS:
        return memory, {
            "version": BAYESIAN_POLICY_LITE_VERSION,
            "mode": "shadow",
            "enabled": True,
            "status": "unsupported_action",
            "posterior_update_action": action,
        }

    family_state = memory["families"][family]
    action_state_before = _normalize_action_state(family_state[action], action=action)
    alpha_before = copy.deepcopy(action_state_before["alpha"])
    update_counts_before = {
        policy_action: int(family_state[policy_action]["update_count"])
        for policy_action in POLICY_LITE_ACTIONS
    }
    subtype = classify_policy_outcome_subtype(
        outcome_type=outcome_type,
        event_level_uncontrollability=event_level_uncontrollability,
    )
    process_modifier = classify_process_modifier(
        actual_strategy=action,
        support_mode=support_mode,
    )
    psychological_interpretation = classify_psychological_interpretation(
        avoid_reason=avoid_reason,
        event_attribution_locus=event_attribution_locus,
        event_attribution_stability=event_attribution_stability,
        event_attribution_scope=event_attribution_scope,
    )
    bounded_rho = clamp_rho(rho)
    bounded_weight = clamp_weight(weight)
    if bounded_weight == 0.0:
        alpha_after = copy.deepcopy(alpha_before)
        update_count_after = int(action_state_before["update_count"])
    else:
        alpha_after = {
            outcome: bounded_rho * float(alpha_before[outcome])
            for outcome in POLICY_OUTCOME_SUBTYPES
        }
        alpha_after[subtype] = float(alpha_after.get(subtype, 0.0)) + bounded_weight
        update_count_after = int(action_state_before["update_count"]) + 1

    family_state[action] = {
        "alpha": alpha_after,
        "update_count": update_count_after,
        "last_policy_outcome_subtype": subtype,
        "last_process_modifier": process_modifier,
        "last_psychological_interpretation": psychological_interpretation,
        "last_updated_day": _safe_int(day, -1),
    }
    update_counts_after = {
        policy_action: int(family_state[policy_action]["update_count"])
        for policy_action in POLICY_LITE_ACTIONS
    }
    memory["families"][family] = family_state
    return memory, {
        "version": BAYESIAN_POLICY_LITE_VERSION,
        "mode": "shadow",
        "enabled": True,
        "status": "updated",
        "task_family": family,
        "posterior_update_action": action,
        "policy_outcome_subtype": subtype,
        "process_modifier": process_modifier,
        "psychological_interpretation": psychological_interpretation,
        "posterior_update_count_before": update_counts_before,
        "posterior_update_count_after": update_counts_after,
        "alpha_before_for_update_action": alpha_before,
        "alpha_after_for_update_action": alpha_after,
        "rho": bounded_rho,
        "weight": bounded_weight,
        "day": _safe_int(day, -1),
    }


def combine_bayesian_policy_audits(
    *,
    pre_audit: Any,
    update_audit: Any,
    actual_strategy: Any,
) -> dict[str, Any]:
    combined = copy.deepcopy(pre_audit if isinstance(pre_audit, dict) else {})
    update = update_audit if isinstance(update_audit, dict) else {}
    if not combined:
        combined = {
            "version": BAYESIAN_POLICY_LITE_VERSION,
            "mode": str(update.get("mode", "off")),
            "status": str(update.get("status", "missing_pre_audit")),
        }
    combined["actual_strategy"] = str(actual_strategy or "")
    combined["strategy_unchanged"] = True
    combined["uses_post_outcome_information_for_policy"] = False
    combined["posterior_update_status"] = str(update.get("status", "not_called"))
    for key in (
        "posterior_update_action",
        "policy_outcome_subtype",
        "process_modifier",
        "psychological_interpretation",
        "posterior_update_count_after",
    ):
        if key in update:
            combined[key] = copy.deepcopy(update[key])
    if combined.get("status") == "computed" and update.get("status") == "updated":
        combined["status"] = "updated"
    return combined
