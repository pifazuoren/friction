from __future__ import annotations

from typing import Any

from .task_templates import TASK_LIBRARY
from .types import (
    ACTIONABLE_APP_CONTEXTS,
    APP_CONTEXT_SET,
    MOBILE_INTENTION_SET,
    _normalize_distribution_for_keys,
    _safe_int,
    _stable_hash,
    _stable_select_from_distribution,
)


def build_rollout_app_context_candidates(
    *,
    habit_memory: dict[str, Any],
    hour: int,
    need_pressures: dict[str, float] | None = None,
    need_context_mapping: dict[str, tuple[str, ...] | list[str]] | None = None,
    top_k: int = 5,
    allow_empty: bool = False,
    actionable_only: bool = False,
) -> dict[str, float]:
    """Build a bounded candidate pool from observed calibration evidence.

    This function deliberately has no population prior fallback. Contexts must come
    from the agent's Day 1-3 memory or from an explicitly supplied, human-reviewed
    need-to-context mapping.
    """
    limit = int(top_k)
    if limit < 1:
        raise ValueError("top_k must be >= 1")
    if not isinstance(habit_memory, dict):
        raise ValueError("habit_memory must be a dictionary")

    hour_key = str(int(hour))
    observed: dict[str, float] = {}
    context_by_hour = habit_memory.get("context_by_hour", {})
    same_hour = context_by_hour.get(hour_key, {}) if isinstance(context_by_hour, dict) else {}
    if isinstance(same_hour, dict):
        for context, count in same_hour.items():
            name = str(context).strip()
            if name == "no_app_context":
                continue
            if name not in APP_CONTEXT_SET:
                raise ValueError(f"unknown app context in habit memory: {name}")
            if float(count) > 0:
                observed[name] = observed.get(name, 0.0) + float(count)

    # If this clock hour has no observed context, use the same device's overall
    # Day 1-3 observed contexts. This is still calibration evidence, not a prior.
    if not observed or (actionable_only and not observed.keys() & ACTIONABLE_APP_CONTEXTS):
        total_counts = habit_memory.get("context_total_counts", {})
        if isinstance(total_counts, dict):
            for context, count in total_counts.items():
                name = str(context).strip()
                if name == "no_app_context":
                    continue
                if name not in APP_CONTEXT_SET:
                    raise ValueError(f"unknown app context in habit memory: {name}")
                if float(count) > 0:
                    observed[name] = observed.get(name, 0.0) + float(count)

    scores = dict(observed)
    pressures = need_pressures or {}
    mapping = need_context_mapping or {}
    if not isinstance(pressures, dict) or not isinstance(mapping, dict):
        raise ValueError("need_pressures and need_context_mapping must be dictionaries")
    for need, pressure in pressures.items():
        try:
            weight = float(pressure)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"need pressure for {need!r} must be numeric") from exc
        if weight < 0.0:
            raise ValueError(f"need pressure for {need!r} must be >= 0")
        for context in mapping.get(str(need), ()):
            name = str(context).strip()
            if name == "no_app_context":
                continue
            if name not in APP_CONTEXT_SET:
                raise ValueError(f"need mapping contains unknown app context: {name}")
            if weight > 0.0:
                scores[name] = scores.get(name, 0.0) + weight

    positive = {name: value for name, value in scores.items()
                if value > 0.0 and (not actionable_only or name in ACTIONABLE_APP_CONTEXTS)}
    if not positive:
        if allow_empty:
            return {}
        raise ValueError("rollout app-context candidate pool is empty")
    selected = sorted(
        positive.items(),
        key=lambda item: (-float(item[1]), str(item[0])),
    )[:limit]
    total = sum(value for _, value in selected)
    return {name: float(value) / float(total) for name, value in selected}

_DEFAULT_UNCALIBRATED_PRIOR: dict[str, float] = {
    "check_information": 0.18,
    "use_payment_or_finance": 0.10,
    "login_or_verify_account": 0.10,
    "submit_service_application": 0.14,
    "upload_or_manage_profile": 0.08,
    "find_location_or_service": 0.10,
    "communicate_or_seek_help": 0.12,
    "browse_entertainment": 0.10,
    "no_mobile_action": 0.06,
    "unknown_or_unmapped": 0.02,
}
_DEFAULT_APP_CONTEXT_PRIOR: dict[str, float] = {
    "finance_context": 0.20,
    "finance_candidate_review": 0.04,
    "public_service_context": 0.03,
    "health_service_context": 0.03,
    "shopping_lifestyle_context": 0.08,
    "navigation_transport_context": 0.07,
    "communication_social_context": 0.15,
    "media_entertainment_context": 0.12,
    "device_tool_context": 0.08,
    "education_work_context": 0.05,
    "taxonomy_profile_only": 0.10,
    "unknown_or_unmapped": 0.05,
}


def top_mobile_intention_candidates(
    candidate_intentions: dict[str, float],
    *,
    top_k: int = 5,
) -> dict[str, float]:
    limit = max(1, int(top_k))
    normalized = _normalize_distribution(candidate_intentions)
    return {
        key: float(value)
        for key, value in sorted(
            normalized.items(),
            key=lambda item: (-float(item[1]), item[0]),
        )[:limit]
    }


def top_app_context_candidates(
    candidate_contexts: dict[str, float],
    *,
    top_k: int = 5,
) -> dict[str, float]:
    limit = max(1, int(top_k))
    normalized = _normalize_app_context_distribution(candidate_contexts)
    return {
        key: float(value)
        for key, value in sorted(
            normalized.items(),
            key=lambda item: (-float(item[1]), item[0]),
        )[:limit]
    }


def mobile_intention_candidate_hash(candidate_intentions: dict[str, float]) -> str:
    return _stable_hash(
        {
            key: round(float(value), 12)
            for key, value in sorted(candidate_intentions.items())
        }
    )[:16]


def app_context_candidate_hash(candidate_contexts: dict[str, float]) -> str:
    return _stable_hash(
        {
            key: round(float(value), 12)
            for key, value in sorted(candidate_contexts.items())
        }
    )[:16]


def _normalize_distribution(values: dict[str, Any]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for intention in MOBILE_INTENTION_SET:
        try:
            cleaned[intention] = max(0.0, float(values.get(intention, 0.0)))
        except (TypeError, ValueError):
            cleaned[intention] = 0.0
    total = sum(cleaned.values())
    if total <= 0.0:
        return dict(_DEFAULT_UNCALIBRATED_PRIOR)
    return {key: value / total for key, value in cleaned.items()}


def _normalize_app_context_distribution(values: dict[str, Any]) -> dict[str, float]:
    return _normalize_distribution_for_keys(
        values,
        keys=APP_CONTEXT_SET,
        default=_DEFAULT_APP_CONTEXT_PRIOR,
    )


def _normalize_task_opportunity_distribution(values: dict[str, Any]) -> dict[str, float]:
    return _normalize_distribution_for_keys(
        values,
        keys=tuple(str(template["task_family"]) for template in TASK_LIBRARY),
        default={str(template["task_family"]): 1.0 / len(TASK_LIBRARY) for template in TASK_LIBRARY},
    )


def _bucket_for_profile(profile: dict[str, Any] | None) -> str:
    payload = profile or {}
    age = _safe_int(payload.get("age"), -1)
    if age < 0:
        age_bucket = "unknown"
    elif age < 65:
        age_bucket = "lt65"
    elif age < 75:
        age_bucket = "65_74"
    else:
        age_bucket = "75plus"
    gender = str(payload.get("gender") or payload.get("sex") or "unknown").strip().lower()
    if gender in {"女", "f", "female"}:
        gender_bucket = "female"
    elif gender in {"男", "m", "male"}:
        gender_bucket = "male"
    else:
        gender_bucket = "unknown"
    digital_experience = float(payload.get("digital_experience", 0.5) or 0.5)
    if digital_experience < 0.34:
        digital_bucket = "digital_low"
    elif digital_experience < 0.67:
        digital_bucket = "digital_mid"
    else:
        digital_bucket = "digital_high"
    return f"{age_bucket}|{gender_bucket}|{digital_bucket}"


def _extract_prior_from_calibration(
    *,
    calibration: dict[str, Any],
    profile: dict[str, Any] | None,
    hour: int,
) -> tuple[dict[str, float], str]:
    if not calibration:
        return dict(_DEFAULT_UNCALIBRATED_PRIOR), "uncalibrated_default"
    bucket = _bucket_for_profile(profile)
    hour_key = str(int(hour))
    candidates = [
        calibration.get("mobile_intention_prior_by_bucket_hour", {})
        if isinstance(calibration.get("mobile_intention_prior_by_bucket_hour"), dict)
        else {},
        calibration.get("priors", {}) if isinstance(calibration.get("priors"), dict) else {},
    ]
    for table in candidates:
        for key in (
            f"{bucket}|hour={hour_key}",
            f"{bucket}|{hour_key}",
            f"{bucket}:{hour_key}",
        ):
            row = table.get(key)
            if isinstance(row, dict):
                values = row.get("p_mobile_intention", row)
                if isinstance(values, dict):
                    return _normalize_distribution(values), f"bucket_hour:{key}"
        row = table.get(bucket)
        if isinstance(row, dict):
            hour_rows = row.get("hours", row)
            if isinstance(hour_rows, dict):
                hour_row = hour_rows.get(hour_key, hour_rows.get(int(hour), None))
                if isinstance(hour_row, dict):
                    values = hour_row.get("p_mobile_intention", hour_row)
                    if isinstance(values, dict):
                        return _normalize_distribution(values), f"bucket:{bucket}:hour:{hour_key}"
    global_hourly = calibration.get("global_hourly_prior", {})
    if isinstance(global_hourly, dict):
        row = global_hourly.get(hour_key, global_hourly.get(int(hour), None))
        if isinstance(row, dict):
            values = row.get("p_mobile_intention", row)
            if isinstance(values, dict):
                return _normalize_distribution(values), f"global_hour:{hour_key}"
    global_prior = calibration.get("global_prior", {})
    if isinstance(global_prior, dict):
        values = global_prior.get("p_mobile_intention", global_prior)
        if isinstance(values, dict):
            return _normalize_distribution(values), "global_prior"
    return dict(_DEFAULT_UNCALIBRATED_PRIOR), "uncalibrated_default"


def _extract_app_context_prior_from_calibration(
    *,
    calibration: dict[str, Any],
    profile: dict[str, Any] | None,
    hour: int,
) -> tuple[dict[str, float], str]:
    if not calibration:
        return dict(_DEFAULT_APP_CONTEXT_PRIOR), "uncalibrated_app_context_default"
    bucket = _bucket_for_profile(profile)
    hour_key = str(int(hour))
    candidates = [
        calibration.get("app_context_prior_by_bucket_hour", {})
        if isinstance(calibration.get("app_context_prior_by_bucket_hour"), dict)
        else {},
        calibration.get("priors", {}) if isinstance(calibration.get("priors"), dict) else {},
    ]
    for table in candidates:
        for key in (
            f"{bucket}|hour={hour_key}",
            f"{bucket}|{hour_key}",
            f"{bucket}:{hour_key}",
        ):
            row = table.get(key)
            if isinstance(row, dict):
                values = row.get("p_app_context", row)
                if isinstance(values, dict):
                    return _normalize_app_context_distribution(values), f"app_context_bucket_hour:{key}"
        row = table.get(bucket)
        if isinstance(row, dict):
            hour_rows = row.get("hours", row)
            if isinstance(hour_rows, dict):
                hour_row = hour_rows.get(hour_key, hour_rows.get(int(hour), None))
                if isinstance(hour_row, dict):
                    values = hour_row.get("p_app_context", hour_row)
                    if isinstance(values, dict):
                        return (
                            _normalize_app_context_distribution(values),
                            f"app_context_bucket:{bucket}:hour:{hour_key}",
                        )
    global_hourly = calibration.get("global_hourly_prior", {})
    if isinstance(global_hourly, dict):
        row = global_hourly.get(hour_key, global_hourly.get(int(hour), None))
        if isinstance(row, dict):
            values = row.get("p_app_context", row)
            if isinstance(values, dict):
                return _normalize_app_context_distribution(values), f"app_context_global_hour:{hour_key}"
    global_prior = calibration.get("global_prior", {})
    if isinstance(global_prior, dict):
        values = global_prior.get("p_app_context", global_prior)
        if isinstance(values, dict):
            return _normalize_app_context_distribution(values), "app_context_global_prior"
    return dict(_DEFAULT_APP_CONTEXT_PRIOR), "uncalibrated_app_context_default"


def _stable_select_intention(
    *,
    priors: dict[str, float],
    seed: int,
    agent_id: int,
    day: int,
    tick_seconds: float,
    profile_bucket: str,
) -> str:
    normalized = _normalize_distribution(priors)
    key = _stable_hash(
        {
            "seed": int(seed),
            "agent_id": int(agent_id),
            "day": int(day),
            "tick": int(round(float(tick_seconds))),
            "profile_bucket": profile_bucket,
            "version": "mobile_intention_rule_v1",
        }
    )
    threshold = int(key[:12], 16) / float(0xFFFFFFFFFFFF)
    cumulative = 0.0
    for intention, probability in normalized.items():
        cumulative += probability
        if threshold <= cumulative:
            return intention
    return "unknown_or_unmapped"


def _stable_select_app_context(
    *,
    priors: dict[str, float],
    seed: int,
    agent_id: int,
    day: int,
    tick_seconds: float,
    profile_bucket: str,
) -> str:
    normalized = _normalize_app_context_distribution(priors)
    return _stable_select_from_distribution(
        values=normalized,
        keys=APP_CONTEXT_SET,
        seed=int(seed),
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        profile_bucket=profile_bucket,
        version="app_context_rule_v1",
    )
