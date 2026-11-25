from __future__ import annotations

from typing import Any

from .bundle import HourlyAppEntryBundle, NO_APP_CONTEXT
from .bundle_loader import simulation_day_to_talkingdata_day
from .evaluator import evaluate_selected_app_context_bundle_for_agent
from .types import MobileEntryDecision


REPLAY_AUDIT_SCHEMA_VERSION = "app_entry_replay_audit_v1"


def evaluate_replay_bundle_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    stable_profile: dict[str, Any] | None,
    bundle: HourlyAppEntryBundle,
    selected_rank: int,
    bundle_hash: str,
    device_mapping_hash: str,
    task_opportunity_mapping_path: str = "",
    task_occurrence_gate_enabled: bool = False,
    task_occurrence_prior_path: str = "",
    task_occurrence_gate_multiplier: float = 1.0,
    existing_task_pending: bool = False,
) -> MobileEntryDecision:
    priors = bundle.context_share_distribution()
    if bundle.primary_context == NO_APP_CONTEXT:
        priors = {}
    replay_audit = {
        "replay_audit_schema_version": REPLAY_AUDIT_SCHEMA_VERSION,
        "entry_mode": "app_context_replay_bundle",
        "entry_layer": "hourly_app_entry_bundle",
        "source": "talkingdata_replay",
        "forced_replay": True,
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "uses_helplessness_state": False,
        "uses_helplessness_state_scope": "app_entry_replay_decision_only",
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "app_entry_does_not_update_psychology": True,
        "task_outcome_may_update_psychology": False,
        "agent_id": int(agent_id),
        "device_id": bundle.device_id,
        "selected_rank": int(selected_rank),
        "simulation_day": int(day),
        "talkingdata_day": int(bundle.day),
        "expected_talkingdata_day": simulation_day_to_talkingdata_day(int(day)),
        "hour": int(bundle.hour),
        "active": bool(bundle.active),
        "active_event_app_exposures": int(bundle.active_event_app_exposures),
        "app_context_counts": dict(bundle.app_context_counts),
        "primary_context": bundle.primary_context,
        "selected_app_context": bundle.primary_context,
        "bundle_hash": str(bundle_hash),
        "device_mapping_hash": str(device_mapping_hash),
        "candidate_app_contexts": dict(priors),
        "context_mapping_basis": "talkingdata_hourly_bundle_replay",
        "latent_process_note": (
            "TalkingData provides observed app-entry exposure only; "
            "task occurrence, strategy, outcome, support, and helplessness "
            "updates are simulated latent processes."
        ),
    }
    if int(bundle.day) != simulation_day_to_talkingdata_day(int(day)):
        raise ValueError(
            "simulation day and TalkingData replay day are misaligned: "
            f"simulation_day={day}, talkingdata_day={bundle.day}"
        )

    decision = evaluate_selected_app_context_bundle_for_agent(
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        env=env,
        stable_profile=stable_profile,
        bundle=bundle,
        entry_mode="app_context_replay_bundle",
        prior_source="talkingdata_hourly_bundle_replay",
        audit_payload=replay_audit,
        calibration_hash=str(bundle_hash),
        task_opportunity_mapping_path=task_opportunity_mapping_path,
        task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
        task_occurrence_prior_path=task_occurrence_prior_path,
        task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
        existing_task_pending=bool(existing_task_pending),
    )
    decision.audit.update(replay_audit)
    decision.audit["task_outcome_may_update_psychology"] = bool(decision.task is not None)
    decision.audit["task_generated"] = bool(decision.task is not None)
    return decision
