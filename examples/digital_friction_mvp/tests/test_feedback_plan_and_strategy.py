import asyncio
from copy import deepcopy
import json

import pytest

from hourly_factorial_design import prepare_design, verify_design_stimuli
from hourly_feedback_state import build_feedback_state
from probe_hourly_intention import DAY, HOUR, PROFILE, SCENES, SIM_HOUR, TICK, load_history, login_offer, run_plan
import probe_hourly_strategy as lower
from proto.experience_memory import extract_memory_features
from proto.memory.packet import build_task_relevant_memory_packet, compact_recent_episodes, compact_support_context
from run_hourly_intention_pairs import CapturePlan
from test_hourly_strategy_probe import APPRAISAL, STRATEGY, Responses, payload, routed_task


def test_updated_preflight_validates_only_the_production_d4_change_at_every_plan_transport():
    history = load_history(None)
    original = asyncio.run(prepare_design(history))
    updated = asyncio.run(prepare_design(history, feedback_mode="updated"))
    assert set(updated) == {*original, "feedback_states"}
    assert updated["manifest"] == original["manifest"]
    assert updated["preflight"] == original["preflight"]
    assert sum(len(routes) for routes in updated["preflight"].values()) == 8
    for routes in updated["preflight"].values():
        assert routes["engage_goal"]["task_admitted"]
        assert routes["defer_goal"]["next_review_at_sim_hour"] == SIM_HOUR + 24
        assert all(not routes[kind]["task_admitted"] for kind in ("defer_goal", "drop_goal", "no_app"))
    for scene, condition, field in (
        ("S0", "failure", "pre_hour_psychology"),
        ("S1", "success", "recent_task_episodes"),
        ("S1", "failure", "day1_3_habit"),
        ("S0", "success", "related_task_episode_ids"),
    ):
        tampered = deepcopy(updated["stimuli"])
        message = tampered[scene][condition]["messages"][1]
        prefix, raw = message["content"].split("\n", 1)
        body = json.loads(raw)
        body["inputs"][field] = {}
        message["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
        with pytest.raises(ValueError, match="Plan request"):
            verify_design_stimuli(
                tampered, feedback_states=updated["feedback_states"], frozen_stimuli=original["stimuli"]
            )


def test_actual_plan_and_both_admitted_messages_share_one_branch(monkeypatch):
    for key, value in lower.FROZEN_RUNTIME_ENV.items():
        monkeypatch.setenv(key, value)
    history = load_history(None)
    design = asyncio.run(prepare_design(history, feedback_mode="updated"))
    strategy_streaks = []
    for name in ("compute_rule_strategy_weights", "choose_attempt_strategy"):
        original_fn = getattr(lower, name)

        def observed(*, _fn=original_fn, **kwargs):
            strategy_streaks.append(kwargs["consecutive_failures"])
            return _fn(**kwargs)

        monkeypatch.setattr(lower, name, observed)

    unchanged_prompts = []
    for condition in ("success", "failure"):
        state = build_feedback_state(condition)
        archived = design["feedback_states"][condition]
        assert json.loads(json.dumps(archived, allow_nan=False)) == state.to_dict()
        episodes = compact_recent_episodes(state.episodes, simulation_day=DAY, tick_seconds=TICK)
        assert len(episodes) == 1
        episode, = episodes
        for scene in SCENES:
            task = routed_task(scene)
            assert task.task_id != episode["task_id"]
            capture = CapturePlan("opportunity_v1")
            asyncio.run(run_plan(
                capture, mode="opportunity_v1", history=history, scene=scene,
                condition=condition, feedback_state=state,
            ))
            assert capture.requests == [design["stimuli"][scene][condition]]
            plan = payload(capture.requests[0]["messages"])["inputs"]
            assert plan["recent_task_episodes"] == episodes
            assert plan["related_task_episode_ids"] == [episode["episode_id"]]
            assert plan["pre_hour_psychology"] == {
                "helplessness": state.helplessness, "trust_in_apps": state.trust, "avoidance_tendency": state.avoidance,
            }
            assert plan["stable_profile"] == PROFILE and plan["hour"] == HOUR
            assert plan["available_opportunities"] == [login_offer(scene=scene)[2]]

            transport = Responses(APPRAISAL, STRATEGY)
            streak_start = len(strategy_streaks)
            result = asyncio.run(lower.measure_admitted(
                transport, condition=condition, feedback_state=archived, task=task, sample_u=0.50,
            ))
            assert result["lower_valid"] and len(transport.dialogs) == 2
            assert strategy_streaks[streak_start:] == [state.consecutive_failures] * 2
            appraisal, strategy = map(payload, transport.dialogs)
            features = extract_memory_features(
                task=task, helplessness_score=state.helplessness, task_domain_memory=state.domain_memory,
                help_effect_memory=state.help_memory, recent_episode_buffer=state.episodes,
                digital_emotion_state=state.emotion, psychology_mode="hybrid",
                task_appraisal_result=result["appraisal"],
            )
            recent = {key: getattr(features, key) for key in (
                "recent_negative_feedback_ratio", "recent_avoid_ratio", "recent_help_seek_ratio",
                "recent_same_task_failure_count", "recent_failure_pressure",
            )}
            packet = build_task_relevant_memory_packet(
                task=task, task_domain_memory=state.domain_memory, help_effect_memory=state.help_memory,
                recent_episode_summary=recent, event_log=state.event_log, recent_episode_buffer=state.episodes,
                simulation_day=DAY, tick_seconds=TICK,
            )
            assert packet["recent_task_episodes"] == episodes
            assert packet["recent_same_task_outcomes_tail"] == [episode["outcome_type"]]
            event, = packet["recent_same_task_events_tail"]
            for field in ("episode_id", "task_id", "day", "tick_seconds", "requested_strategy_type", "outcome_type"):
                assert event[field] == episode[field]
            assert packet["same_task_attempt_count"] == 1
            assert packet["same_task_failure_streak"] == recent["recent_same_task_failure_count"] == int(condition == "failure")
            assert appraisal.pop("Task-Specific Memory") == {
                **packet, "help_success_rate_smoothed_0_1": round(features.help_success_rate_smoothed, 4),
            }
            assert strategy.pop("task_relevant_memory") == packet
            assert result["help_request_dispatched"]
            assert result["help_request"]["memory_context"] == compact_support_context(packet)
            assert appraisal.pop("Recent Experience") == recent
            assert strategy.pop("recent_episode_summary") == {key: round(value, 4) for key, value in recent.items()}
            assert appraisal.pop("Current Status") == {
                "helplessness_now_0_100": round(state.helplessness, 4),
                "task_self_efficacy_0_100": round(features.task_self_efficacy, 4),
            }
            for field in (
                "effective_helplessness", "task_self_efficacy", "help_success_rate_smoothed",
                "recent_negative_feedback_ratio", "recent_same_task_failure_count",
            ):
                assert strategy.pop(field) == round(getattr(features, field), 4)
            expected_emotion = {k: round(state.emotion[k], 4) for k in ("anxiety", "frustration", "relief", "confidence")}
            assert appraisal.pop("Digital Emotion State") == strategy.pop("digital_emotion_state") == expected_emotion
            offer, = plan["available_opportunities"]
            for body, task_key in ((appraisal, "Current Task"), (strategy, "task")):
                assert body[task_key].pop("visible_description") == offer["visible_description"]
            unchanged_prompts.append((appraisal, strategy))
            assert state.to_dict() == archived
    assert all(items == unchanged_prompts[0] for items in unchanged_prompts)


def test_wrong_arm_fails_before_sending_any_model_message(monkeypatch):
    for key, value in lower.FROZEN_RUNTIME_ENV.items():
        monkeypatch.setenv(key, value)
    for_state = build_feedback_state("success").to_dict()
    empty = Responses()
    with pytest.raises(ValueError, match="assigned condition"):
        asyncio.run(run_plan(empty, mode="opportunity_v1", condition="failure", history=load_history(None), feedback_state=for_state))
    with pytest.raises(ValueError, match="assigned condition"):
        asyncio.run(lower.measure_admitted(empty, task=routed_task(), condition="failure", sample_u=0.4, feedback_state=for_state))
    assert not empty.dialogs
