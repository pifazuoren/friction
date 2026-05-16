from __future__ import annotations

import copy
import math
from typing import Any

from .bayesian_policy_lite import (
    DEFAULT_POLICY_LITE_PROB_FLOOR,
    POLICY_LITE_ACTIONS,
    POLICY_OUTCOME_SUBTYPES,
    compute_posterior_predictive_by_action,
    normalize_bayesian_policy_memory,
    normalize_utility_profile,
    outcome_utility_profile,
)


HUYS_DAYAN_LITE_VERSION = "huys_dayan_lite_controllability_v1"
ACTIVE_HUYS_DAYAN_LITE_MODES = {"shadow", "gated_modulate"}
CONTROL_RELEVANT_ACTIONS = ("attempt_self", "seek_help_then_attempt")
DEFAULT_HUYS_DAYAN_LITE_CONFIDENCE_K = 6
DEFAULT_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES = 2
DEFAULT_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT = 0.05
DEFAULT_HUYS_DAYAN_LITE_RHO = 1.0
DEFAULT_HUYS_DAYAN_LITE_WEIGHT_ENTROPY = 0.25
DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CONTRAST = 0.25
DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CHI = 0.50
DEFAULT_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD = 0.50
DEFAULT_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA = 0.10
DEFAULT_HUYS_DAYAN_LITE_LOW_C_THRESHOLD = 0.45
DEFAULT_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD = 0.60

PLAUSIBLE_OUTCOMES_BY_ACTION = {
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

OUTCOME_BIN_BY_SUBTYPE = {
    "success_self": "success",
    "success_with_help": "success",
    "failure_after_attempt_low_uncontrollability": "controllable_failure",
    "failure_after_attempt_mid_uncontrollability": "uncontrollable_failure",
    "failure_after_attempt_high_uncontrollability": "uncontrollable_failure",
    "failure_even_with_help": "uncontrollable_failure",
    "abandon_midway": "dropout",
    "no_attempt": "no_task_evidence",
    "neutral_unknown": "unknown",
}
OUTCOME_BINS = (
    "success",
    "controllable_failure",
    "uncontrollable_failure",
    "dropout",
    "no_task_evidence",
    "unknown",
)
_POST_OUTCOME_FIELD_NAMES = {
    "support_mode",
    "avoid_reason",
    "outcome_type",
    "actual_outcome",
    "event_attribution_locus",
    "event_attribution_stability",
    "event_attribution_scope",
    "event_attribution_scope_amplitude",
    "post_outcome_uncontrollability",
    "event_level_uncontrollability",
    "helplessness_after",
    "self_efficacy_after",
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


def clamp_confidence_k(value: Any) -> int:
    return max(1, _safe_int(value, DEFAULT_HUYS_DAYAN_LITE_CONFIDENCE_K))


def clamp_min_action_updates(value: Any) -> int:
    return max(0, _safe_int(value, DEFAULT_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES))


def clamp_ratio(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _safe_float(value, default)))


def clamp_nonnegative(value: Any, default: float = 0.0) -> float:
    return max(0.0, _safe_float(value, default))


def clamp_modulation_max_delta(value: Any) -> float:
    return clamp_ratio(value, DEFAULT_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA)


def clamp_prob_floor(value: Any) -> float:
    return max(
        0.0,
        min(
            (1.0 / len(POLICY_LITE_ACTIONS)) - 0.000001,
            _safe_float(value, DEFAULT_POLICY_LITE_PROB_FLOOR),
        ),
    )


def normalize_controllability_mode(value: Any) -> str:
    mode = str(value or "off").strip().lower()
    if mode not in {"off", "shadow", "gated_modulate"}:
        raise ValueError(
            "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE must be one of: "
            "off, shadow, gated_modulate"
        )
    return mode


def normalize_metric_weights(
    *,
    weight_entropy: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_ENTROPY,
    weight_contrast: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CONTRAST,
    weight_chi: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CHI,
) -> dict[str, float]:
    raw = {
        "entropy": clamp_nonnegative(
            weight_entropy,
            DEFAULT_HUYS_DAYAN_LITE_WEIGHT_ENTROPY,
        ),
        "contrast": clamp_nonnegative(
            weight_contrast,
            DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CONTRAST,
        ),
        "chi": clamp_nonnegative(weight_chi, DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CHI),
    }
    total = sum(raw.values())
    if total <= 0.0 or not math.isfinite(total):
        return {"entropy": 0.25, "contrast": 0.25, "chi": 0.50}
    return {key: value / total for key, value in raw.items()}


def build_initial_controllability_lite_memory() -> dict[str, Any]:
    return {
        "version": HUYS_DAYAN_LITE_VERSION,
        "mode": "off",
        "global": {
            "global_controllability_trace": 0.5,
            "confidence": 0.0,
            "evidence_count": 0,
            "last_updated_day": -1,
        },
        "families": {},
    }


def _default_family_state() -> dict[str, Any]:
    return {
        "raw_c_family": 0.5,
        "shrunk_c_family": 0.5,
        "family_confidence": 0.0,
        "entropy_control": 0.5,
        "action_contrast_control": 0.5,
        "reward_control_chi_lite": 0.5,
        "reward_achievability": 0.5,
        "reward_action_gain": 0.0,
        "effective_action_count": 0,
        "min_control_action_updates": 0,
        "harmonic_control_action_updates": 0.0,
        "last_updated_day": -1,
    }


def normalize_controllability_lite_memory(
    raw_memory: Any,
    *,
    task_family: Any = "",
) -> dict[str, Any]:
    source = copy.deepcopy(raw_memory) if isinstance(raw_memory, dict) else {}
    memory = build_initial_controllability_lite_memory()
    global_source = source.get("global") if isinstance(source.get("global"), dict) else {}
    memory["global"] = {
        "global_controllability_trace": clamp_ratio(
            global_source.get("global_controllability_trace"),
            0.5,
        ),
        "confidence": clamp_ratio(global_source.get("confidence"), 0.0),
        "evidence_count": max(0, _safe_int(global_source.get("evidence_count"), 0)),
        "last_updated_day": _safe_int(global_source.get("last_updated_day"), -1),
    }
    families_source = source.get("families") if isinstance(source.get("families"), dict) else {}
    families: dict[str, Any] = {}
    for family, family_state in families_source.items():
        if not isinstance(family_state, dict):
            continue
        default_state = _default_family_state()
        default_state.update(
            {
                "raw_c_family": clamp_ratio(family_state.get("raw_c_family"), 0.5),
                "shrunk_c_family": clamp_ratio(
                    family_state.get("shrunk_c_family"),
                    0.5,
                ),
                "family_confidence": clamp_ratio(
                    family_state.get("family_confidence"),
                    0.0,
                ),
                "entropy_control": clamp_ratio(
                    family_state.get("entropy_control"),
                    0.5,
                ),
                "action_contrast_control": clamp_ratio(
                    family_state.get("action_contrast_control"),
                    0.5,
                ),
                "reward_control_chi_lite": clamp_ratio(
                    family_state.get("reward_control_chi_lite"),
                    0.5,
                ),
                "reward_achievability": clamp_ratio(
                    family_state.get("reward_achievability"),
                    0.5,
                ),
                "reward_action_gain": clamp_ratio(
                    family_state.get("reward_action_gain"),
                    0.0,
                ),
                "effective_action_count": max(
                    0,
                    _safe_int(family_state.get("effective_action_count"), 0),
                ),
                "min_control_action_updates": max(
                    0,
                    _safe_int(family_state.get("min_control_action_updates"), 0),
                ),
                "harmonic_control_action_updates": clamp_nonnegative(
                    family_state.get("harmonic_control_action_updates"),
                    0.0,
                ),
                "last_updated_day": _safe_int(
                    family_state.get("last_updated_day"),
                    -1,
                ),
            }
        )
        families[str(family)] = default_state
    family_key = str(task_family or "")
    if family_key and family_key not in families:
        families[family_key] = _default_family_state()
    memory["families"] = families
    return memory


def _normalize_distribution(
    weights: Any,
    *,
    floor: Any = None,
) -> dict[str, float]:
    bounded_floor = None if floor is None else clamp_prob_floor(floor)
    if not isinstance(weights, dict):
        source = {action: 1.0 / len(POLICY_LITE_ACTIONS) for action in POLICY_LITE_ACTIONS}
    else:
        source = {
            action: max(0.0, _safe_float(weights.get(action), 0.0))
            for action in POLICY_LITE_ACTIONS
        }
    if bounded_floor is not None:
        source = {action: max(bounded_floor, value) for action, value in source.items()}
    total = sum(source.values())
    if total <= 0.0 or not math.isfinite(total):
        return {action: 1.0 / len(POLICY_LITE_ACTIONS) for action in POLICY_LITE_ACTIONS}
    return {action: source[action] / total for action in POLICY_LITE_ACTIONS}


def _distribution_delta(
    left: dict[str, float],
    right: dict[str, float],
) -> dict[str, float]:
    return {
        action: _safe_float(left.get(action), 0.0) - _safe_float(right.get(action), 0.0)
        for action in POLICY_LITE_ACTIONS
    }


def _total_variation_distance(
    left: dict[str, float],
    right: dict[str, float],
) -> float:
    return 0.5 * sum(abs(value) for value in _distribution_delta(left, right).values())


def _renormalize_subset(
    probabilities: dict[str, Any],
    outcomes: set[str],
) -> dict[str, float]:
    subset = {
        outcome: max(0.0, _safe_float(probabilities.get(outcome), 0.0))
        for outcome in outcomes
    }
    total = sum(subset.values())
    if total <= 0.0 or not math.isfinite(total):
        value = 1.0 / max(1, len(outcomes))
        return {outcome: value for outcome in outcomes}
    return {outcome: subset[outcome] / total for outcome in outcomes}


def _entropy(probabilities: dict[str, float]) -> float:
    entropy = 0.0
    for probability in probabilities.values():
        if probability > 0.0:
            entropy -= probability * math.log(probability)
    max_entropy = math.log(max(1, len(probabilities)))
    return 0.0 if max_entropy <= 0.0 else entropy / max_entropy


def _post_outcome_fields_present(
    *,
    env: Any = None,
    task_appraisal: Any = None,
) -> list[str]:
    fields: list[str] = []
    for payload in (env, task_appraisal):
        if not isinstance(payload, dict):
            continue
        for key in _POST_OUTCOME_FIELD_NAMES:
            if key in payload:
                fields.append(key)
    return sorted(set(fields))


def _control_actions(*, use_avoid_in_main_score: Any = False) -> tuple[str, ...]:
    if bool(use_avoid_in_main_score):
        return POLICY_LITE_ACTIONS
    return CONTROL_RELEVANT_ACTIONS


def _coarse_posterior(
    predictive: dict[str, float],
) -> dict[str, float]:
    bins = {bin_name: 0.0 for bin_name in OUTCOME_BINS}
    for outcome, probability in predictive.items():
        bin_name = OUTCOME_BIN_BY_SUBTYPE.get(outcome, "unknown")
        bins[bin_name] += max(0.0, _safe_float(probability, 0.0))
    total = sum(bins.values())
    if total <= 0.0 or not math.isfinite(total):
        return {bin_name: 1.0 / len(OUTCOME_BINS) for bin_name in OUTCOME_BINS}
    return {bin_name: value / total for bin_name, value in bins.items()}


def _tvd(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys)


def _utility_norm(profile: Any) -> dict[str, float]:
    utility = outcome_utility_profile(normalize_utility_profile(profile))
    values = [float(utility.get(outcome, 0.0)) for outcome in POLICY_OUTCOME_SUBTYPES]
    min_value = min(values) if values else 0.0
    max_value = max(values) if values else 1.0
    span = max(max_value - min_value, 1e-9)
    return {
        outcome: (float(utility.get(outcome, 0.0)) - min_value) / span
        for outcome in POLICY_OUTCOME_SUBTYPES
    }


def compute_family_controllability_diagnostic(
    *,
    raw_policy_memory: Any,
    task_family: Any,
    confidence_k: Any = DEFAULT_HUYS_DAYAN_LITE_CONFIDENCE_K,
    min_action_updates: Any = DEFAULT_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES,
    use_avoid_in_main_score: Any = False,
    weight_entropy: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_ENTROPY,
    weight_contrast: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CONTRAST,
    weight_chi: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CHI,
    utility_profile: Any = "theory_v2",
) -> dict[str, Any]:
    family = str(task_family or "")
    bounded_k = clamp_confidence_k(confidence_k)
    min_updates = clamp_min_action_updates(min_action_updates)
    policy_memory = normalize_bayesian_policy_memory(
        raw_policy_memory,
        task_family=family,
    )
    if not family:
        return {
            "status": "missing_task_family",
            "task_family": "",
            "raw_c_family": 0.5,
            "shrunk_c_family": 0.5,
            "family_confidence": 0.0,
        }

    family_state = policy_memory["families"][family]
    predictive_by_action = compute_posterior_predictive_by_action(
        raw_memory=policy_memory,
        task_family=family,
    )
    actions = _control_actions(use_avoid_in_main_score=use_avoid_in_main_score)
    update_counts = {
        action: int(family_state[action]["update_count"])
        for action in POLICY_LITE_ACTIONS
    }
    confidence_by_action = {
        action: update_counts[action] / (update_counts[action] + bounded_k)
        for action in POLICY_LITE_ACTIONS
    }
    entropy_by_action: dict[str, float] = {}
    for action in actions:
        plausible = PLAUSIBLE_OUTCOMES_BY_ACTION.get(action, set(POLICY_OUTCOME_SUBTYPES))
        subset = _renormalize_subset(predictive_by_action[action], plausible)
        entropy_by_action[action] = 1.0 - _entropy(subset)
    entropy_weights = [confidence_by_action[action] for action in actions]
    entropy_total = sum(entropy_weights)
    entropy_control = (
        sum(
            entropy_by_action[action] * confidence_by_action[action]
            for action in actions
        )
        / entropy_total
        if entropy_total > 0.0
        else 0.5
    )

    coarse_by_action = {
        action: _coarse_posterior(predictive_by_action[action])
        for action in POLICY_LITE_ACTIONS
    }
    coverage = sum(1 for action in actions if update_counts[action] >= min_updates) / max(
        1,
        len(actions),
    )
    n_attempt = update_counts.get("attempt_self", 0)
    n_help = update_counts.get("seek_help_then_attempt", 0)
    n_eff = 2.0 * n_attempt * n_help / (n_attempt + n_help + 1e-9)
    family_confidence = coverage * n_eff / (n_eff + bounded_k)
    if len(actions) < 2 or coverage < 1.0:
        action_contrast = 0.5
        contrast_status = "insufficient_balanced_evidence"
    else:
        pair_values: list[float] = []
        for i, left_action in enumerate(actions):
            for right_action in actions[i + 1 :]:
                pair_values.append(
                    _tvd(coarse_by_action[left_action], coarse_by_action[right_action])
                )
        action_contrast = sum(pair_values) / len(pair_values) if pair_values else 0.5
        contrast_status = "ok"

    utility_norm = _utility_norm(utility_profile)
    reward_value_by_action: dict[str, float] = {}
    for action in actions:
        reward_value_by_action[action] = sum(
            max(0.0, _safe_float(probability, 0.0))
            * utility_norm.get(outcome, 0.0)
            for outcome, probability in predictive_by_action[action].items()
        )
    reward_values = list(reward_value_by_action.values())
    reward_achievability = max(reward_values) if reward_values else 0.5
    reward_action_gain = (
        max(reward_values) - min(reward_values)
        if len(reward_values) >= 2
        else 0.0
    )
    reward_control_chi_lite = (
        0.70 * reward_achievability + 0.30 * reward_action_gain
    )
    weights = normalize_metric_weights(
        weight_entropy=weight_entropy,
        weight_contrast=weight_contrast,
        weight_chi=weight_chi,
    )
    raw_c_family = (
        weights["entropy"] * entropy_control
        + weights["contrast"] * action_contrast
        + weights["chi"] * reward_control_chi_lite
    )
    shrunk_c_family = family_confidence * raw_c_family + (1.0 - family_confidence) * 0.5
    min_control_updates = min(update_counts[action] for action in actions) if actions else 0
    harmonic_updates = n_eff if len(actions) == 2 else 0.0
    effective_action_count = sum(1 for action in actions if update_counts[action] >= min_updates)

    return {
        "status": "computed",
        "task_family": family,
        "control_relevant_actions": list(actions),
        "excluded_actions": (
            {}
            if bool(use_avoid_in_main_score)
            else {
                "avoid": (
                    "no_attempt is behavioral avoidance, not task "
                    "controllability evidence"
                )
            }
        ),
        "update_counts_by_action": update_counts,
        "confidence_by_action": confidence_by_action,
        "entropy_control_by_action": entropy_by_action,
        "entropy_control": clamp_ratio(entropy_control, 0.5),
        "coarse_posterior_by_action": coarse_by_action,
        "action_contrast_control": clamp_ratio(action_contrast, 0.5),
        "action_contrast_status": contrast_status,
        "reward_value_by_action": reward_value_by_action,
        "reward_achievability": clamp_ratio(reward_achievability, 0.5),
        "reward_action_gain": clamp_ratio(reward_action_gain, 0.0),
        "reward_control_chi_lite": clamp_ratio(reward_control_chi_lite, 0.5),
        "raw_c_family": clamp_ratio(raw_c_family, 0.5),
        "family_confidence": clamp_ratio(family_confidence, 0.0),
        "shrunk_c_family": clamp_ratio(shrunk_c_family, 0.5),
        "effective_action_count": effective_action_count,
        "min_control_action_updates": min_control_updates,
        "harmonic_control_action_updates": harmonic_updates,
        "metric_weights": weights,
        "utility_profile": normalize_utility_profile(utility_profile),
    }


def compute_huys_dayan_lite_before_event_audit(
    *,
    raw_policy_memory: Any,
    raw_controllability_memory: Any,
    mode: Any,
    task_family: Any,
    confidence_k: Any = DEFAULT_HUYS_DAYAN_LITE_CONFIDENCE_K,
    min_action_updates: Any = DEFAULT_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES,
    use_avoid_in_main_score: Any = False,
    weight_entropy: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_ENTROPY,
    weight_contrast: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CONTRAST,
    weight_chi: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CHI,
    utility_profile: Any = "theory_v2",
    day: Any = -1,
    env: Any = None,
    task_appraisal: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_mode = normalize_controllability_mode(mode)
    family = str(task_family or "")
    memory = normalize_controllability_lite_memory(
        raw_controllability_memory,
        task_family=family,
    )
    if normalized_mode not in ACTIVE_HUYS_DAYAN_LITE_MODES:
        return memory, {
            "version": HUYS_DAYAN_LITE_VERSION,
            "mode": normalized_mode,
            "enabled": False,
            "status": "disabled",
            "uses_post_outcome_information_for_controllability_policy": False,
            "policy_unchanged": True,
        }
    diagnostic = compute_family_controllability_diagnostic(
        raw_policy_memory=raw_policy_memory,
        task_family=family,
        confidence_k=confidence_k,
        min_action_updates=min_action_updates,
        use_avoid_in_main_score=use_avoid_in_main_score,
        weight_entropy=weight_entropy,
        weight_contrast=weight_contrast,
        weight_chi=weight_chi,
        utility_profile=utility_profile,
    )
    return memory, {
        "version": HUYS_DAYAN_LITE_VERSION,
        "mode": normalized_mode,
        "enabled": True,
        "status": diagnostic.get("status", "computed"),
        "task_family": family,
        "day": _safe_int(day, -1),
        "pre_update": True,
        "uses_post_outcome_information_for_controllability_policy": False,
        "post_outcome_fields_ignored_for_controllability": _post_outcome_fields_present(
            env=env,
            task_appraisal=task_appraisal,
        ),
        "policy_unchanged": True,
        "state_unchanged": True,
        "outcome_unchanged": True,
        "before_event": {
            **diagnostic,
            "pre_update": True,
            "global_controllability_trace": memory["global"][
                "global_controllability_trace"
            ],
        },
    }


def _family_state_from_diagnostic(
    diagnostic: dict[str, Any],
    *,
    day: Any,
) -> dict[str, Any]:
    state = _default_family_state()
    for key in state:
        if key in diagnostic:
            state[key] = diagnostic[key]
    state["last_updated_day"] = _safe_int(day, -1)
    return state


def update_controllability_lite_shadow_memory(
    *,
    raw_memory: Any,
    diagnostic: dict[str, Any],
    mode: Any,
    global_update_weight: Any = DEFAULT_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT,
    rho: Any = DEFAULT_HUYS_DAYAN_LITE_RHO,
    day: Any = -1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_mode = normalize_controllability_mode(mode)
    family = str(diagnostic.get("task_family") or "")
    memory = normalize_controllability_lite_memory(raw_memory, task_family=family)
    if normalized_mode not in ACTIVE_HUYS_DAYAN_LITE_MODES:
        return memory, {"status": "disabled", "would_update_global": False}
    if not family:
        return memory, {"status": "missing_task_family", "would_update_global": False}
    family_confidence = clamp_ratio(diagnostic.get("family_confidence"), 0.0)
    c_family = clamp_ratio(diagnostic.get("shrunk_c_family"), 0.5)
    memory["families"][family] = _family_state_from_diagnostic(diagnostic, day=day)
    previous_trace = clamp_ratio(
        memory["global"].get("global_controllability_trace"),
        0.5,
    )
    bounded_weight = clamp_ratio(global_update_weight, DEFAULT_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT)
    bounded_rho = clamp_ratio(rho, DEFAULT_HUYS_DAYAN_LITE_RHO)
    would_update_global = family_confidence >= 0.50
    if would_update_global:
        w = bounded_weight * family_confidence
        decayed_previous = bounded_rho * previous_trace + (1.0 - bounded_rho) * 0.5
        new_trace = (1.0 - w) * decayed_previous + w * c_family
        memory["global"]["global_controllability_trace"] = clamp_ratio(new_trace, 0.5)
        memory["global"]["confidence"] = family_confidence
        memory["global"]["evidence_count"] = max(
            0,
            _safe_int(memory["global"].get("evidence_count"), 0),
        ) + 1
        memory["global"]["last_updated_day"] = _safe_int(day, -1)
        reason = "updated"
    else:
        reason = "family_confidence_below_threshold"
    return memory, {
        "status": "updated",
        "would_update_global": would_update_global,
        "global_update_reason": reason,
        "global_controllability_trace_before": previous_trace,
        "global_controllability_trace_after": memory["global"][
            "global_controllability_trace"
        ],
    }


def compute_huys_dayan_lite_after_event_audit(
    *,
    raw_policy_memory: Any,
    raw_controllability_memory: Any,
    mode: Any,
    task_family: Any,
    confidence_k: Any = DEFAULT_HUYS_DAYAN_LITE_CONFIDENCE_K,
    min_action_updates: Any = DEFAULT_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES,
    use_avoid_in_main_score: Any = False,
    weight_entropy: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_ENTROPY,
    weight_contrast: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CONTRAST,
    weight_chi: Any = DEFAULT_HUYS_DAYAN_LITE_WEIGHT_CHI,
    utility_profile: Any = "theory_v2",
    global_update_weight: Any = DEFAULT_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT,
    rho: Any = DEFAULT_HUYS_DAYAN_LITE_RHO,
    day: Any = -1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_mode = normalize_controllability_mode(mode)
    memory = normalize_controllability_lite_memory(
        raw_controllability_memory,
        task_family=task_family,
    )
    if normalized_mode not in ACTIVE_HUYS_DAYAN_LITE_MODES:
        return memory, {
            "status": "disabled",
            "enabled": False,
            "after_event": {"post_update": True, "post_update_memory_status": "disabled"},
        }
    diagnostic = compute_family_controllability_diagnostic(
        raw_policy_memory=raw_policy_memory,
        task_family=task_family,
        confidence_k=confidence_k,
        min_action_updates=min_action_updates,
        use_avoid_in_main_score=use_avoid_in_main_score,
        weight_entropy=weight_entropy,
        weight_contrast=weight_contrast,
        weight_chi=weight_chi,
        utility_profile=utility_profile,
    )
    updated_memory, update_audit = update_controllability_lite_shadow_memory(
        raw_memory=memory,
        diagnostic=diagnostic,
        mode=normalized_mode,
        global_update_weight=global_update_weight,
        rho=rho,
        day=day,
    )
    return updated_memory, {
        "status": update_audit.get("status", "updated"),
        "enabled": True,
        "after_event": {
            **diagnostic,
            "post_update": True,
            "post_update_memory_status": update_audit.get("status", "updated"),
            "global_controllability_trace_before": update_audit.get(
                "global_controllability_trace_before",
                memory["global"]["global_controllability_trace"],
            ),
            "global_controllability_trace_after": update_audit.get(
                "global_controllability_trace_after",
                updated_memory["global"]["global_controllability_trace"],
            ),
            "would_update_global": update_audit.get("would_update_global", False),
            "global_update_reason": update_audit.get("global_update_reason", ""),
        },
    }


def _best_nonavoid_from(
    *,
    pi_base: dict[str, float] | None,
    q_bayes: Any = None,
) -> tuple[str, str]:
    nonavoid = ("attempt_self", "seek_help_then_attempt")
    if pi_base:
        return max(nonavoid, key=lambda action: pi_base.get(action, 0.0)), "phase4_pi_final"
    if isinstance(q_bayes, dict):
        values = {
            action: _safe_float(q_bayes.get(action), float("-inf"))
            for action in nonavoid
        }
        if all(math.isfinite(value) for value in values.values()):
            return max(nonavoid, key=lambda action: values[action]), "q_bayes"
    return "", "unavailable"


def apply_controllability_gated_modulation(
    *,
    mode: Any,
    pi_base: Any,
    q_bayes: Any = None,
    before_event_audit: Any = None,
    gate_threshold: Any = DEFAULT_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD,
    max_delta: Any = DEFAULT_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA,
    low_c_threshold: Any = DEFAULT_HUYS_DAYAN_LITE_LOW_C_THRESHOLD,
    high_c_threshold: Any = DEFAULT_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD,
    prob_floor: Any = DEFAULT_POLICY_LITE_PROB_FLOOR,
) -> tuple[dict[str, float] | None, dict[str, Any]]:
    normalized_mode = normalize_controllability_mode(mode)
    bounded_gate = clamp_ratio(
        gate_threshold,
        DEFAULT_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD,
    )
    bounded_max_delta = clamp_modulation_max_delta(
        max_delta,
    )
    bounded_low = clamp_ratio(low_c_threshold, DEFAULT_HUYS_DAYAN_LITE_LOW_C_THRESHOLD)
    bounded_high = clamp_ratio(high_c_threshold, DEFAULT_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD)
    bounded_floor = clamp_prob_floor(prob_floor)
    audit_source = before_event_audit if isinstance(before_event_audit, dict) else {}
    before = audit_source.get("before_event") if isinstance(audit_source.get("before_event"), dict) else {}
    c_family = clamp_ratio(before.get("shrunk_c_family"), 0.5)
    family_confidence = clamp_ratio(before.get("family_confidence"), 0.0)
    base_available = isinstance(pi_base, dict) and set(POLICY_LITE_ACTIONS).issubset(pi_base)
    pi_base_normalized = _normalize_distribution(pi_base) if base_available else None
    base_for_best = pi_base_normalized if base_available else None
    best_nonavoid, best_source = _best_nonavoid_from(
        pi_base=base_for_best,
        q_bayes=q_bayes,
    )
    base_audit = {
        "controllability_gate_open": False,
        "modulation_family": "none",
        "modulation_status": "disabled",
        "best_nonavoid_action": best_nonavoid,
        "best_nonavoid_source": best_source,
        "uniform_mix_gamma": 0.0,
        "removed_avoid_mass": 0.0,
        "pi_base_before_controllability": pi_base_normalized or {},
        "controllability_delta_before_clamp": {
            action: 0.0 for action in POLICY_LITE_ACTIONS
        },
        "controllability_delta_applied": {
            action: 0.0 for action in POLICY_LITE_ACTIONS
        },
        "pi_after_controllability_shift": pi_base_normalized or {},
        "pi_final_controllability": pi_base_normalized or {},
        "final_delta_after_controllability_floor": {
            action: 0.0 for action in POLICY_LITE_ACTIONS
        },
        "total_variation_distance_from_phase4_pi_final": 0.0,
        "max_abs_controllability_delta": 0.0,
        "low_c_directional_help_shift_enabled": False,
        "extreme_low_c_avoid_shift_enabled": False,
        "intervention_applied": False,
        "policy_unchanged": True,
        "uses_post_outcome_information_for_controllability_policy": False,
        "modulation_gate_threshold": bounded_gate,
        "modulation_max_delta": bounded_max_delta,
        "low_c_threshold": bounded_low,
        "high_c_threshold": bounded_high,
        "C_family_before_event": c_family,
        "family_confidence": family_confidence,
    }
    if normalized_mode != "gated_modulate":
        base_audit["modulation_status"] = "not_gated_modulate"
        return None, base_audit
    if not pi_base_normalized:
        base_audit["modulation_status"] = "base_policy_unavailable"
        return None, base_audit
    if family_confidence < bounded_gate:
        base_audit["modulation_status"] = "gate_closed_low_confidence"
        return pi_base_normalized, base_audit
    pi_shifted = dict(pi_base_normalized)
    uniform = {action: 1.0 / len(POLICY_LITE_ACTIONS) for action in POLICY_LITE_ACTIONS}
    delta_before = {action: 0.0 for action in POLICY_LITE_ACTIONS}
    if c_family < bounded_low:
        gamma = bounded_max_delta * family_confidence * (
            (bounded_low - c_family) / max(bounded_low, 1e-9)
        )
        gamma = min(gamma, bounded_max_delta)
        pi_shifted = {
            action: (1.0 - gamma) * pi_base_normalized[action] + gamma * uniform[action]
            for action in POLICY_LITE_ACTIONS
        }
        delta_before = _distribution_delta(pi_shifted, pi_base_normalized)
        base_audit.update(
            {
                "controllability_gate_open": True,
                "modulation_family": "flatten_low_c",
                "modulation_status": "modulated",
                "uniform_mix_gamma": gamma,
            }
        )
    elif c_family > bounded_high:
        if not best_nonavoid:
            base_audit["modulation_status"] = "base_policy_unavailable"
            return None, base_audit
        delta = bounded_max_delta * family_confidence * (
            (c_family - bounded_high) / max(1.0 - bounded_high, 1e-9)
        )
        delta = min(delta, bounded_max_delta, pi_base_normalized["avoid"])
        pi_shifted["avoid"] = max(0.0, pi_shifted["avoid"] - delta)
        pi_shifted[best_nonavoid] = pi_shifted[best_nonavoid] + delta
        delta_before = _distribution_delta(pi_shifted, pi_base_normalized)
        base_audit.update(
            {
                "controllability_gate_open": True,
                "modulation_family": "reduce_avoid_high_c",
                "modulation_status": "modulated",
                "removed_avoid_mass": delta,
                "best_nonavoid_action": best_nonavoid,
                "best_nonavoid_source": best_source,
            }
        )
    else:
        base_audit["modulation_status"] = "within_neutral_band"
        return pi_base_normalized, base_audit

    pi_after_shift = _normalize_distribution(pi_shifted)
    pi_final = _normalize_distribution(pi_after_shift, floor=bounded_floor)
    final_delta = _distribution_delta(pi_final, pi_base_normalized)
    applied = any(abs(value) > 1e-12 for value in final_delta.values())
    base_audit.update(
        {
            "controllability_delta_before_clamp": delta_before,
            "controllability_delta_applied": _distribution_delta(
                pi_after_shift,
                pi_base_normalized,
            ),
            "pi_after_controllability_shift": pi_after_shift,
            "pi_final_controllability": pi_final,
            "final_delta_after_controllability_floor": final_delta,
            "total_variation_distance_from_phase4_pi_final": (
                _total_variation_distance(pi_final, pi_base_normalized)
            ),
            "max_abs_controllability_delta": max(
                abs(value) for value in final_delta.values()
            ),
            "intervention_applied": applied,
            "policy_unchanged": not applied,
        }
    )
    return pi_final, base_audit


def combine_huys_dayan_lite_audits(
    *,
    before_audit: Any,
    modulation_audit: Any = None,
    after_audit: Any = None,
) -> dict[str, Any]:
    before = copy.deepcopy(before_audit) if isinstance(before_audit, dict) else {}
    modulation = copy.deepcopy(modulation_audit) if isinstance(modulation_audit, dict) else {}
    after = copy.deepcopy(after_audit) if isinstance(after_audit, dict) else {}
    if not before:
        return {}
    combined = before
    if modulation:
        combined.update(modulation)
    if isinstance(after.get("after_event"), dict):
        combined["after_event"] = after["after_event"]
        combined["C_family_after_event"] = after["after_event"].get("shrunk_c_family")
        combined["global_controllability_trace_after"] = after["after_event"].get(
            "global_controllability_trace_after"
        )
    if isinstance(combined.get("before_event"), dict):
        combined["C_family_before_event"] = combined["before_event"].get(
            "shrunk_c_family"
        )
        combined["global_controllability_trace_before"] = combined[
            "before_event"
        ].get("global_controllability_trace")
    combined["policy_unchanged"] = not bool(combined.get("intervention_applied"))
    return combined
