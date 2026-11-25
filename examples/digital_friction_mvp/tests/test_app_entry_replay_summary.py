from __future__ import annotations

import json
import sqlite3

from analysis_parallel_worlds import _compute_app_entry_replay_summary_rows


def test_app_entry_replay_summary_reads_status_json(tmp_path) -> None:
    db_path = tmp_path / "sqlite.db"
    conn = sqlite3.connect(str(db_path))
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
    status = {
        "proto_mobile_entry_decision": {
            "entry_evaluated": True,
            "selected_app_context": "finance_context",
            "entry_status": "entered_mapped_digital_task",
            "task_generated": True,
            "audit": {
                "entry_mode": "app_context_replay_bundle",
                "agent_id": 1,
                "device_id": "device-a",
                "selected_rank": 1,
                "talkingdata_day": 1,
                "hour": 9,
                "active": True,
                "active_event_app_exposures": 3,
                "task_eligible_context_exposure": True,
                "task_occurrence_gate_passed": True,
                "uses_validation_data": False,
                "bundle_hash": "bundlehash",
                "device_mapping_hash": "devicehash",
            },
        },
        "proto_app_entry_habit_memory": {
            "total_hours_seen": 1,
            "active_hours": 1,
            "inactive_hours": 0,
            "context_total_counts": {"finance_context": 3},
        },
        "proto_app_entry_context_only_rows_json": [],
        "proto_day4_replay_snapshot": {},
        "helplessness_score": 42.0,
        "trust_in_apps": 66.0,
        "avoidance_tendency": 31.0,
    }
    cur.execute(
        "INSERT INTO as_exp_mvp_status VALUES (?, ?, ?, ?)",
        (1, 0, 9 * 3600.0, json.dumps(status)),
    )
    conn.commit()

    rows = _compute_app_entry_replay_summary_rows(
        cur,
        "as_exp_mvp_status",
        manifest_row={
            "group_id": "g",
            "world_name": "baseline_low_friction",
            "exp_id": "exp",
            "status": "ok",
        },
    )

    assert len(rows) == 1
    assert rows[0]["replay_hours_seen"] == 1
    assert rows[0]["device_id"] == "device-a"
    assert rows[0]["task_generated_count"] == 1
    assert rows[0]["uses_validation_data_any"] == 0
    assert rows[0]["replay_bundle_hash"] == "bundlehash"
    assert rows[0]["habit_memory_present"] == 1
    assert rows[0]["habit_context_total_counts_json"] == '{"finance_context": 3}'
    conn.close()
