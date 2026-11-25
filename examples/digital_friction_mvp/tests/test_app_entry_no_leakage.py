from __future__ import annotations

from pathlib import Path

import pytest

from proto.app_entry.rollout import build_rollout_input_packet


def _base_kwargs() -> dict[str, object]:
    return {
        "simulation_day": 3,
        "talkingdata_day": 4,
        "hour": 9,
        "stable_profile": {"age": 70},
        "habit_memory": {
            "replay_days": [1, 2, 3],
            "active_by_hour": {},
            "context_by_hour": {},
            "primary_context_by_hour": {},
            "context_total_counts": {},
        },
        "recent_rollout_rows": [],
        "recent_task_episodes": [],
        "latest_reflection": {},
        "helplessness": 40.0,
        "trust": 60.0,
        "avoidance": 35.0,
        "environment": {"friction_level": 1},
        "intensity_profile": {"active_exposure_cap": 4},
    }


def test_rollout_packet_drops_raw_world_name() -> None:
    kwargs = _base_kwargs()
    kwargs["environment"] = {
        "world_name": "high_friction_low_assist",
        "friction_level": 2,
    }

    packet = build_rollout_input_packet(**kwargs)

    assert "world_name" not in packet["environment_cues"]
    assert "validation" not in str(packet).lower()


def test_rollout_packet_rejects_validation_evidence_in_recent_rows() -> None:
    kwargs = _base_kwargs()
    kwargs["recent_rollout_rows"] = [
        {"hour": 8, "heldout_primary_context": "finance_context"}
    ]

    with pytest.raises(ValueError, match="forbidden rollout evidence"):
        build_rollout_input_packet(**kwargs)


def test_rollout_packet_keeps_behavior_but_drops_false_validation_audit() -> None:
    kwargs = _base_kwargs()
    kwargs["recent_rollout_rows"] = [
        {
            "talkingdata_day": 4,
            "hour": 8,
            "active": True,
            "active_event_app_exposures": 2,
            "app_context_counts": {"finance_context": 2},
            "primary_context": "finance_context",
            "uses_validation_data": False,
            "needs_prompt_hash": "audit-only",
        }
    ]

    packet = build_rollout_input_packet(**kwargs)

    assert packet["recent_simulated_bundles"] == [
        {
            "talkingdata_day": 4,
            "hour": 8,
            "active": True,
            "active_event_app_exposures": 2,
            "app_context_counts": {"finance_context": 2},
            "primary_context": "finance_context",
        }
    ]
    assert "validation" not in str(packet).lower()
    assert "prompt_hash" not in str(packet).lower()


def test_rollout_packet_rejects_true_validation_audit_flag() -> None:
    kwargs = _base_kwargs()
    kwargs["recent_rollout_rows"] = [
        {"hour": 8, "uses_validation_data": True}
    ]

    with pytest.raises(ValueError, match="uses_validation_data"):
        build_rollout_input_packet(**kwargs)


def test_runtime_modules_do_not_import_post_run_validation() -> None:
    for path in (
        "examples/digital_friction_mvp/proto/app_entry/rollout.py",
        "examples/digital_friction_mvp/proto/agent.py",
        "examples/digital_friction_mvp/proto/runtime.py",
    ):
        source = Path(path).read_text(encoding="utf-8")
        assert "analysis_app_entry_validation" not in source
