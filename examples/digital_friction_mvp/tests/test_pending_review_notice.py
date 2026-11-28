import json

import pytest

from proto.app_entry.intention_contract import COMPACT_PLAN_V6, COMPACT_PLAN_V7
from proto.app_entry.planner import HourlyIntentionPlanError
from test_hourly_intention_plan import CHANNEL, OFFER, FakeLLM, choice, packet, plan, response


def observation(*, status="deferred", review=96, due=False):
    goal = {**OFFER, "goal_id": "goal:1", "status": status, "next_review_at_sim_hour": review}
    return packet(hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER],
                  current_intention=goal if status else None, goal_review_due=due)


def captured(obs, **options):
    transport = FakeLLM([response(choice("no_app"), additional_apps=[])])
    result = plan(transport, obs, **options)
    return result, transport.requests[0]["dialog"]


def test_future_review_notice_preserves_menu_and_both_activity_options():
    obs = observation()
    idle, current = captured(obs)
    _, frozen = captured(obs, include_pending_review_notice=False)
    _, old_notice = captured(obs, pending_review_notice_version="pending_review_v1")
    assert old_notice[0] == frozen[0]
    instructions = current[0]["content"]
    for token in ("defer_goal", "drop_goal", "engage_goal", "continue_goal", "defer_options"):
        assert token not in instructions and token in old_notice[0]["content"]
    for field in ("habitual_app@open:", "no_app", "attitude", "subjective_norm", "perceived_control",
                  "confidence", "reason", "additional_apps", "exposure_cap"):
        assert field in instructions
    prefix, text = current[1]["content"].split("\n", 1)
    body = json.loads(text)
    notice = body.pop("pending_review_notice")
    assert notice["version"] == "pending_review_v2"
    old_body = json.loads(old_notice[1]["content"].split("\n", 1)[1])
    assert old_body.pop("pending_review_notice") == {**notice, "version": "pending_review_v1"}
    assert old_body == body
    assert notice["next_review_at_sim_hour"] == 96 and notice["hours_until_review"] == 15
    assert "第5天00:00" in notice["message"]
    assert prefix + "\n" + json.dumps(body, ensure_ascii=False) == frozen[1]["content"]
    assert body["targets"] == {} and body["defer_options"] == {}
    assert idle.intent["kind"] == "no_app" and not idle.app_context_counts
    daily = plan(FakeLLM([response(choice("habitual_app"), additional_apps=[])]), obs)
    assert daily.intent["kind"] == "habitual_app" and daily.app_context_counts == {CHANNEL: 1}


@pytest.mark.parametrize("obs,options", [
    (observation(status=None, due=True), {}),
    (observation(review=81, due=True), {}),
    (observation(status="needs_review"), {}),
    (observation(), {"compact_schema_version": COMPACT_PLAN_V6}),
    (observation(), {"compact_schema_version": COMPACT_PLAN_V7}),
])
def test_notice_preserves_unrelated_and_historical_prompts_byte_for_byte(obs, options):
    assert captured(obs, **options)[1] == captured(obs, include_pending_review_notice=False, **options)[1]


def test_another_deferral_while_waiting_is_still_a_failure():
    reply = response(choice("defer_goal", goal="goal:1", review=99), additional_apps=[])
    with pytest.raises(HourlyIntentionPlanError) as exc:
        plan(FakeLLM([reply, reply]), observation())
    assert exc.value.audit["accepted_choice"] is None and exc.value.audit["technical_failure"]
