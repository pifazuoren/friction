from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from analysis_parallel_worlds import _compute_world_proto_metrics
from proto.metrics import summarize_stage_attempts


def test_undelivered_request_counts_as_seeking_help_in_stage_and_world_metrics():
    request = {
        "requested_strategy_type": "seek_help_then_attempt",
        "strategy_type": "attempt_self",
        "outcome_type": "success_self",
        "help_used": False,
    }
    old_independent = {"strategy_type": "attempt_self", "outcome_type": "success_self", "help_used": False}
    old_helped = {"strategy_type": "seek_help_then_attempt", "outcome_type": "success_with_help", "help_used": True}
    rows = [request, old_independent, old_helped]
    stage = summarize_stage_attempts(
        rows=rows, helplessness_start_avg=40, helplessness_end_avg=40,
        day=4, t=0, step=1, stage_name="steady", stage_index=0, agent_count=1,
    )
    assert stage["help_seek_rate"] == 2 / 3
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE attempts(day INT, strategy_type TEXT, outcome_type TEXT, payload_json TEXT)")
        db.executemany(
            "INSERT INTO attempts VALUES (4, ?, ?, ?)",
            [(r["strategy_type"], r["outcome_type"], json.dumps(r)) for r in rows],
        )
        world = _compute_world_proto_metrics(db.cursor(), "attempts")
    assert world["help_seek_count"] == 2
    assert world["help_seek_rate"] == stage["help_seek_rate"]


def _table_name(exp_id: str, suffix: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_{suffix}"


def _write_proto_attempt_table(conn: sqlite3.Connection, exp_id: str, rows: list[tuple]) -> None:
    table = _table_name(exp_id, "proto_attempt_rows")
    conn.execute(
        f"""
        CREATE TABLE {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            t REAL NOT NULL,
            step INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            task_id TEXT,
            task_family TEXT,
            friction_type TEXT,
            strategy_type TEXT,
            outcome_type TEXT,
            support_quality INTEGER,
            event_level_uncontrollability INTEGER,
            rule_event_level_uncontrollability INTEGER,
            uncontrollability_source TEXT,
            uncontrollability_llm_confidence REAL,
            helplessness_before REAL,
            helplessness_after REAL,
            helplessness_delta REAL,
            strategy_weights_json TEXT,
            payload_json TEXT
        )
        """
    )
    conn.executemany(
        f"""
        INSERT INTO {table} (
            agent_id, day, t, step, stage_name, task_id, task_family, friction_type,
            strategy_type, outcome_type, support_quality, event_level_uncontrollability,
            rule_event_level_uncontrollability, uncontrollability_source,
            uncontrollability_llm_confidence,
            helplessness_before, helplessness_after, helplessness_delta,
            strategy_weights_json, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _write_proto_stage_table(conn: sqlite3.Connection, exp_id: str, rows: list[tuple]) -> None:
    table = _table_name(exp_id, "proto_stage_summary")
    conn.execute(
        f"""
        CREATE TABLE {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day INTEGER NOT NULL,
            t REAL NOT NULL,
            step INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            stage_index INTEGER NOT NULL,
            agent_count INTEGER NOT NULL,
            task_count INTEGER NOT NULL,
            attempt_rate REAL,
            success_rate REAL,
            help_seek_rate REAL,
            abandon_rate REAL,
            negative_feedback_rate REAL,
            helplessness_delta REAL
        )
        """
    )
    conn.executemany(
        f"""
        INSERT INTO {table} (
            day, t, step, stage_name, stage_index, agent_count, task_count,
            attempt_rate, success_rate, help_seek_rate, abandon_rate,
            negative_feedback_rate, helplessness_delta
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _write_status_table(conn: sqlite3.Connection, exp_id: str, rows: list[tuple]) -> None:
    table = _table_name(exp_id, "mvp_status")
    conn.execute(
        f"""
        CREATE TABLE {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            t REAL NOT NULL,
            helplessness_score REAL,
            trust_in_apps REAL,
            avoidance_tendency REAL
        )
        """
    )
    conn.executemany(
        f"""
        INSERT INTO {table} (
            agent_id, day, t, helplessness_score, trust_in_apps, avoidance_tendency
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_parallel_summary_outputs_world_stage_and_plots(tmp_path: Path) -> None:
    db_path = tmp_path / "sqlite.db"
    manifest_path = tmp_path / "manifest.json"
    profiles_path = tmp_path / "profiles.json"
    world_summary_csv = tmp_path / "parallel_world_summary_test.csv"
    stage_summary_csv = tmp_path / "parallel_stage_summary_test.csv"
    plot_dir = tmp_path / "parallel_world_plots_test"

    manifest_rows = [
        {
            "group_id": "g1",
            "pair_index": 0,
            "pair_seed": 101,
            "world_order": 0,
            "world_name": "baseline_low_friction",
            "exp_id": "exp-a",
            "status": "ok",
            "agent_count": 1,
            "total_days": 2,
        },
        {
            "group_id": "g1",
            "pair_index": 0,
            "pair_seed": 101,
            "world_order": 1,
            "world_name": "high_friction_high_assist",
            "exp_id": "exp-b",
            "status": "ok",
            "agent_count": 1,
            "total_days": 2,
        },
    ]
    manifest_path.write_text(json.dumps(manifest_rows, ensure_ascii=False), encoding="utf-8")
    profiles_path.write_text("[]", encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    try:
        _write_proto_attempt_table(
            conn,
            "exp-a",
            [
                (
                    1,
                    0,
                    1.0,
                    1,
                    "steady",
                    "task-a",
                    "login_verification",
                    "verification",
                    "attempt_self",
                    "success_self",
                    1,
                    0,
                    0,
                    "rule",
                    0.0,
                    30.0,
                    24.0,
                    -6.0,
                    json.dumps({"attempt_self": 0.7, "seek_help_then_attempt": 0.2, "avoid": 0.1}),
                    "{}",
                ),
                (
                    1,
                    0,
                    2.0,
                    2,
                    "steady",
                    "task-b",
                    "payment_checkout",
                    "payment_risk_popup",
                    "avoid",
                    "avoid_without_attempt",
                    1,
                    0,
                    0,
                    "rule",
                    0.0,
                    24.0,
                    25.0,
                    1.0,
                    json.dumps({"attempt_self": 0.2, "seek_help_then_attempt": 0.2, "avoid": 0.6}),
                    "{}",
                ),
            ],
        )
        _write_proto_attempt_table(
            conn,
            "exp-b",
            [
                (
                    1,
                    0,
                    1.0,
                    1,
                    "steady",
                    "task-c",
                    "appointment_registration",
                    "form_complexity",
                    "seek_help_then_attempt",
                    "success_with_help",
                    2,
                    0,
                    0,
                    "rule_success_short_circuit",
                    0.0,
                    35.0,
                    31.0,
                    -4.0,
                    json.dumps({"attempt_self": 0.1, "seek_help_then_attempt": 0.7, "avoid": 0.2}),
                    "{}",
                ),
                (
                    1,
                    0,
                    2.0,
                    2,
                    "steady",
                    "task-d",
                    "health_info_lookup",
                    "information_overload",
                    "seek_help_then_attempt",
                    "failure_even_with_help",
                    2,
                    2,
                    1,
                    "hybrid_shifted",
                    0.82,
                    31.0,
                    37.0,
                    6.0,
                    json.dumps({"attempt_self": 0.1, "seek_help_then_attempt": 0.65, "avoid": 0.25}),
                    "{}",
                ),
            ],
        )
        _write_proto_stage_table(
            conn,
            "exp-a",
            [(1, 1800.0, 11800, "steady", 0, 1, 2, 0.5, 0.5, 0.0, 0.0, 0.0, -5.0)],
        )
        _write_proto_stage_table(
            conn,
            "exp-b",
            [(1, 1800.0, 11800, "steady", 0, 1, 2, 1.0, 0.5, 1.0, 0.0, 0.5, 2.0)],
        )
        _write_status_table(
            conn,
            "exp-a",
            [
                (1, 0, 0.0, 30.0, 60.0, 20.0),
                (1, 1, 1800.0, 25.0, 63.0, 18.0),
            ],
        )
        _write_status_table(
            conn,
            "exp-b",
            [
                (1, 0, 0.0, 35.0, 58.0, 24.0),
                (1, 1, 1800.0, 37.0, 57.0, 26.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    script_path = (
        Path(__file__).resolve().parents[1] / "analysis_parallel_worlds.py"
    )
    subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--manifest",
            str(manifest_path),
            "--db-path",
            str(db_path),
            "--profiles-path",
            str(profiles_path),
            "--out-csv",
            str(world_summary_csv),
            "--out-stage-csv",
            str(stage_summary_csv),
            "--plot-dir",
            str(plot_dir),
        ],
        check=True,
    )

    assert world_summary_csv.exists()
    assert stage_summary_csv.exists()
    world_rows = list(csv.DictReader(world_summary_csv.open("r", encoding="utf-8")))
    stage_rows = list(csv.DictReader(stage_summary_csv.open("r", encoding="utf-8")))
    assert len(world_rows) == 2
    assert len(stage_rows) == 2
    assert "attempt_rate" in world_rows[0]
    assert "help_seek_rate" in world_rows[0]
    assert "stage_name" in stage_rows[0]

    for filename in (
        "attempt_rate.png",
        "success_rate.png",
        "help_seek_rate.png",
        "abandon_rate.png",
        "negative_feedback_rate.png",
        "helplessness_delta.png",
    ):
        assert (plot_dir / filename).exists()
