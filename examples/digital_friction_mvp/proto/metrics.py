from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def attempt_rows_table_name(exp_id: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_proto_attempt_rows"


def stage_summary_table_name(exp_id: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_proto_stage_summary"


def ensure_attempt_rows_table(db_path: Path, table_name: str) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
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
            event_attribution_scope_amplitude REAL,
            scope_spillover_total REAL,
            scope_spillover_targets_json TEXT,
            helplessness_before REAL,
            helplessness_after REAL,
            helplessness_delta REAL,
            strategy_weights_json TEXT,
            payload_json TEXT
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_stage_time ON {table_name} (stage_name, day, t)"
    )
    existing_columns = {
        row[1]
        for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_type in (
        ("event_level_uncontrollability", "INTEGER"),
        ("rule_event_level_uncontrollability", "INTEGER"),
        ("uncontrollability_source", "TEXT"),
        ("uncontrollability_llm_confidence", "REAL"),
        ("event_attribution_scope_amplitude", "REAL"),
        ("scope_spillover_total", "REAL"),
        ("scope_spillover_targets_json", "TEXT"),
    ):
        if column_name not in existing_columns:
            cur.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )
    conn.commit()
    conn.close()


def ensure_stage_summary_table(db_path: Path, table_name: str) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
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
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_stage ON {table_name} (stage_index, day, t)"
    )
    conn.commit()
    conn.close()


def write_attempt_rows(
    db_path: Path,
    table_name: str,
    rows: Iterable[dict[str, Any]],
) -> None:
    row_list = list(rows)
    if not row_list:
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executemany(
        f"""
        INSERT INTO {table_name} (
            agent_id, day, t, step, stage_name,
            task_id, task_family, friction_type, strategy_type, outcome_type,
            support_quality, event_level_uncontrollability,
            rule_event_level_uncontrollability, uncontrollability_source,
            uncontrollability_llm_confidence, event_attribution_scope_amplitude,
            scope_spillover_total, scope_spillover_targets_json,
            helplessness_before, helplessness_after, helplessness_delta,
            strategy_weights_json, payload_json
        ) VALUES (
            :agent_id, :day, :t, :step, :stage_name,
            :task_id, :task_family, :friction_type, :strategy_type, :outcome_type,
            :support_quality, :event_level_uncontrollability,
            :rule_event_level_uncontrollability, :uncontrollability_source,
            :uncontrollability_llm_confidence, :event_attribution_scope_amplitude,
            :scope_spillover_total, :scope_spillover_targets_json,
            :helplessness_before, :helplessness_after, :helplessness_delta,
            :strategy_weights_json, :payload_json
        )
        """,
        row_list,
    )
    conn.commit()
    conn.close()


def write_stage_summary_rows(
    db_path: Path,
    table_name: str,
    rows: Iterable[dict[str, Any]],
) -> None:
    row_list = list(rows)
    if not row_list:
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executemany(
        f"""
        INSERT INTO {table_name} (
            day, t, step, stage_name, stage_index, agent_count, task_count,
            attempt_rate, success_rate, help_seek_rate, abandon_rate,
            negative_feedback_rate, helplessness_delta
        ) VALUES (
            :day, :t, :step, :stage_name, :stage_index, :agent_count, :task_count,
            :attempt_rate, :success_rate, :help_seek_rate, :abandon_rate,
            :negative_feedback_rate, :helplessness_delta
        )
        """,
        row_list,
    )
    conn.commit()
    conn.close()


def append_csv(output_path: Path, rows: Iterable[dict[str, Any]]) -> None:
    row_list = list(rows)
    if not row_list:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(row_list[0].keys())
    file_exists = output_path.exists()
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in row_list:
            writer.writerow(row)


def summarize_stage_attempts(
    *,
    rows: list[dict[str, Any]],
    helplessness_start_avg: float,
    helplessness_end_avg: float,
    day: int,
    t: float,
    step: int,
    stage_name: str,
    stage_index: int,
    agent_count: int,
) -> dict[str, Any]:
    total = len(rows)
    attempts = sum(1 for row in rows if row.get("outcome_type") != "avoid_without_attempt")
    successes = sum(
        1
        for row in rows
        if row.get("outcome_type") in {"success_self", "success_with_help"}
    )
    help_used = sum(1 for row in rows if bool(row.get("help_used")))
    abandons = sum(1 for row in rows if row.get("outcome_type") == "abandon_midway")
    negative_feedbacks = sum(1 for row in rows if bool(row.get("negative_feedback")))
    denominator = float(total) if total else 1.0
    return {
        "day": int(day),
        "t": float(t),
        "step": int(step),
        "stage_name": stage_name,
        "stage_index": int(stage_index),
        "agent_count": int(agent_count),
        "task_count": int(total),
        "attempt_rate": float(attempts / denominator),
        "success_rate": float(successes / denominator),
        "help_seek_rate": float(help_used / denominator),
        "abandon_rate": float(abandons / denominator),
        "negative_feedback_rate": float(negative_feedbacks / denominator),
        "helplessness_delta": float(helplessness_end_avg - helplessness_start_avg),
    }
