import csv
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_social_memory_run import WORLD, check_run
from proto.metrics import ensure_attempt_rows_table, attempt_rows_table_name


def fixture_run(folder, case="complete", days=7):
    group, exp = "synthetic", str(uuid4())
    device = "local-device"
    manifest = dict(group_id=group, world_name=WORLD, exp_id=exp, status="ok", agent_count=1, return_code=0,
                    qc_config_match=1, stage_mode="single", stage_count=1, stage_days=days, total_days=days,
                    decision_interval_minutes=60, proto_app_entry_replay_days="1,2,3", config_fingerprint="fingerprint",
                    proto_task_entry_mode="app_context_replay_then_llm_rollout", uses_forced_replay=1)
    (folder / f"exp_group_manifest_{group}.json").write_text(json.dumps([manifest]))
    meta = dict(group_id=group, world_name=WORLD, exp_id=exp, agent_id=1, device_id=device)

    def write_csv(name, rows, fields):
        with (folder / f"{name}_{group}.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    replay = dict(**meta, replay_hours_seen=72, uses_validation_data_any=0, day4_snapshot_created=1)
    write_csv("app_entry_replay_summary", [replay], replay)
    db = folder / "db"
    table = attempt_rows_table_name(exp)
    ensure_attempt_rows_table(db, table)
    status_table = "as_" + exp.replace("-", "_") + "_mvp_status"
    prior = {}
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TABLE {status_table} (day INTEGER,t REAL,agent_id INTEGER,status_json TEXT)")
        for day in range(1, 4):
            habit = dict(replay_days=list(range(1, day + 1)), last_updated_day=day,
                         last_updated_hour=23, device_id=device, total_hours_seen=24*day,
                         active_by_hour={str(h): {"seen": day} for h in range(24)})
            if case == "repeated" and day == 2:
                habit["active_by_hour"]["12"]["seen"] = 3
                habit["active_by_hour"]["13"]["seen"] = 1
            state = {"proto_app_entry_habit_memory": habit}
            if day == 3:
                state["proto_day4_replay_snapshot"] = dict(agent_id=1, device_id=device, world=WORLD,
                    created_at_talkingdata_day=3, created_at_hour=23, completed_replay_days=[1,2,3],
                    app_entry_habit_memory=habit)
            conn.execute(f"INSERT INTO {status_table} VALUES (?,?,?,?)", (day, 1, 1, json.dumps(state)))
        for zero_day in (3, 4):
            if case == "no_tasks" or (case == "no_strategy" and zero_day == 4):
                continue
            episode = f"task{zero_day}@{zero_day}/3600"
            prior_record = dict(episode_id=episode, tick_seconds=3600, day=zero_day, task_id=f"task{zero_day}",
                                task_family="health", requested_strategy_type="seek_help_then_attempt",
                                strategy_type="attempt_self", outcome_type="success_self", help_used=False,
                                support_request_id=f"support{zero_day}", support_delivery_status="not_delivered")
            if zero_day == 3:
                prior = prior_record
            data = {**prior_record, "outcome": {"help_used": False}}
            conn.execute(f"INSERT INTO {table}(agent_id,day,t,step,stage_name,task_id,task_family,strategy_type,"
                         "outcome_type,payload_json) VALUES (1,?,3600,1,'single',?,'health','attempt_self',"
                         "'success_self',?)", (zero_day, f"task{zero_day}", json.dumps(data)))

    def record(day, hour, module, kind, **fields):
        return dict(schema_version=1, group_id=group, world=WORLD, agent_id=1, talkingdata_day=day,
                    simulation_day=day-1, hour=hour, tick_seconds=hour*3600, module=module, kind=kind, **fields)

    rollout, errors, trace = [], [], []
    error_fields = [*meta, "config_fingerprint", "entry_status", "simulation_day", "talkingdata_day",
                    "hour", "uses_validation_data", "bundle_generated"]
    for day in range(4, days + 1):
        for hour in range(24):
            fail = day == 6 and hour == 13 and case in {"declared_error", "fake_error", "overlap"}
            row = dict(**meta, config_fingerprint="fingerprint", simulation_day=day-1, talkingdata_day=day,
                       hour=hour, uses_validation_data=0)
            if fail:
                errors.append(dict(**row, entry_status="llm_rollout_error", bundle_generated=0))
                if case != "fake_error":
                    trace.append(record(day, hour, "app_entry", "entry", status="llm_rollout_error"))
            if not fail or case == "overlap":
                rollout.append(dict(**row, source="llm_memory_rollout", needs_actual_requests=1, plan_actual_requests=1))
            modules = ["app_needs", "app_plan"]
            if fail:
                modules.remove("app_plan")
                trace.append(record(day, hour, "app_needs", "error", error_type="transport"))
            if day == 5 and hour == 1 and case not in {"no_tasks", "no_strategy"}:
                modules.append("strategy")
                trace.append(record(5, 1, "task", "decision", status="completed", episode_id="task4@4/3600",
                                    action="avoid" if case == "wrong_outcome" else "attempt_self", outcome="success_self"))
            for module in modules:
                episodes = [prior] if prior and day == 5 else []
                if case == "wrong_episode" and module == "strategy":
                    episodes = [{**prior, "support_delivery_status": "delivered"}]
                memory = {"recent_task_episodes": episodes}
                packet = {"inputs": memory} if module != "strategy" else {
                    "task_relevant_memory": memory, "task": {"task_family": "health", "task_id": "task4"}}
                trace.append(record(day, hour, module, "request", phase="initial", call_id=uuid4().hex,
                                    messages=[{"role": "user", "content": "Return one JSON object only.\n" + json.dumps(packet)}]))
    if case == "duplicate":
        rollout[-1] = dict(rollout[-2])
    if case == "mixed_trace":
        trace[0]["group_id"] = "other"
    write_csv("app_entry_rollout_hourly", rollout, rollout[0])
    write_csv("app_entry_rollout_errors", errors, error_fields)
    trace_dir = folder / "trace"
    trace_dir.mkdir()
    if case != "no_trace":
        (trace_dir / "llm-requests-123.jsonl").write_text("\n".join(json.dumps(r) for r in trace))
    return check_run(folder, group, db, trace_dir, expected_days=days)


def test_complete_week_with_source_episode(tmp_path):
    report = fixture_run(tmp_path)
    assert not report["issues"] and report["run_complete"]
    assert report["replay"]["verified_hours"] == 72 and report["rollout"]["valid_hours"] == 96
    assert report["cross_day_status"] == "verified"
    example = report["cross_day"]["same_family_strategy_example"]
    assert example["day4"]["support_delivery_status"] == "not_delivered"
    assert example["day5"]["episode_id"] == "task4@4/3600"


def test_five_day_run_uses_two_rollout_days_and_preserves_default_week_check(tmp_path):
    report = fixture_run(tmp_path, days=5)
    assert report["run_complete"] and not report["issues"]
    assert report["rollout"]["expected_hours"] == report["rollout"]["valid_hours"] == 48
    assert report["cross_day_status"] == "verified"
    assert not check_run(tmp_path, "synthetic", tmp_path / "db", tmp_path / "trace")["run_complete"]


@pytest.mark.parametrize("case", ["repeated", "duplicate", "overlap", "fake_error", "mixed_trace", "no_trace"])
def test_incomplete_or_wrong_run(tmp_path, case):
    report = fixture_run(tmp_path, case)
    assert report["issues"] and not report["run_complete"]


@pytest.mark.parametrize("case", ["no_tasks", "no_strategy"])
def test_natural_absence_is_reported(tmp_path, case):
    report = fixture_run(tmp_path, case)
    assert report["run_complete"] and not report["issues"]
    assert report["cross_day_status"] == "no_natural_opportunity"


def test_wrong_recorded_delivery_cannot_prove_strategy_memory(tmp_path):
    report = fixture_run(tmp_path, "wrong_episode")
    assert report["run_complete"] and report["cross_day_status"] == "missing_evidence"
    assert report["cross_day"]["modules"]["strategy"]["status"] == "missing_evidence"


def test_trace_and_sql_decision_must_agree(tmp_path):
    report = fixture_run(tmp_path, "wrong_outcome")
    assert report["cross_day_status"] == "missing_evidence"
    assert report["cross_day"]["day5_decision_db_disagreements"] == ["task4@4/3600"]


def test_needs_failure_counts_as_processed_hour_only(tmp_path):
    report = fixture_run(tmp_path, "declared_error")
    assert not report["issues"] and report["run_complete"]
    assert report["rollout"]["accounted_hours"] == 96 and report["rollout"]["valid_hours"] == 95
    assert report["cross_day"]["plan_skipped_after_recorded_needs_error"] == [(6, 13)]


def test_missing_input_writes_no_database(tmp_path):
    report = check_run(tmp_path, "absent", tmp_path / "db", tmp_path / "trace")
    assert not report["run_complete"] and report["issues"]
    assert not (tmp_path / "db").exists()
