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
VALID_BAYESIAN_POLICY_LITE_REFERENCE_MODES = {"hybrid_ref", "semantic_v2"}
DEFAULT_BAYESIAN_POLICY_LITE_REFERENCE_MODE = "hybrid_ref"
VALID_TASK_ENTRY_MODES = {
    "fixed_assignment",
    "mobile_intention_rule",
    "mobile_intention_llm_shadow",
    "mobile_intention_llm_rerank_online_mc",
}
VALID_OUTCOME_MODEL_MODES = {
    "rule_v1",
    "appraisal_rule_v2",
    "trajectory_shadow",
    "trajectory_bounded_online_mc",
}
VALID_OUTCOME_TRAJECTORY_INVALID_POLICIES = {"fail_run"}
VALID_MOBILE_INTENTION_RERANK_LOW_CONFIDENCE_POLICIES = {
    "fail_run",
    "accept_with_audit",
}
VALID_HUYS_DAYAN_LITE_CONTROLLABILITY_MODES = {
    "off",
    "shadow",
    "gated_modulate",
    "control_centered_modulate",
}


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


def _normalize_bayesian_policy_lite_reference_mode(value: str | None) -> str:
    mode = str(
        value or DEFAULT_BAYESIAN_POLICY_LITE_REFERENCE_MODE
    ).strip().lower()
    if mode not in VALID_BAYESIAN_POLICY_LITE_REFERENCE_MODES:
        raise ValueError(
            "PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE must be one of: "
            + ", ".join(sorted(VALID_BAYESIAN_POLICY_LITE_REFERENCE_MODES))
        )
    return mode


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
    proto_bayesian_policy_lite_reference_mode: str
    proto_bayesian_policy_lite_lambda_llm: float
    proto_bayesian_policy_lite_min_llm_confidence: float
    proto_task_entry_mode: str
    proto_mobile_intention_calibration_path: str
    proto_mobile_intention_mapping_path: str
    proto_mobile_intention_confidence_threshold: float
    proto_mobile_intention_eval_interval_minutes: int
    proto_mobile_intention_world_neutral: bool
    proto_mobile_intention_llm_prompt_version: str
    proto_mobile_intention_llm_min_confidence: float
    proto_mobile_intention_rerank_top_k: int
    proto_mobile_intention_rerank_low_confidence_policy: str
    proto_mobile_intention_rerank_schedule_path: str
    proto_mobile_intention_rerank_run_id: str
    proto_outcome_model_mode: str
    proto_outcome_trajectory_prompt_version: str
    proto_outcome_trajectory_taxonomy_version: str
    proto_outcome_trajectory_alpha: float
    proto_outcome_trajectory_max_outcome_shift: float
    proto_outcome_trajectory_max_tvd: float
    proto_outcome_trajectory_min_confidence: float
    proto_outcome_trajectory_strict_schema: bool
    proto_outcome_trajectory_invalid_policy: str
    proto_huys_dayan_lite_controllability_mode: str
    proto_huys_dayan_lite_confidence_k: int
    proto_huys_dayan_lite_min_action_updates: int
    proto_huys_dayan_lite_global_update_weight: float
    proto_huys_dayan_lite_rho: float
    proto_huys_dayan_lite_use_avoid_in_main_score: bool
    proto_huys_dayan_lite_weight_entropy: float
    proto_huys_dayan_lite_weight_contrast: float
    proto_huys_dayan_lite_weight_chi: float
    proto_huys_dayan_lite_modulation_gate_threshold: float
    proto_huys_dayan_lite_modulation_max_delta: float
    proto_huys_dayan_lite_low_c_threshold: float
    proto_huys_dayan_lite_high_c_threshold: float


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
        int(os.getenv("PROTO_LLM_PSYCHOLOGY_TIMEOUT", "45")),
    )
    proto_llm_psychology_retries = max(
        0,
        int(os.getenv("PROTO_LLM_PSYCHOLOGY_RETRIES", "3")),
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
        int(os.getenv("PROTO_LLM_UNCONTROLLABILITY_TIMEOUT", "45")),
    )
    proto_llm_uncontrollability_retries = max(
        0,
        int(os.getenv("PROTO_LLM_UNCONTROLLABILITY_RETRIES", "3")),
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
    proto_bayesian_policy_lite_reference_mode = (
        _normalize_bayesian_policy_lite_reference_mode(
            os.getenv(
                "PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE",
                DEFAULT_BAYESIAN_POLICY_LITE_REFERENCE_MODE,
            )
        )
    )
    proto_bayesian_policy_lite_lambda_llm = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM", "0.25")),
        ),
    )
    proto_bayesian_policy_lite_min_llm_confidence = max(
        0.0,
        min(
            1.0,
            float(
                os.getenv(
                    "PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE",
                    "0.50",
                )
            ),
        ),
    )
    proto_task_entry_mode = (
        os.getenv("PROTO_TASK_ENTRY_MODE", "fixed_assignment").strip().lower()
    )
    if proto_task_entry_mode not in VALID_TASK_ENTRY_MODES:
        raise ValueError(
            "PROTO_TASK_ENTRY_MODE must be one of: "
            + ", ".join(sorted(VALID_TASK_ENTRY_MODES))
        )
    proto_mobile_intention_calibration_path = os.getenv(
        "PROTO_MOBILE_INTENTION_CALIBRATION_PATH",
        "",
    ).strip()
    proto_mobile_intention_mapping_path = os.getenv(
        "PROTO_MOBILE_INTENTION_MAPPING_PATH",
        "",
    ).strip()
    for artifact_name, artifact_path in (
        (
            "PROTO_MOBILE_INTENTION_CALIBRATION_PATH",
            proto_mobile_intention_calibration_path,
        ),
        ("PROTO_MOBILE_INTENTION_MAPPING_PATH", proto_mobile_intention_mapping_path),
    ):
        if artifact_path and "validation" in artifact_path.lower():
            raise ValueError(f"{artifact_name} must not point to validation data")
    proto_mobile_intention_confidence_threshold = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_MOBILE_INTENTION_CONFIDENCE_THRESHOLD", "0.70")),
        ),
    )
    proto_mobile_intention_eval_interval_minutes = max(
        1,
        int(float(os.getenv("PROTO_MOBILE_INTENTION_EVAL_INTERVAL_MINUTES", "60"))),
    )
    proto_mobile_intention_world_neutral = _parse_bool_env(
        "PROTO_MOBILE_INTENTION_WORLD_NEUTRAL",
        True,
    )
    proto_mobile_intention_llm_prompt_version = os.getenv(
        "PROTO_MOBILE_INTENTION_LLM_PROMPT_VERSION",
        "mobile_intention_shadow_v1",
    ).strip()
    proto_mobile_intention_llm_min_confidence = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_MOBILE_INTENTION_LLM_MIN_CONFIDENCE", "0.70")),
        ),
    )
    proto_mobile_intention_rerank_top_k = max(
        1,
        int(float(os.getenv("PROTO_MOBILE_INTENTION_RERANK_TOP_K", "5"))),
    )
    proto_mobile_intention_rerank_low_confidence_policy = (
        os.getenv(
            "PROTO_MOBILE_INTENTION_RERANK_LOW_CONFIDENCE_POLICY",
            "fail_run",
        )
        .strip()
        .lower()
    )
    if (
        proto_mobile_intention_rerank_low_confidence_policy
        not in VALID_MOBILE_INTENTION_RERANK_LOW_CONFIDENCE_POLICIES
    ):
        raise ValueError(
            "PROTO_MOBILE_INTENTION_RERANK_LOW_CONFIDENCE_POLICY must be one of: "
            + ", ".join(sorted(VALID_MOBILE_INTENTION_RERANK_LOW_CONFIDENCE_POLICIES))
        )
    proto_mobile_intention_rerank_schedule_path = os.getenv(
        "PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH",
        "",
    ).strip()
    proto_mobile_intention_rerank_run_id = os.getenv(
        "PROTO_MOBILE_INTENTION_RERANK_RUN_ID",
        "",
    ).strip()
    proto_outcome_model_mode = (
        os.getenv("PROTO_OUTCOME_MODEL_MODE", "rule_v1").strip().lower()
    )
    if proto_outcome_model_mode not in VALID_OUTCOME_MODEL_MODES:
        raise ValueError(
            "PROTO_OUTCOME_MODEL_MODE must be one of: "
            + ", ".join(sorted(VALID_OUTCOME_MODEL_MODES))
        )
    if (
        proto_outcome_model_mode
        in {"trajectory_shadow", "trajectory_bounded_online_mc"}
        and proto_llm_psychology_mode != "hybrid"
    ):
        raise ValueError(
            "PROTO_LLM_PSYCHOLOGY_MODE=hybrid is required when "
            "PROTO_OUTCOME_MODEL_MODE uses trajectory LLM"
        )
    proto_outcome_trajectory_prompt_version = os.getenv(
        "PROTO_OUTCOME_TRAJECTORY_PROMPT_VERSION",
        "trajectory_v1",
    ).strip()
    proto_outcome_trajectory_taxonomy_version = os.getenv(
        "PROTO_OUTCOME_TRAJECTORY_TAXONOMY_VERSION",
        "friction_taxonomy_v1",
    ).strip()
    proto_outcome_trajectory_alpha = max(
        0.0,
        min(1.0, float(os.getenv("PROTO_OUTCOME_TRAJECTORY_ALPHA", "0.10"))),
    )
    proto_outcome_trajectory_max_outcome_shift = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_OUTCOME_TRAJECTORY_MAX_OUTCOME_SHIFT", "0.08")),
        ),
    )
    proto_outcome_trajectory_max_tvd = max(
        0.0,
        min(1.0, float(os.getenv("PROTO_OUTCOME_TRAJECTORY_MAX_TVD", "0.10"))),
    )
    proto_outcome_trajectory_min_confidence = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_OUTCOME_TRAJECTORY_MIN_CONFIDENCE", "0.65")),
        ),
    )
    proto_outcome_trajectory_strict_schema = _parse_bool_env(
        "PROTO_OUTCOME_TRAJECTORY_STRICT_SCHEMA",
        True,
    )
    proto_outcome_trajectory_invalid_policy = (
        os.getenv("PROTO_OUTCOME_TRAJECTORY_INVALID_POLICY", "fail_run")
        .strip()
        .lower()
    )
    if (
        proto_outcome_trajectory_invalid_policy
        not in VALID_OUTCOME_TRAJECTORY_INVALID_POLICIES
    ):
        raise ValueError(
            "PROTO_OUTCOME_TRAJECTORY_INVALID_POLICY first version only supports: "
            + ", ".join(sorted(VALID_OUTCOME_TRAJECTORY_INVALID_POLICIES))
        )
    proto_huys_dayan_lite_controllability_mode = (
        os.getenv("PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE", "off")
        .strip()
        .lower()
    )
    if (
        proto_huys_dayan_lite_controllability_mode
        not in VALID_HUYS_DAYAN_LITE_CONTROLLABILITY_MODES
    ):
        raise ValueError(
            "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE must be one of: "
            + ", ".join(sorted(VALID_HUYS_DAYAN_LITE_CONTROLLABILITY_MODES))
        )
    proto_huys_dayan_lite_confidence_k = max(
        1,
        int(float(os.getenv("PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K", "6"))),
    )
    proto_huys_dayan_lite_min_action_updates = max(
        0,
        int(float(os.getenv("PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES", "1"))),
    )
    proto_huys_dayan_lite_global_update_weight = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT", "0.05")),
        ),
    )
    proto_huys_dayan_lite_rho = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_HUYS_DAYAN_LITE_RHO", "1.0")),
        ),
    )
    proto_huys_dayan_lite_use_avoid_in_main_score = _parse_bool_env(
        "PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE",
        False,
    )
    proto_huys_dayan_lite_weight_entropy = max(
        0.0,
        float(os.getenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY", "0.25")),
    )
    proto_huys_dayan_lite_weight_contrast = max(
        0.0,
        float(os.getenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST", "0.25")),
    )
    proto_huys_dayan_lite_weight_chi = max(
        0.0,
        float(os.getenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI", "0.50")),
    )
    proto_huys_dayan_lite_modulation_gate_threshold = max(
        0.0,
        min(
            1.0,
            float(
                os.getenv(
                    "PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD",
                    "0.50",
                )
            ),
        ),
    )
    proto_huys_dayan_lite_modulation_max_delta = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA", "0.25")),
        ),
    )
    proto_huys_dayan_lite_low_c_threshold = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD", "0.45")),
        ),
    )
    proto_huys_dayan_lite_high_c_threshold = max(
        0.0,
        min(
            1.0,
            float(os.getenv("PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD", "0.60")),
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
        proto_bayesian_policy_lite_reference_mode=(
            proto_bayesian_policy_lite_reference_mode
        ),
        proto_bayesian_policy_lite_lambda_llm=proto_bayesian_policy_lite_lambda_llm,
        proto_bayesian_policy_lite_min_llm_confidence=(
            proto_bayesian_policy_lite_min_llm_confidence
        ),
        proto_task_entry_mode=proto_task_entry_mode,
        proto_mobile_intention_calibration_path=(
            proto_mobile_intention_calibration_path
        ),
        proto_mobile_intention_mapping_path=proto_mobile_intention_mapping_path,
        proto_mobile_intention_confidence_threshold=(
            proto_mobile_intention_confidence_threshold
        ),
        proto_mobile_intention_eval_interval_minutes=(
            proto_mobile_intention_eval_interval_minutes
        ),
        proto_mobile_intention_world_neutral=proto_mobile_intention_world_neutral,
        proto_mobile_intention_llm_prompt_version=(
            proto_mobile_intention_llm_prompt_version
        ),
        proto_mobile_intention_llm_min_confidence=(
            proto_mobile_intention_llm_min_confidence
        ),
        proto_mobile_intention_rerank_top_k=proto_mobile_intention_rerank_top_k,
        proto_mobile_intention_rerank_low_confidence_policy=(
            proto_mobile_intention_rerank_low_confidence_policy
        ),
        proto_mobile_intention_rerank_schedule_path=(
            proto_mobile_intention_rerank_schedule_path
        ),
        proto_mobile_intention_rerank_run_id=(
            proto_mobile_intention_rerank_run_id
        ),
        proto_outcome_model_mode=proto_outcome_model_mode,
        proto_outcome_trajectory_prompt_version=(
            proto_outcome_trajectory_prompt_version
        ),
        proto_outcome_trajectory_taxonomy_version=(
            proto_outcome_trajectory_taxonomy_version
        ),
        proto_outcome_trajectory_alpha=proto_outcome_trajectory_alpha,
        proto_outcome_trajectory_max_outcome_shift=(
            proto_outcome_trajectory_max_outcome_shift
        ),
        proto_outcome_trajectory_max_tvd=proto_outcome_trajectory_max_tvd,
        proto_outcome_trajectory_min_confidence=(
            proto_outcome_trajectory_min_confidence
        ),
        proto_outcome_trajectory_strict_schema=(
            proto_outcome_trajectory_strict_schema
        ),
        proto_outcome_trajectory_invalid_policy=(
            proto_outcome_trajectory_invalid_policy
        ),
        proto_huys_dayan_lite_controllability_mode=(
            proto_huys_dayan_lite_controllability_mode
        ),
        proto_huys_dayan_lite_confidence_k=proto_huys_dayan_lite_confidence_k,
        proto_huys_dayan_lite_min_action_updates=(
            proto_huys_dayan_lite_min_action_updates
        ),
        proto_huys_dayan_lite_global_update_weight=(
            proto_huys_dayan_lite_global_update_weight
        ),
        proto_huys_dayan_lite_rho=proto_huys_dayan_lite_rho,
        proto_huys_dayan_lite_use_avoid_in_main_score=(
            proto_huys_dayan_lite_use_avoid_in_main_score
        ),
        proto_huys_dayan_lite_weight_entropy=(
            proto_huys_dayan_lite_weight_entropy
        ),
        proto_huys_dayan_lite_weight_contrast=(
            proto_huys_dayan_lite_weight_contrast
        ),
        proto_huys_dayan_lite_weight_chi=proto_huys_dayan_lite_weight_chi,
        proto_huys_dayan_lite_modulation_gate_threshold=(
            proto_huys_dayan_lite_modulation_gate_threshold
        ),
        proto_huys_dayan_lite_modulation_max_delta=(
            proto_huys_dayan_lite_modulation_max_delta
        ),
        proto_huys_dayan_lite_low_c_threshold=(
            proto_huys_dayan_lite_low_c_threshold
        ),
        proto_huys_dayan_lite_high_c_threshold=(
            proto_huys_dayan_lite_high_c_threshold
        ),
    )
