from __future__ import annotations

import asyncio
import json
import pytest

from proto.llm_psychology import (
    _STRATEGY_DELIBERATION_PROMPT_VERSION,
    _build_strategy_deliberation_cache_key,
    _sanitize_trajectory_appraisal_for_context,
    clear_llm_psychology_caches,
    maybe_generate_daily_reflection,
    prepare_digital_emotion_state_for_day,
    resolve_event_appraisal,
    resolve_strategy_deliberation,
    resolve_task_appraisal,
    resolve_trajectory_appraisal,
)
from proto.models import (
    AttemptOutcome,
    AttemptStrategy,
    DailyReflection,
    DigitalEmotionState,
    DigitalTask,
    TaskAppraisalResult,
)


class _DummyLLM:
    def __init__(self, responses: list[str] | None = None, *, should_raise: bool = False):
        self._responses = list(responses or [])
        self._should_raise = should_raise
        self.last_dialog = None

    async def atext_request(self, **kwargs: object) -> str:
        self.last_dialog = kwargs.get("dialog")
        if self._should_raise:
            raise RuntimeError("llm error")
        if not self._responses:
            return "{}"
        return self._responses.pop(0)


def _set_hybrid_env(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_TASK_APPRAISAL_ENABLED", "true")
    monkeypatch.setenv("PROTO_LLM_EVENT_APPRAISAL_ENABLED", "true")
    monkeypatch.setenv("PROTO_LLM_DAILY_REFLECTION_ENABLED", "true")
    monkeypatch.setenv("PROTO_LLM_STRATEGY_DELIBERATION_ENABLED", "true")
    monkeypatch.setenv("PROTO_LLM_STAGE_INTERVIEW_ENABLED", "false")
    monkeypatch.setenv("PROTO_LLM_FINAL_INTERVIEW_ENABLED", "false")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MIN_CONFIDENCE", "0.65")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_TIMEOUT", "8")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "1")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "false")


def _make_task() -> DigitalTask:
    return DigitalTask(
        task_id="payment-task",
        task_family="payment_risk_confirmation",
        friction_type="payment_risk_popup",
        difficulty=0.67,
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=1,
    )


def _make_outcome(outcome_type: str) -> AttemptOutcome:
    return AttemptOutcome(
        outcome_type=outcome_type,  # type: ignore[arg-type]
        success=outcome_type in {"success_self", "success_with_help"},
        help_used=outcome_type in {"success_with_help", "failure_even_with_help"},
        negative_feedback=outcome_type in {
            "failure_after_attempt",
            "failure_even_with_help",
            "abandon_midway",
        },
        support_quality=2,
        event_level_uncontrollability=2,
        friction_tier=2,
        success_probability=0.5,
        abandon_probability=0.1,
        note="test",
    )


def _extract_last_user_payload(llm: _DummyLLM) -> dict[str, object]:
    assert llm.last_dialog is not None
    content = llm.last_dialog[1]["content"]
    assert isinstance(content, str)
    return json.loads(content.split("\n", 1)[1])


def test_prepare_digital_emotion_state_for_day_decays_across_days() -> None:
    decayed = prepare_digital_emotion_state_for_day(
        {
            "anxiety": 8.0,
            "frustration": 7.0,
            "relief": 1.0,
            "confidence": 2.0,
            "last_updated_day": 1,
        },
        target_day=4,
    )
    assert decayed.anxiety < 8.0
    assert decayed.anxiety > 4.0
    assert decayed.confidence > 2.0
    assert decayed.confidence < 5.0
    assert decayed.last_updated_day == 4


def _valid_trajectory_payload() -> dict[str, object]:
    return {
        "planned_steps": [
            {"step_id": 1, "action": "open payment confirmation page"},
            {"step_id": 2, "action": "read the risk warning"},
        ],
        "selected_friction_points": [
            {"point": "risk_popup_anxiety", "severity": 0.68, "step_id": 2}
        ],
        "friction_encounter_likelihood": 0.68,
        "cognitive_load": 0.70,
        "help_need": 0.45,
        "trajectory_outcome_tendency": {
            "success_self": 0.35,
            "failure_after_attempt": 0.40,
            "abandon_midway": 0.25,
        },
        "trajectory_confidence": 0.74,
        "reason": "Risk warning creates bounded risk appraisal.",
        "does_not_sample_final_outcome": True,
        "does_not_update_psychology": True,
    }


def test_trajectory_sanitizer_accepts_valid_schema() -> None:
    payload, status = _sanitize_trajectory_appraisal_for_context(
        _valid_trajectory_payload(),
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )
    assert status == "ok"
    assert payload is not None
    assert payload["trajectory_outcome_tendency"]["success_self"] == 0.35


def test_trajectory_sanitizer_rejects_schema_and_taxonomy_errors() -> None:
    missing = dict(_valid_trajectory_payload())
    missing.pop("reason")
    assert _sanitize_trajectory_appraisal_for_context(
        missing,
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )[1] == "invalid_schema"

    extra = dict(_valid_trajectory_payload())
    extra["outcome_type"] = "success_self"
    assert _sanitize_trajectory_appraisal_for_context(
        extra,
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )[1] == "invalid_schema"

    bad_taxonomy = dict(_valid_trajectory_payload())
    bad_taxonomy["selected_friction_points"] = [
        {"point": "made_up_point", "severity": 0.4, "step_id": 1}
    ]
    assert _sanitize_trajectory_appraisal_for_context(
        bad_taxonomy,
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )[1] == "taxonomy_outside"


def test_trajectory_sanitizer_rejects_probability_banned_phrase_and_strategy_keys() -> None:
    bad_sum = dict(_valid_trajectory_payload())
    bad_sum["trajectory_outcome_tendency"] = {
        "success_self": 0.20,
        "failure_after_attempt": 0.20,
        "abandon_midway": 0.20,
    }
    assert _sanitize_trajectory_appraisal_for_context(
        bad_sum,
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )[1] == "invalid_probability_sum"

    banned = dict(_valid_trajectory_payload())
    banned["reason"] = "because the user is old"
    assert _sanitize_trajectory_appraisal_for_context(
        banned,
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )[1] == "banned_phrase"

    wrong_keys = dict(_valid_trajectory_payload())
    wrong_keys["trajectory_outcome_tendency"] = {
        "success_with_help": 0.5,
        "failure_even_with_help": 0.2,
        "failure_after_attempt": 0.2,
        "abandon_midway": 0.1,
    }
    assert _sanitize_trajectory_appraisal_for_context(
        wrong_keys,
        task_family="payment_risk_confirmation",
        strategy_type="attempt_self",
    )[1] == "invalid_outcome_keys"


def test_resolve_trajectory_appraisal_uses_strict_json(monkeypatch) -> None:
    _set_hybrid_env(monkeypatch)
    monkeypatch.setenv("PROTO_OUTCOME_MODEL_MODE", "trajectory_shadow")
    llm = _DummyLLM([json.dumps(_valid_trajectory_payload())])
    result = asyncio.run(
        resolve_trajectory_appraisal(
            llm=llm,
            task=_make_task(),
            strategy=AttemptStrategy("attempt_self"),
            task_appraisal=TaskAppraisalResult(
                mode="hybrid",
                status="ok",
                source="llm",
                confidence=0.8,
                reason="test",
                cache_hit=False,
            ).to_dict(),
            memory_features={
                "effective_helplessness": 50,
                "task_self_efficacy": 60,
                "controllable_success_memory": 0.2,
                "recent_same_task_failure_count": 1,
                "recent_negative_feedback_ratio": 0.1,
            },
            env={"risk_level": 2},
            profile_summary={"digital_experience": 0.5, "vision_limit": 0.2},
        )
    )
    assert result["status"] == "ok"
    assert result["prompt_version"] == "trajectory_v1"
    user_payload = _extract_last_user_payload(llm)
    assert "allowed_friction_points" in user_payload
    assert "allowed_outcome_keys" in user_payload


def test_event_appraisal_parses_json_and_caps_shift(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_event_appraisal(
            llm=_DummyLLM(
                [
                    (
                        '{"anxiety":10,"frustration":9,"relief":0,"confidence":0,'
                        '"judge_confidence":0.92,"reason":"high stress"}'
                    )
                ]
            ),
            task=_make_task(),
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            outcome=_make_outcome("failure_after_attempt"),
            helplessness_now=62.0,
            consecutive_failures_before=2,
            digital_emotion_state={
                "anxiety": 4.0,
                "frustration": 3.0,
                "relief": 2.0,
                "confidence": 5.0,
                "last_updated_day": 0,
            },
            task_domain_snapshot={},
            help_effect_snapshot={},
            recent_episode_summary={},
            day=1,
        )
    )
    assert result.status == "ok"
    assert result.llm_after is not None
    for field in ("anxiety", "frustration", "relief", "confidence"):
        assert abs(result.final_after[field] - result.rule_after[field]) <= 2.0001


def test_event_appraisal_falls_back_for_low_confidence(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_event_appraisal(
            llm=_DummyLLM(
                [
                    (
                        '{"anxiety":7,"frustration":7,"relief":0,"confidence":1,'
                        '"judge_confidence":0.30,"reason":"unsure"}'
                    )
                ]
            ),
            task=_make_task(),
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            outcome=_make_outcome("failure_after_attempt"),
            helplessness_now=62.0,
            consecutive_failures_before=1,
            digital_emotion_state={},
            task_domain_snapshot={},
            help_effect_snapshot={},
            recent_episode_summary={},
            day=1,
        )
    )
    assert result.status == "low_confidence"
    assert result.source == "rule_fallback_low_confidence"
    assert result.final_after == result.rule_after


def test_event_appraisal_falls_back_for_request_error(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_event_appraisal(
            llm=_DummyLLM(should_raise=True),
            task=_make_task(),
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            outcome=_make_outcome("failure_after_attempt"),
            helplessness_now=62.0,
            consecutive_failures_before=1,
            digital_emotion_state={},
            task_domain_snapshot={},
            help_effect_snapshot={},
            recent_episode_summary={},
            day=1,
        )
    )
    assert result.status == "request_error"
    assert result.source == "rule_fallback_request_error"
    assert result.final_after == result.rule_after


def test_event_appraisal_falls_back_for_invalid_schema(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_event_appraisal(
            llm=_DummyLLM(
                [
                    '{"anxiety":"oops"}',
                    '{"broken":true}',
                ]
            ),
            task=_make_task(),
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            outcome=_make_outcome("failure_after_attempt"),
            helplessness_now=62.0,
            consecutive_failures_before=1,
            digital_emotion_state={},
            task_domain_snapshot={},
            help_effect_snapshot={},
            recent_episode_summary={},
            day=1,
        )
    )
    assert result.status == "invalid_schema"
    assert result.source == "rule_fallback_invalid_schema"
    assert result.final_after == result.rule_after


def test_task_appraisal_parses_json(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_task_appraisal(
            llm=_DummyLLM(
                [
                    (
                        '{"perceived_task_difficulty":78,"perceived_task_risk":74,'
                        '"felt_control":29,"expected_help_effectiveness":56,'
                        '"task_value":72,"judge_confidence":0.84,'
                        '"reason":"Repeated failure and fraud concern make this task feel hard and risky."}'
                    )
                ]
            ),
            task=_make_task(),
            stage_key="shock",
            world_context={"risk_level": 3},
            profile_summary={"digital_experience": 0.2},
            helplessness_now=62.0,
            task_self_efficacy=38.0,
            help_success_rate_smoothed=0.55,
            recent_episode_summary={"recent_failure_pressure": 8.0},
            digital_emotion_state={"anxiety": 6.0, "confidence": 4.0},
        )
    )
    assert result.status == "ok"
    assert result.perceived_task_difficulty == 78.0
    assert result.felt_control == 29.0
    assert result.source == "llm"


def test_task_appraisal_prompt_includes_profile_and_task_memory(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    llm = _DummyLLM(
        [
            (
                '{"perceived_task_difficulty":65,"perceived_task_risk":60,'
                '"felt_control":33,"expected_help_effectiveness":58,'
                '"task_value":70,"judge_confidence":0.90,'
                '"reason":"same-task failures make control feel weak"}'
            )
        ]
    )
    asyncio.run(
        resolve_task_appraisal(
            llm=llm,
            task=_make_task(),
            stage_key="steady",
            world_context={"friction_level": 1, "risk_level": 2},
            profile_summary={
                "age": 72,
                "education": "初中",
                "occupation": "退休",
                "persona": "风险回避者",
                "background_summary": "常担心支付风险，遇到复杂流程容易求助。",
                "digital_experience": 0.2,
                "vision_limit": 0.6,
                "past_fraud_experience": 0.4,
            },
            helplessness_now=62.0,
            task_self_efficacy=38.0,
            help_success_rate_smoothed=0.55,
            recent_episode_summary={"recent_failure_pressure": 8.0},
            digital_emotion_state={"anxiety": 6.0, "confidence": 4.0},
            task_relevant_memory={
                "same_task_failure_count": 3,
                "same_task_controllable_success_memory": 0.0,
                "has_controllable_success_evidence": False,
                "recent_same_task_outcomes_tail": [
                    "failure_after_attempt",
                    "failure_even_with_help",
                ],
            },
        )
    )
    assert isinstance(llm.last_dialog, list)
    user_content = str(llm.last_dialog[1]["content"])
    payload = json.loads(user_content.split("\n", 1)[1])
    assert payload["Agent Profile"]["age"] == 72
    assert payload["Agent Profile"]["persona"] == "风险回避者"
    assert payload["Task-Specific Memory"]["same_task_failure_count"] == 3
    assert payload["Task-Specific Memory"]["has_controllable_success_evidence"] is False


def test_task_appraisal_low_confidence_returns_neutral(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_task_appraisal(
            llm=_DummyLLM(
                [
                    (
                        '{"perceived_task_difficulty":80,"perceived_task_risk":70,'
                        '"felt_control":20,"expected_help_effectiveness":40,'
                        '"task_value":60,"judge_confidence":0.20,"reason":"weak"}'
                    )
                ]
            ),
            task=_make_task(),
            stage_key="shock",
            world_context={},
            profile_summary={},
            helplessness_now=62.0,
            task_self_efficacy=38.0,
            help_success_rate_smoothed=0.55,
            recent_episode_summary={},
            digital_emotion_state={},
        )
    )
    assert result.status == "low_confidence"
    assert result.perceived_task_difficulty == 50.0
    assert result.felt_control == 50.0


def test_event_appraisal_prompt_includes_pre_event_and_same_task_context(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    llm = _DummyLLM(
        [
            (
                '{"anxiety":8,"frustration":7,"relief":1,"confidence":2,'
                '"judge_confidence":0.88,"reason":"help failed after low control"}'
            )
        ]
    )
    asyncio.run(
        resolve_event_appraisal(
            llm=llm,
            task=_make_task(),
            strategy=AttemptStrategy(strategy_type="seek_help_then_attempt"),
            outcome=_make_outcome("failure_even_with_help"),
            helplessness_now=70.0,
            consecutive_failures_before=2,
            digital_emotion_state={
                "anxiety": 5.0,
                "frustration": 4.0,
                "relief": 2.0,
                "confidence": 4.0,
                "last_updated_day": 0,
            },
            task_domain_snapshot={},
            help_effect_snapshot={},
            recent_episode_summary={"recent_failure_pressure": 9.0},
            day=1,
            pre_event_task_appraisal={
                "felt_control": 24,
                "perceived_task_risk": 72,
                "expected_help_effectiveness": 68,
                "task_value": 80,
            },
            task_relevant_memory_lite={
                "same_task_failure_count": 3,
                "same_task_controllable_success_memory": 0.0,
                "recent_same_task_outcomes_tail": [
                    "failure_after_attempt",
                    "failure_even_with_help",
                ],
            },
        )
    )
    assert isinstance(llm.last_dialog, list)
    user_content = str(llm.last_dialog[1]["content"])
    payload = json.loads(user_content.split("\n", 1)[1])
    assert payload["pre_event_appraisal"]["felt_control"] == 24
    assert payload["same_task_recent_context"]["same_task_failure_count"] == 3


def test_daily_reflection_generates_once_per_day(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    event_log = [
        {
            "day": 1,
            "scenario": "login_verification",
            "message": "login_verification:failure_after_attempt",
            "decision": {
                "task_family": "login_verification",
                "primary_reason": "failure_after_attempt",
            },
        }
    ]
    updates, reflection = asyncio.run(
        maybe_generate_daily_reflection(
            llm=_DummyLLM(
                [
                    (
                        '{"dominant_task_family":"login_verification",'
                        '"help_effective":false,"mastery_signal":"struggle",'
                        '"text":"昨天验证码又卡住了，我还是有点怕","judge_confidence":0.84}'
                    )
                ]
            ),
            current_day=2,
            last_reflection_day=0,
            event_log=event_log,
            digital_emotion_state={},
            task_domain_memory={},
            help_effect_memory={},
            reflection_history=[],
        )
    )
    assert reflection is not None
    assert updates["proto_last_reflection_day"] == 1
    assert len(updates["proto_daily_reflection_history"]) == 1
    second_updates, second_reflection = asyncio.run(
        maybe_generate_daily_reflection(
            llm=_DummyLLM(),
            current_day=2,
            last_reflection_day=1,
            event_log=event_log,
            digital_emotion_state={},
            task_domain_memory={},
            help_effect_memory={},
            reflection_history=updates["proto_daily_reflection_history"],
        )
    )
    assert second_updates == {}
    assert second_reflection is None


def test_daily_reflection_skips_when_previous_day_has_no_events(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    updates, reflection = asyncio.run(
        maybe_generate_daily_reflection(
            llm=_DummyLLM(),
            current_day=3,
            last_reflection_day=0,
            event_log=[],
            digital_emotion_state={},
            task_domain_memory={},
            help_effect_memory={},
            reflection_history=[],
        )
    )
    assert updates == {"proto_last_reflection_day": 2}
    assert reflection is None


def test_strategy_deliberation_parses_json_and_blends_weights(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_strategy_deliberation(
            llm=_DummyLLM(
                [
                    (
                        '{"attempt_self_score":0.18,"seek_help_score":0.57,'
                        '"avoid_score":0.25,"dominant_strategy":"seek_help_then_attempt",'
                        '"judge_confidence":0.80,'
                        '"reason":"Low control and decent support history make help-seeking the most acceptable option."}'
                    )
                ]
            ),
            task=_make_task(),
            task_appraisal=TaskAppraisalResult(
                mode="hybrid",
                status="ok",
                source="llm",
                confidence=0.8,
                reason="",
                cache_hit=False,
                perceived_task_difficulty=78.0,
                perceived_task_risk=74.0,
                felt_control=29.0,
                expected_help_effectiveness=56.0,
                task_value=72.0,
            ).to_dict(),
            effective_helplessness=74.0,
            task_self_efficacy=42.0,
            help_success_rate_smoothed=0.68,
            recent_negative_feedback_ratio=0.25,
            recent_same_task_failure_count=1,
            digital_emotion_state={"anxiety": 4.0, "confidence": 6.0},
            daily_reflection=DailyReflection(
                day=1,
                dominant_task_family="payment_checkout",
                help_effective=True,
                mastery_signal="mixed",
                text="昨天有顺也有卡，我还在慢慢摸索",
            ).to_dict(),
            rule_weights={
                "attempt_self": 0.30,
                "seek_help_then_attempt": 0.45,
                "avoid": 0.25,
            },
        )
    )
    assert result.status == "ok"
    assert result.dominant_strategy == "seek_help_then_attempt"
    assert result.llm_weights is not None
    assert abs(sum(result.final_weights.values()) - 1.0) < 1e-9
    assert result.final_weights != result.rule_weights
    assert result.final_weights == pytest.approx(
        {
            "attempt_self": 0.3 * 0.30 + 0.7 * 0.18,
            "seek_help_then_attempt": 0.3 * 0.45 + 0.7 * 0.57,
            "avoid": 0.3 * 0.25 + 0.7 * 0.25,
        }
    )


def test_strategy_deliberation_includes_profile_and_memory_context(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    profile_summary = {
        "age": 72,
        "persona": "cautious older adult",
        "digital_experience": 0.25,
        "past_fraud_experience": 0.8,
    }
    task_relevant_memory = {
        "same_task_failure_count": 3,
        "same_task_failure_streak": 2,
        "same_task_controllable_success_memory": 0.1,
        "help_success_rate_same_task": 0.75,
        "recent_same_task_outcomes_tail": ["failure_after_attempt", "success_with_help"],
        "same_task_attribution_summary": "stable attribution " * 40,
        "recent_same_task_events_tail": [{"raw": "do not pass raw event dicts"}],
    }
    recent_episode_summary = {
        "recent_negative_feedback_ratio": 0.6,
        "recent_avoid_ratio": 0.25,
        "recent_help_seek_ratio": 0.4,
        "recent_same_task_failure_count": 3,
        "recent_failure_pressure": 12.0,
    }
    retrieved_text = (
        "Past login attempts failed until a family member helped. "
        + "x" * 1000
    )
    retrieved_episodic_memory = {
        "condition": "retrieved",
        "status": "ok",
        "count": 2,
        "hash": "abc123",
        "text": retrieved_text,
    }
    llm = _DummyLLM(
        [
            (
                '{"attempt_self_score":0.18,"seek_help_score":0.57,'
                '"avoid_score":0.25,"dominant_strategy":"seek_help_then_attempt",'
                '"judge_confidence":0.80,"reason":"context-rich help preference"}'
            )
        ]
    )
    result = asyncio.run(
        resolve_strategy_deliberation(
            llm=llm,
            task=_make_task(),
            task_appraisal=TaskAppraisalResult(
                mode="hybrid",
                status="ok",
                source="llm",
                confidence=0.8,
                reason="",
                cache_hit=False,
                perceived_task_difficulty=78.0,
                perceived_task_risk=74.0,
                felt_control=29.0,
                expected_help_effectiveness=56.0,
                task_value=72.0,
            ).to_dict(),
            effective_helplessness=74.0,
            task_self_efficacy=42.0,
            help_success_rate_smoothed=0.68,
            recent_negative_feedback_ratio=0.25,
            recent_same_task_failure_count=1,
            digital_emotion_state={"anxiety": 4.0, "confidence": 6.0},
            daily_reflection=DailyReflection(
                day=1,
                dominant_task_family="payment_checkout",
                help_effective=True,
                mastery_signal="mixed",
                text="昨天有顺也有卡，我还在慢慢摸索",
            ).to_dict(),
            rule_weights={
                "attempt_self": 0.30,
                "seek_help_then_attempt": 0.45,
                "avoid": 0.25,
            },
            profile_summary=profile_summary,
            task_relevant_memory=task_relevant_memory,
            recent_episode_summary=recent_episode_summary,
            retrieved_episodic_memory=retrieved_episodic_memory,
        )
    )
    payload = _extract_last_user_payload(llm)
    assert payload["prompt_version"] == _STRATEGY_DELIBERATION_PROMPT_VERSION
    assert payload["agent_profile"] == profile_summary
    assert payload["task_relevant_memory"]["same_task_failure_count"] == 3
    assert "recent_same_task_events_tail" not in payload["task_relevant_memory"]
    assert len(payload["task_relevant_memory"]["same_task_attribution_summary"]) == 300
    assert payload["recent_episode_summary"]["recent_negative_feedback_ratio"] == 0.6
    assert "family member helped" in payload["retrieved_episodic_memory"]["text"]
    assert len(payload["retrieved_episodic_memory"]["text"]) == 900
    assert payload["allowed_strategies"] == [
        "attempt_self",
        "seek_help_then_attempt",
        "avoid",
    ]
    assert "rule weights as baseline" in " ".join(payload["decision_dimensions"])
    assert "authoritative current appraisal" in llm.last_dialog[0]["content"]
    assert result.llm_weights is not None
    assert set(result.llm_weights) == {
        "attempt_self",
        "seek_help_then_attempt",
        "avoid",
    }
    assert abs(sum(result.llm_weights.values()) - 1.0) < 1e-9


def test_strategy_deliberation_cache_key_includes_profile_and_memory_context() -> None:
    appraisal = TaskAppraisalResult(
        mode="hybrid",
        status="ok",
        source="llm",
        confidence=0.8,
        reason="",
        cache_hit=False,
        perceived_task_difficulty=78.0,
        perceived_task_risk=74.0,
        felt_control=29.0,
        expected_help_effectiveness=56.0,
        task_value=72.0,
    ).to_dict()
    base_kwargs = {
        "task": _make_task(),
        "task_appraisal": appraisal,
        "effective_helplessness": 74.0,
        "task_self_efficacy": 42.0,
        "help_success_rate_smoothed": 0.68,
        "recent_negative_feedback_ratio": 0.25,
        "recent_same_task_failure_count": 1,
        "digital_emotion_state": DigitalEmotionState(anxiety=4.0, confidence=6.0),
        "mastery_signal": "mixed",
        "profile_summary": {
            "age": 72,
            "education": "高中",
            "persona": "cautious older adult",
            "background_summary": "retired user",
            "digital_experience": 0.25,
            "past_fraud_experience": 0.8,
        },
        "task_relevant_memory": {
            "same_task_failure_count": 3,
            "same_task_failure_streak": 2,
            "same_task_controllable_success_memory": 0.1,
            "recent_same_task_outcomes_tail": ["failure_after_attempt"],
        },
        "recent_episode_summary": {
            "recent_avoid_ratio": 0.25,
            "recent_help_seek_ratio": 0.4,
            "recent_failure_pressure": 12.0,
        },
        "retrieved_episodic_memory": {
            "condition": "retrieved",
            "status": "ok",
            "count": 2,
            "hash": "abc123",
        },
    }
    first = _build_strategy_deliberation_cache_key(**base_kwargs)
    changed = dict(base_kwargs)
    changed["profile_summary"] = {
        **base_kwargs["profile_summary"],
        "digital_experience": 0.9,
    }
    second = _build_strategy_deliberation_cache_key(**changed)
    changed_recent = dict(base_kwargs)
    changed_recent["recent_episode_summary"] = {
        **base_kwargs["recent_episode_summary"],
        "recent_avoid_ratio": 0.8,
    }
    third = _build_strategy_deliberation_cache_key(**changed_recent)
    assert first[0] == _STRATEGY_DELIBERATION_PROMPT_VERSION
    assert first != second
    assert first != third


def test_strategy_deliberation_low_confidence_keeps_rule_weights(monkeypatch) -> None:
    clear_llm_psychology_caches()
    _set_hybrid_env(monkeypatch)
    result = asyncio.run(
        resolve_strategy_deliberation(
            llm=_DummyLLM(
                [
                    (
                        '{"attempt_self_score":0.20,"seek_help_score":0.50,'
                        '"avoid_score":0.30,"dominant_strategy":"seek_help_then_attempt",'
                        '"judge_confidence":0.30,"reason":"weak"}'
                    )
                ]
            ),
            task=_make_task(),
            task_appraisal={},
            effective_helplessness=74.0,
            task_self_efficacy=42.0,
            help_success_rate_smoothed=0.68,
            recent_negative_feedback_ratio=0.25,
            recent_same_task_failure_count=1,
            digital_emotion_state={},
            daily_reflection={},
            rule_weights={
                "attempt_self": 0.30,
                "seek_help_then_attempt": 0.45,
                "avoid": 0.25,
            },
        )
    )
    assert result.status == "low_confidence"
    assert result.final_weights == result.rule_weights
