from __future__ import annotations

import asyncio
import json

import pytest

from proto.app_entry.evaluator import failed_rollout_entry_decision
from proto.app_entry.planner import CALIBRATED_PLAN_VERSION
from proto.app_entry.rollout import (
    build_rollout_input_packet,
    run_app_entry_rollout_hour,
)


class FakeLLM:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls = 0

    async def atext_request(self, **kwargs):
        self.calls += 1
        if not self.responses:
            raise RuntimeError("no fake response configured")
        return self.responses.pop(0)


def _needs_payload() -> dict[str, object]:
    return {
        "need_pressures": {
            "social_need": 0.3,
            "entertainment_need": 0.2,
            "finance_need": 0.8,
            "tool_need": 0.1,
            "health_need": 0.1,
            "habitual_check_need": 0.5,
            "idle_browse_need": 0.2,
            "avoidance_need": 0.3,
            "no_app_need": 0.1,
        },
        "active_intent": 0.8,
        "intensity_hint": 0.5,
        "confidence": 0.9,
        "reasoning": "Finance and habitual-use pressures are strongest.",
    }


def _plan_payload() -> dict[str, object]:
    return {
        "active": True,
        "app_context_counts": {
            "finance_context": 2,
            "communication_social_context": 1,
        },
        "attitude": 0.7,
        "subjective_norm": 0.5,
        "perceived_control": 0.4,
        "confidence": 0.8,
        "reasoning": "Habit supports use while control remains moderate.",
    }


def _habit() -> dict[str, object]:
    return {
        "replay_days": [1, 2, 3],
        "active_exposure_samples": [2, 3, 4],
        "active_by_hour": {"9": {"seen": 3, "active": 3}},
        "intensity_by_hour": {"9": {"count": 3, "sum": 9, "mean": 3.0}},
        "context_by_hour": {
            "9": {
                "finance_context": 6,
                "communication_social_context": 3,
            }
        },
        "primary_context_by_hour": {"9": {"finance_context": 3}},
        "context_total_counts": {
            "finance_context": 10,
            "communication_social_context": 5,
        },
    }


def test_rollout_input_packet_is_bounded_and_excludes_raw_world_label() -> None:
    packet = build_rollout_input_packet(
        simulation_day=3,
        talkingdata_day=4,
        hour=9,
        stable_profile={"age": 70, "gender": "female", "unused": "x"},
        habit_memory=_habit(),
        recent_rollout_rows=[{"hour": index} for index in range(10)],
        recent_task_episodes=[{"task_family": "payment", "extra": "x"}] * 8,
        latest_reflection={"text": "steady", "extra": "x"},
        helplessness=42.0,
        trust=65.0,
        avoidance=35.0,
        environment={"world_name": "forbidden", "friction_level": 1},
        intensity_profile={"active_exposure_cap": 4},
    )

    assert "world_name" not in packet["environment_cues"]
    assert len(packet["recent_simulated_bundles"]) == 6
    assert len(packet["recent_task_episodes"]) == 5
    assert "unused" not in packet["stable_profile"]


@pytest.mark.parametrize("calibrated", [False, True])
def test_rollout_hour_runs_needs_plan_bundle_and_shared_gate(calibrated: bool) -> None:
    plan = _plan_payload()
    habit = _habit()
    if calibrated:
        plan["app_context_weights"] = plan.pop("app_context_counts")
        # Three observations including a zero: (70 + 0 + 56) / 3 = 42.
        habit["active_by_hour"]["9"] = {"seen": 3, "active": 2}
        habit["intensity_by_hour"]["9"] = {"count": 3, "sum": 126, "mean": 42}
    llm = FakeLLM(
        [json.dumps(_needs_payload()), json.dumps(plan)]
    )

    result = asyncio.run(
        run_app_entry_rollout_hour(
            llm=llm,
            agent_id=7,
            simulation_day=3,
            tick_seconds=9 * 3600,
            environment={"friction_level": 1, "assist_level": 1},
            stable_profile={"age": 70, "gender": "female"},
            device_id="device-a",
            selected_rank=1,
            habit_memory=habit,
            day4_snapshot={"schema_version": "snapshot-v1"},
            recent_rollout_rows=[],
            recent_task_episodes=[],
            latest_reflection={},
            helplessness=42.0,
            trust=65.0,
            avoidance=35.0,
            needs_prompt_version="digital_needs_v1",
            plan_prompt_version=CALIBRATED_PLAN_VERSION if calibrated else "app_entry_plan_v3",
            json_attempts=1,
            min_confidence=0.5,
            top_k=5,
            absolute_exposure_cap=8,
            timeout=30,
            retries=0,
            task_occurrence_gate_enabled=False,
        )
    )

    assert llm.calls == 2
    assert result.bundle.day == 4
    expected_counts = {"finance_context": 28, "communication_social_context": 14} if calibrated else plan["app_context_counts"]
    assert result.bundle.app_context_counts == expected_counts
    assert result.bundle.active_event_app_exposures == sum(expected_counts.values())
    assert result.bundle.primary_context == "finance_context"
    assert result.decision.task is not None
    assert result.decision.audit["entry_phase"] == "llm_rollout"
    assert result.decision.audit["uses_validation_data"] is False
    assert result.decision.audit["forced_replay"] is False
    assert len(result.decision.audit["needs_prompt_hash"]) == 16
    assert len(result.decision.audit["plan_prompt_hash"]) == 16
    assert result.decision.audit["needs_json_attempts_used"] == 1
    assert result.decision.audit["needs_actual_requests"] == 1
    assert result.decision.audit["needs_repair_requests"] == 0
    assert result.decision.audit["plan_json_attempts_used"] == 1
    assert result.decision.audit["plan_actual_requests"] == 1
    assert result.decision.audit["plan_repair_requests"] == 0


def test_rollout_requires_snapshot_before_calling_llm() -> None:
    llm = FakeLLM([])

    with pytest.raises(ValueError, match="snapshot is required"):
        asyncio.run(
            run_app_entry_rollout_hour(
                llm=llm,
                agent_id=7,
                simulation_day=3,
                tick_seconds=9 * 3600,
                environment={},
                stable_profile={},
                device_id="device-a",
                selected_rank=1,
                habit_memory=_habit(),
                day4_snapshot={},
                recent_rollout_rows=[],
                recent_task_episodes=[],
                latest_reflection={},
                helplessness=42.0,
                trust=65.0,
                avoidance=35.0,
                needs_prompt_version="digital_needs_v1",
                plan_prompt_version="app_entry_plan_v3",
                json_attempts=1,
                min_confidence=0.5,
                top_k=5,
                absolute_exposure_cap=8,
                timeout=30,
                retries=0,
            )
        )

    assert llm.calls == 0


def test_rollout_plan_failure_reports_agent_and_hour_context() -> None:
    invalid_plan = _plan_payload()
    invalid_plan["primary_context"] = "finance_context"
    llm = FakeLLM(
        [
            json.dumps(_needs_payload()),
            json.dumps(invalid_plan),
            json.dumps(invalid_plan),
        ]
    )

    with pytest.raises(ValueError) as captured:
        asyncio.run(
            run_app_entry_rollout_hour(
                llm=llm,
                agent_id=7,
                simulation_day=3,
                tick_seconds=9 * 3600,
                environment={"friction_level": 1},
                stable_profile={"age": 70},
                device_id="device-a",
                selected_rank=1,
                habit_memory=_habit(),
                day4_snapshot={"schema_version": "snapshot-v1"},
                recent_rollout_rows=[],
                recent_task_episodes=[],
                latest_reflection={},
                helplessness=42.0,
                trust=65.0,
                avoidance=35.0,
                needs_prompt_version="digital_needs_v1",
                plan_prompt_version="app_entry_plan_v3",
                json_attempts=1,
                min_confidence=0.5,
                top_k=5,
                absolute_exposure_cap=8,
                timeout=30,
                retries=0,
            )
        )

    message = str(captured.value)
    assert "agent_id=7" in message
    assert "device_id=device-a" in message
    assert "talkingdata_day=4" in message
    assert "hour=9" in message
    assert "last_validation_error=" in message


def test_rollout_error_decision_is_explicit_missing_data_not_no_app() -> None:
    decision = failed_rollout_entry_decision(
        agent_id=7,
        device_id="device-a",
        simulation_day=3,
        talkingdata_day=4,
        tick_seconds=9 * 3600,
        entry_mode="app_context_replay_then_llm_rollout",
        error=ValueError("invalid plan output"),
    )

    assert decision.entry_evaluated is True
    assert decision.entry_status == "llm_rollout_error"
    assert decision.selected_mobile_intention == ""
    assert decision.task_generated is False
    assert decision.task is None
    assert decision.audit["bundle_generated"] is False
    assert decision.audit["does_not_update_psychology"] is True
    assert decision.audit["uses_validation_data"] is False
    assert len(decision.audit["error_hash"]) == 16
