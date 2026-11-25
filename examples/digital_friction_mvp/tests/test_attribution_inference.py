from __future__ import annotations

import asyncio

from proto.attribution_inference import (
    clear_event_attribution_cache,
    infer_event_attribution,
)
from proto.models import AttemptOutcome, DigitalTask


class FakeLLM:
    def __init__(self, responses: list[object]):
        self._responses = list(responses)
        self.calls = 0

    async def atext_request(self, **kwargs):
        self.calls += 1
        if not self._responses:
            raise RuntimeError("no fake response configured")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _make_task() -> DigitalTask:
    return DigitalTask(
        task_id="task-1",
        task_family="payment_risk_confirmation",
        friction_type="payment_risk_popup",
        difficulty=0.82,
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=1,
    )


def _make_failure_outcome() -> AttemptOutcome:
    return AttemptOutcome(
        outcome_type="failure_even_with_help",
        success=False,
        help_used=True,
        negative_feedback=True,
        support_quality=2,
        event_level_uncontrollability=2,
        friction_tier=2,
        success_probability=0.33,
        abandon_probability=0.08,
        note="roll=0.9",
        support_mode="substituting_support",
    )


def _make_enabling_failure_outcome() -> AttemptOutcome:
    outcome = _make_failure_outcome()
    outcome.support_mode = "enabling_support"
    return outcome


def test_valid_json_populates_event_attribution(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    clear_event_attribution_cache()
    llm = FakeLLM(
        [
            '{"event_attribution_locus":"mixed","event_attribution_stability":"stable","event_attribution_scope_amplitude":0.85,"event_attribution_explanation":"Failure even with help suggests the difficulty may persist across similar tasks.","judge_confidence":0.82}'
        ]
    )
    result = asyncio.run(
        infer_event_attribution(
            llm=llm,
            task=_make_task(),
            outcome=_make_failure_outcome(),
            task_self_efficacy=31,
            felt_control=24,
            recent_same_task_failure_count=3,
        )
    )
    assert result.status == "ok"
    assert result.source == "llm_classified"
    assert result.event_attribution_stability == "stable"
    assert result.event_attribution_scope == "family_generalizing"
    assert result.event_attribution_scope_amplitude == 0.85
    assert result.judge_confidence > 0.8


def test_enabling_support_softens_stable_and_generalizing_attribution(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    clear_event_attribution_cache()
    llm = FakeLLM(
        [
            '{"event_attribution_locus":"mixed","event_attribution_stability":"stable","event_attribution_scope_amplitude":0.85,"event_attribution_explanation":"Failure even with help suggests the difficulty may persist across similar tasks.","judge_confidence":0.82}'
        ]
    )
    result = asyncio.run(
        infer_event_attribution(
            llm=llm,
            task=_make_task(),
            outcome=_make_enabling_failure_outcome(),
            task_self_efficacy=31,
            felt_control=24,
            recent_same_task_failure_count=3,
        )
    )
    assert result.status == "ok"
    assert result.source == "llm_classified_support_guarded"
    assert result.event_attribution_stability == "mixed"
    assert result.event_attribution_scope == "mixed"
    assert result.event_attribution_scope_amplitude == 0.5
    assert result.judge_confidence == 0.82


def test_low_confidence_falls_back_to_conservative_labels(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    clear_event_attribution_cache()
    llm = FakeLLM(
        [
            '{"event_attribution_locus":"self","event_attribution_stability":"stable","event_attribution_scope_amplitude":0.85,"event_attribution_explanation":"Too uncertain.","judge_confidence":0.22}'
        ]
    )
    result = asyncio.run(
        infer_event_attribution(
            llm=llm,
            task=_make_task(),
            outcome=_make_failure_outcome(),
            task_self_efficacy=31,
            felt_control=24,
            recent_same_task_failure_count=3,
        )
    )
    assert result.status == "low_confidence"
    assert result.source == "conservative_fallback_low_confidence"
    assert result.event_attribution_locus == "not_applicable"
    assert result.event_attribution_stability == "not_applicable"
    assert result.event_attribution_scope == "not_applicable"
    assert result.event_attribution_scope_amplitude == 0.0


def test_success_outcome_is_not_applicable(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    clear_event_attribution_cache()
    llm = FakeLLM(
        [
            '{"event_attribution_locus":"mixed","event_attribution_stability":"mixed","event_attribution_scope_amplitude":0.1,"event_attribution_explanation":"unused","judge_confidence":0.8}'
        ]
    )
    outcome = AttemptOutcome(
        outcome_type="success_self",
        success=True,
        help_used=False,
        negative_feedback=False,
        support_quality=1,
        event_level_uncontrollability=0,
        friction_tier=1,
        success_probability=0.72,
        abandon_probability=0.08,
    )
    result = asyncio.run(
        infer_event_attribution(
            llm=llm,
            task=_make_task(),
            outcome=outcome,
            task_self_efficacy=55,
            felt_control=68,
            recent_same_task_failure_count=0,
        )
    )
    assert result.status == "not_applicable"
    assert result.event_attribution_locus == "not_applicable"
    assert llm.calls == 0
