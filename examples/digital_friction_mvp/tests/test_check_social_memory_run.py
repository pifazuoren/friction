import csv
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_social_memory_run import WORLD, app_activity_flow, check_run
from proto.metrics import ensure_attempt_rows_table, attempt_rows_table_name
from proto.retry_review import RETRY_REVIEW_VERSION


def test_explicit_leave_phone_requires_one_matching_inactive_export():
    clock = {"talkingdata_day": 4, "hour": 3}
    route = {**clock, "kind": "hourly_intention", "module": "hourly_intention", "status": "accepted",
             "executed_choice": "no_app", "retry_review_version": RETRY_REVIEW_VERSION}
    choice = {**clock, "module": "app_needs", "kind": "parse", "status": "ok_repaired",
              "parsed": {"phone_use_decision": "leave_phone"}}
    row = {**clock, "entry_status": "intention_no_app", "active": "0", "active_event_app_exposures": "0",
           "app_context_counts_json": "{}", "opened_channel": "", "primary_context": "no_app_context"}
    def issues(exports, records=(choice, route)):
        return app_activity_flow(records, exports, {(4, 3)})["issues"]

    assert issues([row]) == []
    for exports in ([], [row, row]):
        assert issues(exports)
    for field, wrong in (("active", "1"), ("active_event_app_exposures", "1"),
                         ("app_context_counts_json", '{"finance_context":1}'), ("opened_channel", "finance_context"),
                         ("entry_status", "intention_habitual_app"), ("primary_context", "finance_context")):
        assert issues([{**row, field: wrong}])
    # A task-hour no_app and an archived policy do not imply that Needs explicitly chose inactivity.
    assert issues([], records=(route,)) == []
    assert issues([], records=(choice, {k: v for k, v in route.items() if k != "retry_review_version"})) == []
    # V5 may sample inactivity after the model suggested use_phone or follow_habit.
    marker = {**clock, "module": "app_needs", "kind": "phone_use_resolution",
              "resolution": {"final_choice": "leave_phone"}}
    for recommendation in ("use_phone", "follow_habit"):
        records = ({**choice, "parsed": {"phone_use_decision": recommendation}}, marker, route)
        assert not issues([row], records)
        assert issues([], records)


def fixture_run(folder, case="complete", days=7, *, help_exchange=None):
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
    prior_by_day = {}
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
        for zero_day in range(3, days if case == "every_day" else 5):
            if case == "no_tasks" or (case == "no_strategy" and zero_day == 4):
                continue
            episode = f"task{zero_day}@{zero_day}/3600"
            prior_record = dict(episode_id=episode, tick_seconds=3600, day=zero_day, task_id=f"task{zero_day}",
                                task_family="health", requested_strategy_type="seek_help_then_attempt",
                                strategy_type="attempt_self", outcome_type="success_self", help_used=False,
                                support_request_id=f"support{zero_day}", support_delivery_status="not_delivered")
            data = {}
            prior_by_day[zero_day] = prior_record
            if zero_day == 3 and help_exchange:
                request, response = help_exchange
                prior_record.update(
                    strategy_type="seek_help_then_attempt", outcome_type="success_with_help",
                    help_used=True, support_delivery_status="delivered",
                )
                data.update(support_request=request, support_response=response)
                prior_by_day[zero_day] = {**prior_record, **request, **response}
            data.update(**prior_record, outcome={"help_used": prior_record["help_used"]})
            conn.execute(f"INSERT INTO {table}(agent_id,day,t,step,stage_name,task_id,task_family,strategy_type,"
                         "outcome_type,payload_json) VALUES (1,?,3600,1,'single',?,'health',?,?,?)",
                         (zero_day, f"task{zero_day}", prior_record["strategy_type"],
                          prior_record["outcome_type"], json.dumps(data)))

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
            if (day == 5 or (day > 5 and case == "every_day")) and hour == 1 and day - 1 in prior_by_day:
                modules.append("strategy")
                trace.append(record(day, 1, "task", "decision", status="completed", episode_id=prior_by_day[day - 1]["episode_id"],
                                    action="avoid" if case == "wrong_outcome" else "attempt_self", outcome="success_self"))
            for module in modules:
                episodes = [ep for earlier, ep in prior_by_day.items() if earlier < day - 1
                            and (day == 5 or case == "every_day")]
                if case == "wrong_episode" and module == "strategy":
                    episodes = [{**episodes[0], "support_delivery_status": "delivered"}]
                memory = {"recent_task_episodes": episodes}
                packet = {"inputs": memory} if module != "strategy" else {
                    "task_relevant_memory": memory, "task": {"task_family": "health", "task_id": f"task{day-1}"}}
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


def test_week_checks_late_task_decisions_strategy_and_older_help_facts(tmp_path):
    request = {"requested_support_style": "guidance", "requested_support_style_source": "llm"}
    response = {"support_style": "substituting", "instruction_quality": "medium",
                "autonomy_preservation": "low", "proxy_completion_level": "full"}
    report = fixture_run(tmp_path, "every_day", help_exchange=(request, response))
    assert report["acceptance_ok"]
    days = report["cross_day"]["by_target_day"]
    assert len(days) == 3
    for day in (5, 6, 7):
        assert days[str(day)]["modules"]["strategy"]["status"] == "verified"
        assert days[str(day)]["completed_tasks"] == 1
        assert days[str(day)]["same_family_strategy_example"][f"day{day}"]["episode_id"] == f"task{day-1}@{day-1}/3600"
    trace, = (tmp_path / "trace").glob("*.jsonl")
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    rows = [r for r in rows if (r["talkingdata_day"], r["module"]) not in {(7, "strategy"), (6, "task")}]
    d7 = next(r for r in rows if (r["talkingdata_day"], r["module"]) == (7, "app_needs"))
    prefix, raw = d7["messages"][0]["content"].split("\n", 1)
    packet = json.loads(raw)
    episode = next(e for e in packet["inputs"]["recent_task_episodes"] if e["day"] == 3)
    episode["requested_support_style"] = "proxy"
    d7["messages"][0]["content"] = prefix + "\n" + json.dumps(packet)
    trace.write_text("\n".join(json.dumps(r) for r in rows))
    damaged = check_run(tmp_path, "synthetic", tmp_path / "db", trace.parent)
    assert not damaged["acceptance_ok"]
    late = damaged["cross_day"]["by_target_day"]
    assert late["6"]["decision_db_disagreements"] == ["task5@5/3600"]
    assert late["7"]["completed_task_ticks_without_strategy_request"] == [3600]
    assert late["7"]["support_memory_disagreements"] == [
        {"episode_id": "task3@3/3600", "call_id": d7["call_id"], "module": "app_needs"}]


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


@pytest.mark.parametrize(("fact", "replacement"), [
    ("requested_support_style", "proxy"), ("requested_support_style_source", None),
    ("support_style", "enabling"), ("instruction_quality", None),
    ("autonomy_preservation", None), ("proxy_completion_level", "none"),
])
def test_sql_help_exchange_must_match_even_if_other_calls_recall_it_correctly(tmp_path, fact, replacement):
    request = {"requested_support_style": "guidance", "requested_support_style_source": "llm"}
    response = {"support_style": "substituting", "instruction_quality": "medium",
                "autonomy_preservation": "low", "proxy_completion_level": "full"}
    report = fixture_run(tmp_path, days=5, help_exchange=(request, response))
    assert report["cross_day_status"] == "verified" and report["acceptance_ok"]
    original = report["cross_day"]["same_family_strategy_example"]["day4"]
    assert all(original[k] == v for k, v in (request | response).items())

    trace, = (tmp_path / "trace").glob("*.jsonl")
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    row = next(r for r in rows if (r["talkingdata_day"], r["module"]) == (5, "app_plan"))
    prefix, raw = row["messages"][0]["content"].split("\n", 1)
    packet = json.loads(raw)
    episode, = packet["inputs"]["recent_task_episodes"]
    if replacement is None:
        del episode[fact]
    else:
        episode[fact] = replacement
    row["messages"][0]["content"] = prefix + "\n" + json.dumps(packet)
    trace.write_text("\n".join(json.dumps(r) for r in rows))
    report = check_run(tmp_path, "synthetic", tmp_path / "db", trace.parent, expected_days=5)
    assert report["cross_day_status"] == "missing_evidence" and not report["acceptance_ok"]
    assert report["cross_day"]["day5_support_memory_disagreements"] == [{
        "episode_id": original["episode_id"], "call_id": row["call_id"], "module": "app_plan",
    }]


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


def test_daily_app_flow_verifies_export_and_actual_next_inputs_across_midnight():
    channel_counts = {"health_service_context": 2, "communication_social_context": 1}
    # The person's first App differs from the most frequently used one in this hour.
    opening = "communication_social_context"
    token = "habitual_app@open:" + opening
    menu = {"schema_version": "hourly_plan_compact_v6", "actions": [token], "channels": list(channel_counts)}
    prior = dict(talkingdata_day=4, hour=23, active=True, active_event_app_exposures=3,
                 app_context_counts=channel_counts, opened_channel=opening)
    observation = dict(simulation_day=4, talkingdata_day=5, hour=0, recent_simulated_bundles=[prior])
    packet = json.dumps({"inputs": observation})
    def event(day, hour, module, kind, **values):
        return dict(talkingdata_day=day, hour=hour, module=module, kind=kind, **values)
    rows = [event(4, 23, "hourly_intention", "hourly_intention", status="accepted", executed_choice="habitual_app"),
            event(4, 23, "app_plan", "request", phase="initial", call_id="daily",
                  messages=[{"role": "user", "content": json.dumps(menu)}]),
            event(4, 23, "app_plan", "response", phase="repair", call_id="daily-repair", raw=json.dumps({"action": token})),
            event(4, 23, "app_plan", "parse", phase="repair", call_id="daily-repair",
                  status="ok_repaired", parsed={"app_context_counts": channel_counts}),
            event(5, 0, "hourly_intention", "hourly_intention", status="technical_failure"),
            event(5, 0, "app_plan", "intent_validation", raw_choice={"kind": "habitual_app"}, raw_activity={})]
    for module in ("app_needs", "app_plan"):
        rows.append(event(5, 0, module, "request", phase="initial", call_id=module,
                          messages=[{"role": "user", "content": packet}]))
    rows += [event(5, 0, "app_needs", "response", phase="initial", call_id="app_needs", raw=packet[:-4]),
             event(5, 0, "app_needs", "parse", phase="initial", call_id="app_needs", status="invalid_schema"),
             event(5, 0, "app_needs", "request", phase="repair", call_id="repair"),
             event(5, 0, "app_needs", "parse", phase="repair", call_id="repair", status="ok_repaired")]
    hourly = [{"talkingdata_day": "4", "hour": "23", "entry_status": "intention_habitual_app", "active": "1",
               "active_event_app_exposures": "3", "opened_channel": opening,
               "app_context_counts_json": json.dumps(channel_counts)}]
    expected = {(4, 23), (5, 0)}
    result = app_activity_flow(rows, hourly, expected)
    assert not result["issues"]
    d4, d5 = result["by_day"]["4"], result["by_day"]["5"]
    assert d4["daily_exports_verified"] == d4["next_needs_verified"] == d4["next_plan_verified"] == 1
    assert d4["daily_opening_exports_verified"] == 1
    assert d5["needs_first_reply_echoed_observation"] == d5["needs_repair_requests"] == 1
    assert d5["needs_requests"] == 2 and d5.get("needs_first_pass_valid", 0) == 0
    assert d5["failed_after_initial_daily_choice_without_channel"] == d5["technical_failure_hours"] == 1
    assert not d5.get("accepted_daily_choices")
    last = app_activity_flow(rows, hourly, {(4, 23)})
    assert last["totals"]["daily_at_run_end"] == 1 and not last["totals"].get("next_plan_verified")
    # An unverified following plan, a contradictory next observation and a missing
    # hourly export are distinguishable from each other and from a valid decision.
    plan_call = next(r for r in rows if (r["talkingdata_day"], r["module"], r["kind"]) == (5, "app_plan", "request"))
    rows.remove(plan_call)
    assert app_activity_flow(rows, hourly, expected)["totals"]["next_plan_not_observed"] == 1
    plan_call["messages"] = [{"role": "user", "content": json.dumps({
        "inputs": {"recent_simulated_bundles": [{**prior, "opened_channel": "health_service_context"}]}})}]
    rows.append(plan_call)
    broken = app_activity_flow(rows, hourly, expected)
    assert broken["issues"] and not broken["totals"].get("next_plan_verified")
    broken_export = app_activity_flow(rows, [], expected)
    assert broken_export["issues"] and not broken_export["totals"].get("daily_exports_verified")
    wrong_opening = app_activity_flow(rows, [{**hourly[0], "opened_channel": "health_service_context"}], expected)
    assert wrong_opening["issues"] and not wrong_opening["totals"].get("daily_opening_exports_verified")
