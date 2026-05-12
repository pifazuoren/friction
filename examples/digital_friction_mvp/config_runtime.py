from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime


VALID_EXPERIMENT_MODES = {"single_world", "parallel_worlds"}
DEFAULT_WORLD_BATCH = (
    "baseline_low_friction",
    "high_friction_low_assist",
    "high_friction_high_assist",
    "low_friction_high_assist",
)
VALID_BAYESIAN_POLICY_LITE_MODES = {"off", "shadow", "gated_lite"}
VALID_BAYESIAN_POLICY_LITE_UTILITY_PROFILES = {"shadow_v1", "theory_v2"}
DEFAULT_BAYESIAN_POLICY_LITE_UTILITY_PROFILE = "shadow_v1"


def _parse_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    lowered = value.strip().lower()
    return lowered not in {"0", "false", "no", "off"}


def _normalize_bayesian_policy_lite_utility_profile(value: str | None) -> str:
    profile = str(
        value or DEFAULT_BAYESIAN_POLICY_LITE_UTILITY_PROFILE
    ).strip().lower()
    if profile not in VALID_BAYESIAN_POLICY_LITE_UTILITY_PROFILES:
        raise ValueError(
            "PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE must be one of: "
            + ", ".join(sorted(VALID_BAYESIAN_POLICY_LITE_UTILITY_PROFILES))
        )
    return profile


@dataclass(frozen=True)
class RuntimeConfig:
    experiment_mode: str
    world_batch: tuple[str, ...]
    parallel_group_name: str
    proto_llm_psychology_mode: str
    proto_llm_task_appraisal_enabled: bool
    proto_llm_event_appraisal_enabled: bool
    proto_llm_daily_reflection_enabled: bool
    proto_llm_strategy_deliberation_enabled: bool
    proto_llm_stage_interview_enabled: bool
    proto_llm_final_interview_enabled: bool
    proto_llm_psychology_min_confidence: float
    proto_llm_psychology_timeout: int
    proto_llm_psychology_retries: int
    proto_llm_psychology_cache_enabled: bool
    proto_llm_uncontrollability_mode: str
    proto_llm_uncontrollability_min_confidence: float
    proto_llm_uncontrollability_max_shift: int
    proto_llm_uncontrollability_timeout: int
    proto_llm_uncontrollability_retries: int
    proto_llm_uncontrollability_cache_enabled: bool
    proto_scope_spillover_beta: float
    proto_scope_spillover_threshold: float
    proto_scope_spillover_sigma: float
    proto_stream_episode_recording_enabled: bool
    proto_stream_task_appraisal_retrieval_enabled: bool
    proto_stream_attribution_retrieval_enabled: bool
    proto_bayesian_control_audit_enabled: bool
    proto_bayesian_control_rho: float
    proto_bayesian_control_weight: float
    proto_bayesian_policy_lite_mode: str
    proto_bayesian_policy_lite_tau: float
    proto_bayesian_policy_lite_confidence_k: int
    proto_bayesian_policy_lite_rho: float
    proto_bayesian_policy_lite_weight: float
    proto_bayesian_policy_lite_utility_profile: str
    proto_bayesian_policy_lite_gate_threshold: float
    proto_bayesian_policy_lite_entropy_threshold: float
    proto_bayesian_policy_lite_max_delta: float
    proto_bayesian_policy_lite_prob_floor: float


def load_runtime_config() -> RuntimeConfig:
    experiment_mode = os.getenv("EXPERIMENT_MODE", "single_world").strip().lower()
    if experiment_mode not in VALID_EXPERIMENT_MODES:
        raise ValueError(
            "EXPERIMENT_MODE must be one of: single_world, parallel_worlds"
        )

    raw_world_batch = os.getenv("WORLD_BATCH", ",".join(DEFAULT_WORLD_BATCH)).strip()
    world_batch = tuple(
        token.strip()
        for token in raw_world_batch.split(",")
        if token.strip()
    ) or DEFAULT_WORLD_BATCH

    parallel_group_name = (
        os.getenv("PARALLEL_GROUP_NAME", "").strip()
        or datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    proto_llm_psychology_mode = (
        os.getenv("PROTO_LLM_PSYCHOLOGY_MODE", "off").strip().lower()
    )
    if proto_llm_psychology_mode not in {"off", "hybrid"}:
        raise ValueError(
            "PROTO_LLM_PSYCHOLOGY_MODE must be one of: off, hybrid"
        )
    proto_llm_task_appraisal_enabled = _parse_bool_env(
        "PROTO_LLM_TASK_APPRAISAL_ENABLED",
        False,
    )
    proto_llm_event_appraisal_enabled = _parse_bool_env(
        "PROTO_LLM_EVENT_APPRAISAL_ENABLED",
        True,
    )
    proto_llm_daily_reflection_enabled = _parse_bool_env(
        "PROTO_LLM_DAILY_REFLECTION_ENABLED",
        True,
    )
    proto_llm_strategy_deliberation_enabled = _parse_bool_env(
        "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED",
        False,
    )
    proto_llm_stage_interview_enabled = _parse_bool_env(
        "PROTO_LLM_STAGE_INTERVIEW_ENABLED",
        False,
    )
    proto_llm_final_interview_enabled = _parse_bool_env(
        "PROTO_LLM_FINAL_INTERVIEW_ENABLED",
        False,
    )
    proto_llm_psychology_min_confidence = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_LLM_PSYCHOLOGY_MIN_CONFIDENCE", "0.65")),
        ),
    )
    proto_llm_psychology_timeout = max(
        1,
        int(os.getenv("PROTO_LLM_PSYCHOLOGY_TIMEOUT", "8")),
    )
    proto_llm_psychology_retries = max(
        0,
        int(os.getenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "1")),
    )
    proto_llm_psychology_cache_enabled = _parse_bool_env(
        "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED",
        True,
    )

    raw_uncontrollability_mode = os.getenv("PROTO_LLM_UNCONTROLLABILITY_MODE")
    if raw_uncontrollability_mode is None or not raw_uncontrollability_mode.strip():
        proto_llm_uncontrollability_mode = (
            "hybrid" if proto_llm_psychology_mode == "hybrid" else "off"
        )
    else:
        proto_llm_uncontrollability_mode = raw_uncontrollability_mode.strip().lower()
    if proto_llm_uncontrollability_mode not in {"off", "hybrid"}:
        raise ValueError(
            "PROTO_LLM_UNCONTROLLABILITY_MODE must be one of: off, hybrid"
        )
    proto_llm_uncontrollability_min_confidence = max(
        0.0,
        min(
            1.0,
            float(
                os.getenv("PROTO_LLM_UNCONTROLLABILITY_MIN_CONFIDENCE", "0.60")
            ),
        ),
    )
    proto_llm_uncontrollability_max_shift = max(
        0,
        min(
            2,
            int(os.getenv("PROTO_LLM_UNCONTROLLABILITY_MAX_SHIFT", "1")),
        ),
    )
    proto_llm_uncontrollability_timeout = max(
        1,
        int(os.getenv("PROTO_LLM_UNCONTROLLABILITY_TIMEOUT", "8")),
    )
    proto_llm_uncontrollability_retries = max(
        0,
        int(os.getenv("PROTO_LLM_UNCONTROLLABILITY_RETRIES", "1")),
    )
    proto_llm_uncontrollability_cache_enabled = _parse_bool_env(
        "PROTO_LLM_UNCONTROLLABILITY_CACHE_ENABLED",
        True,
    )
    proto_scope_spillover_beta = max(
        0.0,
        float(os.getenv("PROTO_SCOPE_SPILLOVER_BETA", "1.2")),
    )
    proto_scope_spillover_threshold = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_SCOPE_SPILLOVER_THRESHOLD", "0.15")),
        ),
    )
    proto_scope_spillover_sigma = max(
        0.01,
        float(os.getenv("PROTO_SCOPE_SPILLOVER_SIGMA", "0.45")),
    )
    proto_stream_episode_recording_enabled = _parse_bool_env(
        "PROTO_STREAM_EPISODE_RECORDING_ENABLED",
        True,
    )
    proto_stream_task_appraisal_retrieval_enabled = _parse_bool_env(
        "PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED",
        True,
    )
    proto_stream_attribution_retrieval_enabled = _parse_bool_env(
        "PROTO_STREAM_ATTRIBUTION_RETRIEVAL_ENABLED",
        True,
    )
    proto_bayesian_control_audit_enabled = _parse_bool_env(
        "PROTO_BAYESIAN_CONTROL_AUDIT_ENABLED",
        True,
    )
    proto_bayesian_control_rho = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_BAYESIAN_CONTROL_RHO", "0.98")),
        ),
    )
    proto_bayesian_control_weight = max(
        0.0,
        float(os.getenv("PROTO_BAYESIAN_CONTROL_WEIGHT", "1.0")),
    )
    proto_bayesian_policy_lite_mode = (
        os.getenv("PROTO_BAYESIAN_POLICY_LITE_MODE", "off").strip().lower()
    )
    if proto_bayesian_policy_lite_mode not in VALID_BAYESIAN_POLICY_LITE_MODES:
        raise ValueError(
            "PROTO_BAYESIAN_POLICY_LITE_MODE must be one of: "
            + ", ".join(sorted(VALID_BAYESIAN_POLICY_LITE_MODES))
        )
    proto_bayesian_policy_lite_tau = max(
        0.000001,
        float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_TAU", "1.0")),
    )
    proto_bayesian_policy_lite_confidence_k = max(
        1,
        int(float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K", "4"))),
    )
    proto_bayesian_policy_lite_rho = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_RHO", "1.0")),
        ),
    )
    proto_bayesian_policy_lite_weight = max(
        0.0,
        float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_WEIGHT", "1.0")),
    )
    proto_bayesian_policy_lite_utility_profile = (
        _normalize_bayesian_policy_lite_utility_profile(
            os.getenv(
                "PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE",
                DEFAULT_BAYESIAN_POLICY_LITE_UTILITY_PROFILE,
            )
        )
    )
    proto_bayesian_policy_lite_gate_threshold = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD", "0.50")),
        ),
    )
    proto_bayesian_policy_lite_entropy_threshold = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD", "0.85")),
        ),
    )
    proto_bayesian_policy_lite_max_delta = max(
        0.0,
        float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA", "0.05")),
    )
    proto_bayesian_policy_lite_prob_floor = max(
        0.0,
        min(
            0.32,
            float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR", "0.05")),
        ),
    )

    return RuntimeConfig(
        experiment_mode=experiment_mode,
        world_batch=world_batch,
        parallel_group_name=parallel_group_name,
        proto_llm_psychology_mode=proto_llm_psychology_mode,
        proto_llm_task_appraisal_enabled=proto_llm_task_appraisal_enabled,
        proto_llm_event_appraisal_enabled=proto_llm_event_appraisal_enabled,
        proto_llm_daily_reflection_enabled=proto_llm_daily_reflection_enabled,
        proto_llm_strategy_deliberation_enabled=proto_llm_strategy_deliberation_enabled,
        proto_llm_stage_interview_enabled=proto_llm_stage_interview_enabled,
        proto_llm_final_interview_enabled=proto_llm_final_interview_enabled,
        proto_llm_psychology_min_confidence=proto_llm_psychology_min_confidence,
        proto_llm_psychology_timeout=proto_llm_psychology_timeout,
        proto_llm_psychology_retries=proto_llm_psychology_retries,
        proto_llm_psychology_cache_enabled=proto_llm_psychology_cache_enabled,
        proto_llm_uncontrollability_mode=proto_llm_uncontrollability_mode,
        proto_llm_uncontrollability_min_confidence=proto_llm_uncontrollability_min_confidence,
        proto_llm_uncontrollability_max_shift=proto_llm_uncontrollability_max_shift,
        proto_llm_uncontrollability_timeout=proto_llm_uncontrollability_timeout,
        proto_llm_uncontrollability_retries=proto_llm_uncontrollability_retries,
        proto_llm_uncontrollability_cache_enabled=proto_llm_uncontrollability_cache_enabled,
        proto_scope_spillover_beta=proto_scope_spillover_beta,
        proto_scope_spillover_threshold=proto_scope_spillover_threshold,
        proto_scope_spillover_sigma=proto_scope_spillover_sigma,
        proto_stream_episode_recording_enabled=proto_stream_episode_recording_enabled,
        proto_stream_task_appraisal_retrieval_enabled=proto_stream_task_appraisal_retrieval_enabled,
        proto_stream_attribution_retrieval_enabled=proto_stream_attribution_retrieval_enabled,
        proto_bayesian_control_audit_enabled=proto_bayesian_control_audit_enabled,
        proto_bayesian_control_rho=proto_bayesian_control_rho,
        proto_bayesian_control_weight=proto_bayesian_control_weight,
        proto_bayesian_policy_lite_mode=proto_bayesian_policy_lite_mode,
        proto_bayesian_policy_lite_tau=proto_bayesian_policy_lite_tau,
        proto_bayesian_policy_lite_confidence_k=proto_bayesian_policy_lite_confidence_k,
        proto_bayesian_policy_lite_rho=proto_bayesian_policy_lite_rho,
        proto_bayesian_policy_lite_weight=proto_bayesian_policy_lite_weight,
        proto_bayesian_policy_lite_utility_profile=(
            proto_bayesian_policy_lite_utility_profile
        ),
        proto_bayesian_policy_lite_gate_threshold=(
            proto_bayesian_policy_lite_gate_threshold
        ),
        proto_bayesian_policy_lite_entropy_threshold=(
            proto_bayesian_policy_lite_entropy_threshold
        ),
        proto_bayesian_policy_lite_max_delta=proto_bayesian_policy_lite_max_delta,
        proto_bayesian_policy_lite_prob_floor=proto_bayesian_policy_lite_prob_floor,
    )
