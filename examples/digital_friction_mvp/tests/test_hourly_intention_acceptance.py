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
    memory_window,
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
        # All other episode fields still match. Alter only the resident's original
        # request in SQLite and keep the next-day model inputs untouched.
        payload = json.loads(conn.execute(f"SELECT payload_json FROM {table}").fetchone()[0])
        asked = payload["support_request"].get("requested_support_style")
        payload["support_request"].update(
            requested_support_style="proxy" if asked == "guidance" else "guidance",
            requested_support_style_source="llm",
        )
        conn.execute(f"UPDATE {table} SET payload_json=?", (json.dumps(payload),))
        mismatched = check()
        assert mismatched["cross_day_status"] == "missing_evidence"
        assert not mismatched["day5_memory_examples"]
        assert any("recalled support exchange differs" in issue for issue in mismatched["issues"])
        conn.execute(f"DELETE FROM {table}")
        assert any("outcomes disagree" in issue for issue in check()["issues"])


def recorded(tmp_path):
    return [
        json.loads(line)
        for p in sorted(tmp_path.glob("*.jsonl"))
        for line in p.read_text().splitlines()
    ]


def test_free_hour_resolution_matches_raw_recommendation_history_seed_plan_and_execution(
    resident, monkeypatch, tmp_path,
):
    from copy import deepcopy
    from check_hourly_choice_evidence import request_payload
    from proto.app_entry import PHONE_USE_NEEDS_V5, RESIDENT_DECISION_PLAN_VERSION

    step, data, llm, _ = resident
    monkeypatch.setenv("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION", RESIDENT_DECISION_PLAN_VERSION)
    monkeypatch.setenv("PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION", PHONE_USE_NEEDS_V5)
    monkeypatch.setenv("PROTO_PAIRED_ENVIRONMENT_SEED", "73")
    archive = tmp_path / "experiment_source.zip"
    archive.write_bytes(b"test policy")
    code_hash = sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setenv("PROTO_RUN_SOURCE_SHA256", code_hash)
    monkeypatch.setenv("PARALLEL_GROUP_NAME", "test-week")
    # Two suggestions will be reversed by the sampled policy, one will be neutral.
    activity = {"6": {"seen": 3, "active": 3}, "7": {"seen": 3, "active": 3}, "8": {"seen": 3, "active": 0}}
    replay = data["proto_app_entry_habit_memory"]
    replay["active_by_hour"].update(activity)
    recommendations = {6: "follow_habit", 7: "leave_phone", 8: "use_phone"}
    transport = llm.atext_request

    async def choose(*, dialog, **kw):
        wire = dialog[1]["content"]
        packet = json.loads(wire[wire.index("{"):])
        if packet.get("schema_version") == PHONE_USE_NEEDS_V5:
            raw = await transport(dialog=dialog, **kw)
            return json.dumps({**json.loads(raw), "phone_use_decision": recommendations[packet["inputs"]["hour"]],
                               "intensity_hint": None})
        if "actions" in packet:
            llm.action = "no_app" if packet["actions"] == ["no_app"] else "habitual_app"
        return await transport(dialog=dialog, **kw)

    monkeypatch.setattr(llm, "atext_request", choose)
    for hour in recommendations:
        step(3, hour, "no_app")
    slots = {(4, hour) for hour in recommendations}

    def audit(records, seed=73, history=replay):
        return audit_hours(records, {}, slots, set(), False, code_hash, require_resident_choices=True,
                           phone_use_needs_version=PHONE_USE_NEEDS_V5, replay_habit=history,
                           paired_environment_seed=seed)

    rows = recorded(tmp_path)
    result = audit(rows)
    assert not result["issues"]
    assert result["phone_use_llm_recommendation_counts"] == {"follow_habit": 1, "leave_phone": 1, "use_phone": 1}
    markers = [r for r in rows if r["kind"] == "phone_use_resolution"]
    assert [r["resolution"]["final_choice"] for r in markers][1:] == ["use_phone", "leave_phone"]
    n_use = sum(r["resolution"]["final_choice"] == "use_phone" for r in markers)
    assert result["phone_use_resolved_counts"] == {"leave_phone": 3 - n_use, "use_phone": n_use}
    assert result["free_hour_execution_counts"] == {"no_app": 3 - n_use, "habitual_app": n_use}
    # The formal weekly checker must obtain the seed and day-three baseline from the run archive.
    config = {"source_sha256": code_hash, "settings": {"PROTO_HOURLY_INTENTION_MODE": "opportunity_v1"},
              "runtime": {"proto_hourly_intention_mode": "opportunity_v1", "proto_scheduled_login_hour": None,
                          "proto_app_entry_plan_prompt_version": RESIDENT_DECISION_PLAN_VERSION,
                          "proto_app_entry_phone_use_needs_version": PHONE_USE_NEEDS_V5,
                          "proto_paired_environment_seed": 73}}
    (tmp_path / "resolved_config.json").write_text(json.dumps(config))
    exp = str(uuid4())
    db = tmp_path / "run.sqlite"
    ensure_attempt_rows_table(db, attempt_rows_table_name(exp))
    with closing(sqlite3.connect(db)) as conn:
        table = f"as_{exp.replace('-', '_')}_mvp_status"
        conn.execute(f"CREATE TABLE {table} (agent_id INTEGER, day INTEGER, t REAL, status_json TEXT)")
        handoff = json.dumps({"proto_day4_replay_snapshot": {"app_entry_habit_memory": replay}})
        conn.execute(f"INSERT INTO {table} VALUES(7,3,82801,?)", (handoff,))
        assert audit_intention_run(tmp_path, tmp_path, conn, exp, "7", "test-week", WORLD, slots, set()) == result
    assert audit(rows, seed=74)["issues"]
    other_history = deepcopy(replay)
    other_history["active_by_hour"]["7"]["active"] = 1
    assert audit(rows, history=other_history)["issues"]
    marker = markers[1]
    idx = rows.index(marker)
    for field, wrong in (("prior_use_probability", 0), ("odds_multiplier", 2), ("sample_u", 0.99),
                         ("llm_recommendation", "use_phone"), ("final_choice", "leave_phone")):
        damaged = deepcopy(rows)
        damaged[idx]["resolution"][field] = wrong
        assert audit(damaged)["issues"], field
    assert audit([r for r in rows if r is not marker])["issues"]
    assert audit([*rows, marker])["issues"]
    assert audit([marker, *(r for r in rows if r is not marker)])["issues"]
    damaged = deepcopy(rows)
    plan = next(r for r in damaged if (r["kind"], r["module"], r["hour"]) == ("request", "app_plan", 7))
    packet = request_payload(plan)
    packet["digital_needs"]["phone_use_resolution"] = marker["resolution"]
    plan["messages"][1]["content"] = json.dumps(packet)
    assert audit(damaged)["issues"]


def test_fourth_policy_free_hour_and_post_failure_appointment_match_actual_calls_and_sqlite(
    resident, monkeypatch, tmp_path,
):
    from copy import deepcopy
    import proto.agent as agent_module
    from proto.app_entry import RESIDENT_DECISION_PLAN_VERSION
    from proto.app_entry.needs import PHONE_USE_NEEDS_V1, PHONE_USE_NEEDS_V2, PHONE_USE_NEEDS_VERSION, HABIT_KEY, OBSERVED_HABIT_KEY
    from proto.retry_review import LEGACY_RETRY_REVIEW_VERSION, RETRY_REVIEW_VERSION
    from proto.models import AttemptStrategy
    from check_social_memory_run import read_attempts

    step, data, llm, _ = resident
    transport = llm.atext_request
    monkeypatch.setenv("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION", RESIDENT_DECISION_PLAN_VERSION)
    monkeypatch.setenv("PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION", PHONE_USE_NEEDS_VERSION)
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr(agent_module, "choose_attempt_strategy", lambda **_: AttemptStrategy("avoid"))

    async def choose(*, dialog, **kw):
        msg = dialog[1]["content"]
        body = json.loads(msg[msg.index("{"):])
        if body.get("schema_version") == RETRY_REVIEW_VERSION:
            return '": {"review_day":5,"review_hour":9}'
        raw = await transport(dialog=dialog, **kw)
        if body.get("schema_version") == PHONE_USE_NEEDS_VERSION:
            phone = "leave_phone" if llm.action == "no_app" else "use_phone"
            need = json.loads(raw)
            if phone == "leave_phone":
                need["intensity_hint"] = None
            pressures = need["need_pressures"]
            pressures[OBSERVED_HABIT_KEY] = pressures.pop(HABIT_KEY)
            return json.dumps({**need, "phone_use_decision": phone})
        return raw

    monkeypatch.setattr(llm, "atext_request", choose)
    step(3, 8, "no_app")
    step(3, 9, "engage_goal")
    step(3, 10, "habitual_app")
    exp = str(uuid4())
    table = attempt_rows_table_name(exp)
    db = tmp_path / "attempts.sqlite"
    ensure_attempt_rows_table(db, table)
    write_attempt_rows(db, table, json.loads(data["proto_stage_attempt_rows_json"]))
    with closing(sqlite3.connect(db)) as conn:
        episodes = read_attempts(conn, exp, "7")[3]
        episode, = episodes.values()
        raw = json.loads(conn.execute(f"SELECT payload_json FROM {table}").fetchone()[0])
        persisted = {(4, 9): [{**episode, "retry_review": raw["retry_review"]}]}
    rows = recorded(tmp_path)
    hours = {(4, 8), (4, 9), (4, 10)}

    def audit(events):
        return audit_hours(events, persisted, hours, set(), False, None, require_resident_choices=True)

    original = audit(rows)
    assert original["issues"] == []
    assert original["phone_use_decision_counts"] == {"leave_phone": 1, "use_phone": 1}
    assert original["retry_review_counts"] == {"scheduled": 1}
    assert raw["retry_review"]["next_review_at_sim_hour"] == 105
    plan = next(r for r in rows if (r["module"], r["kind"], r["hour"]) == ("app_plan", "request", 8))
    def read_body(call):
        text = call["messages"][1]["content"]
        return json.loads(text[text.index("{"):])
    assert read_body(plan)["digital_needs"]["intensity_hint"] is None
    def audit_against_replay(events):
        return audit_hours(events, persisted, hours, set(), False, None, require_resident_choices=True,
                           phone_use_needs_version=PHONE_USE_NEEDS_VERSION, replay_habit=data["proto_app_entry_habit_memory"])
    assert not audit_against_replay(rows)["issues"]
    damaged = deepcopy(rows)
    free_request = next(r for r in damaged if (r["module"], r["kind"], r["hour"]) == ("app_needs", "request", 8))
    altered = read_body(free_request)
    altered["inputs"]["day1_3_habit"]["device_history_fact"] = "这一小时曾记录到通讯社交活动。"
    free_request["messages"][1]["content"] = json.dumps(altered)
    assert any("differs from the replay handoff" in s for s in audit_against_replay(damaged)["issues"])
    damaged = deepcopy(rows)
    damaged_plan = damaged[rows.index(plan)]
    altered_body = read_body(damaged_plan)
    altered_body["digital_needs"]["intensity_hint"] = 0
    damaged_plan["messages"][1]["content"] = json.dumps(altered_body)
    assert any("preceding accepted phone choice" in error for error in audit(damaged)["issues"])
    for module, kind, hour in (("app_needs", "response", 8), ("retry_review", "response", 9)):
        damaged = deepcopy(rows)
        response = next(r for r in damaged if (r["module"], r["kind"], r["hour"]) == (module, kind, hour))
        change = {"phone_use_decision": "use_phone"} if hour == 8 else {"review_hour": 8}
        wire = response["raw"]
        response["raw"] = json.dumps({**json.loads(wire[wire.index("{"):]), **change})
        assert audit(damaged)["issues"]
    damaged = deepcopy(rows)
    marker = next(r for r in damaged if r["kind"] == "pressure_key_normalized")
    damaged.remove(marker)
    assert any("normalization" in error for error in audit(damaged)["issues"])
    # The same raw responses would not have been accepted by the earlier wire formats.
    damaged = deepcopy(rows)
    request = next(r for r in damaged if r["module"] == "app_needs" and r["kind"] == "request")
    body = json.loads(request["messages"][1]["content"].split("\n", 1)[1])
    body["schema_version"] = PHONE_USE_NEEDS_V1
    del body["pressure_keys"]
    request["messages"][1]["content"] = json.dumps(body)
    assert any("invalid phone preference accepted" in error for error in audit(damaged)["issues"])
    damaged = deepcopy(rows)
    request = next(r for r in damaged if r["module"] == "app_needs" and r["kind"] == "request")
    body = read_body(request)
    body["schema_version"] = PHONE_USE_NEEDS_V2
    request["messages"][1]["content"] = json.dumps(body)
    assert any("invalid phone preference accepted" in error for error in audit(damaged)["issues"])
    damaged = deepcopy(rows)
    for event in damaged:
        if event.get("retry_review_version"):
            event["retry_review_version"] = LEGACY_RETRY_REVIEW_VERSION
        if event.get("retry_review"):
            event["retry_review"]["version"] = LEGACY_RETRY_REVIEW_VERSION
        if event["module"] == "retry_review" and event["kind"] == "request":
            body = json.loads(event["messages"][1]["content"])
            body["schema_version"] = LEGACY_RETRY_REVIEW_VERSION
            event["messages"][1]["content"] = json.dumps(body)
    persisted[4, 9][0]["retry_review"]["version"] = LEGACY_RETRY_REVIEW_VERSION
    assert any("invalid retry time accepted" in error for error in audit(damaged)["issues"])
    persisted[4, 9][0]["retry_review"]["version"] = RETRY_REVIEW_VERSION
    damaged = deepcopy(rows)
    missing = next(r for r in damaged if r["kind"] == "hourly_intention")
    del missing["retry_review_version"]
    assert any("version" in error for error in audit(damaged)["issues"])
    persisted[4, 9][0]["retry_review"] = {**raw["retry_review"], "next_review_at_sim_hour": 104}
    assert any("SQLite" in error for error in audit(rows)["issues"])


@pytest.mark.parametrize("version", ["digital_needs_phone_use_v3", "digital_needs_phone_use_v5"])
@pytest.mark.parametrize("case", ["invalid_needs", "no_available_channel", "invalid_plan"])
def test_technical_phone_measurement_is_separate_from_voluntary_inactivity(
    resident, monkeypatch, tmp_path, case, version,
):
    from proto.app_entry import PHONE_USE_NEEDS_V5, RESIDENT_DECISION_PLAN_VERSION, rollout
    from check_social_memory_run import audit_trace

    step, _, llm, _ = resident
    monkeypatch.setenv("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION", RESIDENT_DECISION_PLAN_VERSION)
    monkeypatch.setenv("PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION", version)
    transport = llm.atext_request

    async def choose(*, dialog, **kw):
        if case == "invalid_needs" or case == "invalid_plan" and '"digital_needs"' in dialog[1]["content"]:
            return "{}"
        raw = await transport(dialog=dialog, **kw)
        return json.dumps({**json.loads(raw), "phone_use_decision": "use_phone"})

    monkeypatch.setattr(llm, "atext_request", choose)
    if case == "no_available_channel":
        monkeypatch.setattr(rollout, "build_rollout_app_context_candidates", lambda **_: {})
    step(3, 8, "habitual_app")
    rows = recorded(tmp_path)
    hour = {(4, 8)}
    report = audit_hours(rows, {}, hour, hour, False, None, require_resident_choices=True,
                         phone_use_needs_version=version)
    assert not report["issues"] and report["choices"] == {}
    key = {"invalid_needs": "unmeasured", "no_available_channel": "use_phone_channel_unavailable",
           "invalid_plan": "use_phone"}[case]
    assert report["phone_use_decision_counts"] == {key: 1}
    if version == PHONE_USE_NEEDS_V5:
        assert report["phone_use_llm_recommendation_counts"] == ({} if case == "invalid_needs" else {"use_phone": 1})
        assert report["phone_use_resolved_counts"] == report["phone_use_llm_recommendation_counts"]
        execution = {"invalid_needs": "needs_unmeasured", "no_available_channel": key,
                     "invalid_plan": "plan_technical_failure"}[case]
        assert report["free_hour_execution_counts"] == {execution: 1}
    completeness = audit_trace(rows, {3: {}, 4: {}}, hour, 5)
    assert (4, 8) not in completeness["missing_app_request_hours"]["app_plan"]
    if case == "no_available_channel":
        marker = next(r for r in rows if r["kind"] == "channel_unavailable")
        marker["candidate_app_contexts"] = {"finance_context": 1}
        assert audit_hours(rows, {}, hour, hour, False, None, require_resident_choices=True)["issues"]


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


def test_window_distinguishes_absent_recall_missing_measurement_and_wrong_recall():
    episode = {"episode_id": "login-day6", "task_id": "login", "strategy_type": "attempt_self",
               "outcome_type": "success_self", "requested_strategy_type": "attempt_self",
               "support_delivery_status": "not_requested", "help_used": False}
    source = {(6, 9): [episode]}
    no_recall = [(0, "initial", "no_app", [])]
    assert memory_window(6, 7, {}, no_recall)[0]["status"] == "no_source_task"
    assert memory_window(6, 7, source, [])[0]["status"] == "no_valid_plan"
    window, _, issues = memory_window(6, 7, source, no_recall)
    assert window["status"] == "not_observed" and not issues
    recalled = [(1, "later", "no_app", [episode]), (2, "wrong", "no_app", [dict(episode, help_used=True)])]
    window, matches, issues = memory_window(6, 7, source, recalled)
    assert window["status"] == "mismatch" and len(matches) == len(issues) == 1


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


@pytest.mark.parametrize("days", [5, 7])
def test_ten_resident_audit_partitions_shared_hours_and_checks_archived_device_mapping(
    resident, run_task, replay_files, monkeypatch, tmp_path, days
):
    from copy import deepcopy
    from proto.app_entry.bundle_loader import get_replay_source

    def write_rows(path, rows):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    folder = tmp_path
    fixture_run(folder, "no_tasks", days=days)
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
    if days == 7:
        monkeypatch.setenv("PROTO_LOGIN_DIFFICULTY_ARM", "standard")
        snapshot["runtime"]["proto_login_difficulty_arm"] = "standard"
        snapshot["settings"]["PROTO_LOGIN_DIFFICULTY_ARM"] = "standard"
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
            for day in range(3, days):
                for hour in range(24):
                    fails = agent_id == 10 and day == days - 1 and hour >= (21 if days == 5 else 18)
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
        return check_run(folder, "synthetic", db, trace, expected_days=days, expected_agents=10)

    report = check()
    assert report["issues"] == [] and report["acceptance_ok"]
    assert report["replay"] == {"expected_hours": 720, "verified_hours": 720}
    expected = (days - 3) * 24 * 10
    failed = 3 if days == 5 else 6
    assert report["rollout"] == {"expected_hours": expected, "accounted_hours": expected,
                                 "valid_hours": expected - failed, "error_hours_count": failed}
    intention = report["hourly_intention"]
    assert intention["scheduled_login_opportunities"] == intention["expected_scheduled_login_opportunities"] == (days - 3) * 10
    if days == 7:
        assert intention["memory_transition_status_counts"] == {
            "D4->D5": {"verified": 1, "no_source_task": 9},
            "D5->D6": {"no_source_task": 10}, "D6->D7": {"no_source_task": 10},
        }
        assert intention["day7_earlier_memory_status_counts"] == {
            "D4->D7": {"verified": 1, "no_source_task": 9}, "D5->D7": {"no_source_task": 10},
        }
        saved = report["agents"]["1"]["hourly_intention"]["day7_earlier_memory"]["D4->D7"]
        assert saved["valid_target_plans"] == 24 and saved["source_completed_tasks"] == 1
        assert saved["first_evidence"]["episode_id"] in saved["matched_episode_ids"]
        assert saved["first_evidence"]["executed_choice"] == "no_app"
    assert report["cross_day_status_counts"] == {"verified": 1, "no_day4_completed_task": 9}
    assert report["agents"]["1"]["cross_day_status"] == "verified"
    assert report["stability_gate"]["valid_decision_rate"] == (expected - failed) / expected
    assert not report["stability_gate"]["eligible_by_technical_stability"]
    assert not report["agents"]["10"]["stability_gate"]["eligible_by_technical_stability"]
    assert all(report["agents"][str(i)]["stability_gate"]["eligible_by_technical_stability"] for i in range(1, 10))
    trace_file, = trace.glob("llm-requests-*.jsonl")
    events = [json.loads(line) for line in trace_file.read_text().splitlines()]
    # Keep the total count intact but reassign one final-day scheduled event to another resident.
    event = next(row for row in events if row["agent_id"] == 2 and row["kind"] == "opportunity_published"
                 and row["talkingdata_day"] == days and row["source"] == "scheduled_login")
    event["agent_id"] = 3
    trace_file.write_text("".join(json.dumps(row) + "\n" for row in events))
    damaged = check()
    assert not damaged["acceptance_ok"]
    assert all(damaged["agents"][str(i)]["issues"] for i in (2, 3))
    assert all(not damaged["agents"][str(i)]["issues"] for i in (1, 4, 5, 6, 7, 8, 9, 10))
    replay[0]["device_id"], replay[1]["device_id"] = replay[1]["device_id"], replay[0]["device_id"]
    write_rows(replay_path, replay)
    assert "archived device mapping" in check()["issues"][0]
