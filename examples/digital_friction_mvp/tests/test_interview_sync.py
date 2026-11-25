from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import interview_sync


class _FakeDBWriter:
    def __init__(self, sqlite_path: Path, exp_id: str = "exp-test") -> None:
        self._sqlite_path = sqlite_path
        self.exp_id = exp_id
        self.logged_metrics: list[tuple[str, float, int]] = []

    async def log_metric(self, metrics):
        self.logged_metrics.extend(metrics)


class _FakeEnv:
    def __init__(self) -> None:
        self.environment = {
            "digital_stage": "baseline_low_friction:steady",
            "stage_name": "steady",
        }

    def get_datetime(self):
        return 1, 3600.0


class _FakeSimulation:
    def __init__(self, sqlite_path: Path) -> None:
        self._database_writer = _FakeDBWriter(sqlite_path)
        self.environment = _FakeEnv()
        self.status_store = {
            1: {
                "proto_stage_interview_history": [],
                "proto_stage_interview": {},
                "proto_final_interview": {},
            }
        }

    async def gather(self, key, agent_ids, keep_id=True):
        assert keep_id is True
        return {
            int(agent_id): self.status_store.get(int(agent_id), {}).get(key)
            for agent_id in agent_ids
        }

    async def update(self, agent_ids, key, value):
        for agent_id in agent_ids:
            self.status_store.setdefault(int(agent_id), {})[key] = value


def _create_dialog_table(db_path: Path, exp_id: str) -> str:
    table_name = f"as_{exp_id.replace('-', '_')}_agent_dialog"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                id INTEGER,
                day INTEGER,
                t REAL,
                type INTEGER,
                speaker TEXT,
                content TEXT,
                created_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    return table_name


def test_sync_interview_feedback_updates_stage_and_final_status(tmp_path: Path) -> None:
    db_path = tmp_path / "dialogs.sqlite"
    exp_id = "exp-test"
    table_name = _create_dialog_table(db_path, exp_id)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            f"""
            INSERT INTO {table_name} (id, day, t, type, speaker, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    1,
                    3600.0,
                    2,
                    "user",
                    "[PROTO_STAGE_INTERVIEW_V1][stage=steady][index=1] test",
                    "2026-03-25T00:00:00Z",
                ),
                (
                    1,
                    1,
                    3600.0,
                    2,
                    "",
                    (
                        '{"stage_name":"steady","stage_index":1,'
                        '"main_difficulty_source":"verification_friction",'
                        '"support_comment":"limited","future_intention":"seek_help",'
                        '"short_quote":"如果有人先帮我看一眼，我会更敢继续。",'
                        '"confidence":0.82,"source":"llm","status":"ok"}'
                    ),
                    "2026-03-25T00:00:01Z",
                ),
                (
                    1,
                    2,
                    7200.0,
                    2,
                    "user",
                    "[PROTO_FINAL_INTERVIEW_V1] test",
                    "2026-03-25T00:10:00Z",
                ),
                (
                    1,
                    2,
                    7200.0,
                    2,
                    "",
                    (
                        '{"overall_trajectory":"mixed","main_barrier":"risk_concern",'
                        '"support_takeaway":"helpful","future_orientation":"seek_help",'
                        '"short_quote":"我不是完全不会，只是怕再踩坑。",'
                        '"confidence":0.79,"source":"llm","status":"ok"}'
                    ),
                    "2026-03-25T00:10:01Z",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    simulation = _FakeSimulation(db_path)
    interview_sync._LAST_INTERVIEW_SYNC_ROWID = None
    simulation._database_writer.exp_id = exp_id

    asyncio.run(interview_sync.sync_interview_feedback(simulation))

    stage_result = simulation.status_store[1]["proto_stage_interview"]
    final_result = simulation.status_store[1]["proto_final_interview"]
    assert stage_result["future_intention"] == "seek_help"
    assert stage_result["stage_name"] == "steady"
    assert len(simulation.status_store[1]["proto_stage_interview_history"]) == 1
    assert final_result["future_orientation"] == "seek_help"
    metric_names = {name for name, _, _ in simulation._database_writer.logged_metrics}
    assert "baseline_low_friction:steady.stage_interview_count" in metric_names
    assert "final.interview_count" in metric_names


def test_sync_interview_feedback_preserves_raw_answer_for_parse_failure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "dialogs_bad.sqlite"
    exp_id = "exp-bad"
    table_name = _create_dialog_table(db_path, exp_id)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            f"""
            INSERT INTO {table_name} (id, day, t, type, speaker, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    1,
                    3600.0,
                    2,
                    "user",
                    "[PROTO_STAGE_INTERVIEW_V1][stage=steady][index=1] test",
                    "2026-03-25T00:00:00Z",
                ),
                (
                    1,
                    1,
                    3600.0,
                    2,
                    "",
                    "not-json-answer",
                    "2026-03-25T00:00:01Z",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    simulation = _FakeSimulation(db_path)
    interview_sync._LAST_INTERVIEW_SYNC_ROWID = None
    simulation._database_writer.exp_id = exp_id

    asyncio.run(interview_sync.sync_interview_feedback(simulation))

    stage_result = simulation.status_store[1]["proto_stage_interview"]
    assert stage_result["status"] == "parse_failed"
    assert stage_result["raw_answer"] == "not-json-answer"
