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
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def clamp_term(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def efficacy_loss_term(task_self_efficacy: float) -> float:
    return clamp_term((50.0 - float(task_self_efficacy)) / 22.0, 0.0, 1.6)


def damping_factor(helplessness_before: float) -> float:
    return clamp_term(1.0 - 0.45 * float(helplessness_before) / 100.0, 0.55, 1.0)


def avoid_reason_multiplier(avoid_reason: str) -> float:
    return float(AVOID_REASON_MULTIPLIERS.get(str(avoid_reason), 1.0))


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


def apply_helplessness_update(
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
    )
