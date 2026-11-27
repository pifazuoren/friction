import asyncio
import json

import pytest

from hourly_feedback_state import FeedbackState, build_feedback_state
from probe_hourly_intention import DAY, TICK, login_offer
from proto.llm_psychology import (
    prepare_digital_emotion_state_for_day,
    resolve_event_appraisal,
)
from proto.models import AttemptOutcome, AttemptStrategy
from proto.memory.packet import build_task_relevant_memory_packet


FAMILY = "account_login_verification"


def test_intervention_starts_at_same_scheduled_attempt_and_ends_after_one_event():
    success, failure = map(build_feedback_state, ("success", "failure"))
    for key in (
        "before",
        "task",
        "strategy",
        "profile",
        "environment",
        "pre_event_appraisal",
    ):
        assert success.audit[key] == failure.audit[key]
    task4, _, _ = login_offer(day=DAY - 1)
    task5, _, _ = login_offer()
    assert success.audit["task"] == task4.to_dict()
    assert success.episodes[0]["episode_id"] == failure.episodes[0]["episode_id"]
    assert success.help_memory == failure.help_memory
    for state in (success, failure):
        (episode,) = state.episodes
        assert (
            episode["day"] == DAY - 1
            and episode["hour"] == 9
            and episode["tick_seconds"] == TICK
        )
        assert episode["task_id"] == task4.task_id != task5.task_id
        assert (
            episode["requested_strategy_type"]
            == episode["strategy_type"]
            == "attempt_self"
        )
        assert (
            episode["support_delivery_status"] == "not_requested"
            and not episode["help_used"]
        )
        assert episode["outcome_type"] == state.audit["intervention"]["target_outcome"]
        assert episode["helplessness_delta"] == pytest.approx(state.helplessness - 50)
        assert state.audit["outcome"]["event_level_uncontrollability"] == 0
        assert state.audit["event_time"]["report_day"] == 4
        assert state.audit["read_time"]["report_day"] == 5
        assert (
            state.audit["read_time"]["sim_hour"] - state.audit["event_time"]["sim_hour"]
            == 24
        )
        assert (
            state.audit["d4_llm_calls"]
            == state.audit["carry_forward"]["intervening_hourly_steps_executed"]
            == 0
        )
        assert "daily_reflection" in state.audit["carry_forward"]["skipped"]


@pytest.mark.parametrize(
    ("condition", "h", "trust", "avoidance", "efficacy", "streak"),
    [
        ("success", 47.6, 55, 47, 36.12, 0),
        ("failure", 51.16531818181818, 42, 55, 25.12, 1),
    ],
)
def test_d5_values_match_production_rule_updates(
    condition, h, trust, avoidance, efficacy, streak
):
    state = build_feedback_state(condition)
    domain = state.domain_memory[FAMILY]
    assert (state.helplessness, state.trust, state.avoidance) == pytest.approx(
        (h, trust, avoidance)
    )
    assert domain["task_self_efficacy"] == pytest.approx(efficacy)
    assert domain["attempt_count"] == 1 and domain["last_updated_day"] == DAY - 1
    assert state.consecutive_failures == domain["same_task_failure_streak"] == streak
    assert domain["failure_count"] == streak and domain["success_count"] == 1 - streak
    assert domain["recent_negative_feedback_ema"] == pytest.approx(0.3 * streak)
    assert state.help_memory["overall"]["help_attempt_count"] == 0
    assert (
        domain["controllable_success_memory"] == 0
    )  # Neutral pre-event felt control is below 55.
    assert all(
        other["attempt_count"] == 0
        for name, other in state.domain_memory.items()
        if name != FAMILY
    )
    assert state.audit["after"]["task_domain"] == domain


@pytest.mark.parametrize("condition", ["success", "failure"])
def test_emotion_matches_rule_event_appraisal_then_one_day_decay(
    condition, monkeypatch
):
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "off")
    state = build_feedback_state(condition)
    task, _, _ = login_offer(day=DAY - 1)
    before = state.audit["before"]
    event = asyncio.run(
        resolve_event_appraisal(
            llm=None,
            task=task,
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            outcome=AttemptOutcome(**state.audit["outcome"]),
            day=DAY - 1,
            helplessness_now=before["helplessness"],
            consecutive_failures_before=0,
            digital_emotion_state=before["emotion"],
            task_domain_snapshot=before["task_domain"],
            help_effect_snapshot=before["help_overall"],
            recent_episode_summary={},
        )
    )
    assert event.source == "rule"
    after_event = {**event.final_after, "last_updated_day": DAY - 1}
    assert state.audit["post_event_emotion"] == after_event
    assert (
        state.emotion
        == prepare_digital_emotion_state_for_day(after_event, target_day=DAY).to_dict()
    )
    # The live D5 hybrid psychology setting must not run a D4 model or alter either branch.
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    assert build_feedback_state(condition).to_dict() == state.to_dict()


def test_state_can_be_replayed_without_shared_mutable_memory():
    state = build_feedback_state("success")
    archive = json.loads(json.dumps(state.to_dict(), allow_nan=False))
    recovered = FeedbackState.from_dict(archive)
    assert recovered == state
    recovered.domain_memory[FAMILY]["attempt_count"] += 1
    assert (
        archive["domain_memory"][FAMILY]["attempt_count"]
        == state.domain_memory[FAMILY]["attempt_count"]
        == 1
    )
    assert build_feedback_state("success") == state


def test_unknown_outcome_is_rejected():
    with pytest.raises(ValueError, match="condition"):
        build_feedback_state("avoid")


@pytest.mark.parametrize("condition", ["success", "failure"])
def test_production_reader_retrieves_same_d4_attempt_from_both_memory_sources(
    condition,
):
    state = build_feedback_state(condition)
    (episode,) = state.episodes
    (event,) = state.event_log
    assert state.audit["before"]["event_log"] == []
    assert state.audit["after"]["event_log"] == [event]
    assert event["day"] == episode["day"] and event["t"] == episode["tick_seconds"]
    assert event["attempt_uid"] == episode["task_id"] and event["scenario"] == FAMILY
    assert event["roll"] == state.audit["outcome"]["success_probability"]
    assert event["decision"]["primary_reason"] == episode["outcome_type"]
    task, _, _ = login_offer()
    inputs = dict(
        task=task,
        task_domain_memory=state.domain_memory,
        help_effect_memory=state.help_memory,
        recent_episode_summary={},
        recent_episode_buffer=state.episodes,
        event_log=state.event_log,
        tick_seconds=TICK,
    )
    packet = build_task_relevant_memory_packet(**inputs, simulation_day=DAY)
    assert packet["recent_same_task_outcomes_tail"] == [episode["outcome_type"]]
    (same_task,) = packet["recent_same_task_events_tail"]
    (recent,) = packet["recent_task_episodes"]
    for key in (
        "episode_id",
        "task_id",
        "day",
        "hour",
        "tick_seconds",
        "task_family",
        "strategy_type",
        "requested_strategy_type",
        "outcome_type",
        "help_used",
        "support_delivery_status",
    ):
        assert same_task[key] == recent[key] == episode[key]
    assert same_task["feedback_valence"] == (
        "positive" if condition == "success" else "negative"
    )
    assert same_task["support_quality"] == state.audit["outcome"]["support_quality"]
    before_event = build_task_relevant_memory_packet(**inputs, simulation_day=DAY - 1)
    assert (
        before_event["recent_same_task_events_tail"]
        == before_event["recent_task_episodes"]
        == []
    )
    skipped = state.audit["d4_post_outcome_modules"]
    assert all(
        not module["called"] and module["status"] == "not_called"
        for module in skipped.values()
    )
    assert skipped["infer_event_attribution"]["attribution_confidence"] == 0
    assert skipped["calibrate_uncontrollability"]["value_source"] == "rule"
