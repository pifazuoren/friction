"""Resolve free-hour phone activity from replay history and the resident's current recommendation."""

from __future__ import annotations

from ..paired_random import PairedRandomProvider
from . import PHONE_USE_NEEDS_V5


# Fixed modeling assumptions, not estimated from the held-out device hours.
PHONE_USE_ODDS_MULTIPLIERS = {"leave_phone": 0.5, "follow_habit": 1.0, "use_phone": 2.0}
DEFAULT_PHONE_USE_SEED = 101


def replay_activity_counts(same_hour_active: dict | None) -> tuple[int, int] | None:
    if not isinstance(same_hour_active, dict):
        return None
    seen, active = same_hour_active.get("seen"), same_hour_active.get("active")
    if type(seen) is int and type(active) is int and 1 <= seen <= 3 and 0 <= active <= seen:
        return seen, active
    return None


def resolve_phone_use(
    *, same_hour_active: dict | None, recommendation: str, agent_id: int | str,
    talkingdata_day: int, hour: int, paired_environment_seed: int | None = None,
) -> dict:
    if recommendation not in PHONE_USE_ODDS_MULTIPLIERS:
        raise ValueError("unknown phone-use recommendation")
    seed = DEFAULT_PHONE_USE_SEED if paired_environment_seed is None else paired_environment_seed
    counts = replay_activity_counts(same_hour_active)
    record = {
        "version": PHONE_USE_NEEDS_V5, "source": "llm_without_history", "seen": None, "active": None,
        "seed": seed, "prior_use_probability": None, "odds_multiplier": None,
        "use_probability": None, "sample_u": None, "llm_recommendation": recommendation,
        "final_choice": recommendation,
    }
    if counts is None:
        if recommendation == "follow_habit":
            raise ValueError("follow_habit requires observed replay hours")
        return record
    seen, active = counts
    prior = (active + 0.5) / (seen + 1)
    multiplier = PHONE_USE_ODDS_MULTIPLIERS[recommendation]
    probability = (prior * multiplier) / ((1 - prior) + prior * multiplier)
    rng = PairedRandomProvider(seed).rng(agent_id, f"day{talkingdata_day}:hour{hour}", 1, "free_hour_phone_use_v5")
    draw = rng.random()
    record.update(
        source="habit_plus_llm", seen=seen, active=active, prior_use_probability=prior,
        odds_multiplier=multiplier, use_probability=probability, sample_u=draw,
        final_choice="use_phone" if draw < probability else "leave_phone",
    )
    return record
