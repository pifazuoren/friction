from __future__ import annotations

import json
import sqlite3

from analysis_parallel_worlds import (
    _compute_app_entry_rollout_error_rows,
    _compute_app_entry_rollout_hourly_rows,
)


def test_rollout_summary_exports_unique_hourly_rows(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "sqlite.db"))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE as_exp_mvp_status (
            agent_id INTEGER,
            day INTEGER,
            t REAL,
            status_json TEXT
        )
        """
    )
    rollout_row = {
        "device_id": "device-a",
        "simulation_day": 3,
        "talkingdata_day": 4,
        "hour": 9,
        "active": True,
        "active_event_app_exposures": 3,
        "app_context_counts": {"finance_context": 3},
        "primary_context": "finance_context",
        "source": "llm_memory_rollout",
        "dominant_need": "finance_need",
        "need_pressures": {"finance_need": 0.8},
        "attitude": 0.7,
        "subjective_norm": 0.5,
        "perceived_control": 0.4,
        "plan_confidence": 0.8,
        "entry_status": "entered_mapped_digital_task",
        "task_generated": True,
        "needs_prompt_version": "digital_needs_v1",
        "needs_prompt_hash": "needhash",
        "needs_json_attempts_used": 1,
        "needs_actual_requests": 1,
        "needs_repair_requests": 0,
        "plan_prompt_version": "app_entry_plan_v1",
        "plan_prompt_hash": "planhash",
        "plan_json_attempts_used": 2,
        "plan_actual_requests": 3,
        "plan_repair_requests": 1,
        "input_packet_hash": "inputhash",
        "uses_validation_data": False,
    }
    status = {"proto_app_entry_rollout_rows_json": [rollout_row]}
    for t in (9 * 3600, 10 * 3600):
        cur.execute(
            "INSERT INTO as_exp_mvp_status VALUES (?, ?, ?, ?)",
            (1, 3, t, json.dumps(status)),
        )
    conn.commit()

    rows = _compute_app_entry_rollout_hourly_rows(
        cur,
        "as_exp_mvp_status",
        manifest_row={
            "group_id": "g",
            "world_name": "baseline_low_friction",
            "exp_id": "exp",
            "status": "ok",
            "config_fingerprint": "config123",
        },
    )

    assert len(rows) == 1
    assert rows[0]["device_id"] == "device-a"
    assert rows[0]["talkingdata_day"] == 4
    assert rows[0]["uses_validation_data"] == 0
    assert rows[0]["config_fingerprint"] == "config123"
    assert rows[0]["needs_actual_requests"] == 1
    assert rows[0]["plan_actual_requests"] == 3
    assert rows[0]["plan_repair_requests"] == 1
    assert rows[0]["app_context_counts_json"] == '{"finance_context": 3}'
    conn.close()


def test_rollout_summary_exports_error_hours_separately(tmp_path) -> None:
    conn = sqlite3.connect(str(tmp_path / "sqlite.db"))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE as_exp_mvp_status (
            agent_id INTEGER,
            day INTEGER,
            t REAL,
            status_json TEXT
        )
        """
    )
    error_row = {
        "device_id": "device-a",
        "simulation_day": 3,
        "talkingdata_day": 4,
        "hour": 9,
        "entry_status": "llm_rollout_error",
        "bundle_generated": False,
        "task_generated": False,
        "error_type": "ValueError",
        "error_message": "invalid plan output",
        "error_hash": "errorhash",
        "uses_validation_data": False,
    }
    status = {"proto_app_entry_rollout_error_rows_json": [error_row]}
    cur.execute(
        "INSERT INTO as_exp_mvp_status VALUES (?, ?, ?, ?)",
        (1, 3, 9 * 3600, json.dumps(status)),
    )
    conn.commit()

    rows = _compute_app_entry_rollout_error_rows(
        cur,
        "as_exp_mvp_status",
        manifest_row={
            "group_id": "g",
            "world_name": "baseline_low_friction",
            "exp_id": "exp",
            "status": "ok",
            "config_fingerprint": "config123",
        },
    )

    assert len(rows) == 1
    assert rows[0]["entry_status"] == "llm_rollout_error"
    assert rows[0]["bundle_generated"] == 0
    assert rows[0]["error_hash"] == "errorhash"
    assert rows[0]["uses_validation_data"] == 0
    conn.close()
