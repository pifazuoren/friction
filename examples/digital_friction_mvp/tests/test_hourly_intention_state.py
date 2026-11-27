import pytest

from proto.hourly_intention import IntentionLedger
from proto.logical_clock import monotonic_sim_hour
from proto.runtime import scheduled_login_for_day


def login(day=3):
    return scheduled_login_for_day(
        hour=9,
        agent_id=7,
        day=day,
        tick_seconds=32401,
        env={},
        existing_task=None,
        last_scheduled_day=-1,
    )


def intent(kind, *, oid=None, gid=None, review=None):
    return {
        "kind": kind,
        "opportunity_id": oid,
        "goal_id": gid,
        "next_review_at_sim_hour": review,
        "reason": "A fixture choice.",
    }


def test_deferral_persists_across_midnight_and_new_offers_cannot_displace_it():
    start, end = monotonic_sim_hour(3, 32401), monotonic_sim_hour(4, 32401)
    ledger = IntentionLedger()
    first = ledger.publish(login(), source="scheduled_login", sim_hour=start)
    oid = first["opportunity_id"]
    assert all(
        ledger.publish(login(), source="scheduled_login", sim_hour=h) == first
        for h in (start, start + 1, start + 2)
    )
    assert "template" not in first and "difficulty" not in first
    assert (
        ledger.apply(intent("defer_goal", oid=oid, review=end), sim_hour=start) is None
    )
    ledger = IntentionLedger(ledger.state)
    gid = ledger.goal["goal_id"]
    other = ledger.publish(login(4), source="scheduled_login", sim_hour=end)
    with pytest.raises(ValueError, match="deferred"):
        ledger.apply(intent("continue_goal", gid=gid), sim_hour=end - 1)
    with pytest.raises(ValueError, match="replace"):
        ledger.apply(intent("engage_goal", oid=other["opportunity_id"]), sim_hour=end)
    assert ledger.apply(intent("no_app"), sim_hour=end - 1) is None
    assert ledger.apply(intent("drop_goal", gid=gid), sim_hour=end) is None
    assert ledger.goal is None and ledger.visible(end) == [other]
    ledger.publish(login(), source="scheduled_login", sim_hour=end)
    assert [o["opportunity_id"] for o in ledger.visible(end)] == [
        other["opportunity_id"]
    ]


def test_natural_discovery_is_delayed_and_take_up_resolves_only_offered_identity():
    ledger = IntentionLedger()
    task = login()
    offer = ledger.publish(
        task, source="natural_context", sim_hour=81, required_channel="finance_context"
    )
    oid = offer["opportunity_id"]
    assert not ledger.visible(81)
    with pytest.raises(ValueError, match="invisible"):
        ledger.apply(intent("engage_goal", oid=oid), sim_hour=81)
    assert (
        ledger.apply(intent("engage_goal", oid=oid), sim_hour=82).task_id
        == task.task_id
    )
    ledger.settle(success=False, operation_started=False, episode_id="real-avoid")
    assert (
        ledger.goal["decision_index"] == 1
        and ledger.goal["operation_attempt_count"] == 0
    )
    assert ledger.goal["status"] == "needs_review"
    assert (
        ledger.apply(
            intent("continue_goal", gid=ledger.goal["goal_id"]), sim_hour=84
        ).task_id
        == task.task_id
    )
    ledger.settle(success=True, operation_started=True, episode_id="completed")
    completed = ledger.state["goal"]
    assert (
        completed["decision_index"] == 2 and completed["operation_attempt_count"] == 1
    )
    assert completed["last_episode_ids"] == ["real-avoid", "completed"]


def test_visible_deadline_travels_with_goal_and_expiry_never_executes_a_task():
    ledger = IntentionLedger()
    offer = ledger.publish(
        login(), source="scheduled_login", sim_hour=81, known_deadline_sim_hour=84
    )
    with pytest.raises(ValueError, match="review hour"):
        ledger.apply(
            intent("defer_goal", oid=offer["opportunity_id"], review=85), sim_hour=81
        )
    ledger.apply(
        intent("defer_goal", oid=offer["opportunity_id"], review=84), sim_hour=81
    )
    assert ledger.goal["known_deadline_sim_hour"] == 84 and ledger.visible(84)
    with pytest.raises(ValueError, match="invisible"):
        ledger.apply(intent("continue_goal", gid=ledger.goal["goal_id"]), sim_hour=85)
    assert ledger.expire(85) == [offer["opportunity_id"]]
    assert ledger.state["goal"]["status"] == "expired"
    assert not ledger.visible(85) and not ledger.expire(86) and not ledger.goal
