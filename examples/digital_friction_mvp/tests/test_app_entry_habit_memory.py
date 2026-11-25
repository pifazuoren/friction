from __future__ import annotations

import pytest

from proto.app_entry.bundle import HourlyAppEntryBundle, NO_APP_CONTEXT
from proto.app_entry.habit_memory import (
    append_context_only_row,
    build_calibrated_intensity_profile,
    build_rollout_intensity_profile,
    update_habit_memory_from_bundle,
)


def test_habit_memory_aggregates_hourly_bundle_counts() -> None:
    active = HourlyAppEntryBundle(
        device_id="device-a",
        day=1,
        hour=9,
        active=True,
        active_event_app_exposures=3,
        app_context_counts={
            "finance_context": 2,
            "communication_social_context": 1,
        },
        primary_context="finance_context",
        source="talkingdata_active_hour",
    )
    inactive = HourlyAppEntryBundle(
        device_id="device-a",
        day=1,
        hour=10,
        active=False,
        active_event_app_exposures=0,
        app_context_counts={},
        primary_context=NO_APP_CONTEXT,
        source="talkingdata_inactive_hour",
    )

    memory = update_habit_memory_from_bundle({}, active)
    memory = update_habit_memory_from_bundle(memory, inactive)

    assert memory["total_hours_seen"] == 2
    assert memory["active_hours"] == 1
    assert memory["inactive_hours"] == 1
    assert memory["active_event_app_exposures"] == 3
    assert memory["active_exposure_samples"] == [3]
    assert memory["active_by_hour"]["9"]["active"] == 1
    assert memory["active_by_hour"]["10"]["active"] == 0
    assert memory["context_total_counts"]["finance_context"] == 2
    assert memory["context_by_hour"]["9"]["communication_social_context"] == 1
    assert memory["task_eligible_primary_hours"] == 1
    assert memory["last_updated_hour"] == 10


def test_context_only_rows_are_appended_separately() -> None:
    rows = append_context_only_row(
        [],
        decision={
            "entry_status": "communication_social_context_context_only",
            "task_generated": False,
            "selected_app_context": "communication_social_context",
            "audit": {
                "agent_id": 3,
                "simulation_day": 0,
                "talkingdata_day": 1,
                "hour": 9,
                "device_id": "device-a",
                "active": True,
                "active_event_app_exposures": 2,
                "context_only_reason": "app_context_only",
            },
        },
    )

    assert len(rows) == 1
    assert rows[0]["primary_context"] == "communication_social_context"
    assert rows[0]["context_only_reason"] == "app_context_only"
    assert rows[0]["task_generated"] is False


def test_rollout_intensity_profile_uses_reference_p95_and_absolute_cap() -> None:
    memory = {
        "active_exposure_samples": [1, 2, 3, 4, 20],
        "intensity_by_hour": {"9": {"count": 3, "sum": 9, "mean": 3.0}},
        "active_by_hour": {"9": {"seen": 3, "active": 2}},
    }

    profile = build_rollout_intensity_profile(
        memory,
        hour=9,
        absolute_cap=8,
    )

    assert profile["reference_active_exposure_p95"] == 20
    assert profile["active_exposure_cap"] == 8
    assert profile["same_hour_mean_exposures"] == 3.0
    assert profile["same_hour_active_rate"] == 2 / 3
    assert profile["calibration_source"] == "talkingdata_day1_3_habit_memory"


def test_rollout_intensity_profile_rejects_missing_reference_samples() -> None:
    try:
        build_rollout_intensity_profile({}, hour=9, absolute_cap=8)
    except ValueError as exc:
        assert "no active exposure calibration samples" in str(exc)
    else:
        raise AssertionError("missing calibration samples must fail")


def test_calibrated_intensity_preserves_zero_history_and_rejects_other_days() -> None:
    memory = {
        "replay_days": [1, 2, 3],
        "intensity_by_hour": {"9": {"count": 3, "sum": 0}},
        "active_by_hour": {"9": {"seen": 3, "active": 0}},
    }
    profile = build_calibrated_intensity_profile(memory, hour=9)
    assert profile["same_hour_active_rate"] == profile["same_hour_mean_exposures"] == 0
    assert profile["exposures_if_active"] == 1
    with pytest.raises(ValueError, match="three observations"):
        build_calibrated_intensity_profile(memory, hour=2)
    memory["replay_days"].append(4)
    with pytest.raises(ValueError, match="1, 2 and 3 only"):
        build_calibrated_intensity_profile(memory, hour=9)
