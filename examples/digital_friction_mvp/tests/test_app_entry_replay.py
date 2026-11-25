from __future__ import annotations

from proto.app_entry.bundle import HourlyAppEntryBundle, NO_APP_CONTEXT
from proto.app_entry.replay import evaluate_replay_bundle_for_agent


def _decision_for_bundle(
    bundle: HourlyAppEntryBundle,
    *,
    existing_task_pending: bool = False,
):
    return evaluate_replay_bundle_for_agent(
        agent_id=3,
        day=int(bundle.day) - 1,
        tick_seconds=float(bundle.hour * 3600),
        env={
            "friction_level": 1,
            "malicious_friction_level": 1,
            "complexity_level": 1,
            "risk_level": 1,
            "assist_level": 1,
            "accessibility_level": 1,
            "human_support_level": 1,
        },
        stable_profile={"age": 70, "gender": "unknown"},
        bundle=bundle,
        selected_rank=1,
        bundle_hash="bundlehash",
        device_mapping_hash="devicehash",
        task_occurrence_gate_enabled=False,
        existing_task_pending=existing_task_pending,
    )


def test_replay_inactive_hour_is_context_only_noop() -> None:
    bundle = HourlyAppEntryBundle(
        device_id="device-a",
        day=1,
        hour=0,
        active=False,
        active_event_app_exposures=0,
        app_context_counts={},
        primary_context=NO_APP_CONTEXT,
        source="talkingdata_inactive_hour",
    )

    decision = _decision_for_bundle(bundle)

    assert decision.task is None
    assert decision.entry_status == "no_app_context_noop"
    assert decision.audit["forced_replay"] is True
    assert decision.audit["uses_validation_data"] is False
    assert decision.audit["uses_helplessness_state"] is False
    assert decision.audit["app_entry_does_not_update_psychology"] is True


def test_replay_non_task_context_stays_context_only() -> None:
    bundle = HourlyAppEntryBundle(
        device_id="device-a",
        day=1,
        hour=10,
        active=True,
        active_event_app_exposures=2,
        app_context_counts={"communication_social_context": 2},
        primary_context="communication_social_context",
        source="talkingdata_active_hour",
    )

    decision = _decision_for_bundle(bundle)

    assert decision.task is None
    assert decision.entry_status == "communication_social_context_context_only"
    assert decision.audit["task_eligible_context_exposure"] is False
    assert decision.audit["task_outcome_may_update_psychology"] is False


def test_replay_task_eligible_primary_enters_existing_gate_and_task_factory() -> None:
    bundle = HourlyAppEntryBundle(
        device_id="device-a",
        day=1,
        hour=11,
        active=True,
        active_event_app_exposures=3,
        app_context_counts={"finance_context": 3},
        primary_context="finance_context",
        source="talkingdata_active_hour",
    )

    decision = _decision_for_bundle(bundle)

    assert decision.task is not None
    assert decision.task.task_id.startswith("app_context_replay_bundle_")
    assert decision.entry_status == "entered_mapped_digital_task"
    assert decision.audit["task_occurrence_gate_passed"] is True
    assert decision.audit["task_outcome_may_update_psychology"] is True


def test_replay_pending_task_keeps_audit_but_blocks_new_task() -> None:
    bundle = HourlyAppEntryBundle(
        device_id="device-a",
        day=1,
        hour=12,
        active=True,
        active_event_app_exposures=1,
        app_context_counts={"finance_context": 1},
        primary_context="finance_context",
        source="talkingdata_active_hour",
    )

    decision = _decision_for_bundle(bundle, existing_task_pending=True)

    assert decision.task is None
    assert decision.entry_status == "task_eligible_context_existing_task_pending"
    assert decision.audit["context_only_reason"] == "existing_task_pending"
    assert decision.audit["forced_replay"] is True
    assert decision.audit["device_id"] == "device-a"
