from __future__ import annotations

from .app_entry.artifacts import (
    _CALIBRATION_CACHE,
    _MAPPING_CACHE,
    _TASK_OCCURRENCE_CACHE,
    _artifact_hash,
    _load_json_artifact,
)
from .app_entry.audit import _context_review_status, _entry_audit
from .app_entry.candidate import (
    _DEFAULT_APP_CONTEXT_PRIOR,
    _DEFAULT_UNCALIBRATED_PRIOR,
    _bucket_for_profile,
    _extract_app_context_prior_from_calibration,
    _extract_prior_from_calibration,
    _normalize_app_context_distribution,
    _normalize_distribution,
    _normalize_task_opportunity_distribution,
    _stable_select_app_context,
    _stable_select_intention,
    app_context_candidate_hash,
    mobile_intention_candidate_hash,
    top_app_context_candidates,
    top_mobile_intention_candidates,
)
from .app_entry.evaluator import (
    _evaluate_app_context_entry_for_agent,
    _mapping_confidence_for_intention,
    _stable_select_task_family_for_context,
    _task_opportunity_for_context,
    evaluate_mobile_entry_for_agent,
    failed_rollout_entry_decision,
    skipped_mobile_entry_decision,
)
from .app_entry.gate import (
    _TASK_OCCURRENCE_SCHEMA_VERSION,
    _stable_task_occurrence_gate_roll,
    _task_occurrence_probability_for_context,
)
from .app_entry.task_templates import (
    TASK_LIBRARY,
    TASK_OPPORTUNITY_BY_CONTEXT,
    _TASK_WINDOW_SECONDS,
    _TASK_WINDOW_TOLERANCE_SECONDS,
    _build_task_from_template,
    _resolve_schedule_seed,
    _scheduled_template_for_window,
    _task_template_for_family,
    _window_index_for_tick,
    decode_task,
    encode_task,
    is_task_window_tick,
    select_task_for_agent,
    task_pressure_from_env,
)
from .app_entry.types import (
    APP_CONTEXT_SET,
    CONTEXT_ONLY_MOBILE_INTENTIONS,
    MOBILE_INTENTION_SET,
    MOBILE_INTENTION_TO_TASK_FAMILY,
    TASK_ELIGIBLE_APP_CONTEXTS,
    MobileEntryDecision,
    _hour_for_tick,
    _normalize_distribution_for_keys,
    _safe_int,
    _stable_hash,
    _stable_select_from_distribution,
    clamp_score,
)

__all__ = [
    "APP_CONTEXT_SET",
    "CONTEXT_ONLY_MOBILE_INTENTIONS",
    "MOBILE_INTENTION_SET",
    "MOBILE_INTENTION_TO_TASK_FAMILY",
    "TASK_ELIGIBLE_APP_CONTEXTS",
    "TASK_LIBRARY",
    "TASK_OPPORTUNITY_BY_CONTEXT",
    "MobileEntryDecision",
    "app_context_candidate_hash",
    "clamp_score",
    "decode_task",
    "encode_task",
    "evaluate_mobile_entry_for_agent",
    "failed_rollout_entry_decision",
    "is_task_window_tick",
    "mobile_intention_candidate_hash",
    "select_task_for_agent",
    "skipped_mobile_entry_decision",
    "task_pressure_from_env",
    "top_app_context_candidates",
    "top_mobile_intention_candidates",
]
