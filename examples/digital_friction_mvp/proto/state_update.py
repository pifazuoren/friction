from __future__ import annotations

from .models import HelplessnessUpdateInput, HelplessnessUpdateResult

BASE_DELTAS = {
    "success_self": -1.4,
    "success_with_help": -0.7,
    "failure_after_attempt": 0.6,
    "failure_even_with_help": 0.9,
    "abandon_midway": 0.45,
    "avoid_without_attempt": 0.15,
}

FAILURE_TYPES = {
    "failure_after_attempt",
    "failure_even_with_help",
    "abandon_midway",
    "avoid_without_attempt",
}
SUCCESS_TYPES = {"success_self", "success_with_help"}
UNCONTROLLABILITY_DELTAS = {0: 0.0, 1: 1.2, 2: 2.4}
AVOID_REASON_MULTIPLIERS = {
    "helpless_avoid": 1.0,
    "risk_avoid": 0.35,
    "low_value_avoid": 0.15,
    "rational_security_avoid": 0.0,
}
HELPLESSNESS_UPDATE_MODES = {"rule_v1", "theory_update_v2"}
H_UPDATE_CALIBRATION_MODES = {
    "original_v2",
    "scaled_nonlinear",
    "scaled_nonlinear_daily_cap",
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def clamp_term(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def efficacy_loss_term(task_self_efficacy: float) -> float:
    return clamp_term((50.0 - float(task_self_efficacy)) / 22.0, 0.0, 1.6)


def damping_factor(helplessness_before: float) -> float:
    return clamp_term(1.0 - 0.45 * float(helplessness_before) / 100.0, 0.55, 1.0)


def nonlinear_harm_damping_factor(
    *,
    helplessness_before: float,
    strength: float,
    power: float,
    floor: float,
) -> float:
    h_ratio = clamp_score(helplessness_before) / 100.0
    safe_strength = max(0.0, float(strength))
    safe_power = max(0.01, float(power))
    safe_floor = clamp_term(float(floor), 0.0, 1.0)
    return clamp_term(
        1.0 - safe_strength * (h_ratio ** safe_power),
        safe_floor,
        1.0,
    )


def _normalize_calibration_mode(value: str) -> str:
    mode = str(value or "original_v2").strip().lower()
    if mode not in H_UPDATE_CALIBRATION_MODES:
        return "original_v2"
    return mode


def _apply_daily_harm_cap(
    *,
    delta_before_cap: float,
    daily_harm_cap: float,
    daily_harm_used_before: float,
) -> tuple[float, float, float, bool]:
    cap = max(0.0, float(daily_harm_cap))
    used_before = max(0.0, float(daily_harm_used_before))
    if cap <= 0.0 or delta_before_cap <= 0.0:
        return delta_before_cap, used_before, max(0.0, cap - used_before), False
    remaining = max(0.0, cap - used_before)
    delta_after_cap = min(float(delta_before_cap), remaining)
    used_after = used_before + max(0.0, delta_after_cap)
    return (
        delta_after_cap,
        used_after,
        remaining,
        delta_after_cap < float(delta_before_cap),
    )


def avoid_reason_multiplier(avoid_reason: str) -> float:
    return float(AVOID_REASON_MULTIPLIERS.get(str(avoid_reason), 1.0))


def attribution_harm_multiplier(
    *,
    locus: str,
    stability: str,
    scope: str,
    confidence: float,
) -> float:
    if float(confidence) < 0.55:
        return 1.0
    multiplier = 1.0
    if str(locus) == "self":
        multiplier += 0.10
    elif str(locus) == "situation":
        multiplier -= 0.10
    if str(stability) == "stable":
        multiplier += 0.10
    elif str(stability) == "transient":
        multiplier -= 0.08
    if str(scope) == "family_generalizing":
        multiplier += 0.12
    elif str(scope) == "task_specific":
        multiplier -= 0.08
    return clamp_term(multiplier, 0.70, 1.30)


def controllable_success_protection(controllable_success_memory: float) -> float:
    memory = clamp_term(controllable_success_memory, 0.0, 1.0)
    return clamp_term(memory * 0.45, 0.0, 0.45)


def success_recovery_bonus(
    *,
    outcome_type: str,
    ended_failure_streak: bool,
    support_mode: str,
) -> float:
    if outcome_type == "success_self":
        bonus = 1.0
    elif str(support_mode) == "enabling_support":
        bonus = 0.35
    else:
        bonus = 0.1

    if ended_failure_streak:
        bonus += 0.25

    return bonus


def apply_helplessness_update_rule_v1(
    payload: HelplessnessUpdateInput,
) -> HelplessnessUpdateResult:
    outcome_type = payload.outcome_type
    helplessness_before = clamp_score(payload.helplessness_now)
    base = BASE_DELTAS[outcome_type]
    current_failures = int(payload.consecutive_failures)
    next_failures = current_failures
    uncontrollability = 0.0
    efficacy_loss = 0.0
    recovery = 0.0
    raw_delta = 0.0
    damping = 1.0
    avoid_multiplier = 1.0
    success_protection = 0.0

    if outcome_type in SUCCESS_TYPES:
        next_failures = 0
        recovery = success_recovery_bonus(
            outcome_type=outcome_type,
            ended_failure_streak=current_failures > 0,
            support_mode=str(payload.support_mode),
        )
        # 即时恢复保持简洁：自己做成最强，enabling help 次之，其余帮助成功最弱。
        raw_delta = base - recovery
        helplessness_after = clamp_score(helplessness_before + raw_delta)
    else:
        next_failures = (
            current_failures
            if outcome_type == "avoid_without_attempt"
            else current_failures + 1
        )
        uncontrollability = UNCONTROLLABILITY_DELTAS.get(
            int(payload.event_level_uncontrollability), 0.0
        )
        efficacy_loss = efficacy_loss_term(float(payload.task_self_efficacy))
        # support 不再直接减 helplessness，而是通过效能感、mastery 和记忆等间接路径起作用。
        raw_delta = base + uncontrollability + efficacy_loss
        if outcome_type == "avoid_without_attempt":
            avoid_multiplier = avoid_reason_multiplier(payload.avoid_reason)
            raw_delta = max(0.0, raw_delta * avoid_multiplier)
        # 过去积累过可控成功，后面同样的打击会没那么伤。
        success_protection = controllable_success_protection(
            payload.controllable_success_memory
        )
        raw_delta = max(0.0, raw_delta * (1.0 - success_protection))
        # 已经很无助时，再一次失败的边际伤害应更小。
        damping = damping_factor(helplessness_before)
        helplessness_after = clamp_score(helplessness_before + raw_delta * damping)

    return HelplessnessUpdateResult(
        helplessness_before=helplessness_before,
        helplessness_after=helplessness_after,
        delta=helplessness_after - helplessness_before,
        base_delta=base,
        uncontrollability_delta=uncontrollability,
        efficacy_loss_term=efficacy_loss,
        recovery_bonus=recovery,
        mastery_recovery_term=recovery,
        raw_delta_before_damping=raw_delta,
        damping_factor=damping,
        avoid_reason_multiplier=avoid_multiplier,
        controllable_success_protection=success_protection,
        next_consecutive_failures=next_failures,
        calibration_mode_configured=str(payload.h_update_calibration_mode),
        calibration_mode_effective="not_applicable",
        negative_scale=1.0,
        damping_formula="linear_v1",
        damping_strength=0.45,
        damping_power=1.0,
        damping_floor=0.55,
        delta_before_daily_cap=helplessness_after - helplessness_before,
        daily_harm_cap=0.0,
        daily_harm_used_before=0.0,
        daily_harm_remaining_before=0.0,
        daily_cap_applied=False,
        delta_after_daily_cap=helplessness_after - helplessness_before,
        daily_harm_used_after=max(0.0, float(payload.h_update_daily_harm_used_before)),
    )


def apply_helplessness_update_v2(
    payload: HelplessnessUpdateInput,
) -> HelplessnessUpdateResult:
    outcome_type = payload.outcome_type
    helplessness_before = clamp_score(payload.helplessness_now)
    base = BASE_DELTAS[outcome_type]
    current_failures = int(payload.consecutive_failures)
    next_failures = current_failures
    uncontrollability = 0.0
    efficacy_loss = 0.0
    recovery = 0.0
    raw_delta = 0.0
    damping = 1.0
    avoid_multiplier = 1.0
    success_protection = 0.0
    attribution_multiplier = 1.0
    attribution_recovery_multiplier = 1.0
    affective_distress_harm = 0.0
    calibration_mode = _normalize_calibration_mode(payload.h_update_calibration_mode)
    negative_scale = 1.0
    damping_formula = "linear_v1"
    damping_strength = 0.45
    damping_power = 1.0
    damping_floor = 0.55
    daily_harm_cap = 0.0
    daily_harm_used_before = max(0.0, float(payload.h_update_daily_harm_used_before))
    daily_harm_remaining_before = 0.0
    daily_cap_applied = False
    delta_before_daily_cap = 0.0
    delta_after_daily_cap = 0.0
    daily_harm_used_after = daily_harm_used_before

    if outcome_type in SUCCESS_TYPES:
        next_failures = 0
        recovery = success_recovery_bonus(
            outcome_type=outcome_type,
            ended_failure_streak=current_failures > 0,
            support_mode=str(payload.support_mode),
        )
        raw_delta = base - recovery
        helplessness_after = clamp_score(helplessness_before + raw_delta)
        delta_before_daily_cap = helplessness_after - helplessness_before
        delta_after_daily_cap = delta_before_daily_cap
    else:
        next_failures = (
            current_failures
            if outcome_type == "avoid_without_attempt"
            else current_failures + 1
        )
        uncontrollability = UNCONTROLLABILITY_DELTAS.get(
            int(payload.event_level_uncontrollability), 0.0
        )
        efficacy_loss = efficacy_loss_term(float(payload.task_self_efficacy))
        raw_delta = base + uncontrollability + efficacy_loss + affective_distress_harm
        attribution_multiplier = attribution_harm_multiplier(
            locus=str(payload.event_attribution_locus),
            stability=str(payload.event_attribution_stability),
            scope=str(payload.event_attribution_scope),
            confidence=float(payload.event_attribution_confidence),
        )
        raw_delta = max(0.0, raw_delta * attribution_multiplier)
        if outcome_type == "avoid_without_attempt":
            avoid_multiplier = avoid_reason_multiplier(payload.avoid_reason)
            raw_delta = max(0.0, raw_delta * avoid_multiplier)
        success_protection = controllable_success_protection(
            payload.controllable_success_memory
        )
        raw_delta = max(0.0, raw_delta * (1.0 - success_protection))
        if calibration_mode in {"scaled_nonlinear", "scaled_nonlinear_daily_cap"}:
            negative_scale = max(0.0, float(payload.h_update_negative_scale))
            raw_delta = max(0.0, raw_delta * negative_scale)
            damping_strength = max(0.0, float(payload.h_update_damping_strength))
            damping_power = max(0.01, float(payload.h_update_damping_power))
            damping_floor = clamp_term(float(payload.h_update_damping_floor), 0.0, 1.0)
            damping = nonlinear_harm_damping_factor(
                helplessness_before=helplessness_before,
                strength=damping_strength,
                power=damping_power,
                floor=damping_floor,
            )
            damping_formula = "nonlinear_v1"
        else:
            damping = damping_factor(helplessness_before)
        delta_before_daily_cap = clamp_score(helplessness_before + raw_delta * damping) - helplessness_before
        delta_after_daily_cap = delta_before_daily_cap
        if calibration_mode == "scaled_nonlinear_daily_cap":
            daily_harm_cap = max(0.0, float(payload.h_update_daily_harm_cap))
            (
                delta_after_daily_cap,
                daily_harm_used_after,
                daily_harm_remaining_before,
                daily_cap_applied,
            ) = _apply_daily_harm_cap(
                delta_before_cap=delta_before_daily_cap,
                daily_harm_cap=daily_harm_cap,
                daily_harm_used_before=daily_harm_used_before,
            )
        helplessness_after = clamp_score(helplessness_before + delta_after_daily_cap)

    return HelplessnessUpdateResult(
        helplessness_before=helplessness_before,
        helplessness_after=helplessness_after,
        delta=helplessness_after - helplessness_before,
        base_delta=base,
        uncontrollability_delta=uncontrollability,
        efficacy_loss_term=efficacy_loss,
        recovery_bonus=recovery,
        mastery_recovery_term=recovery,
        raw_delta_before_damping=raw_delta,
        damping_factor=damping,
        avoid_reason_multiplier=avoid_multiplier,
        controllable_success_protection=success_protection,
        next_consecutive_failures=next_failures,
        mode="theory_update_v2",
        status="ok",
        base_failure_signal=base if outcome_type in FAILURE_TYPES else 0.0,
        noncontingency_harm=uncontrollability,
        self_efficacy_harm=efficacy_loss,
        affective_distress_harm=affective_distress_harm,
        attribution_multiplier=attribution_multiplier,
        attribution_recovery_multiplier=attribution_recovery_multiplier,
        calibration_mode_configured=str(payload.h_update_calibration_mode),
        calibration_mode_effective=calibration_mode,
        negative_scale=negative_scale,
        damping_formula=damping_formula,
        damping_strength=damping_strength,
        damping_power=damping_power,
        damping_floor=damping_floor,
        delta_before_daily_cap=delta_before_daily_cap,
        daily_harm_cap=daily_harm_cap,
        daily_harm_used_before=daily_harm_used_before,
        daily_harm_remaining_before=daily_harm_remaining_before,
        daily_cap_applied=daily_cap_applied,
        delta_after_daily_cap=helplessness_after - helplessness_before,
        daily_harm_used_after=daily_harm_used_after,
    )


def apply_helplessness_update(
    payload: HelplessnessUpdateInput,
) -> HelplessnessUpdateResult:
    mode = str(payload.helplessness_update_mode or "rule_v1").strip().lower()
    if mode not in HELPLESSNESS_UPDATE_MODES:
        raise ValueError(
            "helplessness_update_mode must be one of: "
            + ", ".join(sorted(HELPLESSNESS_UPDATE_MODES))
        )
    if mode == "theory_update_v2":
        return apply_helplessness_update_v2(payload)
    return apply_helplessness_update_rule_v1(payload)
