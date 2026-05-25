from __future__ import annotations

import json
import asyncio

from proto.llm_psychology import resolve_trajectory_appraisal
from proto.models import AttemptStrategy, DigitalTask, MemoryFeatures, TaskAppraisalResult


class _SequenceLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def atext_request(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("LLM called more often than expected")
        return self._responses.pop(0)


def _valid_trajectory_payload() -> str:
    return json.dumps(
        {
            "planned_steps": [
                {"step_id": 1, "action": "open the service page"},
                {"step_id": 2, "action": "read the required fields"},
            ],
            "selected_friction_points": [],
            "friction_encounter_likelihood": 0.35,
            "cognitive_load": 0.40,
            "help_need": 0.25,
            "trajectory_outcome_tendency": {
                "success_self": 0.45,
                "failure_after_attempt": 0.30,
                "abandon_midway": 0.25,
            },
            "trajectory_confidence": 0.80,
            "reason": "Moderate friction is expected before any final outcome is sampled.",
            "does_not_sample_final_outcome": True,
            "does_not_update_psychology": True,
        }
    )


def test_trajectory_appraisal_retries_after_invalid_schema(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_OUTCOME_TRAJECTORY_JSON_ATTEMPTS", "3")
    monkeypatch.setenv("PROTO_OUTCOME_TRAJECTORY_MIN_CONFIDENCE", "0.65")

    llm = _SequenceLLM(
        [
            '{"planned_steps": []}',
            '{"planned_steps": []}',
            _valid_trajectory_payload(),
        ]
    )

    result = asyncio.run(
        resolve_trajectory_appraisal(
            llm=llm,
            task=DigitalTask(
                task_id="task-1",
                task_family="service_application_submission",
                friction_type="form_complexity",
                difficulty=0.5,
                need_type="daily_task",
                support_sensitivity=0.5,
                assigned_tick=0,
            ),
            strategy=AttemptStrategy(strategy_type="attempt_self"),
            task_appraisal=TaskAppraisalResult(
                mode="rule",
                status="ok",
                source="rule",
                confidence=1.0,
                reason="",
                cache_hit=False,
            ).to_dict(),
            memory_features=MemoryFeatures(
                effective_helplessness=30.0,
                task_self_efficacy=60.0,
                controllable_success_memory=50.0,
                task_specific_pressure=0.0,
                help_success_rate_smoothed=0.5,
                help_confidence_bonus=0.0,
                recent_negative_feedback_ratio=0.0,
                recent_avoid_ratio=0.0,
                recent_help_seek_ratio=0.0,
                recent_same_task_failure_count=0,
                recent_failure_pressure=0.0,
            ).to_dict(),
            env={},
            profile_summary={},
            run_context={"agent_id": 1},
        )
    )

    assert result["status"] == "ok"
    assert result["invalid_reason"] == ""
    assert result["trajectory_json_attempts_configured"] == 3
    assert result["trajectory_json_attempts_used"] == 2
    assert len(llm.calls) == 3
