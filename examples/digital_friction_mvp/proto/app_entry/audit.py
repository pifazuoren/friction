from __future__ import annotations

from typing import Any

from .types import TASK_ELIGIBLE_APP_CONTEXTS


def _context_review_status(app_context: str) -> str:
    if app_context in TASK_ELIGIBLE_APP_CONTEXTS:
        return "task_context_auto"
    if app_context == "finance_candidate_review":
        return "finance_candidate_needs_review"
    if app_context == "taxonomy_profile_only":
        return "taxonomy_profile_only"
    if app_context == "unknown_or_unmapped":
        return "unknown_needs_review"
    return "context_only_auto"


def _entry_audit(
    *,
    entry_mode: str,
    agent_id: int,
    day: int,
    tick_seconds: float,
    hour: int,
    selected_mobile_intention: str,
    entry_status: str,
    mapped_task_family: str | None,
    mapping_confidence: float,
    task_generated: bool,
    candidate_intentions: dict[str, float],
    calibration_hash: str,
    mapping_hash: str,
    reason: str,
    llm_shadow: dict[str, Any] | None = None,
    rerank_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = {
        "agent_id": int(agent_id),
        "day": int(day),
        "tick_seconds": float(tick_seconds),
        "hour": int(hour),
        "entry_mode": str(entry_mode),
        "entry_eval_interval_minutes": None,
        "entry_evaluated": True,
        "candidate_intentions": dict(candidate_intentions),
        "selected_mobile_intention": str(selected_mobile_intention),
        "mapped_task_family": mapped_task_family,
        "mapping_confidence": float(mapping_confidence),
        "entry_status": str(entry_status),
        "task_generated": bool(task_generated),
        "calibration_split": "elder_reference_may1_may3",
        "calibration_artifact_hash": calibration_hash,
        "mapping_artifact_hash": mapping_hash,
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "uses_previous_task_outcome": False,
        "uses_recent_failure_history": False,
        "uses_recent_avoid_ratio": False,
        "uses_recent_help_history": False,
        "uses_helplessness_state": False,
        "uses_self_efficacy_delta": False,
        "uses_controllability_posterior": False,
        "uses_bayesian_posterior": False,
        "uses_phase4_policy": False,
        "uses_phase5c_policy": False,
        "uses_world_specific_env": False,
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "is_avoidance": False,
        "is_help_action": False,
        "helper_triggered": False,
        "reason": str(reason),
        "llm_shadow": llm_shadow or {},
    }
    if rerank_audit:
        audit.update(dict(rerank_audit))
    return audit
