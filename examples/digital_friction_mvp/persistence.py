from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def stage_explanation_table_name(exp_id: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_mvp_stage_explanation"


def ensure_stage_explanation_table(db_path: Path, table_name: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
            stage_index INTEGER NOT NULL,
            top_negative_tags TEXT,
            top_positive_tags TEXT,
            top_primary_reasons TEXT,
            negative_tag_counts_json TEXT,
            positive_tag_counts_json TEXT,
            primary_reason_counts_json TEXT,
            summary_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_agent_stage ON {table_name} (agent_id, stage_index)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_time ON {table_name} (day, t)"
    )
    conn.commit()
    conn.close()


def write_stage_explanation_rows(
    db_path: Path,
    table_name: str,
    rows: Iterable[tuple[Any, ...]],
) -> None:
    row_list = list(rows)
    if not row_list:
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executemany(
        f"""
        INSERT INTO {table_name} (
            agent_id, day, t, step, stage_name, stage_index,
            top_negative_tags, top_positive_tags, top_primary_reasons,
            negative_tag_counts_json, positive_tag_counts_json, primary_reason_counts_json,
            summary_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row_list,
    )
    conn.commit()
    conn.close()


def append_stage_explanation_csv(
    output_path: Path,
    rows: Iterable[dict[str, Any]],
) -> None:
    row_list = list(rows)
    if not row_list:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "agent_id",
        "day",
        "t",
        "step",
        "stage_name",
        "stage_index",
        "top_negative_tags",
        "top_positive_tags",
        "top_primary_reasons",
        "negative_tag_counts_json",
        "positive_tag_counts_json",
        "primary_reason_counts_json",
        "summary_text",
    ]
    file_exists = output_path.exists()
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in row_list:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
