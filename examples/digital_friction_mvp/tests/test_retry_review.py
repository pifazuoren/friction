import asyncio
import json

import pytest

from proto.hourly_intention import IntentionLedger
from proto.models import AttemptStrategy
from proto.retry_review import LEGACY_RETRY_REVIEW_VERSION, RETRY_REVIEW_VERSION, choose_retry_review, parse_review_time
from test_hourly_intention_execution import resident, run_task  # noqa: F401 - shared agent fixtures
from test_hourly_intention_state import intent, login


class Reply:
    def __init__(self, content):
        self.content = content
        self.packets = []

    async def atext_request(self, *, dialog, **kwargs):
        self.packets.append(json.loads(dialog[1]["content"]))
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


def settled(*, success=False, deadline=None):
    ledger = IntentionLedger()
    offer = ledger.publish(login(), source="scheduled_login", sim_hour=95, known_deadline_sim_hour=deadline)
    ledger.apply(intent("engage_goal", oid=offer["opportunity_id"]), sim_hour=95)
    episode = {"episode_id": "test-episode", "outcome_type": "success_self" if success else "avoid_without_attempt",
               "strategy_type": "attempt" if success else "avoid", "help_used": False}
    ledger.settle(success=success, operation_started=success, episode_id=episode["episode_id"])
    return ledger, episode


def review(ledger, episode, llm):
    return asyncio.run(choose_retry_review(llm=llm, goal=ledger.state["goal"], episode=episode, resident={"age": 73},
                                          sim_hour=95, max_defer_hours=24, timeout=30))


def test_resident_can_choose_first_or_latest_available_hour_across_midnight():
    ledger, episode = settled(deadline=105)
    for hour, expected in [(0, 96), (9, 105)]:
        llm = Reply(json.dumps({"review_day": 5, "review_hour": hour}))
        result = review(ledger, episode, llm)
        assert result == {"version": RETRY_REVIEW_VERSION, "status": "scheduled", "next_review_at_sim_hour": expected}
        packet, = llm.packets
        assert packet["now"] == {"day": 4, "hour": 23}
        assert packet["earliest"] == {"day": 5, "hour": 0}
        assert packet["latest"] == {"day": 5, "hour": 9}
        assert packet["resident"] == {"age": 73}
        assert packet["task"]["decision_count"] == 1 and packet["task"]["operation_count"] == 0
        assert packet["outcome"] == {**episode, "operation_started": False}
        saved = IntentionLedger(ledger.state)
        saved.schedule_retry(expected, sim_hour=95, max_defer_hours=24)
        restored = IntentionLedger(saved.state)
        assert not restored.review_due(expected - 1)
        assert restored.review_due(expected)
        assert restored.goal["decision_index"] == 1 and restored.goal["operation_attempt_count"] == 0


@pytest.mark.parametrize("raw", [
    '{"review_day":5,"review_hour":10}', '{"review_day":4,"review_hour":23}',
    '{"review_day":4,"review_hour":24}', '{"review_day":true,"review_hour":9}',
    '{"review_day":5,"review_hour":0,"review_hour":9}', '{"review_day":5,"review_hour":"9"}',
])
def test_invalid_time_does_not_become_a_reminder(raw):
    assert parse_review_time(raw, 96, 105) is None


def test_known_glm_reply_prefix_preserves_the_only_complete_time():
    raw = '": {\n  "review_day": 5,\n  "review_hour": 10\n}'
    assert parse_review_time(raw, 106, 120) == ({"review_day": 5, "review_hour": 10}, 106)
    assert parse_review_time(raw, 106, 120, version=LEGACY_RETRY_REVIEW_VERSION) is None
    assert parse_review_time(raw, 96, 105) is None
    for ambiguous in (raw + '{}', raw + " or 09:00", "maybe " + raw, raw.replace('"review_hour":', '"review_day":5,"review_hour":')):
        assert parse_review_time(ambiguous, 106, 120) is None


@pytest.mark.parametrize("success, deadline, reply, status, calls", [
    (True, None, "unused", "not_needed", 0),
    (False, 95, "unused", "no_future_hour", 0),
    (False, None, None, "missing_llm", 0),
    (False, None, "not a date", "invalid_response", 1),
    (False, None, TimeoutError(), "request_error", 1),
])
def test_no_invented_appointment(success, deadline, reply, status, calls):
    ledger, episode = settled(success=success, deadline=deadline)
    llm = Reply(reply) if reply is not None else None
    result = review(ledger, episode, llm)
    assert result["status"] == status and result["next_review_at_sim_hour"] is None
    assert len(llm.packets if llm else []) == calls
    assert ledger.state["goal"]["status"] == ("completed" if success else "needs_review")


@pytest.mark.parametrize("raw,status,time", [
    ('{"review_day":5,"review_hour":9}', "scheduled", 105),
    ('{"review_day":5,"review_hour":10}', "invalid_response", None),
    (TimeoutError(), "request_error", None),
])
def test_forward_records_actual_appointment_separately_from_task_outcome(resident, monkeypatch, tmp_path, raw, status, time):
    import proto.agent as agent_module
    from proto.app_entry import DEFAULT_PHONE_USE_NEEDS_VERSION, RESIDENT_DECISION_PLAN_VERSION

    step, data, llm, _ = resident
    ordinary_request = llm.atext_request
    fixture_reply = Reply(raw)

    async def respond(*, dialog, **kwargs):
        if RETRY_REVIEW_VERSION in dialog[1]["content"] and "review_day" in dialog[0]["content"]:
            return await fixture_reply.atext_request(dialog=dialog, **kwargs)
        ordinary = await ordinary_request(dialog=dialog, **kwargs)
        if json.dumps(DEFAULT_PHONE_USE_NEEDS_VERSION) in dialog[1]["content"]:
            return json.dumps({**json.loads(ordinary), "phone_use_decision": "leave_phone"})
        return ordinary

    monkeypatch.setenv("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION", RESIDENT_DECISION_PLAN_VERSION)
    monkeypatch.setattr(llm, "atext_request", respond)
    monkeypatch.setattr(agent_module, "choose_attempt_strategy", lambda **_: AttemptStrategy("avoid"))
    step(3, 9, "engage_goal")
    (episode,) = data["recent_episode_buffer"]
    (row,) = json.loads(data["proto_stage_attempt_rows_json"])
    payload = json.loads(row["payload_json"])
    assert row["outcome_type"] == episode["outcome_type"] == "avoid_without_attempt"
    assert payload["retry_review"] == {"version": RETRY_REVIEW_VERSION, "status": status, "next_review_at_sim_hour": time}
    gate = IntentionLedger(data["proto_goal_state_json"])
    assert gate.goal["next_review_at_sim_hour"] == time and gate.goal["last_episode_ids"] == [episode["episode_id"]]
    assert gate.review_due(104) == (time is None)
    assert gate.review_due(105)
    events = [json.loads(line) for path in tmp_path.glob("*.jsonl") for line in path.read_text().splitlines()]
    settled_trace, = [r for r in events if r["kind"] == "goal_outcome"]
    assert settled_trace["retry_review"] == payload["retry_review"] and settled_trace["goal_state_after"] == gate.goal
    assert len(fixture_reply.packets) == 1
    step(3, 9, "engage_goal")
    assert len(fixture_reply.packets) == 1 and len(data["recent_episode_buffer"]) == 1
    if status == "scheduled":
        for day, hour in ((3, 10), (4, 8)):
            step(day, hour, "no_app")
            assert llm.plans[-1]["actions"] == ["no_app"]
            assert data["proto_goal_state_json"]["goal"]["next_review_at_sim_hour"] == 105
            assert (data["proto_app_entry_rollout_rows_json"][-1]["hour"], data["proto_app_entry_rollout_rows_json"][-1]["active"]) == (hour, False)
        step(4, 9, "drop_goal")
        assert data["proto_goal_state_json"]["goal"]["status"] == "dropped"
        assert len(fixture_reply.packets) == 1 and len(data["recent_episode_buffer"]) == 1
