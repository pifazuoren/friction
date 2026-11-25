from __future__ import annotations

import asyncio
import json

from proto.models import AttemptOutcome, AttemptStrategy, DigitalTask
from proto.uncontrollability_calibrator import (
    calibrate_uncontrollability,
    clear_uncontrollability_calibration_cache,
)


class FakeLLM:
    def __init__(self, responses: list[object]):
        self._responses = list(responses)
        self.calls = 0
        self.last_dialog = None

    async def atext_request(self, **kwargs):
        self.calls += 1
        self.last_dialog = kwargs.get("dialog")
        if not self._responses:
            raise RuntimeError("no fake response configured")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_task() -> DigitalTask:
    return DigitalTask(
        task_id="task-1",
        task_family="payment_checkout",
        friction_type="payment_risk_popup",
        difficulty=0.82,
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=1,
    )


def _make_strategy() -> AttemptStrategy:
    return AttemptStrategy(
        strategy_type="seek_help_then_attempt",
        support_requested=True,
        rationale="test",
        weights={"attempt_self": 0.2, "seek_help_then_attempt": 0.6, "avoid": 0.2},
    )


def _make_failure_outcome(*, rule_value: int = 1) -> AttemptOutcome:
    return AttemptOutcome(
        outcome_type="failure_even_with_help",
        success=False,
        help_used=True,
        negative_feedback=True,
        support_quality=2,
        event_level_uncontrollability=rule_value,
        friction_tier=2,
        success_probability=0.33,
        abandon_probability=0.08,
        note="roll=0.9",
        rule_event_level_uncontrollability=rule_value,
    )


def test_mode_off_keeps_rule_without_llm_call(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "off")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.95, "reason": "unused"}'
        ]
    )
    result = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
        )
    )
    assert result.final_value == 1
    assert result.source == "rule"
    assert llm.calls == 0


def test_valid_json_can_shift_one_level(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MIN_CONFIDENCE", "0.60")
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MAX_SHIFT", "1")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.91, "reason": "Failure even with help under high friction feels highly uncontrollable."}'
        ]
    )
    result = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
        )
    )
    assert result.final_value == 2
    assert result.source == "hybrid_shifted"
    assert result.status == "ok"


def test_invalid_schema_falls_back_to_rule(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"wrong_key": 2}',
            '{"wrong_key": 1}',
        ]
    )
    result = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
        )
    )
    assert result.final_value == 1
    assert result.source == "rule_fallback_invalid_schema"


def test_low_confidence_falls_back_to_rule(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MIN_CONFIDENCE", "0.60")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.31, "reason": "Too uncertain to deviate strongly."}'
        ]
    )
    result = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
        )
    )
    assert result.final_value == 1
    assert result.source == "rule_fallback_low_confidence"


def test_shift_is_clamped_to_one_level(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MAX_SHIFT", "1")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.92, "reason": "Strongly out of control."}'
        ]
    )
    result = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=0),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=88,
            consecutive_failures_before=3,
        )
    )
    assert result.llm_value == 2
    assert result.final_value == 1


def test_success_outcome_does_not_trigger_llm(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.99, "reason": "unused"}'
        ]
    )
    success_outcome = AttemptOutcome(
        outcome_type="success_self",
        success=True,
        help_used=False,
        negative_feedback=False,
        support_quality=1,
        event_level_uncontrollability=0,
        friction_tier=1,
        success_probability=0.7,
        abandon_probability=0.1,
        note="roll=0.2",
        rule_event_level_uncontrollability=0,
    )
    result = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            outcome=success_outcome,
            env={
                "friction_level": 1,
                "malicious_friction_level": 1,
                "complexity_level": 1,
                "risk_level": 1,
                "assist_level": 1,
                "accessibility_level": 1,
                "human_support_level": 1,
            },
            helplessness_now=35,
            consecutive_failures_before=0,
        )
    )
    assert result.final_value == 0
    assert result.source == "rule_success_short_circuit"
    assert llm.calls == 0


def test_cache_hit_skips_second_llm_request(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_CACHE_ENABLED", "true")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.88, "reason": "High friction plus repeated failure increases loss of control."}'
        ]
    )
    first = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
        )
    )
    second = asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 3,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
        )
    )
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert llm.calls == 1


def test_payload_includes_pre_event_appraisal_and_same_task_history(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_UNCONTROLLABILITY_MIN_CONFIDENCE", "0.60")
    clear_uncontrollability_calibration_cache()
    llm = FakeLLM(
        [
            '{"event_level_uncontrollability": 2, "confidence": 0.88, "reason": "Repeated failure plus low control suggests stronger loss of control."}'
        ]
    )
    asyncio.run(
        calibrate_uncontrollability(
            llm=llm,
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_failure_outcome(rule_value=1),
            env={
                "friction_level": 3,
                "malicious_friction_level": 2,
                "complexity_level": 3,
                "risk_level": 3,
                "assist_level": 2,
                "accessibility_level": 2,
                "human_support_level": 2,
            },
            helplessness_now=76,
            consecutive_failures_before=2,
            pre_event_task_appraisal={
                "felt_control": 21,
                "perceived_task_risk": 78,
                "expected_help_effectiveness": 64,
                "task_value": 82,
            },
            task_relevant_memory={
                "same_task_attempt_count": 4,
                "same_task_failure_count": 3,
                "same_task_failure_streak": 2,
                "same_task_last_outcome": "failure_after_attempt",
                "same_task_controllable_success_memory": 0.0,
                "help_success_rate_same_task": 0.25,
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
    assert payload["context"]["pre_event_appraisal"]["felt_control"] == 21
    assert payload["context"]["same_task_history"]["same_task_failure_count"] == 3
    assert (
        payload["context"]["same_task_history"]["has_controllable_success_evidence"]
        is False
    )
