from __future__ import annotations

import pytest

from proto.app_entry.bundle import (
    HourlyAppEntryBundle,
    NO_APP_CONTEXT,
    derive_primary_context,
)


def test_derive_primary_context_uses_rollout_v1_tie_rule() -> None:
    counts = {
        "communication_social_context": 2,
        "finance_context": 2,
    }

    assert derive_primary_context(counts) == "finance_context"


def test_derive_primary_context_uses_no_app_sentinel_for_empty_counts() -> None:
    assert derive_primary_context({}) == NO_APP_CONTEXT


def test_hourly_bundle_parses_inactive_hour() -> None:
    bundle = HourlyAppEntryBundle.from_row(
        {
            "device_id": "device-a",
            "day_index": "1",
            "hour": "0",
            "active": "false",
            "active_event_app_exposures": "0",
            "app_context_counts_json": "{}",
            "primary_context": NO_APP_CONTEXT,
            "source": "talkingdata_inactive_hour",
        }
    )

    assert bundle.active is False
    assert bundle.primary_context == NO_APP_CONTEXT
    assert bundle.app_context_counts == {}
    assert bundle.context_share_distribution() == {}


def test_hourly_bundle_parses_active_hour() -> None:
    bundle = HourlyAppEntryBundle.from_row(
        {
            "device_id": "device-a",
            "day_index": "1",
            "hour": "9",
            "active": "true",
            "active_event_app_exposures": "3",
            "app_context_counts_json": (
                '{"finance_context": 2, "communication_social_context": 1}'
            ),
            "primary_context": "finance_context",
            "source": "talkingdata_active_hour",
        }
    )

    assert bundle.active is True
    assert bundle.is_task_eligible_primary() is True
    assert bundle.context_share_distribution()["finance_context"] == pytest.approx(
        2 / 3
    )


def test_hourly_bundle_rejects_count_mismatch() -> None:
    with pytest.raises(ValueError, match="sum\\(app_context_counts\\)"):
        HourlyAppEntryBundle.from_row(
            {
                "device_id": "device-a",
                "day_index": "1",
                "hour": "9",
                "active": "true",
                "active_event_app_exposures": "3",
                "app_context_counts_json": '{"finance_context": 2}',
                "primary_context": "finance_context",
            }
        )


def test_hourly_bundle_rejects_no_app_context_as_active_primary() -> None:
    with pytest.raises(ValueError, match="active hour cannot use no_app_context"):
        HourlyAppEntryBundle.from_row(
            {
                "device_id": "device-a",
                "day_index": "1",
                "hour": "9",
                "active": "true",
                "active_event_app_exposures": "1",
                "app_context_counts_json": '{"finance_context": 1}',
                "primary_context": NO_APP_CONTEXT,
            }
        )
