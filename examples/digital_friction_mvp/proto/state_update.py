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
SUPPORT_BUFFERS = {0: 0.0, 1: 0.05, 2: 0.12}
UNCONTROLLABILITY_DELTAS = {0: 0.0, 1: 1.2, 2: 2.4}
AVOID_REASON_MULTIPLIERS = {
    "helpless_avoid": 1.0,
    "risk_avoid": 0.35,
    "low_value_avoid": 0.15,
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def clamp_term(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def repetition_delta(consecutive_failures: int) -> float:
    consecutive_failures = int(consecutive_failures)
    if consecutive_failures <= 1:
        return 0.0
    if consecutive_failures == 2:
        return 0.5
    if consecutive_failures == 3:
        return 1.0
    return 1.5


def efficacy_loss_term(task_self_efficacy: float) -> float:
    return clamp_term((50.0 - float(task_self_efficacy)) / 22.0, 0.0, 1.6)


def control_loss_term(felt_control: float) -> float:
    return clamp_term((50.0 - float(felt_control)) / 28.0, 0.0, 0.9)


def damping_factor(helplessness_before: float) -> float:
    return clamp_term(1.0 - 0.45 * float(helplessness_before) / 100.0, 0.55, 1.0)


def avoid_reason_multiplier(avoid_reason: str) -> float:
    return float(AVOID_REASON_MULTIPLIERS.get(str(avoid_reason), 1.0))


def controllable_success_protection(controllable_success_memory: float) -> float:
    memory = clamp_term(controllable_success_memory, 0.0, 1.0)
    return clamp_term(memory * 0.45, 0.0, 0.45)


def mastery_recovery_term(
    *,
    outcome_type: str,
    support_quality: int,
    ended_failure_streak: bool,
    felt_control: float,
    expected_help_effectiveness: float,
    support_mode: str,
) -> float:
    bonus = 0.0
    if outcome_type == "success_self":
        bonus += 0.9
    elif outcome_type == "success_with_help":
        if (
            str(support_mode) == "enabling_support"
            and float(expected_help_effectiveness) >= 60.0
            and float(felt_control) >= 50.0
        ):
            bonus += 0.35
        elif int(support_quality) == 2 and float(expected_help_effectiveness) >= 55.0:
            bonus += 0.15
    if ended_failure_streak:
        bonus += 0.35
    if outcome_type == "success_self" and float(felt_control) >= 55.0:
        bonus += 0.4
    if outcome_type == "success_self" and float(felt_control) >= 70.0:
        bonus += 0.2
    return bonus


def apply_helplessness_update(
    payload: HelplessnessUpdateInput,
) -> HelplessnessUpdateResult:
    outcome_type = payload.outcome_type
    helplessness_before = clamp_score(payload.helplessness_now)
    base = BASE_DELTAS[outcome_type]
    current_failures = int(payload.consecutive_failures)
    next_failures = current_failures
    rep_delta = 0.0
    uncontrollability = 0.0
    efficacy_loss = 0.0
    control_loss = 0.0
    support_buffer = 0.0
    recovery = 0.0
    raw_delta = 0.0
    damping = 1.0
    avoid_multiplier = 1.0
    success_protection = 0.0

    if outcome_type in SUCCESS_TYPES:
        next_failures = 0
        recovery = mastery_recovery_term(
            outcome_type=outcome_type,
            support_quality=int(payload.support_quality),
            ended_failure_streak=current_failures > 0,
            felt_control=float(payload.felt_control),
            expected_help_effectiveness=float(payload.expected_help_effectiveness),
            support_mode=str(payload.support_mode),
        )
        # 自己做成而且感觉可控，恢复应强于被帮助完成。
        raw_delta = base - recovery
        helplessness_after = clamp_score(helplessness_before + raw_delta)
    else:
        next_failures = (
            current_failures
            if outcome_type == "avoid_without_attempt"
            else current_failures + 1
        )
        rep_delta = repetition_delta(next_failures)
        uncontrollability = UNCONTROLLABILITY_DELTAS.get(
            int(payload.perceived_uncontrollability), 0.0
        )
        efficacy_loss = efficacy_loss_term(float(payload.task_self_efficacy))
        control_loss = control_loss_term(float(payload.felt_control))
        support_buffer = 0.0
        if outcome_type in {"failure_even_with_help", "abandon_midway"}:
            if str(payload.support_mode) == "enabling_support":
                support_buffer = SUPPORT_BUFFERS.get(int(payload.support_quality), 0.0)
            elif int(payload.support_quality) >= 2:
                support_buffer = SUPPORT_BUFFERS.get(int(payload.support_quality), 0.0) * 0.5
        # 失败本身只给小底分，真正更伤的是失控感和低效能。
        raw_delta = (
            base
            + rep_delta
            + uncontrollability
            + efficacy_loss
            + control_loss
            - support_buffer
        )
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
        repetition_delta=rep_delta,
        uncontrollability_delta=uncontrollability,
        efficacy_loss_term=efficacy_loss,
        control_loss_term=control_loss,
        support_buffer=support_buffer,
        recovery_bonus=recovery,
        mastery_recovery_term=recovery,
        raw_delta_before_damping=raw_delta,
        damping_factor=damping,
        avoid_reason_multiplier=avoid_multiplier,
        controllable_success_protection=success_protection,
        next_consecutive_failures=next_failures,
    )
