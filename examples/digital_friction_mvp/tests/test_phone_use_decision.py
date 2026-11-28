"""Run both hourly blocks with controlled replies and check the actual messages and execution."""
import asyncio
import json

import pytest

from proto.app_entry import DEFAULT_PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V5, RESIDENT_DECISION_PLAN_VERSION
from proto.app_entry.intention_contract import COMPACT_PLAN_V8, COMPACT_PLAN_V9
from proto.app_entry.needs import (
    DIGITAL_NEED_LABELS, HABIT_KEY, OBSERVED_HABIT_KEY, PHONE_USE_NEEDS_V1, PHONE_USE_NEEDS_V2,
    PHONE_USE_NEEDS_V3, PHONE_USE_NEEDS_VERSION, DigitalNeedsBlock, sanitize_digital_needs_payload, sanitize_phone_needs,
)
from proto.app_entry.planner import HourlyIntentionPlanError
from proto.app_entry.phone_policy import resolve_phone_use
from proto.app_entry.rollout import phone_use_habit_fact, run_app_entry_rollout_hour, with_phone_use_habit_fact
from test_app_entry_needs import _payload
from test_app_entry_planner import FakeLLM
from test_app_entry_rollout import _habit
from test_daily_channel_choices import SOCIAL, wire
from test_hourly_intention_plan import OFFER


def run_hour(llm, **overrides):
    options = dict(
        agent_id=2, simulation_day=3, tick_seconds=3 * 3600 + 1, environment={}, stable_profile={"age": 71},
        device_id="device-2", selected_rank=2, habit_memory={**_habit(), "active_by_hour": {"3": {"seen": 3, "active": 0}}},
        day4_snapshot={"initialized": True}, recent_rollout_rows=[{
            "talkingdata_day": 4, "hour": 2, "active": True, "primary_context": SOCIAL,
        }], recent_task_episodes=[], latest_reflection={}, helplessness=40, trust=50, avoidance=50,
        needs_prompt_version="digital_needs_compact_v2", plan_prompt_version=RESIDENT_DECISION_PLAN_VERSION,
        phone_use_needs_version=PHONE_USE_NEEDS_VERSION,
        json_attempts=1, min_confidence=.5, top_k=6, absolute_exposure_cap=8, timeout=10, retries=1,
        hourly_intention_mode="opportunity_v1",
    )
    return asyncio.run(run_app_entry_rollout_hour(llm=llm, **{**options, **overrides}))


def sent(llm, index):
    content = llm.requests[index]["dialog"][1]["content"]
    return json.loads(content[content.index("{"):])


def test_new_and_archived_free_hour_only_differ_by_replay_fact_and_version():
    counts = {SOCIAL: 2, "finance_context": 2, "taxonomy_profile_only": 12}
    habit = {**_habit(), "active_by_hour": {"3": {"seen": 3, "active": 2}}, "context_by_hour": {"3": counts}}
    replies = [json.dumps(_payload(phone_use_decision="leave_phone", intensity_hint=None)),
               json.dumps(wire("no_app", []))]
    old, new = FakeLLM(list(replies)), FakeLLM(list(replies))
    run_hour(old, habit_memory=habit, phone_use_needs_version=PHONE_USE_NEEDS_V3)
    run_hour(new, habit_memory=habit)
    a, b = sent(old, 0), sent(new, 0)
    assert old.requests[0]["dialog"][0] == new.requests[0]["dialog"][0]
    assert a["schema_version"] == PHONE_USE_NEEDS_V3
    assert set(a["inputs"]["day1_3_habit"]) == {"replay_days", "same_hour_active"}
    assert b == {**a, "schema_version": PHONE_USE_NEEDS_VERSION,
                 "inputs": with_phone_use_habit_fact(a["inputs"], counts)}
    fact = b["inputs"]["day1_3_habit"]["device_history_fact"]
    assert "03:00 至 03:59" in fact and "其中 2 天记录到 App 活动" in fact
    assert "并列最多的是通讯社交、金融" in fact and "taxonomy" not in fact
    assert sent(old, 1) == sent(new, 1)


@pytest.mark.parametrize("frequency,counts,expected", [
    ({"seen": 3, "active": 0}, {SOCIAL: 99}, "均未记录到 App 活动"),
    ({"seen": 2, "active": 1}, {"unknown_or_unmapped": 4}, "2 天设备记录，其中 1 天记录到 App 活动。"),
    ({"seen": 3, "active": 3}, {}, "3 天设备记录，其中 3 天记录到 App 活动。"),
    ({"seen": 0, "active": 0}, {}, "设备资料不足"),
    ({"seen": 3}, {}, "设备资料不足"),
    (None, None, "设备资料不足"),
])
def test_habit_fact_distinguishes_observed_inactivity_from_unknown_hours_and_categories(frequency, counts, expected):
    fact = phone_use_habit_fact(23, frequency, counts)
    assert expected in fact and "23:00 至 23:59" in fact and "最多" not in fact

@pytest.mark.parametrize("choice,score,action", [
    ("leave_phone", 1.0, "no_app"),
    ("use_phone", 0.0, "habitual_app@open:" + SOCIAL),
])
def test_same_free_hour_can_go_either_way_regardless_of_numeric_intent(choice, score, action):
    llm = FakeLLM([json.dumps(_payload(phone_use_decision=choice, active_intent=score)),
                   json.dumps(wire(action, []))])
    result = run_hour(llm)
    decision, plan = sent(llm, 0), sent(llm, 1)
    assert llm.calls == 2 and decision["schema_version"] == PHONE_USE_NEEDS_VERSION
    assert decision["inputs"]["phone_use_context"] == {"task_opportunity": "none_actionable"}
    assert decision["inputs"]["day1_3_habit"]["same_hour_active"] == {"seen": 3, "active": 0}
    assert decision["inputs"]["recent_simulated_bundles"][0]["primary_context"] == SOCIAL
    assert not {"actions", "channels", "candidate_app_contexts"} & decision.keys()
    assert plan["schema_version"] == COMPACT_PLAN_V9
    assert plan["digital_needs"]["phone_use_decision"] == result.needs.phone_use_decision == choice
    if choice == "leave_phone":
        assert plan["actions"] == ["no_app"] and not plan["channels"]
        assert not result.bundle.active and not result.bundle.app_context_counts
    else:
        assert "no_app" not in plan["actions"] and SOCIAL in plan["channels"]
        assert result.bundle.app_context_counts == {SOCIAL: 1}


@pytest.mark.parametrize("choice,reverse", [
    ("leave_phone", "habitual_app@open:" + SOCIAL), ("use_phone", "no_app"),
])
def test_plan_cannot_reverse_the_phone_choice(choice, reverse):
    bad = json.dumps(wire(reverse, []))
    llm = FakeLLM([json.dumps(_payload(phone_use_decision=choice)), bad, bad])
    with pytest.raises(HourlyIntentionPlanError):
        run_hour(llm)


@pytest.mark.parametrize("repaired,accepted", [("use_phone", False), ("leave_phone", True)])
def test_needs_format_repair_preserves_explicit_decision_and_observation(repaired, accepted):
    llm = FakeLLM(['{"phone_use_decision":"leave_phone","active_intent":',
                   json.dumps(_payload(phone_use_decision=repaired)), json.dumps(wire("no_app", []))])
    if accepted:
        result = run_hour(llm)
        assert result.needs.phone_use_decision == "leave_phone" and not result.bundle.active
    else:
        with pytest.raises(ValueError, match="changed_phone_use_decision"):
            run_hour(llm)
        assert llm.calls == 2
    assert sent(llm, 0) == sent(llm, 1)


def test_unspecified_or_unexecutable_commitment_is_a_technical_failure():
    llm = FakeLLM([json.dumps(_payload()), json.dumps(_payload())])
    with pytest.raises(ValueError, match="DigitalNeedsBlock failed"):
        run_hour(llm)
    empty = _payload(phone_use_decision="use_phone")
    empty["need_pressures"] = dict.fromkeys(empty["need_pressures"], 0)
    llm = FakeLLM([json.dumps(empty)])
    with pytest.raises(HourlyIntentionPlanError) as exc:
        run_hour(llm, habit_memory={"active_exposure_samples": [1]})
    assert llm.calls == 1 and exc.value.audit["parse_status"] == "channel_unavailable"


def test_waiting_hour_keeps_appointment_and_decides_daily_use_independently():
    goal = {**OFFER, "status": "deferred", "goal_id": "g", "next_review_at_sim_hour": 81}
    llm = FakeLLM([json.dumps(_payload(phone_use_decision="leave_phone")), json.dumps(wire("no_app", []))])
    result = run_hour(llm, current_intention=goal, available_opportunities=[OFFER], goal_review_due=False)
    assert sent(llm, 0)["inputs"]["phone_use_context"] == {
        "task_opportunity": "none_actionable", "next_review_at_sim_hour": 81, "hours_until_review": 6,
    }
    assert sent(llm, 1)["pending_review_notice"]["next_review_at_sim_hour"] == 81
    assert result.plan.intent["kind"] == "no_app"


def test_reachable_daytime_task_still_allows_freely_choosing_no_phone():
    llm = FakeLLM([json.dumps(_payload()), json.dumps(wire("no_app", []))])
    result = run_hour(llm, tick_seconds=9 * 3600 + 1, available_opportunities=[OFFER])
    assert "phone_use_context" not in sent(llm, 0)["inputs"] and result.needs.phone_use_decision is None
    assert "engage_goal@o1@open:public_service_context" in sent(llm, 1)["actions"]
    assert result.plan.intent["kind"] == "no_app"


def test_explicit_v3_free_hour_remains_replayable_without_a_phone_commitment():
    llm = FakeLLM([json.dumps(_payload()), json.dumps(wire("no_app", []))])
    run_hour(llm, plan_prompt_version="app_entry_plan_v3")
    assert "phone_use_context" not in sent(llm, 0)["inputs"]
    assert sent(llm, 1)["schema_version"] == COMPACT_PLAN_V8


# First provider reply in resident_choice_20261128_163129_9306a0; all six replies had the same misspelling.
OBSERVED_REPLY = {
    "phone_use_decision": "leave_phone",
    "reasoning": "It's late in the day, and I prefer to spend the remaining time relaxing without distractions.",
    "need_pressures": {"social_need": .5, "entertainment_need": .1, "finance_need": 0., "tool_need": 0.,
                      "health_need": 0., "habital_check_need": 0., "idle_browse_need": 0.,
                      "avoidance_need": 0., "no_app_need": 0.},
    "active_intent": .1, "intensity_hint": 0., "confidence": .8,
}


def test_provider_spelling_is_normalized_and_audited_in_current_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    raw = "```json\n" + json.dumps(OBSERVED_REPLY, indent=2) + "\n```"
    llm = FakeLLM([raw, json.dumps(wire("no_app", []))])
    result = run_hour(llm)
    raw_scores = OBSERVED_REPLY["need_pressures"]
    expected_scores = dict(raw_scores)
    expected_scores[HABIT_KEY] = expected_scores.pop(OBSERVED_HABIT_KEY)
    assert sent(llm, 0)["pressure_keys"] == list(DIGITAL_NEED_LABELS)
    assert OBSERVED_HABIT_KEY in raw_scores and HABIT_KEY not in raw_scores
    assert result.needs.need_pressures == expected_scores and not result.bundle.active
    assert result.needs.audit["parse_status"] == "ok" and llm.calls == 2
    trace = [json.loads(line) for path in tmp_path.glob("*.jsonl") for line in path.read_text().splitlines()]
    events = [r for r in trace if r["module"] == "app_needs"]
    assert [r["kind"] for r in events] == ["request", "response", "pressure_key_normalized", "parse"]
    assert events[1]["raw"] == raw
    assert events[2]["from_key"] == OBSERVED_HABIT_KEY and events[2]["to_key"] == HABIT_KEY
    assert events[2]["phase"] == "initial" and events[3]["parsed"]["need_pressures"] == expected_scores
    old = FakeLLM([raw, raw])
    with pytest.raises(ValueError, match="invalid_schema"):
        asyncio.run(DigitalNeedsBlock().forward(llm=old, input_payload={}, prompt_version=PHONE_USE_NEEDS_V1))


def test_observed_alias_never_supplies_missing_scores_or_hides_conflicts():
    def decode(scores):
        return sanitize_digital_needs_payload({**OBSERVED_REPLY, "need_pressures": scores},
                                               require_phone_decision=True, allow_observed_pressure_alias=True)[0]
    scores = dict(OBSERVED_REPLY["need_pressures"])
    assert decode({**scores, OBSERVED_HABIT_KEY: .73})["need_pressures"][HABIT_KEY] == .73
    assert decode({**scores, HABIT_KEY: 0.}) is None
    assert decode({**scores, OBSERVED_HABIT_KEY: "0.4"}) is None
    assert decode({**scores, "another_typo": 0.}) is None
    scores.pop(OBSERVED_HABIT_KEY)
    assert decode(scores) is None and decode({**scores, "habitull_check_need": .2}) is None


def test_explicit_unused_intensity_survives_from_raw_reply_to_plan_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    # GLM returned this choice and null for the intensity at 03:00 in the archived V2 recheck.
    no_phone = _payload(phone_use_decision="leave_phone", intensity_hint=None)
    llm = FakeLLM([json.dumps(no_phone), json.dumps(wire("no_app", []))])
    result = run_hour(llm)
    assert llm.calls == 2 and result.needs.audit["parse_status"] == "ok"
    assert result.needs.intensity_hint is None and sent(llm, 1)["digital_needs"]["intensity_hint"] is None
    assert result.decision.audit["needs"]["intensity_hint"] is None and not result.bundle.active
    records = [json.loads(line) for path in tmp_path.glob("*.jsonl") for line in path.read_text().splitlines()]
    accepted, = [r["parsed"] for r in records if r["module"] == "app_needs" and r["kind"] == "parse"]
    assert accepted["intensity_hint"] is None and accepted["phone_use_decision"] == "leave_phone"
    for old in (PHONE_USE_NEEDS_V1, PHONE_USE_NEEDS_V2):
        assert sanitize_phone_needs(no_phone, old) == (None, "invalid_schema")
    assert sanitize_phone_needs({**no_phone, "phone_use_decision": "use_phone"}, PHONE_USE_NEEDS_VERSION)[0] is None
    assert sanitize_phone_needs({k: v for k, v in no_phone.items() if k != "intensity_hint"}, PHONE_USE_NEEDS_VERSION)[0] is None
    assert sanitize_phone_needs({**no_phone, "intensity_hint": 0}, PHONE_USE_NEEDS_VERSION)[0]["intensity_hint"] == 0.0


def test_v5_history_and_current_advice_change_odds_with_a_common_hourly_draw():
    def resolve(active, advice, **changes):
        args = dict(agent_id=2, talkingdata_day=4, hour=3)
        return resolve_phone_use(same_hour_active={"seen": 3, "active": active}, recommendation=advice,
                                 **{**args, **changes})

    frequent = resolve(3, "leave_phone")
    idle = resolve(0, "leave_phone")
    assert frequent["source"] == idle["source"] == "habit_plus_llm"
    assert frequent["seed"] == idle["seed"] == 101
    assert frequent["prior_use_probability"] == 7 / 8 and idle["prior_use_probability"] == 1 / 8
    assert frequent["use_probability"] == pytest.approx(7 / 9) and idle["use_probability"] == pytest.approx(1 / 15)
    assert frequent["sample_u"] == idle["sample_u"] and frequent["final_choice"] != idle["final_choice"]
    mixed = [resolve(2, advice) for advice in ("leave_phone", "follow_habit", "use_phone")]
    assert [r["odds_multiplier"] for r in mixed] == [.5, 1, 2]
    assert [r["use_probability"] for r in mixed] == pytest.approx([5 / 11, 5 / 8, 10 / 13])
    assert all(r["sample_u"] == frequent["sample_u"] for r in mixed)
    assert mixed[0]["final_choice"] != mixed[-1]["final_choice"]
    assert resolve(2, "follow_habit", paired_environment_seed=101) == mixed[1]
    for change in ({"paired_environment_seed": 0}, {"agent_id": 3}, {"talkingdata_day": 5}, {"hour": 4}):
        assert resolve(2, "follow_habit", **change)["sample_u"] != mixed[1]["sample_u"]


@pytest.mark.parametrize("counts", [None, {}, {"seen": 0, "active": 0}, {"seen": True, "active": 0},
                                    {"seen": 4, "active": 3}, {"seen": 2, "active": -1}, {"seen": 2, "active": 3}])
def test_v5_no_history_adopts_only_an_explicit_action(counts):
    kwargs = dict(same_hour_active=counts, agent_id=2, talkingdata_day=4, hour=3)
    for advice in ("use_phone", "leave_phone"):
        record = resolve_phone_use(recommendation=advice, **kwargs)
        assert record["source"] == "llm_without_history" and record["final_choice"] == advice
        assert all(record[k] is None for k in ("seen", "active", "prior_use_probability", "odds_multiplier",
                                               "use_probability", "sample_u"))
    with pytest.raises(ValueError):
        resolve_phone_use(recommendation="follow_habit", **kwargs)
    with pytest.raises(ValueError):
        resolve_phone_use(recommendation="unknown", **kwargs)


def test_v5_habit_can_lead_to_an_actual_app_open_despite_leave_advice(tmp_path, monkeypatch):
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    assert DEFAULT_PHONE_USE_NEEDS_VERSION == PHONE_USE_NEEDS_V5
    # In this hour the only positively supported actionable category comes from device-wide replay.
    habit = {**_habit(), "active_by_hour": {"3": {"seen": 3, "active": 3}},
             "context_by_hour": {"3": {"taxonomy_profile_only": 3}}, "context_total_counts": {SOCIAL: 5}}
    raw = _payload(phone_use_decision="leave_phone", intensity_hint=None, reasoning="I'd prefer to finish reading.")
    raw["need_pressures"] = dict.fromkeys(raw["need_pressures"], 0)
    llm = FakeLLM([json.dumps(raw), json.dumps(wire("habitual_app@open:" + SOCIAL, []))])
    result = run_hour(llm, habit_memory=habit, phone_use_needs_version=PHONE_USE_NEEDS_V5)
    resolution = result.needs.phone_use_resolution
    assert resolution["llm_recommendation"] == "leave_phone" and resolution["final_choice"] == "use_phone"
    assert result.needs.reasoning == raw["reasoning"] and result.needs.intensity_hint is None
    assert result.bundle.app_context_counts == {SOCIAL: 1} and result.bundle.active
    assert result.decision.audit["needs"]["phone_use_resolution"] == resolution
    assert result.decision.audit["needs"]["phone_use_decision"] == "use_phone"
    plan = sent(llm, 1)
    assert "phone_use_resolution" not in plan["digital_needs"]
    assert not any(key in json.dumps(plan) for key in ("sample_u", "odds_multiplier", "prior_use_probability"))
    assert plan["digital_needs"]["intensity_hint"] is None and plan["digital_needs"]["phone_use_decision"] == "use_phone"
    assert plan["actions"] == ["habitual_app@open:" + SOCIAL]
    assert "模拟结果" in llm.requests[1]["dialog"][0]["content"]
    events = [json.loads(line) for p in tmp_path.glob("*.jsonl") for line in p.read_text().splitlines()]
    assert [r["kind"] for r in events if r["module"] == "app_needs"] == [
        "request", "response", "parse", "phone_use_resolution",
    ]
    assert events[2]["parsed"]["phone_use_decision"] == "leave_phone" and events[3]["resolution"] == resolution
    assert events[4]["module"] == "app_plan" and events[4]["kind"] == "request"


def test_v5_with_history_allows_neutral_but_a_repair_cannot_overturn_it():
    neutral = _payload(phone_use_decision="follow_habit", intensity_hint=None)
    llm = FakeLLM([json.dumps(neutral), json.dumps(wire("no_app", []))])
    result = run_hour(llm, phone_use_needs_version=PHONE_USE_NEEDS_V5)
    assert "follow_habit" in sent(llm, 0)["recommendation_options"]
    assert result.needs.phone_use_resolution["odds_multiplier"] == 1 and not result.bundle.active
    changed = FakeLLM(['{"phone_use_decision":"follow_habit","confidence":',
                       json.dumps({**neutral, "phone_use_decision": "use_phone"})])
    with pytest.raises(ValueError, match="changed_phone_use_decision"):
        run_hour(changed, phone_use_needs_version=PHONE_USE_NEEDS_V5)


def test_v5_without_history_repairs_invalid_neutral_and_preserves_unmeasured_intensity():
    neutral = _payload(phone_use_decision="follow_habit", intensity_hint=None)
    llm = FakeLLM([json.dumps(neutral), json.dumps({**neutral, "phone_use_decision": "use_phone"}),
                   json.dumps(wire("habitual_app@open:" + SOCIAL, []))])
    result = run_hour(llm, habit_memory=_habit(), phone_use_needs_version=PHONE_USE_NEEDS_V5)
    assert "follow_habit" not in sent(llm, 0)["recommendation_options"]
    assert result.bundle.active and result.needs.phone_use_resolution["source"] == "llm_without_history"
    assert result.needs.intensity_hint is None and result.needs.audit["repair_requests"] == 1
    bad = FakeLLM([json.dumps(neutral), json.dumps(neutral)])
    with pytest.raises(ValueError, match="DigitalNeedsBlock failed"):
        run_hour(bad, habit_memory=_habit(), phone_use_needs_version=PHONE_USE_NEEDS_V5)
    assert bad.calls == 2


def test_v5_resolved_use_without_channels_fails_explicitly():
    reply = _payload(phone_use_decision="follow_habit", intensity_hint=None)
    reply["need_pressures"] = dict.fromkeys(reply["need_pressures"], 0)
    llm = FakeLLM([json.dumps(reply)])
    habit = {"active_by_hour": {"3": {"seen": 3, "active": 3}}, "active_exposure_samples": [1],
             "context_by_hour": {"3": {"unknown_or_unmapped": 8}}}
    with pytest.raises(HourlyIntentionPlanError) as exc:
        run_hour(llm, habit_memory=habit, phone_use_needs_version=PHONE_USE_NEEDS_V5)
    assert llm.calls == 1 and exc.value.audit["parse_status"] == "channel_unavailable"
    assert exc.value.audit["phone_use_resolution"]["final_choice"] == "use_phone"


def test_v5_rejects_later_replay_days_before_any_model_request():
    llm = FakeLLM([])
    with pytest.raises(ValueError, match="replay days 1..3"):
        run_hour(llm, habit_memory={**_habit(), "replay_days": [1, 2, 4]}, phone_use_needs_version=PHONE_USE_NEEDS_V5)
    assert llm.calls == 0


def test_v5_leaves_task_opportunity_to_the_existing_planner():
    llm = FakeLLM([json.dumps(_payload()), json.dumps(wire("no_app", []))])
    result = run_hour(llm, tick_seconds=9 * 3600 + 1, available_opportunities=[OFFER],
                      phone_use_needs_version=PHONE_USE_NEEDS_V5)
    assert result.needs.phone_use_decision is None and result.needs.phone_use_resolution is None
    assert "recommendation_options" not in sent(llm, 0)
    assert "phone_use_resolution" not in sent(llm, 1)["digital_needs"]
    assert "engage_goal@o1@open:public_service_context" in sent(llm, 1)["actions"]
