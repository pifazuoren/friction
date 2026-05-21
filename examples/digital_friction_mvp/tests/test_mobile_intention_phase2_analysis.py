from __future__ import annotations

import json
import sqlite3

from analysis_parallel_worlds import (
    _compute_mobile_entry_metrics,
    _compute_world_proto_metrics,
)


def test_mobile_entry_metrics_parse_status_json_once_per_entry() -> None:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE status_rows (
            agent_id INTEGER,
            day INTEGER,
            t REAL,
            status_json TEXT
        )
        """
    )
    decision = {
        "entry_evaluated": True,
        "selected_mobile_intention": "use_payment_or_finance",
        "mapped_task_family": "payment_risk_confirmation",
        "task_generated": True,
        "entry_status": "entered_mapped_digital_task",
        "audit": {
            "agent_id": 7,
            "day": 1,
            "tick_seconds": 3600.0,
        },
    }
    cur.executemany(
        "INSERT INTO status_rows VALUES (?, ?, ?, ?)",
        [
            (7, 1, 3600.0, json.dumps({"proto_mobile_entry_decision": decision})),
            (7, 1, 3600.0, json.dumps({"proto_mobile_entry_decision": decision})),
            (
                8,
                1,
                3600.0,
                json.dumps(
                    {
                        "proto_mobile_entry_decision": {
                            "entry_evaluated": True,
                            "selected_mobile_intention": "browse_entertainment",
                            "mapped_task_family": None,
                            "task_generated": False,
                            "entry_status": "browse_context_only",
                            "audit": {
                                "agent_id": 8,
                                "day": 1,
                                "tick_seconds": 3600.0,
                            },
                        }
                    }
                ),
            ),
        ],
    )

    metrics = _compute_mobile_entry_metrics(cur, "status_rows")

    assert metrics["mobile_entry_eval_count"] == 2
    assert metrics["mobile_entry_task_generated_count"] == 1
    assert metrics["mobile_entry_context_count"] == 1
    assert metrics["mobile_entry_task_generated_rate"] == 0.5
    assert json.loads(metrics["mobile_entry_top_intentions_json"]) == {
        "browse_entertainment": 1,
        "use_payment_or_finance": 1,
    }
    assert json.loads(metrics["mobile_entry_mapped_task_families_json"]) == {
        "payment_risk_confirmation": 1,
    }


def test_world_proto_metrics_parse_trajectory_audit_from_payload_json() -> None:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE attempt_rows (
            strategy_type TEXT,
            outcome_type TEXT,
            payload_json TEXT
        )
        """
    )
    cur.executemany(
        "INSERT INTO attempt_rows VALUES (?, ?, ?)",
        [
            (
                "attempt_self",
                "failure_after_attempt",
                json.dumps(
                    {
                        "outcome": {
                            "outcome_model_mode": "trajectory_bounded_online_mc",
                            "trajectory_status": "ok",
                            "trajectory_tvd_from_rule": 0.04,
                        }
                    }
                ),
            ),
            (
                "attempt_self",
                "success_self",
                json.dumps(
                    {
                        "outcome": {
                            "outcome_model_mode": "trajectory_shadow",
                            "trajectory_status": "low_confidence",
                            "trajectory_tvd_from_rule": 0.0,
                        }
                    }
                ),
            ),
        ],
    )

    metrics = _compute_world_proto_metrics(cur, "attempt_rows")

    assert metrics["trajectory_call_count"] == 2
    assert metrics["trajectory_low_confidence_count"] == 1
    assert metrics["trajectory_invalid_count"] == 0
    assert metrics["trajectory_mean_tvd_from_rule"] == 0.04
    assert json.loads(metrics["outcome_model_modes_json"]) == {
        "trajectory_bounded_online_mc": 1,
        "trajectory_shadow": 1,
    }
