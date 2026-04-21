from __future__ import annotations

from dataclasses import asdict, dataclass

AVOID_COMPAT_DELTAS = {
    "helpless_avoid": (-2.0, 4.0),
    "risk_avoid": (-0.5, 2.5),
    "low_value_avoid": (0.0, 1.0),
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


@dataclass(slots=True)
class CompatibilityUpdate:
    trust_in_apps: float
    avoidance_tendency: float
    trust_delta: float
    avoidance_delta: float
    negative_event_increment: int
    help_request_increment: int
    success_increment: int
    failure_increment: int
    intercept_increment: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def apply_compatibility_updates(
    *,
    trust_now: float,
    avoidance_now: float,
    outcome_type: str,
    help_used: bool,
    avoid_reason: str = "not_applicable",
) -> CompatibilityUpdate:
    if outcome_type in {"success_self", "success_with_help"}:
        trust_delta = 5.0
        avoidance_delta = -3.0
    elif outcome_type == "avoid_without_attempt":
        trust_delta, avoidance_delta = AVOID_COMPAT_DELTAS.get(
            str(avoid_reason),
            (-1.0, 2.0),
        )
    elif outcome_type == "abandon_midway":
        trust_delta = -5.0
        avoidance_delta = 4.0
    else:
        trust_delta = -8.0
        avoidance_delta = 5.0

    return CompatibilityUpdate(
        trust_in_apps=clamp_score(trust_now + trust_delta),
        avoidance_tendency=clamp_score(avoidance_now + avoidance_delta),
        trust_delta=trust_delta,
        avoidance_delta=avoidance_delta,
        negative_event_increment=1
        if outcome_type
        in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"}
        else 0,
        help_request_increment=1 if help_used else 0,
        success_increment=1 if outcome_type in {"success_self", "success_with_help"} else 0,
        failure_increment=1
        if outcome_type
        in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"}
        else 0,
        intercept_increment=1 if outcome_type == "success_with_help" else 0,
    )
