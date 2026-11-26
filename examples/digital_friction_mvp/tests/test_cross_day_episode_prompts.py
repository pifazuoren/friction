import asyncio
import json

import pytest

from proto.app_entry.rollout import run_app_entry_rollout_hour
from proto.experience_memory import (
    build_initial_help_effect_memory,
    update_experience_memory,
    update_help_effect_memory,
)
from proto.llm_psychology import clear_llm_psychology_caches, resolve_strategy_deliberation
from proto.memory.packet import build_task_relevant_memory_packet, compact_recent_episodes
from proto.models import AttemptStrategy
from proto.support_protocol import SupportResponse
from test_app_entry_rollout import _habit, _needs_payload, _plan_payload
from test_experience_memory import _make_outcome, _make_task
from test_llm_psychology import _set_hybrid_env


class RecordingLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    async def atext_request(self, *, dialog, **kwargs):
        self.prompts.append(json.loads(dialog[1]["content"].split("\n", 1)[1]))
        return json.dumps(self.responses.pop(0))


def record_attempt(outcome_type, tick, history=(), **extra):
    task = _make_task()
    return update_experience_memory(
        task=task, strategy=AttemptStrategy("attempt_self"),
        outcome=_make_outcome(outcome_type, negative_feedback=outcome_type == "failure_after_attempt"),
        day=3, tick_seconds=tick, helplessness_delta=0.0,
        task_domain_memory={}, help_effect_memory={}, recent_episode_buffer=list(history),
        rationale_memory=[], **extra,
    )


def strategy_call(llm, memory):
    packet = build_task_relevant_memory_packet(
        task=_make_task(), task_domain_memory={}, help_effect_memory={},
        recent_episode_summary={}, event_log=[], recent_episode_buffer=memory,
    )
    return asyncio.run(resolve_strategy_deliberation(
        llm=llm, task=_make_task(), task_appraisal={}, effective_helplessness=50,
        task_self_efficacy=50, help_success_rate_smoothed=.5,
        recent_negative_feedback_ratio=.5, recent_same_task_failure_count=1,
        digital_emotion_state={}, daily_reflection={},
        rule_weights={"attempt_self":.4, "seek_help_then_attempt":.4, "avoid":.2},
        task_relevant_memory=packet, recent_episode_summary={},
    ))


def test_completed_attempts_reach_next_days_actual_prompts_and_separate_cache(monkeypatch):
    _set_hybrid_env(monkeypatch)
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "true")
    clear_llm_psychology_caches()
    strategy_reply = {
        "attempt_self_score": .45, "seek_help_score": .4, "avoid_score": .15,
        "dominant_strategy": "attempt_self", "judge_confidence": .9, "reason": "test",
    }
    strategy_llm = RecordingLLM(strategy_reply, strategy_reply, strategy_reply)
    histories = []
    for final_outcome in ("success_self", "failure_after_attempt"):
        first = record_attempt("success_self", 8 * 3600)["recent_episode_buffer"]
        history = record_attempt(
            final_outcome, 10 * 3600, first, requested_strategy_type="seek_help_then_attempt",
            support_request_id="family-request-2", support_delivery_status="not_delivered",
        )["recent_episode_buffer"]
        histories.append(history)
        assert history[0]["episode_id"] != history[1]["episode_id"]
        app_llm = RecordingLLM(_needs_payload(), _plan_payload())
        asyncio.run(run_app_entry_rollout_hour(
            llm=app_llm, agent_id=7, simulation_day=4, tick_seconds=9 * 3600,
            environment={}, stable_profile={}, device_id="fixture", selected_rank=1,
            habit_memory=_habit(), day4_snapshot={"schema_version":"fixture"}, recent_rollout_rows=[],
            recent_task_episodes=history, latest_reflection={}, helplessness=50, trust=50,
            avoidance=50, needs_prompt_version="digital_needs_v1", plan_prompt_version="app_entry_plan_v3",
            json_attempts=1, min_confidence=.5, top_k=5, absolute_exposure_cap=8,
            timeout=1, retries=0, task_occurrence_gate_enabled=False,
        ))
        assert len(app_llm.prompts) == 2
        strategy_call(strategy_llm, history)
        assert len(strategy_llm.prompts) == len(histories)
        for records in [
            *[p["inputs"]["recent_task_episodes"] for p in app_llm.prompts],
            strategy_llm.prompts[-1]["task_relevant_memory"]["recent_task_episodes"],
        ]:
            assert [r["hour"] for r in records] == [8,10]
            assert records[-1]["day"] == 3 and records[-1]["task_id"] == _make_task().task_id
            assert records[-1]["episode_id"] == history[1]["episode_id"]
            assert records[-1]["outcome_type"] == final_outcome
            assert records[-1]["strategy_type"] == "attempt_self"
            assert records[-1]["requested_strategy_type"] == "seek_help_then_attempt"
            assert records[-1]["support_delivery_status"] == "not_delivered"
            assert records[-1]["support_request_id"] == "family-request-2"
    assert histories[0][1]["episode_id"] == histories[1][1]["episode_id"]
    strategy_call(strategy_llm, histories[-1])
    assert len(strategy_llm.prompts) == 2
    strategy_call(strategy_llm, histories[-1][::-1])
    assert len(strategy_llm.prompts) == 3


def test_legacy_history_keeps_available_facts_without_inventing_time_or_identifier():
    legacy = {
        "task_family":"account_login_verification", "strategy":"attempt_self",
        "outcome":"success_self", "support_mode":"enabling_support",
        "private_unstructured_text":"do not publish",
    }
    history = record_attempt("success_self", 8 * 3600, [legacy])["recent_episode_buffer"]
    first = compact_recent_episodes(history)[0]
    assert first["strategy_type"] == "attempt_self" and first["outcome_type"] == "success_self"
    assert first["support_mode"] == "enabling_support"
    assert not {"episode_id", "tick_seconds", "hour", "day", "private_unstructured_text"} & first.keys()


@pytest.mark.parametrize("response", [
    SupportResponse.unavailable(request=None, source="llm_family_helper", audit_status="ok"),
    SupportResponse.unavailable(request=None, source="transport", audit_status="connection_error"),
    {"requester_agent_id":"invalid"},
])
def test_undelivered_support_cannot_count_as_help_success_or_failure(response):
    initial = build_initial_help_effect_memory()
    for outcome_type in ("success_with_help", "failure_even_with_help", "abandon_midway"):
        after = update_help_effect_memory(task=_make_task(), strategy=AttemptStrategy("seek_help_then_attempt"),
            outcome=_make_outcome(outcome_type), help_effect_memory=initial, support_response=response)
        assert after["overall"] == initial["overall"]
    result = record_attempt("success_self", 8*3600, requested_strategy_type="seek_help_then_attempt",
                            support_delivery_status="not_delivered")
    assert result["recent_episode_summary"]["recent_help_seek_ratio"] == 1.0
    assert result["help_effect_memory"]["overall"]["help_attempt_count"] == 0


def test_old_log_recalls_same_family_beyond_recent_five_without_future_or_invented_outcome(monkeypatch):
    from proto.memory.packet import extract_event_log_episodes

    family = _make_task().task_family
    logs = [
        {"scenario": family, "outcome": "negative"},
        {"scenario": family, "day": 3, "t": 60, "attempt_uid":"legacy-task",
         "decision":{"primary_reason":"failure_after_attempt", "strategy_type":"attempt_self",
                     "future_outcome":"secret", "support_response":{"private":"secret"}}},
        *[{"scenario":"another_family", "day":3, "t":3600*h, "outcome":"positive"} for h in range(1,8)],
        {"scenario":family, "day":4, "t":3600, "decision":{"primary_reason":"success_with_help"}},
        {"scenario":family, "day":5, "t":0, "decision":{"primary_reason":"success_with_help"}},
    ]
    prior = extract_event_log_episodes(logs, simulation_day=4, tick_seconds=3600)
    assert all(r["task_family"] == "another_family" for r in prior) and len(prior) == 5
    packet = build_task_relevant_memory_packet(task=_make_task(), task_domain_memory={},
        help_effect_memory={}, recent_episode_summary={}, event_log=logs, simulation_day=4, tick_seconds=3600)
    assert packet["recent_task_episodes"] == prior

    _set_hybrid_env(monkeypatch)
    llm = RecordingLLM({"attempt_self_score": .45, "seek_help_score": .4, "avoid_score": .15,
                        "dominant_strategy": "attempt_self", "judge_confidence": .9, "reason":"test"})
    asyncio.run(resolve_strategy_deliberation(llm=llm, task=_make_task(), task_appraisal={},
        effective_helplessness=50, task_self_efficacy=50, help_success_rate_smoothed=.5,
        recent_negative_feedback_ratio=0, recent_same_task_failure_count=1, digital_emotion_state={},
        daily_reflection={}, rule_weights={"attempt_self":.4, "seek_help_then_attempt":.4, "avoid":.2},
        task_relevant_memory=packet))
    prior_family = llm.prompts[0]["task_relevant_memory"]["recent_same_task_events_tail"]
    assert len(prior_family) == 2
    assert prior_family[0] == {"task_family":family, "feedback_valence":"negative"}
    assert prior_family[1]["outcome_type"] == "failure_after_attempt"
    assert prior_family[1]["strategy_type"] == "attempt_self"
    assert prior_family[1]["tick_seconds"] == 60 and prior_family[1]["day"] == 3
    assert "secret" not in json.dumps(llm.prompts[0])


@pytest.mark.parametrize(("outcome_type","help_used","status"), [
    ("success_self",False,"technical_failure"), ("success_with_help",False,"not_delivered"),
    ("failure_even_with_help",True,"not_delivered"), ("abandon_midway",True,"not_delivered"),
])
def test_invalid_assistance_cannot_write_or_update_personal_history(outcome_type, help_used, status):
    history = [{"day":1,"task_family":"older"}]
    initial = build_initial_help_effect_memory()
    with pytest.raises(ValueError):
        update_experience_memory(task=_make_task(),strategy=AttemptStrategy("seek_help_then_attempt"),
            outcome=_make_outcome(outcome_type,help_used=help_used), day=3, tick_seconds=3600,
            helplessness_delta=8,task_domain_memory={},help_effect_memory=initial,
            recent_episode_buffer=history,rationale_memory=[], support_delivery_status=status)
    assert history == [{"day":1,"task_family":"older"}]
    assert initial["overall"]["help_attempt_count"] == 0


def test_verified_family_delivery_source_preserves_existing_help_bucket():
    response = SupportResponse(request_id="family-1",support_style="enabling",instruction_quality="high",
        autonomy_preservation="high",proxy_completion_level="none",emotional_tone="patient",
        response_delay="immediate",confidence=.95,responded=True,source="llm_family_helper",audit_status="ok")
    result = update_experience_memory(task=_make_task(),strategy=AttemptStrategy("seek_help_then_attempt"),
        outcome=_make_outcome("success_with_help",help_used=True),day=3,tick_seconds=3600,helplessness_delta=-1,
        task_domain_memory={}, help_effect_memory={},recent_episode_buffer=[],rationale_memory=[],
        support_response=response)
    assert result["recent_episode_buffer"][-1]["help_source"] == "family_helper"
    assert result["help_effect_memory"]["by_source"]["generic"]["help_success_count"] == 1

@pytest.mark.parametrize("timestamps", [{}, {"tick_seconds":"", "hour":float("nan")}])
def test_sparse_legacy_row_remains_sparse_after_another_append(timestamps):
    sparse = {"day":2, "task_family":"account_login_verification", **timestamps}
    result = record_attempt("success_self", 1, [sparse])
    assert result["recent_episode_buffer"][0] == {"day":2, "task_family":"account_login_verification"}
    assert compact_recent_episodes(result["recent_episode_buffer"])[0] == {
        "day":2, "task_family":"account_login_verification",
    }


@pytest.mark.parametrize("tick", ["", float("nan"), float("inf")])
def test_new_timed_attempt_rejects_invalid_clock(tick):
    with pytest.raises(ValueError, match="finite nonnegative"):
        record_attempt("success_self", tick)
