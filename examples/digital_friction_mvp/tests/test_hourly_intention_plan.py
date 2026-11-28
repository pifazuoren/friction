"""Check the messages sent to the production Plan and the actions it accepts."""

import asyncio
import json

import pytest

from proto.app_entry.intention_contract import (
    COMPACT_PLAN_VERSION,
    COMPACT_PLAN_V3,
    COMPACT_PLAN_V4,
    COMPACT_PLAN_V7,
    COMPACT_PLAN_V8,
    compact_menu,
    compact_observation,
)
from proto.app_entry.planner import (
    CALIBRATED_PLAN_VERSION,
    DigitalAppEntryPlanBlock,
    HourlyIntentionPlanError,
    decode_compact_plan,
)
from proto.app_entry.rollout import (
    build_rollout_input_packet,
    run_app_entry_rollout_hour,
)
from proto.app_entry.types import _stable_hash
from test_app_entry_planner import FakeLLM, _active_payload, _needs
from test_app_entry_rollout import _habit, _needs_payload


CHANNEL = "public_service_context"
OFFER = {
    "opportunity_id": "login:1",
    "source": "scheduled_login",
    "task_family": "login",
    "visible_description": "A login is available.",
    "required_channel": CHANNEL,
    "offered_at_sim_hour": 81,
    "visible_from_sim_hour": 81,
    "known_deadline_sim_hour": 105,
    "status": "offered",
    "hidden_success_probability": 0.27,
}


def packet(**options):
    return build_rollout_input_packet(
        simulation_day=3,
        talkingdata_day=4,
        hour=9,
        stable_profile={},
        habit_memory={},
        recent_rollout_rows=[],
        recent_task_episodes=[
            {
                "day": 2,
                "episode_id": "previous",
                "task_family": "login",
                "outcome_type": "failure",
            },
            {"day": 3, "hour": 9, "episode_id": "same_hour", "task_family": "login"},
        ],
        latest_reflection={},
        helplessness=20,
        trust=30,
        avoidance=40,
        environment={},
        intensity_profile={"active_exposure_cap": 5},
        **options,
    )


def choice(kind, opp=None, goal=None, review=None):
    return dict(
        kind=kind,
        opportunity_id=opp,
        goal_id=goal,
        next_review_at_sim_hour=review,
        reason="A choice for this hour.",
    )


def response(intent, **fields):
    token = intent["kind"]
    if intent["opportunity_id"] is not None:
        token += "@o1" if intent["opportunity_id"] == "login:1" else "@unknown"
    if intent["goal_id"] is not None:
        token += "@g1" if intent["goal_id"] == "goal:1" else "@unknown"
    handling = intent["kind"] in {"engage_goal", "continue_goal"}
    if handling or intent["kind"] == "habitual_app":
        token += "@open:" + CHANNEL
    if intent["next_review_at_sim_hour"] is not None:
        token += "@" + str(intent["next_review_at_sim_hour"])
    return json.dumps(
        {
            "action": token,
            "additional_apps": [] if handling else [CHANNEL],
            "attitude": 0.7,
            "subjective_norm": 0.2,
            "perceived_control": 0.4,
            "confidence": 0.8,
            "reason": intent["reason"],
            **fields,
        }
    )


def plan(llm, observation, **options):
    return asyncio.run(
        DigitalAppEntryPlanBlock().forward(
            llm=llm,
            needs=_needs(),
            input_payload=observation,
            candidate_contexts={"communication_social_context": 1.0},
            intensity_profile={"active_exposure_cap": 5, "exposures_if_active": 5},
            json_attempts=5,
            **options,
        )
    )


def test_offered_channel_is_selectable_without_previous_use_and_no_hidden_information():
    future = {**OFFER, "opportunity_id": "tomorrow", "visible_from_sim_hour": 105}
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER, future]
    )
    action = choice("engage_goal", "login:1")
    llm = FakeLLM([response(action)])
    result = plan(llm, observation)
    message = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert message["inputs"]["monotonic_sim_hour"] == 81
    assert [
        o["opportunity_id"] for o in message["inputs"]["available_opportunities"]
    ] == ["login:1"]
    assert (
        "hidden_success_probability"
        not in message["inputs"]["available_opportunities"][0]
    )
    assert message["inputs"]["related_task_episode_ids"] == ["previous"]
    assert [r["episode_id"] for r in message["inputs"]["recent_task_episodes"]] == [
        "previous"
    ]
    assert CHANNEL in message["channels"]
    assert message["schema_version"] == COMPACT_PLAN_VERSION
    assert set(message["actions"]) == {
        "habitual_app@open:communication_social_context",
        "habitual_app@open:" + CHANNEL,
        "no_app",
        "engage_goal@o1@open:" + CHANNEL,
        "drop_goal@o1",
    }
    assert message["targets"] == {"o1": "login:1"}
    assert message["defer_options"] == {
        "o1": [f"defer_goal@o1@{hour}" for hour in range(82, 106)]
    }
    assert "output_schema" not in message
    assert result.audit["input_packet_hash"] == _stable_hash(message["inputs"])[:16]
    assert (
        result.intent
        == result.audit["accepted_choice"]
        == result.audit["raw_choice"]
        == action
    )
    assert result.audit["repaired_choice"] is None


def test_legacy_observation_and_plan_do_not_expose_new_choices():
    observation = packet(available_opportunities=[OFFER])
    assert "available_opportunities" not in observation
    llm = FakeLLM(
        [
            json.dumps(
                _active_payload(app_context_counts={"communication_social_context": 1})
            )
        ]
    )
    result = plan(llm, observation)
    assert "intent" not in result.to_dict()
    assert "intent_contract" not in llm.requests[0]["dialog"][1]["content"]


@pytest.mark.parametrize(
    "action,fields",
    [
        (choice("engage_goal", "invisible"), {}),
        (choice("engage_goal", "login:1"), {"apps": []}),
        (
            choice("engage_goal", "login:1"),
            {"apps": ["communication_social_context"]},
        ),
        (choice("continue_goal", goal="missing"), {}),
        (choice("defer_goal", "login:1", review=81), {}),
        (choice("defer_goal", "login:1", review=106), {}),
        (choice("defer_goal", "login:1", review=83.5), {}),
        (choice("no_app"), {"apps": {CHANNEL: 0}}),
        (choice("no_app"), {}),
        (choice("habitual_app", "login:1"), {}),
    ],
)
def test_invalid_intent_fails_after_one_repair(action, fields):
    raw = response(action, **fields)
    llm = FakeLLM([raw, raw, raw])
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            llm,
            packet(
                hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
            ),
        )
    assert llm.calls == 2
    assert caught.value.audit["technical_failure"]
    assert caught.value.audit["accepted_choice"] is None


def test_defer_allows_messaging_and_waits_until_goal_is_due():
    args = dict(hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER])
    action = choice("defer_goal", "login:1", review=105)
    result = plan(
        FakeLLM([response(action, additional_apps=["communication_social_context"])]),
        packet(**args),
    )
    assert result.intent == action and result.active
    current = {
        **OFFER,
        "status": "deferred",
        "goal_id": "goal:1",
        "next_review_at_sim_hour": 105,
    }
    observation = packet(**args, current_intention=current, goal_review_due=False)
    raw = response(choice("continue_goal", goal="goal:1"))
    with pytest.raises(HourlyIntentionPlanError, match="available token"):
        plan(FakeLLM([raw, raw]), observation)
    idle = response(choice("no_app"), additional_apps=[])
    assert plan(FakeLLM([idle]), observation).intent == choice("no_app")


def test_repair_cannot_swap_identifiable_intent_even_when_outer_json_is_broken():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    original = choice("defer_goal", "login:1", review=90)
    changed = choice("engage_goal", "login:1")
    malformed = '{"intent": ' + json.dumps(original) + ', "active":'
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([malformed, response(changed)]), observation)
    audit = caught.value.audit
    assert audit["parse_status"] == "changed_intent_on_repair"
    assert audit["raw_choice"] == original and audit["repaired_choice"] == changed
    assert audit["accepted_choice"] is None and audit["repair_changed_choice"]
    assert (
        audit["input_packet_hash"]
        == _stable_hash(compact_observation(observation))[:16]
    )
    assert audit["input_episode_ids"] == ["previous"]


def test_unknown_original_and_repaired_choice_remain_distinct():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    repaired = choice("drop_goal", "login:1")
    result = plan(FakeLLM(["not a plan", response(repaired)]), observation)
    assert result.audit["raw_choice"] is None
    assert (
        result.audit["repaired_choice"] == result.audit["accepted_choice"] == repaired
    )
    assert result.audit["parse_status"] == "ok_repaired"


def test_repair_may_not_turn_a_stated_inactive_hour_into_an_executed_goal():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    inconsistent = json.loads(response(action, action="engage_goal@o1"))
    inconsistent["apps"] = inconsistent.pop("additional_apps")
    inconsistent = json.dumps(inconsistent)
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([inconsistent, response(action)]), observation)
    assert caught.value.audit["repair_changed_choice"]
    assert (
        caught.value.audit["raw_active"] is False
        and caught.value.audit["repaired_active"] is True
    )


@pytest.mark.parametrize("kind", ["engage_goal", "continue_goal"])
def test_handling_explicit_goal_suppresses_same_hour_natural_task_discovery(kind):
    goal = (
        {**OFFER, "goal_id": "goal:1", "status": "needs_review"}
        if kind == "continue_goal"
        else None
    )
    action = choice(kind, goal="goal:1") if goal else choice(kind, "login:1")
    raw = response(action, additional_apps=["finance_context", "finance_context"])
    llm = FakeLLM([json.dumps(_needs_payload()), raw])
    result = asyncio.run(
        run_app_entry_rollout_hour(
            llm=llm,
            agent_id=7,
            simulation_day=3,
            tick_seconds=9 * 3600,
            environment={},
            stable_profile={},
            device_id="device",
            selected_rank=1,
            habit_memory=_habit(),
            day4_snapshot={"schema_version": "snapshot-v1"},
            recent_rollout_rows=[],
            recent_task_episodes=[],
            latest_reflection={},
            helplessness=40,
            trust=60,
            avoidance=30,
            needs_prompt_version="digital_needs_v1",
            plan_prompt_version="app_entry_plan_v3",
            json_attempts=1,
            min_confidence=0.5,
            top_k=1,
            absolute_exposure_cap=8,
            timeout=30,
            retries=0,
            hourly_intention_mode="opportunity_v1",
            available_opportunities=[OFFER],
            current_intention=goal,
            # A second natural draw would access a prior. The named goal must go straight to execution.
            task_occurrence_gate_enabled=True,
            task_occurrence_prior_path="",
        )
    )
    assert (
        result.bundle.primary_context == "finance_context"
        and result.plan.intent == action
    )
    assert result.decision.task is None
    assert result.decision.entry_status == "task_eligible_context_existing_task_pending"
    assert len(llm.requests) == 2
    assert "available_opportunities" not in llm.requests[0]["dialog"][1]["content"]
    assert "available_opportunities" in llm.requests[1]["dialog"][1]["content"]


def test_exposure_volume_cannot_change_in_a_format_repair():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    original = json.loads(response(action, additional_apps=[CHANNEL, CHANNEL]))
    del original["confidence"]
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM(
                [json.dumps(original), response(action, additional_apps=[CHANNEL])]
            ),
            observation,
        )
    assert caught.value.audit["parse_status"] == "changed_intent_on_repair"


def test_one_checked_repair_can_restore_a_missing_field():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("defer_goal", "login:1", review=90)
    correct = response(action, additional_apps=[])
    original = json.loads(correct)
    del original["perceived_control"]
    llm = FakeLLM([json.dumps(original), correct])
    result = plan(llm, observation)
    prompt = json.loads(llm.requests[1]["dialog"][1]["content"])
    assert "perceived_control" in prompt["error"]
    assert prompt["preserve"]["choice"] == action
    assert prompt["preserve"]["activity"] == {}
    assert result.audit["parse_status"] == "ok_repaired"
    assert result.audit["raw_choice"] == result.audit["accepted_choice"] == action


@pytest.mark.parametrize(
    "field,value",
    [
        ("action", "engage_goal"),
        ("action", ["no_app"]),
        ("action", "engage_goal:opportunity:missing"),
        ("action", "continue_goal:goal:login:1"),
        ("additional_apps", [CHANNEL] * 6),
        ("additional_apps", [" " + CHANNEL]),
        ("additional_apps", [CHANNEL, False]),
        ("additional_apps", {CHANNEL: 1}),
        ("confidence", True),
        ("review", True),
    ],
)
def test_invalid_wire_field_is_never_filled_in_or_clamped(field, value):
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    raw = response(choice("engage_goal", "login:1"), **{field: value})
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([raw, raw]), observation)
    assert (
        caught.value.audit["technical_failure"]
        and caught.value.audit["accepted_choice"] is None
    )


def test_echo_then_old_plan_with_a_missing_service_exposure_stays_rejected():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    raw = (
        '{"schema_version":"hourly_plan_compact_v2","inputs":'
        + json.dumps(observation)[:300]
    )
    repair = json.dumps(
        _active_payload(
            intent=choice("engage_goal", "login:1"),
            app_context_counts={
                "communication_social_context": 8,
                "health_service_context": 3,
                "media_entertainment_context": 1,
                "device_tool_context": 1,
                CHANNEL: 0,
            },
        )
    )
    llm = FakeLLM([raw, repair])
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(llm, observation)
    audit = caught.value.audit
    assert audit["raw_choice"] is None and audit["accepted_choice"] is None
    assert audit["repaired_choice"] == choice("engage_goal", "login:1")
    repair_request = json.loads(llm.requests[1]["dialog"][1]["content"])
    initial = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert repair_request["inputs"] == initial["inputs"]
    assert repair_request["digital_needs"] == initial["digital_needs"]


def test_calibrated_wire_uses_relative_weights_and_the_original_integer_allocation():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    raw = json.loads(response(action))
    del raw["additional_apps"]
    raw["action"] = "engage_goal@o1"
    raw["weights"] = {CHANNEL: 1, "communication_social_context": 1}
    llm = FakeLLM([json.dumps(raw)])
    result = plan(llm, observation, prompt_version=CALIBRATED_PLAN_VERSION)
    message = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert message["schema_version"] == COMPACT_PLAN_V3
    assert message["actions"] == [
        "habitual_app",
        "no_app",
        "engage_goal@o1",
        "drop_goal@o1",
    ]
    assert message["exposures_if_active"] == 5 and "exposure_cap" not in message
    assert result.app_context_counts == {CHANNEL: 2, "communication_social_context": 3}
    assert result.intent == action
    raw["weights"] = {CHANNEL: 0, "communication_social_context": 100}
    with pytest.raises(HourlyIntentionPlanError, match="required_channel"):
        plan(
            FakeLLM([json.dumps(raw)] * 2),
            observation,
            prompt_version=CALIBRATED_PLAN_VERSION,
        )


def test_duplicate_action_cannot_hide_an_incompatible_initial_choice():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    contradictory = '{"action":"no_app",' + response(action)[1:]
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([contradictory, response(action)]), observation)
    assert caught.value.audit["repair_changed_choice"]


def test_malformed_scalar_before_choice_does_not_hide_its_target():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    original = '{"attitude":bad,"action":"defer_goal@o1@90","apps":[]'
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM([original, response(choice("engage_goal", "login:1"))]), observation
        )
    assert caught.value.audit["raw_choice"]["kind"] == "defer_goal"
    assert caught.value.audit["parse_status"] == "changed_intent_on_repair"


def test_partial_list_locks_complete_exposures_and_allows_an_incomplete_name_to_be_finished():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    original = '{"action":"engage_goal@o1@open:public_service_context","additional_apps":["communication_social_context", "public'
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([original, response(action)]), observation)
    assert caught.value.audit["parse_status"] == "changed_intent_on_repair"
    result = plan(
        FakeLLM(
            [
                original,
                response(
                    action, additional_apps=["communication_social_context", CHANNEL]
                ),
            ]
        ),
        observation,
    )
    assert result.audit["parse_status"] == "ok_repaired"


def test_echoed_needs_confidence_is_not_a_stated_decision_score():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    echo = '{"inputs":{"goal_review_due":true},"digital_needs":{"confidence":0.25,"active":true}}'
    result = plan(
        FakeLLM([echo, response(choice("no_app"), additional_apps=[])]),
        observation,
        min_confidence=0.6,
    )
    assert result.audit["parse_status"] == "ok_repaired"
    assert result.audit["raw_choice"] is None


def test_repair_may_not_raise_a_valid_confidence_to_cross_the_acceptance_floor():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("no_app")
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM(
                [
                    response(action, additional_apps=[], confidence=0.2),
                    response(action, additional_apps=[], confidence=0.9),
                ]
            ),
            observation,
            min_confidence=0.6,
        )
    assert caught.value.audit["parse_status"] == "changed_intent_on_repair"


@pytest.mark.parametrize(
    "first",
    [
        {"action": "defer_goal@o1"},
        {"action": "defer_goal:opportunity:login:1", "review": None},
        {"action": "defer_goal:opportunity:login:1", "review": {"review": None}},
    ],
)
def test_only_the_model_can_supply_a_missing_defer_hour_in_a_repair(first):
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("defer_goal", "login:1", review=96)
    malformed = json.dumps(
        {**json.loads(response(action, additional_apps=[])), **first}
    )
    llm = FakeLLM([malformed, response(action, additional_apps=[])])
    result = plan(llm, observation)
    assert result.audit["parse_status"] == "ok_repaired" and llm.calls == 2
    assert result.audit["raw_choice"]["next_review_at_sim_hour"] is None
    assert result.intent["next_review_at_sim_hour"] == 96
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM(
                [
                    malformed,
                    response(choice("drop_goal", "login:1"), additional_apps=[]),
                ]
            ),
            observation,
        )
    assert caught.value.audit["repair_changed_choice"]


def test_stated_complete_defer_token_cannot_be_rescheduled_by_repair():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    original = json.loads(response(choice("defer_goal", "login:1", review=85)))
    del original["attitude"]
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM(
                [
                    json.dumps(original),
                    response(choice("defer_goal", "login:1", review=86)),
                ]
            ),
            observation,
        )
    assert caught.value.audit["repair_changed_choice"]


def test_aliases_map_multiple_opportunities_with_distinct_deadlines_and_colons_in_ids():
    second = {**OFFER, "opportunity_id": "a:@:second", "known_deadline_sim_hour": 81}
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER, second]
    )
    action = choice("defer_goal", "login:1", review=103)
    llm = FakeLLM([response(action, action="defer_goal@o2@103")])
    result = plan(llm, observation)
    body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert body["targets"] == {"o2": "login:1", "o1": "a:@:second"}
    assert all("defer" not in token for token in body["actions"])
    assert list(body["defer_options"]) == ["o2"] and result.intent == action
    assert result.audit["raw_choice"] == action


def test_active_goal_can_be_deferred_to_every_legal_integer_in_a_large_window():
    current = {
        **OFFER,
        "goal_id": "goal:1",
        "status": "needs_review",
        "known_deadline_sim_hour": None,
    }
    observation = packet(
        hourly_intention_mode="opportunity_v1",
        available_opportunities=[OFFER],
        current_intention=current,
        goal_review_due=True,
        max_defer_hours=10**8,
    )
    last = 81 + 10**8
    action = choice("defer_goal", goal="goal:1", review=last)
    llm = FakeLLM([response(action, additional_apps=[])])
    result = plan(llm, observation)
    body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert body["defer_options"] == {
        "g1": {"prefix": "defer_goal@g1@", "first_hour": 82, "last_hour": last}
    }
    assert body["targets"] == {"g1": "goal:1"}
    assert result.intent == action and not result.active
    invalid = response(action, action=f"defer_goal@g1@{last + 1}", additional_apps=[])
    with pytest.raises(HourlyIntentionPlanError):
        plan(FakeLLM([invalid, invalid]), observation)


def test_a_separate_but_stated_integer_time_still_binds_format_repair():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("defer_goal", "login:1", review=93)
    malformed = response(action, action="defer_goal@o1", review=93)
    assert (
        plan(FakeLLM([malformed, response(action)]), observation).audit["parse_status"]
        == "ok_repaired"
    )
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM([malformed, response(choice("defer_goal", "login:1", review=94))]),
            observation,
        )
    assert caught.value.audit["repair_changed_choice"]


@pytest.mark.parametrize("kind", ["engage_goal", "continue_goal"])
def test_explicit_open_and_extra_events_are_counted_once_each(kind):
    goal = (
        {**OFFER, "goal_id": "goal:1", "status": "needs_review"}
        if kind == "continue_goal"
        else None
    )
    observation = packet(
        hourly_intention_mode="opportunity_v1",
        available_opportunities=[OFFER],
        current_intention=goal,
    )
    action = choice(kind, goal="goal:1") if goal else choice(kind, "login:1")
    chat = "communication_social_context"
    for extras in ([], [CHANNEL, chat, CHANNEL, chat]):
        raw = response(action, additional_apps=extras)
        result = plan(FakeLLM([raw]), observation)
        counts = {CHANNEL: 1 + extras.count(CHANNEL)}
        if chat in extras:
            counts[chat] = extras.count(chat)
        assert result.active and result.intent == action
        assert result.audit["raw_opened_channel"] == CHANNEL
        assert result.audit["raw_activity"] == result.app_context_counts == counts
        assert result.active_event_app_exposures == 1 + len(extras)
        assert result.audit["raw_additional_activity"] == {
            channel: extras.count(channel) for channel in set(extras)
        }
    over_cap = response(action, additional_apps=[chat] * 5)
    with pytest.raises(HourlyIntentionPlanError, match="exposure cap"):
        plan(FakeLLM([over_cap] * 2), observation)


@pytest.mark.parametrize("kind,alias", [("engage_goal", "o1"), ("continue_goal", "g1")])
@pytest.mark.parametrize(
    "first_apps", [["health_service_context"], ["made_up_channel"], []]
)
def test_bare_previous_action_and_wrong_channel_cannot_gain_an_opening_on_repair(
    kind, alias, first_apps
):
    goal = (
        {**OFFER, "goal_id": "goal:1", "status": "needs_review"}
        if kind == "continue_goal"
        else None
    )
    health = {
        **OFFER,
        "opportunity_id": "zhealth",
        "required_channel": "health_service_context",
    }
    observation = packet(
        hourly_intention_mode="opportunity_v1",
        available_opportunities=[OFFER, health],
        current_intention=goal,
    )
    action = choice(kind, goal="goal:1") if goal else choice(kind, "login:1")
    original = json.loads(response(action))
    original.pop("additional_apps")
    original.update(action=f"{kind}@{alias}", apps=first_apps)
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM(
                [json.dumps(original), response(action, additional_apps=first_apps)]
            ),
            observation,
        )
    assert caught.value.audit["parse_status"] == "changed_intent_on_repair"
    assert caught.value.audit["raw_opened_channel"] is None
    assert caught.value.audit["accepted_choice"] is None
    assert caught.value.audit["raw_activity"] == {channel: 1 for channel in first_apps}


@pytest.mark.parametrize("apps", [[], ["communication_social_context"]])
def test_composite_token_mixed_with_legacy_claim_of_total_activity_rejects_contradiction(
    apps,
):
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    original = json.loads(response(action))
    original.pop("additional_apps")
    original["apps"] = apps
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(
            FakeLLM([json.dumps(original), response(action, additional_apps=apps)]),
            observation,
        )
    assert caught.value.audit["parse_status"] == "changed_intent_on_repair"


def test_invalid_target_channel_pair_cannot_be_substituted_even_if_both_channels_are_visible():
    second = {
        **OFFER,
        "opportunity_id": "zhealth",
        "required_channel": "health_service_context",
    }
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER, second]
    )
    action = choice("engage_goal", "login:1")
    valid = response(action, additional_apps=["health_service_context"])
    llm = FakeLLM([valid])
    result = plan(llm, observation)
    body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert "engage_goal@o2@open:health_service_context" in body["actions"]
    assert result.app_context_counts == {CHANNEL: 1, "health_service_context": 1}
    forged = json.loads(valid)
    forged["action"] = "engage_goal@o2@open:" + CHANNEL
    with pytest.raises(ValueError):
        decode_compact_plan(forged, body)
    forged_menu = {**body, "actions": [*body["actions"], forged["action"]]}
    with pytest.raises(ValueError, match="menu is inconsistent"):
        decode_compact_plan(forged, forged_menu)


def test_goal_opening_may_not_be_counted_as_an_explicitly_stated_extra_open_on_repair():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    token = json.loads(response(action))["action"]
    raw = (
        '{"action":'
        + json.dumps(token)
        + ',"additional_apps":['
        + json.dumps(CHANNEL)
        + ","
    )
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([raw, response(action)]), observation)
    assert caught.value.audit["repair_changed_choice"]
    llm = FakeLLM([raw, response(action, additional_apps=[CHANNEL])])
    result = plan(llm, observation)
    assert result.audit["parse_status"] == "ok_repaired"
    assert result.audit["raw_active"] is True and result.audit["raw_activity"] is None
    assert result.audit["accepted_opened_channel"] == CHANNEL
    assert (
        result.audit["repaired_activity"] == result.app_context_counts == {CHANNEL: 2}
    )
    repair = json.loads(llm.requests[1]["dialog"][1]["content"])
    assert repair["preserve"]["opened_channel"] == CHANNEL
    assert repair["preserve"]["partial_additional_apps"] == {CHANNEL: 1}


def test_historical_v3_count_reply_can_only_be_replayed_against_its_own_contract():
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    action = choice("engage_goal", "login:1")
    current = response(action)
    llm = FakeLLM([current])
    plan(llm, observation)
    body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    previous_request = {
        **body,
        "schema_version": COMPACT_PLAN_V3,
        **compact_menu(body["inputs"], COMPACT_PLAN_V3),
    }
    older = json.loads(current)
    older.pop("additional_apps")
    older.update(action="engage_goal@o1", apps=[CHANNEL])
    assert decode_compact_plan(older, previous_request)["app_context_counts"] == {
        CHANNEL: 1
    }
    with pytest.raises(ValueError):
        decode_compact_plan(older, body)
    older["apps"] = ["communication_social_context"]
    with pytest.raises(ValueError, match="required_channel"):
        decode_compact_plan(older, previous_request)


@pytest.mark.parametrize(
    "action,extras",
    [
        (choice("defer_goal", "login:1", review=89), []),
        (choice("drop_goal", "login:1"), ["communication_social_context"]),
        (choice("no_app"), []),
    ],
)
def test_nonhandling_actions_only_open_the_explicitly_listed_apps(action, extras):
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER]
    )
    result = plan(FakeLLM([response(action, additional_apps=extras)]), observation)
    assert result.intent == action and result.active == bool(extras)
    assert result.audit["raw_opened_channel"] is None
    assert (
        result.audit["raw_activity"]
        == result.app_context_counts
        == {app: 1 for app in extras}
    )


@pytest.mark.parametrize("extras", [[], [CHANNEL, "communication_social_context", CHANNEL, CHANNEL]])
def test_habitual_first_open_and_repeated_additional_apps_count_towards_the_cap(extras):
    observation = packet(hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER])
    result = plan(FakeLLM([response(choice("habitual_app"), additional_apps=extras)]), observation)
    expected = {channel: extras.count(channel) for channel in set(extras)}
    expected[CHANNEL] = expected.get(CHANNEL, 0) + 1
    assert result.intent == choice("habitual_app")
    assert result.app_context_counts == result.audit["raw_activity"] == expected
    assert result.audit["raw_opened_channel"] == CHANNEL
    assert result.active and result.active_event_app_exposures == 1 + len(extras)
    too_many = response(choice("habitual_app"), additional_apps=[CHANNEL] * 5)
    with pytest.raises(HourlyIntentionPlanError, match="exposure cap"):
        plan(FakeLLM([too_many] * 2), observation)


@pytest.mark.parametrize(
    "first_action", ["habitual_app", "habitual_app@open:unlisted", "habitual_app@open:communication_social_context"]
)
def test_repair_cannot_choose_or_replace_the_first_habitual_channel(first_action):
    observation = packet(hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER])
    correct = response(choice("habitual_app"), additional_apps=[])
    incomplete = {**json.loads(correct), "action": first_action}
    del incomplete["attitude"]
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([json.dumps(incomplete), correct]), observation)
    assert caught.value.audit["repair_changed_choice"]
    assert caught.value.audit["accepted_choice"] is None
    assert caught.value.audit["raw_choice"] == choice("habitual_app")


@pytest.mark.parametrize("extra_fragment", ['["unlisted",', '["communication_social_context",false]'])
def test_habitual_repair_preserves_complete_channel_names_in_a_malformed_extra_list(extra_fragment):
    observation = packet(hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER])
    correct = response(choice("habitual_app"), additional_apps=[])
    original = '{"action":"habitual_app@open:' + CHANNEL + '","additional_apps":' + extra_fragment
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(FakeLLM([original, correct]), observation)
    assert caught.value.audit["repair_changed_choice"]


def test_historical_v4_habitual_decisions_are_revalidated_against_the_transmitted_menu():
    observation = packet(hourly_intention_mode="opportunity_v1", available_opportunities=[OFFER])
    old = response(choice("habitual_app"), action="habitual_app", additional_apps=[CHANNEL, CHANNEL])
    historical = FakeLLM([old])
    before = plan(historical, observation, compact_schema_version=COMPACT_PLAN_V4)
    old_body = json.loads(historical.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    new = response(choice("habitual_app"), additional_apps=[CHANNEL])
    llm = FakeLLM([new])
    after = plan(llm, observation)
    new_body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert old_body["schema_version"] == COMPACT_PLAN_V4
    assert before.app_context_counts == after.app_context_counts == {CHANNEL: 2}
    assert before.audit["raw_opened_channel"] is None
    assert after.audit["raw_opened_channel"] == CHANNEL
    with pytest.raises(ValueError, match="available token"):
        decode_compact_plan(json.loads(old), new_body)
    with pytest.raises(ValueError, match="available token"):
        decode_compact_plan(json.loads(new), old_body)
    with pytest.raises(ValueError, match="active flag"):
        decode_compact_plan({**json.loads(old), "additional_apps": []}, old_body)
    forged = {**new_body, "actions": new_body["actions"] + ["habitual_app"]}
    with pytest.raises(ValueError, match="menu is inconsistent"):
        decode_compact_plan(json.loads(old), forged)


def test_v5_with_no_channels_offers_only_no_app_and_zero_cap_stops_before_request():
    llm = FakeLLM([response(choice("no_app"), additional_apps=[])])
    options = dict(
        llm=llm,
        needs=_needs(),
        input_payload=packet(hourly_intention_mode="opportunity_v1"),
        candidate_contexts={},
        intensity_profile={"active_exposure_cap": 1},
    )
    result = asyncio.run(DigitalAppEntryPlanBlock().forward(**options))
    body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
    assert body["actions"] == ["no_app"] and body["channels"] == []
    assert not result.active
    options["intensity_profile"] = {"active_exposure_cap": 0}
    with pytest.raises(ValueError, match="must be >= 1"):
        asyncio.run(DigitalAppEntryPlanBlock().forward(**options))
    assert len(llm.requests) == 1


@pytest.mark.parametrize(
    "first_token,correct_token,field",
    [
        ("engage_goal@o1", "engage_goal@o1@open:finance_context", "required_opening"),
        ("continue_goal@g1", "continue_goal@g1@open:finance_context", "required_opening"),
        ("defer_goal@g1@3", "defer_goal@g1@100", "review_hour"),
        ("defer_goal@g1@5", "defer_goal@g1@105", "review_hour"),
    ],
)
def test_model_can_complete_only_the_identified_missing_field(first_token, correct_token, field):
    from check_hourly_intention_run import check_compact_repair_request, decode_received_plan

    offer = {**OFFER, "required_channel": "finance_context", "known_deadline_sim_hour": None}
    current = {**offer, "goal_id": "goal:1", "status": "needs_review"} if "@g1" in first_token else None
    observation = packet(
        hourly_intention_mode="opportunity_v1", available_opportunities=[offer],
        current_intention=current, goal_review_due=bool(current),
    )
    observation["monotonic_sim_hour"] = 99
    original = response(choice("no_app"), action=first_token, additional_apps=[])
    corrected = response(choice("no_app"), action=correct_token, additional_apps=[])
    for version in (COMPACT_PLAN_V7, COMPACT_PLAN_V8):
        llm = FakeLLM([original, corrected])
        if version == COMPACT_PLAN_V7:
            with pytest.raises(HourlyIntentionPlanError) as caught:
                plan(llm, observation, compact_schema_version=version)
            assert caught.value.audit["parse_status"] == "changed_intent_on_repair"
        else:
            result = plan(llm, observation, compact_schema_version=version)
            assert result.audit["parse_status"] == "ok_repaired"
            assert result.audit["repair_field"] == field
            assert result.audit["accepted_choice"] == result.intent
        assert llm.calls == 2
        body = json.loads(llm.requests[0]["dialog"][1]["content"].split("\n", 1)[1])
        repair = json.loads(llm.requests[1]["dialog"][1]["content"])
        check_compact_repair_request({"messages": llm.requests[1]["dialog"]}, original, body)
        if version == COMPACT_PLAN_V7:
            assert "repair_field" not in repair and repair["preserve"]["action"] == first_token
            with pytest.raises(ValueError, match="repair changed"):
                decode_received_plan(corrected, original, body, True)
        elif field == "review_hour":
            assert "action" not in repair["preserve"]
            assert repair["preserve"]["choice"]["next_review_at_sim_hour"] is None
            assert repair["preserve"]["choice"]["goal_id"] == "goal:1"
            assert result.audit["raw_choice"]["next_review_at_sim_hour"] == int(first_token.split("@")[-1])
            assert decode_received_plan(corrected, original, body, True)["intent"] == result.intent
        else:
            assert repair["preserve"]["action"] == correct_token
            assert result.audit["raw_opened_channel"] is None
            assert result.app_context_counts == {"finance_context": 1}
            assert decode_received_plan(corrected, original, body, True)["intent"] == result.intent


@pytest.mark.parametrize(
    "first,second,has_window",
    [
        ("defer_goal@o1@3", "defer_goal@o2@90", True),
        ("defer_goal@o1@3", "drop_goal@o1", True),
        ("defer_goal@o1@3", "defer_goal@o1@3", True),
        ("defer_goal@g1@3", "no_app", False),
        ("defer_goal", "no_app", False),
        ("engage_goal@o1", "engage_goal@o2@open:public_service_context", True),
    ],
)
def test_repair_cannot_switch_targets_kinds_or_accept_an_unavailable_time(first, second, has_window):
    current = None if has_window else {
        **OFFER, "goal_id": "goal:1", "status": "deferred", "next_review_at_sim_hour": 104,
    }
    observation = packet(
        hourly_intention_mode="opportunity_v1", current_intention=current, goal_review_due=False,
        available_opportunities=[OFFER, {**OFFER, "opportunity_id": "other"}],
    )
    replies = [response(choice("no_app"), action=token, additional_apps=[]) for token in (first, second)]
    llm = FakeLLM(replies)
    with pytest.raises(HourlyIntentionPlanError) as caught:
        plan(llm, observation)
    assert llm.calls == 2 and caught.value.audit["accepted_choice"] is None
    if not has_window:
        assert "repair_field" not in caught.value.audit
