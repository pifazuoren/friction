"""A two-day controlled window through the production hourly router, with offline model replies."""

from contextlib import closing
import csv
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

import pytest

from check_hourly_intention_run import (
    audit_hours,
    audit_intention_run,
    check_plan_calls,
)
from check_social_memory_run import WORLD, check_run, rollout_hours
from proto.app_entry.intention_contract import compact_menu
from proto.app_entry.types import _stable_hash
from proto.metrics import (
    attempt_rows_table_name,
    ensure_attempt_rows_table,
    write_attempt_rows,
)
from test_check_social_memory_run import fixture_run

import test_hourly_intention_execution as execution_fixtures

resident = execution_fixtures.resident
run_task = execution_fixtures.run_task


def test_continuous_controlled_window_matches_real_messages_and_database(
    resident, monkeypatch, tmp_path
):
    step, data, _, _ = resident
    archive = tmp_path / "experiment_source.zip"
    archive.write_bytes(b"controlled test archive")
    code_hash = sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setenv("PARALLEL_GROUP_NAME", "controlled-window")
    monkeypatch.setenv("PROTO_RUN_SOURCE_SHA256", code_hash)
    (tmp_path / "resolved_config.json").write_text(
        json.dumps(
            {
                "source_sha256": code_hash,
                "settings": {"PROTO_HOURLY_INTENTION_MODE": "opportunity_v1"},
                "runtime": {
                    "proto_hourly_intention_mode": "opportunity_v1",
                    "proto_scheduled_login_hour": 9,
                },
            }
        )
    )
    for day in (3, 4):
        for hour in range(24):
            if (day, hour) == (3, 9):
                step(day, hour, "engage_goal")
            else:
                step(day, hour, "no_app")
    exp = str(uuid4())
    table = attempt_rows_table_name(exp)
    db = tmp_path / "attempts.sqlite"
    ensure_attempt_rows_table(db, table)
    attempts = json.loads(data["proto_stage_attempt_rows_json"])
    assert len(attempts) == 1
    write_attempt_rows(db, table, attempts)
    with closing(sqlite3.connect(db)) as conn:

        def check():
            return audit_intention_run(
                tmp_path,
                tmp_path,
                conn,
                exp,
                "7",
                "controlled-window",
                WORLD,
                rollout_hours(5),
                set(),
            )

        report = check()
        assert report["issues"] == []
        assert report["cross_day_status"] == "verified"
        assert report["published_opportunities"] == 2
        assert report["valid_intention_decisions"] == 48
        assert report["distinct_tasks_entered"] == report["operations_started"] == 1
        assert report["help_requests"] == 1
        assert len(report["day5_memory_examples"]) == 24
        conn.execute(f"DELETE FROM {table}")
        assert any("outcomes disagree" in issue for issue in check()["issues"])


def recorded(tmp_path):
    return [
        json.loads(line)
        for p in sorted(tmp_path.glob("*.jsonl"))
        for line in p.read_text().splitlines()
    ]


@pytest.mark.parametrize(
    "damage",
    [
        "missing_raw",
        "foreign_parse",
        "extra_repair",
        "contradictory_raw_activity",
        "contradictory_parsed_choice",
        "contradictory_executed_choice",
        "unknown_encoded_action",
        "duplicate_action_key",
    ],
)
def test_receipt_must_match_the_actual_sent_request_and_accepted_plan(
    resident, tmp_path, damage
):
    step, _, _, _ = resident
    step(3, 8, "no_app")
    rows = recorded(tmp_path)
    initial = next(
        r for r in rows if (r["module"], r["kind"]) == ("app_plan", "request")
    )
    response = next(
        r for r in rows if (r["module"], r["kind"]) == ("app_plan", "response")
    )
    parsed = next(r for r in rows if (r["module"], r["kind"]) == ("app_plan", "parse"))
    if damage == "missing_raw":
        rows.remove(response)
    elif damage == "foreign_parse":
        parsed["call_id"] = "another-query"
    elif damage == "extra_repair":
        rows.append({**initial, "phase": "repair", "call_id": "unreported-repair"})
    elif damage == "contradictory_parsed_choice":
        parsed["parsed"]["intent"]["kind"] = "habitual_app"
    elif damage == "contradictory_executed_choice":
        route = next(r for r in rows if r["kind"] == "hourly_intention")
        route["executed_choice"] = "drop_goal"
    elif damage == "duplicate_action_key":
        response["raw"] = response["raw"].replace(
            '"action":', '"action":"engage_goal:opportunity:hidden","action":', 1
        )
    else:
        raw = json.loads(response["raw"])
        if damage == "unknown_encoded_action":
            raw["action"] = "engage_goal:opportunity:hidden"
        else:
            raw["additional_apps"] = ["communication_social_context"]
        response["raw"] = json.dumps(raw)
    report = audit_hours(rows, {}, {(4, 8)}, set(), False, None)
    assert report["issues"] and not report["valid_intention_decisions"]


def test_early_review_and_disappearing_pending_goal_are_detected(resident, tmp_path):
    step, _, _, _ = resident
    step(3, 9, "defer_goal", review=105)
    step(3, 10, "no_app")
    rows = recorded(tmp_path)
    hours = {(4, 9), (4, 10)}
    assert not audit_hours(rows, {}, hours, set(), False, None)["issues"]
    request = next(
        r
        for r in rows
        if (r["module"], r["kind"], r["hour"]) == ("app_plan", "request", 10)
    )
    route = next(r for r in rows if r["kind"] == "hourly_intention" and r["hour"] == 10)
    original = json.loads(request["messages"][1]["content"].split("\n", 1)[1])
    original["inputs"]["goal_review_due"] = True
    original.update(compact_menu(original["inputs"], original["schema_version"], channels=original["channels"]))
    request["messages"][1]["content"] = json.dumps(original)
    route["visible_observation_hash"] = _stable_hash(original["inputs"])[:16]
    assert any(
        "review hour" in i
        for i in audit_hours(rows, {}, hours, set(), False, None)["issues"]
    )
    route["goal_state_before"] = None
    assert any(
        "carry over" in i
        for i in audit_hours(rows, {}, hours, set(), False, None)["issues"]
    )


@pytest.mark.parametrize("wire_version", [2, 3, 4, 5])
def test_review_time_in_received_action_matches_the_persisted_goal(resident, tmp_path, wire_version):
    step, data, _, helper = resident
    step(4, 9, "defer_goal", review=115)
    rows = recorded(tmp_path)
    response = next(r for r in rows if (r["module"], r["kind"]) == ("app_plan", "response"))
    request = next(r for r in rows if (r["module"], r["kind"]) == ("app_plan", "request"))
    route = next(r for r in rows if r["kind"] == "hourly_intention")
    payload = json.loads(request["messages"][1]["content"].split("\n", 1)[1])
    raw = json.loads(response["raw"])
    assert raw["action"] == "defer_goal@o1@115" and "review" not in raw
    assert "defer_goal@o1@115" in payload["defer_options"]["o1"]
    assert route["goal_state_after"]["next_review_at_sim_hour"] == 115
    assert data["proto_goal_state_json"]["goal"]["next_review_at_sim_hour"] == 115
    assert not data["proto_assigned_task_json"] and not helper.requests
    if wire_version in {2, 3}:
        raw["apps"] = raw.pop("additional_apps")
    if wire_version < 5:
        payload["schema_version"] = f"hourly_plan_compact_v{wire_version}"
    if wire_version in {3, 4}:
        payload.update(compact_menu(payload["inputs"], schema_version=payload["schema_version"]))
    elif wire_version == 2:
        oid = payload.pop("targets")["o1"]
        payload.pop("defer_options")
        payload["actions"] = ["habitual_app", "no_app"] + [
            f"{kind}:opportunity:{oid}" for kind in ("engage_goal", "drop_goal", "defer_goal")
        ]
        raw.update(action=f"defer_goal:opportunity:{oid}", review=115)
    if wire_version < 5:
        request["messages"][1]["content"] = json.dumps(payload)
        response["raw"] = json.dumps(raw)
    assert check_plan_calls(rows, route) == payload["inputs"]
    if wire_version == 2:
        raw["review"] = None
    else:
        raw["action"] = "defer_goal@o1"
    response["raw"] = json.dumps(raw)
    with pytest.raises(ValueError, match="accepted parse failed"):
        check_plan_calls(rows, route)


def test_entirely_failed_window_is_not_evidence_of_no_opportunity(resident, tmp_path):
    step, _, _, _ = resident
    step(3, 8, "bad_id")
    report = audit_hours(recorded(tmp_path), {}, {(4, 8)}, {(4, 8)}, False, None)
    assert not report["issues"] and not report["valid_intention_decisions"]
    assert report["cross_day_status"] == "technical_failure"


def test_natural_four_day_rollout_has_95_valid_idle_hours_and_one_failed_plan(
    resident, tmp_path, monkeypatch
):
    step, _, llm, helper = resident
    monkeypatch.delenv("PROTO_SCHEDULED_LOGIN_HOUR")
    normal_request = llm.atext_request

    async def controlled_request(*, dialog, **kwargs):
        request = json.loads(dialog[1]["content"].split("\n", 1)[1])
        observation = request["inputs"]
        if "digital_needs" in request and (
            observation["talkingdata_day"],
            observation["hour"],
        ) == (4, 19):
            raise TimeoutError("offline transport failure")
        return await normal_request(dialog=dialog, **kwargs)

    monkeypatch.setattr(llm, "atext_request", controlled_request)
    for day in range(3, 7):
        for hour in range(24):
            step(day, hour, "no_app")
    report = audit_hours(
        recorded(tmp_path), {}, rollout_hours(7), {(4, 19)}, False, None
    )
    assert not report["issues"]
    assert report["technical_failure_hours"] == [(4, 19)]
    assert report["choices"] == {"no_app": 95}
    assert report["cross_day_status"] == "no_natural_opportunity"
    assert not report["published_opportunities"] and not helper.requests


@pytest.mark.parametrize(
    "failed_hours,rate_passes", [(1, True), (3, False), (48, False)]
)
def test_old_archive_format_distinguishes_coverage_acceptance_and_valid_fraction(
    tmp_path, failed_hours, rate_passes
):
    fixture_run(tmp_path, "no_tasks", days=5)
    rollout = tmp_path / "app_entry_rollout_hourly_synthetic.csv"
    errors = tmp_path / "app_entry_rollout_errors_synthetic.csv"
    with rollout.open() as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    with errors.open() as handle:
        error_fields = csv.DictReader(handle).fieldnames
    with rollout.open("w") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows[failed_hours:])
    with errors.open("w") as handle:
        writer = csv.DictWriter(handle, error_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {**r, "bundle_generated": 0, "entry_status": "llm_rollout_error"}
            for r in rows[:failed_hours]
        )
    failures = {
        (int(r["talkingdata_day"]), int(r["hour"])) for r in rows[:failed_hours]
    }
    trace = next((tmp_path / "trace").glob("*.jsonl"))
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    for entry in list(events):
        if (entry["talkingdata_day"], entry["hour"]) in failures:
            if entry["module"] == "app_plan":
                events.remove(entry)
            elif entry["module"] == "app_needs":
                events.extend(
                    [
                        {**entry, "kind": "error"},
                        {
                            **entry,
                            "kind": "entry",
                            "module": "app_entry",
                            "status": "llm_rollout_error",
                        },
                    ]
                )
    trace.write_text("\n".join(json.dumps(row) for row in events))
    report = check_run(tmp_path, "synthetic", tmp_path / "db", tmp_path / "trace", 5)
    assert report["run_complete"]
    assert report["acceptance_ok"] == (failed_hours < 48)
    assert report["stability_gate"]["eligible_by_technical_stability"] == rate_passes
    assert report["stability_gate"]["valid_decision_rate"] == (48 - failed_hours) / 48
    if failed_hours == 48:
        assert report["cross_day_status"] == "technical_failure"


@pytest.mark.parametrize("count_field", ["app_context_counts", "app_context_weights"])
def test_archived_nested_intent_still_revalidates_with_the_published_old_schema(
    count_field,
):
    choice = dict(
        kind="no_app",
        opportunity_id=None,
        goal_id=None,
        next_review_at_sim_hour=None,
        reason="Idle",
    )
    observation = dict(
        available_opportunities=[],
        current_intention=None,
        goal_review_due=True,
        monotonic_sim_hour=104,
        max_defer_hours=24,
    )
    body = {
        "schema_version": (
            "app_entry_plan_v2"
            if count_field == "app_context_counts"
            else "app_entry_plan_context_weights_v1"
        )
        + "_with_intent_v1",
        "inputs": observation,
        "output_schema": {"properties": {count_field: {}}},
        "candidate_app_contexts": {"finance_context": 1},
        "intensity_profile": {"exposures_if_active": 3},
        "runtime_output_constraints": {
            "minimum_confidence": 0.5,
            "active_exposure_maximum": 3,
        },
    }
    base = {
        "attitude": 0.5,
        "subjective_norm": 0.4,
        "perceived_control": 0.6,
        "confidence": 0.95,
        "active": False,
        "reasoning": "Idle",
    }
    raw = {**base, "intent": choice, count_field: {}}
    parsed = {
        **base,
        "intent": choice,
        "active_event_app_exposures": 0,
        "app_context_counts": {},
    }
    ctx = dict(module="app_plan", query_id="q", call_id="c", phase="initial")
    rows = [
        dict(
            **ctx,
            kind="request",
            messages=[{"role": "user", "content": json.dumps(body)}],
        ),
        dict(**ctx, kind="response", raw=json.dumps(raw)),
        dict(**ctx, kind="parse", status="ok", parsed=parsed),
    ]
    route = dict(
        status="accepted",
        repair_count=0,
        visible_observation_hash=_stable_hash(observation)[:16],
        raw_choice=choice,
        repaired_choice=None,
        accepted_choice=choice,
    )
    assert check_plan_calls(rows, route) == observation
    rows[2].update(status="invalid_schema", parsed=None)
    with pytest.raises(
        ValueError, match="valid raw Plan was recorded as a rejected parse"
    ):
        check_plan_calls(
            rows, {**route, "status": "technical_failure", "accepted_choice": None}
        )


@pytest.mark.parametrize("damage", ["change_action", "remove_review_option", "change_opened_channel", "change_extras"])
def test_repair_receipt_includes_original_raw_commitments_and_identical_goal_constraints(
    resident, tmp_path, monkeypatch, damage
):
    step, _, llm, _ = resident
    transport = llm.atext_request
    complete = None

    async def omit_confidence_in_first_plan(*, dialog, **kw):
        nonlocal complete
        content = dialog[1]["content"]
        if content.startswith("{") and "preserve" in json.loads(content):
            return json.dumps(complete)
        raw = await transport(dialog=dialog, **kw)
        if "action" not in json.loads(raw):
            return raw
        complete = json.loads(raw)
        return json.dumps({k: v for k, v in complete.items() if k != "confidence"})

    monkeypatch.setattr(llm, "atext_request", omit_confidence_in_first_plan)
    if damage in {"change_opened_channel", "change_extras"}:
        step(3, 9, "habitual_app")
    else:
        step(3, 9, "defer_goal", review=102)
    rows = recorded(tmp_path)

    def audit():
        return audit_hours(rows, {}, {(4, 9)}, set(), False, None)

    assert not audit()["issues"]
    correction = next(
        r for r in rows if r["kind"] == "request" and r.get("phase") == "repair"
    )
    body = json.loads(correction["messages"][1]["content"])
    if damage == "change_action":
        body["preserve"]["action"] = "no_app"
    elif damage == "remove_review_option":
        body["defer_options"]["o1"].remove("defer_goal@o1@102")
    elif damage == "change_opened_channel":
        assert body["preserve"]["opened_channel"] == "communication_social_context"
        body["preserve"]["opened_channel"] = "finance_context"
    else:
        assert body["preserve"]["additional_activity"] == {}
        body["preserve"]["additional_activity"] = {"communication_social_context": 1}
    correction["messages"][1]["content"] = json.dumps(body)
    assert any("repair prompt changed" in e for e in audit()["issues"])


def test_ten_resident_audit_partitions_shared_hours_and_checks_archived_device_mapping(
    resident, run_task, replay_files, monkeypatch, tmp_path
):
    from copy import deepcopy
    from proto.app_entry.bundle_loader import get_replay_source

    def write_rows(path, rows):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    folder = tmp_path
    fixture_run(folder, "no_tasks", days=5)
    manifest_path = folder / "exp_group_manifest_synthetic.json"
    manifest, = json.loads(manifest_path.read_text())
    manifest.update(agent_count=10, proto_hourly_intention_mode="opportunity_v1")
    manifest_path.write_text(json.dumps([manifest]))
    archive = folder / "experiment_source.zip"
    archive.write_bytes(b"offline cohort source")
    code_hash = sha256(archive.read_bytes()).hexdigest()
    trace = folder / "cohort_trace"
    monkeypatch.setenv("PROTO_RUN_SOURCE_SHA256", code_hash)
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(trace))
    monkeypatch.setenv("PARALLEL_GROUP_NAME", "synthetic")
    source = get_replay_source(**replay_files, replay_days=(1, 2, 3))
    assignments = source.assignments_for_agent_ids(range(1, 11))
    profiles_path = folder / "profiles.json"
    profiles_path.write_text(json.dumps([{"id": i} for i in assignments]))
    snapshot = {
        "settings": {"AGENT_COUNT": "10", "PROTO_HOURLY_INTENTION_MODE": "opportunity_v1",
                     "DIGITAL_FRICTION_PROFILES_PATH": str(profiles_path),
                     "PROTO_APP_ENTRY_REPLAY_DEVICE_PATH": replay_files["device_mapping_path"],
                     "PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH": replay_files["bundle_path"]},
        "runtime": {"proto_hourly_intention_mode": "opportunity_v1", "proto_scheduled_login_hour": 9},
        "source_sha256": code_hash, "profiles_sha256": sha256(profiles_path.read_bytes()).hexdigest(),
        "reference_hash": source.bundle_hash, "device_mapping_hash": source.device_mapping_hash,
        "cohort": [dict(agent_id=i, profile_id=i, selected_rank=item.selected_rank, device_id=item.device_id)
                   for i, item in assignments.items()],
    }
    (folder / "resolved_config.json").write_text(json.dumps(snapshot))
    step, data, _, helper = resident
    agent, _ = run_task
    initial_state = deepcopy(data)
    db = folder / "db"
    status_table = "as_" + manifest["exp_id"].replace("-", "_") + "_mvp_status"
    attempt_table = attempt_rows_table_name(manifest["exp_id"])
    replay, rollout, errors = [], [], []
    with sqlite3.connect(db) as conn:
        base_states = conn.execute(f"SELECT day,t,status_json FROM {status_table}").fetchall()
        conn.execute(f"DELETE FROM {status_table}")
        for agent_id, item in assignments.items():
            device = item.device_id
            agent._id = agent_id
            agent.step_count = 0
            data.clear()
            data.update(deepcopy(initial_state), proto_app_entry_replay_device_id=device,
                        proto_app_entry_replay_selected_rank=item.selected_rank, family_helper_agent_id=agent_id+20)
            agent.set_support_helper_registry({agent_id+20: helper})
            identity = dict(group_id="synthetic", world_name=WORLD, exp_id=manifest["exp_id"],
                            agent_id=agent_id, device_id=device)
            replay.append(dict(**identity, selected_rank=item.selected_rank, replay_hours_seen=72,
                               uses_validation_data_any=0, day4_snapshot_created=1,
                               replay_bundle_hash=source.bundle_hash, device_mapping_hash=source.device_mapping_hash))
            for day, tick, raw in base_states:
                state = json.loads(raw)
                state["proto_app_entry_habit_memory"]["device_id"] = device
                if day == 3:
                    state["proto_day4_replay_snapshot"].update(agent_id=agent_id, device_id=device)
                conn.execute(f"INSERT INTO {status_table} VALUES (?,?,?,?)", (day, tick, agent_id, json.dumps(state)))
            for day in (3, 4):
                for hour in range(24):
                    fails = agent_id == 10 and day == 4 and hour >= 21
                    engage = agent_id == 1 and day == 3 and hour == 9
                    action = "no_app"
                    if engage:
                        action = "engage_goal"
                    if fails:
                        action = "bad_id"
                    step(day, hour, action)
                    row = dict(**identity, simulation_day=day, talkingdata_day=day+1, hour=hour,
                               uses_validation_data=0, config_fingerprint="fingerprint")
                    if fails:
                        errors.append(dict(**row, entry_status="llm_rollout_error", bundle_generated=0))
                    else:
                        rollout.append(dict(**row, source="llm_memory_rollout", needs_actual_requests=1,
                                            plan_actual_requests=1))
            if agent_id == 1:
                completed = json.loads(data["proto_stage_attempt_rows_json"])
    write_attempt_rows(db, attempt_table, completed)
    replay_path = folder / "app_entry_replay_summary_synthetic.csv"
    write_rows(replay_path, list(reversed(replay)))
    write_rows(folder / "app_entry_rollout_hourly_synthetic.csv",
               sorted(rollout, key=lambda r: (r["simulation_day"], r["hour"])))
    write_rows(folder / "app_entry_rollout_errors_synthetic.csv", errors)
    def check():
        return check_run(folder, "synthetic", db, trace, expected_days=5, expected_agents=10)

    report = check()
    assert report["issues"] == [] and report["acceptance_ok"]
    assert report["replay"] == {"expected_hours": 720, "verified_hours": 720}
    assert report["rollout"] == {"expected_hours": 480, "accounted_hours": 480, "valid_hours": 477, "error_hours_count": 3}
    assert report["hourly_intention"]["scheduled_login_opportunities"] == 20
    assert report["cross_day_status_counts"] == {"verified": 1, "no_day4_completed_task": 9}
    assert report["agents"]["1"]["cross_day_status"] == "verified"
    assert report["stability_gate"]["valid_decision_rate"] == 477/480
    assert not report["stability_gate"]["eligible_by_technical_stability"]
    assert not report["agents"]["10"]["stability_gate"]["eligible_by_technical_stability"]
    assert all(report["agents"][str(i)]["stability_gate"]["eligible_by_technical_stability"] for i in range(1, 10))
    trace_file, = trace.glob("llm-requests-*.jsonl")
    events = [json.loads(line) for line in trace_file.read_text().splitlines()]
    # The cohort still has twenty publication records, but one resident gets another's 09:00 event.
    event = next(row for row in events if row["agent_id"] == 2 and row["kind"] == "opportunity_published")
    event["agent_id"] = 3
    trace_file.write_text("".join(json.dumps(row) + "\n" for row in events))
    damaged = check()
    assert not damaged["acceptance_ok"]
    assert all(damaged["agents"][str(i)]["issues"] for i in (2, 3))
    assert all(not damaged["agents"][str(i)]["issues"] for i in (1, 4, 5, 6, 7, 8, 9, 10))
    replay[0]["device_id"], replay[1]["device_id"] = replay[1]["device_id"], replay[0]["device_id"]
    write_rows(replay_path, replay)
    assert "archived device mapping" in check()["issues"][0]
