from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .bundle import HourlyAppEntryBundle

APP_ENTRY_HABIT_SCHEMA_VERSION = "app_entry_habit_memory_v1"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _base_memory(bundle: HourlyAppEntryBundle) -> dict[str, Any]:
    return {
        "schema_version": APP_ENTRY_HABIT_SCHEMA_VERSION,
        "device_id": bundle.device_id,
        "replay_days": [],
        "total_hours_seen": 0,
        "active_hours": 0,
        "inactive_hours": 0,
        "active_event_app_exposures": 0,
        "active_exposure_samples": [],
        "active_by_hour": {},
        "intensity_by_hour": {},
        "context_total_counts": {},
        "context_by_hour": {},
        "primary_context_by_hour": {},
        "task_eligible_primary_hours": 0,
        "last_updated_day": -1,
        "last_updated_hour": -1,
    }


def _counter_add(container: dict[str, Any], key: str, amount: int) -> None:
    container[key] = _safe_int(container.get(key), 0) + int(amount)


def update_habit_memory_from_bundle(
    raw_memory: Any,
    bundle: HourlyAppEntryBundle,
) -> dict[str, Any]:
    memory = (
        deepcopy(raw_memory)
        if isinstance(raw_memory, dict)
        and raw_memory.get("schema_version") == APP_ENTRY_HABIT_SCHEMA_VERSION
        else _base_memory(bundle)
    )
    memory["schema_version"] = APP_ENTRY_HABIT_SCHEMA_VERSION
    memory["device_id"] = bundle.device_id
    replay_days = {
        _safe_int(day, -1)
        for day in memory.get("replay_days", [])
        if _safe_int(day, -1) > 0
    }
    replay_days.add(int(bundle.day))
    memory["replay_days"] = sorted(replay_days)
    memory["total_hours_seen"] = _safe_int(memory.get("total_hours_seen"), 0) + 1
    if bundle.active:
        memory["active_hours"] = _safe_int(memory.get("active_hours"), 0) + 1
        samples = [
            _safe_int(value, 0)
            for value in memory.get("active_exposure_samples", [])
            if _safe_int(value, 0) > 0
        ]
        samples.append(int(bundle.active_event_app_exposures))
        memory["active_exposure_samples"] = samples[-72:]
    else:
        memory["inactive_hours"] = _safe_int(memory.get("inactive_hours"), 0) + 1
    memory["active_event_app_exposures"] = (
        _safe_int(memory.get("active_event_app_exposures"), 0)
        + int(bundle.active_event_app_exposures)
    )

    hour_key = str(int(bundle.hour))
    active_by_hour = memory.setdefault("active_by_hour", {})
    hour_active = active_by_hour.setdefault(hour_key, {"seen": 0, "active": 0})
    hour_active["seen"] = _safe_int(hour_active.get("seen"), 0) + 1
    if bundle.active:
        hour_active["active"] = _safe_int(hour_active.get("active"), 0) + 1

    intensity_by_hour = memory.setdefault("intensity_by_hour", {})
    hour_intensity = intensity_by_hour.setdefault(
        hour_key,
        {"count": 0, "sum": 0, "mean": 0.0},
    )
    hour_intensity["count"] = _safe_int(hour_intensity.get("count"), 0) + 1
    hour_intensity["sum"] = _safe_int(hour_intensity.get("sum"), 0) + int(
        bundle.active_event_app_exposures
    )
    hour_intensity["mean"] = float(hour_intensity["sum"]) / float(
        max(1, hour_intensity["count"])
    )

    context_total = memory.setdefault("context_total_counts", {})
    context_by_hour = memory.setdefault("context_by_hour", {})
    hour_context = context_by_hour.setdefault(hour_key, {})
    for context, count in bundle.app_context_counts.items():
        _counter_add(context_total, context, int(count))
        _counter_add(hour_context, context, int(count))

    primary_by_hour = memory.setdefault("primary_context_by_hour", {})
    hour_primary = primary_by_hour.setdefault(hour_key, {})
    _counter_add(hour_primary, bundle.primary_context, 1)
    if bundle.is_task_eligible_primary():
        memory["task_eligible_primary_hours"] = (
            _safe_int(memory.get("task_eligible_primary_hours"), 0) + 1
        )
    memory["last_updated_day"] = int(bundle.day)
    memory["last_updated_hour"] = int(bundle.hour)
    return memory


def build_rollout_intensity_profile(
    habit_memory: dict[str, Any],
    *,
    hour: int,
    absolute_cap: int,
) -> dict[str, Any]:
    """Build a Day 1-3-only prompt reference and active exposure safety cap."""
    if not isinstance(habit_memory, dict):
        raise ValueError("habit_memory must be a dictionary")
    cap_limit = int(absolute_cap)
    if cap_limit < 1:
        raise ValueError("absolute_cap must be >= 1")
    samples = sorted(
        _safe_int(value, 0)
        for value in habit_memory.get("active_exposure_samples", [])
        if _safe_int(value, 0) > 0
    )
    if not samples:
        raise ValueError("habit memory has no active exposure calibration samples")
    p95_index = max(0, int(math.ceil(0.95 * len(samples))) - 1)
    reference_p95 = int(samples[p95_index])
    active_exposure_cap = max(1, min(reference_p95, cap_limit))

    hour_key = str(int(hour))
    intensity_row = habit_memory.get("intensity_by_hour", {}).get(hour_key, {})
    active_row = habit_memory.get("active_by_hour", {}).get(hour_key, {})
    seen = _safe_int(active_row.get("seen"), 0) if isinstance(active_row, dict) else 0
    active = _safe_int(active_row.get("active"), 0) if isinstance(active_row, dict) else 0
    same_hour_mean = (
        float(intensity_row.get("mean", 0.0))
        if isinstance(intensity_row, dict)
        else 0.0
    )
    return {
        "same_hour_mean_exposures": same_hour_mean,
        "same_hour_active_rate": float(active) / float(seen) if seen > 0 else 0.0,
        "reference_active_exposure_p95": reference_p95,
        "active_exposure_cap": active_exposure_cap,
        "absolute_safety_cap": cap_limit,
        "calibration_active_sample_count": len(samples),
        "calibration_source": "talkingdata_day1_3_habit_memory",
    }


def build_calibrated_intensity_profile(habit_memory: dict[str, Any], *, hour: int) -> dict[str, Any]:
    """Estimate hourly exposure from the three replay observations, including zeros."""
    if set(habit_memory.get("replay_days", [])) != {1, 2, 3}:
        raise ValueError("calibrated intensity requires replay days 1, 2 and 3 only")
    key = str(hour)
    intensity = habit_memory.get("intensity_by_hour", {}).get(key, {})
    activity = habit_memory.get("active_by_hour", {}).get(key, {})
    if intensity.get("count") != 3 or activity.get("seen") != 3:
        raise ValueError("calibrated intensity requires three observations of this hour")
    total = intensity["sum"]
    if type(total) is not int or total < 0:
        raise ValueError("calibration exposure sum must be a nonnegative integer")
    return {
        "same_hour_mean_exposures": total / 3,
        "same_hour_active_rate": activity["active"] / 3,
        "exposures_if_active": max(1, (total + 1) // 3),
        "calibration_source": "device_day1_3_same_hour_mean_including_zeros",
    }


def append_context_only_row(
    raw_rows: Any,
    *,
    decision: dict[str, Any],
    max_rows: int = 2000,
) -> list[dict[str, Any]]:
    rows = list(raw_rows) if isinstance(raw_rows, list) else []
    audit = decision.get("audit", {}) if isinstance(decision, dict) else {}
    if not isinstance(audit, dict):
        audit = {}
    row = {
        "agent_id": _safe_int(audit.get("agent_id"), 0),
        "simulation_day": _safe_int(audit.get("simulation_day", audit.get("day")), 0),
        "talkingdata_day": _safe_int(audit.get("talkingdata_day"), 0),
        "hour": _safe_int(audit.get("hour"), 0),
        "device_id": str(audit.get("device_id", "")),
        "active": bool(audit.get("active", False)),
        "active_event_app_exposures": _safe_int(
            audit.get("active_event_app_exposures"), 0
        ),
        "primary_context": str(
            audit.get("primary_context")
            or audit.get("selected_app_context")
            or decision.get("selected_app_context", "")
        ),
        "context_only_reason": str(audit.get("context_only_reason", "")),
        "entry_status": str(decision.get("entry_status", "")),
        "task_generated": bool(decision.get("task_generated", False)),
    }
    rows.append(row)
    if len(rows) > max_rows:
        rows = rows[-max_rows:]
    return rows
