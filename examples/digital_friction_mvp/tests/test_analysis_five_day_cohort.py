import csv
import json
import sqlite3
from uuid import uuid4

from analysis_five_day_cohort import HELP, WORLD, build_report, day_summary, render, summarize_helper_mapping, trace_by_day
from proto.metrics import attempt_rows_table_name


def test_help_evidence_separates_dispatch_delivery_and_simulated_outcome():
    records, attempts = [], []
    for i, (delivered, result) in enumerate([(True, "abandon_midway"), (False, "success_self")]):
        tick, task, episode, request = f"t{i}", f"task{i}", f"ep{i}", f"request{i}"
        call = dict(tick_id=tick, task_id=task)
        status = "delivered" if delivered else "not_delivered"
        records.extend([dict(call, module="strategy", kind="sample", action=HELP),
                        dict(call, module="helper", kind="request", phase="initial", prompt_helper_id=2),
                        dict(call, module="helper", kind="request", phase="repair"),
                        dict(call, module="hourly_intention", kind="goal_outcome", status="completed", episode_id=episode,
                             outcome_type=result, operation_started=True),
                        dict(call, module="task", kind="decision", status="completed", episode_id=episode,
                             help_used=delivered, outcome=result, support_delivery_status=status, support_request_id=request)])
        identity = dict(request_id=request, helper_agent_id=2, requester_agent_id=1)
        response = dict(identity, support_style="enabling" if delivered else "unavailable",
                        instruction_quality="high" if delivered else "none", confidence=.8,
                        response_delay="immediate" if delivered else "no_response",
                        autonomy_preservation="high" if delivered else "not_applicable",
                        emotional_tone="neutral" if delivered else "not_applicable",
                        proxy_completion_level="none", responded=delivered, audit_status="ok", source="llm",
                        response_text="OK" if delivered else "", rationale="test")
        attempts.append(dict(episode_id=episode, support_request_id=request, support_request=dict(identity, task_id=task),
                             task=dict(task_id=task), outcome=dict(outcome_type=result, help_used=delivered),
                             requested_strategy_type=HELP, support_response=response, support_delivery_status=status))
    failure = dict(tick_id="t3", task_id="task3")
    records.extend([dict(failure, module="strategy", kind="sample", action=HELP),
                    dict(failure, module="helper", kind="request", phase="initial", prompt_helper_id=2),
                    dict(failure, module="task", kind="decision", status="technical_failure",
                         simulation_day=3, tick_seconds=9, requested_action=HELP, support_request_id="1-3-9-task3")])
    summary = day_summary(records, attempts, agent_id=1)
    assert summary["operations"] == 2 and summary["task_technical_failures"] == 1
    assert summary["help_choices"] == summary["dispatched_help"] == 3
    assert summary["delivery"] == {"delivered": 1, "not_delivered": 1, "technical_failure": 1}
    assert summary["outcomes_with_delivered_help"] == {"abandon_midway": 1}
    assert summary["operation_evidence"] == {"recorded_starts": 2, "recorded_decisions": 2}
    records[3]["operation_started"] = False
    mismatch = day_summary(records, attempts, agent_id=1)
    assert mismatch["operations"] == 1 and "操作启动标记与 SQLite 结局不一致" in mismatch["issues"]
    attempts[0]["support_request"]["requester_agent_id"] = attempts[0]["support_response"]["requester_agent_id"] = 9
    wrong_person = day_summary(records, attempts, agent_id=1)
    assert wrong_person["dispatched_help"] == 2 and wrong_person["help_request_evidence"]["unverified_persisted_requests"] == 1
    attempts[0]["support_request"]["requester_agent_id"] = attempts[0]["support_response"]["requester_agent_id"] = 1
    attempts[0]["support_response"]["request_id"] = "unrelated"
    broken = day_summary(records, attempts, agent_id=1)
    assert broken["delivery"]["unverified"] == 1 and not broken["outcomes_with_delivered_help"]


def test_report_scopes_days_and_memory_to_the_correct_rank_and_marks_missing_evidence(tmp_path):
    group, exp = tmp_path.name, str(uuid4())
    (tmp_path / f"exp_group_manifest_{group}.json").write_text(json.dumps([
        dict(group_id=group, exp_id=exp, world_name=WORLD, total_days=5, agent_count=3)]))
    with (tmp_path / f"app_entry_replay_summary_{group}.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=["group_id", "world_name", "exp_id", "agent_id", "selected_rank"])
        writer.writeheader()
        for rank, agent in [(1, "20"), (2, "11")]:
            writer.writerow(dict(group_id=group, world_name=WORLD, exp_id=exp, agent_id=agent, selected_rank=rank))
    (tmp_path / "trace").mkdir()
    route = dict(group_id=group, world=WORLD, hour=9, module="hourly_intention", kind="hourly_intention")
    rows = [dict(route, talkingdata_day=4, agent_id=11, status="accepted", executed_choice="no_app"),
            dict(route, talkingdata_day=5, agent_id=20, status="technical_failure")]
    (tmp_path / "trace/llm-requests-a.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (tmp_path / "acceptance.json").write_text(json.dumps({
        "group_id": group, "acceptance_ok": False,
        "agents": {"11": {"acceptance_ok": False, "replay": {"verified_hours": 72},
                          "cross_day": {"modules": {"app_plan": {"status": "verified"}}},
                          "hourly_intention": {"day5_memory_examples": [
                              {"episode_id": "e", "day5_hour": 10}, {"episode_id": "e", "day5_hour": 13}],
                              "opportunities": []}}}}))
    db = tmp_path / "db"
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TABLE {attempt_rows_table_name(exp)}(id,t,day,agent_id,payload_json)")
    report = build_report(tmp_path, db)
    first, second = report["profiles"]
    assert report["missing_ranks"] == [3]
    assert first["days"]["5"]["failed_hours"] == 1 and first["days"]["4"]["valid_hours"] == 0
    assert first["day4_episodes_in_valid_day5_plan"] is None and first["days"]["4"]["distinct_visible_offers"] is None
    assert second["days"]["4"]["valid_hours"] == 1 and second["days"]["5"]["failed_hours"] == 0
    assert second["day4_episodes_in_valid_day5_plan"] == 1 and second["day5_valid_plan_hours_with_day4_episode"] == 2
    assert "缺证" in render(report)


def test_observed_pairs_are_extracted_from_actual_prompts_and_checked_across_people_and_days(tmp_path):
    group = "two-day-report"
    (tmp_path / "trace").mkdir()
    raw = []
    for resident, day, helper in [(1, 4, 10), (1, 5, 11), (2, 4, 10), (3, 5, 12)]:
        packet = {"task": {"task_id": "t"}, "relationship": {"relationship_type": "family", "mapped_helper_agent_id": helper}}
        raw.append(dict(agent_id=resident, talkingdata_day=day, tick_id="tick", task_id="t", group_id=group, world=WORLD,
                        module="helper", kind="request", phase="initial", messages=[dict(role="user", content=json.dumps(packet))]))
    (tmp_path / "trace/llm-requests-one.jsonl").write_text("\n".join(map(json.dumps, raw)))
    traces = trace_by_day(tmp_path, group, {"1", "2", "3", "4"})
    people = []
    for agent in range(1, 5):
        days = {str(day): day_summary(traces[str(agent), day], [], agent_id=agent) for day in (4, 5)}
        people.append(dict(rank=agent, days=days))
    result = summarize_helper_mapping(people, {1, 2, 3, 4})
    assert result["observed_one_to_one"] is False
    assert result["residents_with_observed_target"] == result["distinct_observed_helpers"] == 3
    assert [p["observed_helper"]["status"] for p in people] == ["conflict", "conflict", "prompt_only", "incomplete_trace"]
    assert people[0]["observed_helper"]["helper_labels"] == ["H01", "H02"]
