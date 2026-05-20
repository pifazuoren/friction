from __future__ import annotations

import pytest

from config_runtime import load_runtime_config

from proto.runtime import (
    assign_task_with_entry_decision,
    assign_task_if_missing,
    build_stage_transition_updates,
    build_task_surface_updates,
)
from proto.task_assignment import TASK_LIBRARY, select_task_for_agent
from world_runner import _build_config_payload

TASK_WINDOW_MORNING = 9 * 60 * 60
TASK_WINDOW_AFTERNOON = 14 * 60 * 60
NON_WINDOW_TICK = 8 * 60 * 60


def test_assign_task_if_missing_seeds_task_and_updates(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    env = {
        "friction_level": 1,
        "malicious_friction_level": 1,
        "complexity_level": 1,
        "risk_level": 1,
        "assist_level": 1,
        "accessibility_level": 1,
        "human_support_level": 1,
    }
    task, updates, seeded = assign_task_if_missing(
        existing_task=None,
        agent_id=7,
        day=1,
        tick_seconds=float(TASK_WINDOW_MORNING),
        env=env,
    )
    assert seeded is True
    assert task is not None
    assert updates["digital_todo_pending"] == 1
    assert updates["digital_task_hint"] == task.task_family
    assert updates["digital_todo_active_task_id"] == task.task_id
    assert updates["proto_assigned_task_json"]


def test_assign_task_if_missing_returns_none_outside_window(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    task, updates, seeded = assign_task_if_missing(
        existing_task=None,
        agent_id=7,
        day=1,
        tick_seconds=float(NON_WINDOW_TICK),
        env={},
    )
    assert task is None
    assert updates == {}
    assert seeded is False


def test_assign_task_with_mobile_noop_does_not_write_task_surface(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"browse_entertainment":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    task, updates, seeded, decision = assign_task_with_entry_decision(
        existing_task=None,
        agent_id=7,
        day=1,
        tick_seconds=float(NON_WINDOW_TICK),
        env={},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )
    assert task is None
    assert updates == {}
    assert seeded is False
    assert decision is not None
    assert decision.entry_status == "browse_context_only"
    assert decision.audit["is_avoidance"] is False


def test_assign_task_with_mobile_mapped_task_writes_surface(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    calibration = tmp_path / "reference_calibration.json"
    calibration.write_text(
        '{"global_prior":{"p_mobile_intention":{"use_payment_or_finance":1.0}},'
        '"uses_validation_data":false}',
        encoding="utf-8",
    )
    task, updates, seeded, decision = assign_task_with_entry_decision(
        existing_task=None,
        agent_id=7,
        day=1,
        tick_seconds=float(NON_WINDOW_TICK),
        env={"risk_level": 2, "malicious_friction_level": 2},
        entry_mode="mobile_intention_rule",
        calibration_path=str(calibration),
    )
    assert seeded is True
    assert task is not None
    assert decision is not None
    assert decision.entry_status == "entered_mapped_digital_task"
    assert updates["proto_assigned_task_json"]
    assert updates["digital_todo_pending"] == 1
    assert updates["digital_task_hint"] == "payment_risk_confirmation"


def test_assign_task_if_missing_keeps_existing_task_and_skips_new_window(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    env = {
        "friction_level": 2,
        "malicious_friction_level": 2,
        "complexity_level": 2,
        "risk_level": 2,
        "assist_level": 1,
        "accessibility_level": 1,
        "human_support_level": 1,
    }
    existing = select_task_for_agent(
        agent_id=3,
        day=0,
        tick_seconds=float(TASK_WINDOW_MORNING),
        env=env,
    )
    assert existing is not None
    task, updates, seeded = assign_task_if_missing(
        existing_task=existing,
        agent_id=3,
        day=0,
        tick_seconds=float(TASK_WINDOW_AFTERNOON),
        env=env,
    )
    assert seeded is False
    assert task == existing
    assert updates == {}


def test_build_task_surface_updates_matches_task_identity(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    env = {
        "friction_level": 0,
        "malicious_friction_level": 0,
        "complexity_level": 0,
        "risk_level": 1,
        "assist_level": 3,
        "accessibility_level": 3,
        "human_support_level": 3,
    }
    task = select_task_for_agent(
        agent_id=5,
        day=2,
        tick_seconds=float(TASK_WINDOW_AFTERNOON),
        env=env,
    )
    assert task is not None
    updates = build_task_surface_updates(
        task=task,
        day=2,
        tick_seconds=float(TASK_WINDOW_AFTERNOON),
    )
    assert updates["digital_task_hint"] == task.task_family
    assert updates["digital_task_hint_need"] == task.need_type
    assert updates["digital_todo_active_day"] == 2
    assert updates["digital_todo_active_t"] == float(TASK_WINDOW_AFTERNOON)


def test_task_rotation_can_cover_all_six_task_families(monkeypatch) -> None:
    monkeypatch.setenv("PARALLEL_PAIR_SEED", "101")
    env = {
        "friction_level": 1,
        "malicious_friction_level": 1,
        "complexity_level": 1,
        "risk_level": 1,
        "assist_level": 1,
        "accessibility_level": 1,
        "human_support_level": 1,
    }
    seen = set()
    for day in range(6):
        for tick_seconds in (TASK_WINDOW_MORNING, TASK_WINDOW_AFTERNOON):
            task = select_task_for_agent(
                agent_id=2,
                day=day,
                tick_seconds=float(tick_seconds),
                env=env,
            )
            assert task is not None
            seen.add(task.task_family)
    assert seen == {str(template["task_family"]) for template in TASK_LIBRARY}


def test_build_stage_transition_updates_resets_stage_scoped_state() -> None:
    updates, changed = build_stage_transition_updates(
        current_stage_key="shock",
        previous_stage_key="steady",
        helplessness=62.5,
    )
    assert changed is True
    assert updates["proto_active_stage_key"] == "shock"
    assert updates["event_log"] == []
    assert updates["proto_stage_attempt_rows_json"] == "[]"
    assert updates["proto_stage_start_helplessness"] == 62.5
    assert updates["proto_stage_daily_reflection_count"] == 0
    assert "proto_bayesian_control_memory" not in updates
    assert "proto_bayesian_policy_memory" not in updates


def test_build_stage_transition_updates_noops_when_stage_is_unchanged() -> None:
    updates, changed = build_stage_transition_updates(
        current_stage_key="recovery",
        previous_stage_key="recovery",
        helplessness=48.0,
    )
    assert changed is False
    assert updates == {}


def test_build_stage_transition_updates_noops_for_blank_stage() -> None:
    updates, changed = build_stage_transition_updates(
        current_stage_key="",
        previous_stage_key="steady",
        helplessness=35.0,
    )
    assert changed is False
    assert updates == {}


def test_load_runtime_config_exposes_scope_spillover_defaults_and_overrides(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_SCOPE_SPILLOVER_BETA", "1.4")
    monkeypatch.setenv("PROTO_SCOPE_SPILLOVER_THRESHOLD", "0.22")
    monkeypatch.setenv("PROTO_SCOPE_SPILLOVER_SIGMA", "0.55")
    config = load_runtime_config()
    assert config.proto_scope_spillover_beta == 1.4
    assert config.proto_scope_spillover_threshold == 0.22
    assert config.proto_scope_spillover_sigma == 0.55


def test_load_runtime_config_exposes_bayesian_control_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PROTO_BAYESIAN_CONTROL_AUDIT_ENABLED", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_CONTROL_RHO", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_CONTROL_WEIGHT", raising=False)

    config = load_runtime_config()

    assert config.proto_bayesian_control_audit_enabled is True
    assert config.proto_bayesian_control_rho == 0.98
    assert config.proto_bayesian_control_weight == 1.0


def test_load_runtime_config_bayesian_control_overrides_and_clamps(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_BAYESIAN_CONTROL_AUDIT_ENABLED", "0")
    monkeypatch.setenv("PROTO_BAYESIAN_CONTROL_RHO", "1.7")
    monkeypatch.setenv("PROTO_BAYESIAN_CONTROL_WEIGHT", "-4")

    config = load_runtime_config()

    assert config.proto_bayesian_control_audit_enabled is False
    assert config.proto_bayesian_control_rho == 1.0
    assert config.proto_bayesian_control_weight == 0.0


def test_load_runtime_config_exposes_bayesian_policy_lite_defaults(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_MODE", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_TAU", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_RHO", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_WEIGHT", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM", raising=False)
    monkeypatch.delenv("PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE", raising=False)

    config = load_runtime_config()

    assert config.proto_bayesian_policy_lite_mode == "off"
    assert config.proto_bayesian_policy_lite_tau == 1.0
    assert config.proto_bayesian_policy_lite_confidence_k == 4
    assert config.proto_bayesian_policy_lite_rho == 1.0
    assert config.proto_bayesian_policy_lite_weight == 1.0
    assert config.proto_bayesian_policy_lite_utility_profile == "shadow_v1"
    assert config.proto_bayesian_policy_lite_gate_threshold == 0.50
    assert config.proto_bayesian_policy_lite_entropy_threshold == 0.85
    assert config.proto_bayesian_policy_lite_max_delta == 0.05
    assert config.proto_bayesian_policy_lite_prob_floor == 0.05
    assert config.proto_bayesian_policy_lite_reference_mode == "hybrid_ref"
    assert config.proto_bayesian_policy_lite_lambda_llm == 0.25
    assert config.proto_bayesian_policy_lite_min_llm_confidence == 0.50


def test_load_runtime_config_exposes_mobile_entry_defaults(monkeypatch) -> None:
    for key in (
        "PROTO_TASK_ENTRY_MODE",
        "PROTO_MOBILE_INTENTION_CALIBRATION_PATH",
        "PROTO_MOBILE_INTENTION_MAPPING_PATH",
        "PROTO_MOBILE_INTENTION_CONFIDENCE_THRESHOLD",
        "PROTO_MOBILE_INTENTION_EVAL_INTERVAL_MINUTES",
        "PROTO_MOBILE_INTENTION_WORLD_NEUTRAL",
        "PROTO_MOBILE_INTENTION_LLM_PROMPT_VERSION",
        "PROTO_MOBILE_INTENTION_LLM_MIN_CONFIDENCE",
        "PROTO_MOBILE_INTENTION_RERANK_TOP_K",
        "PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH",
        "PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_ROLE",
        "PROTO_MOBILE_INTENTION_RERANK_RUN_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    config = load_runtime_config()

    assert config.proto_task_entry_mode == "fixed_assignment"
    assert config.proto_mobile_intention_calibration_path == ""
    assert config.proto_mobile_intention_mapping_path == ""
    assert config.proto_mobile_intention_confidence_threshold == 0.70
    assert config.proto_mobile_intention_eval_interval_minutes == 60
    assert config.proto_mobile_intention_world_neutral is True
    assert config.proto_mobile_intention_llm_prompt_version == "mobile_intention_shadow_v1"
    assert config.proto_mobile_intention_llm_min_confidence == 0.70
    assert config.proto_mobile_intention_rerank_top_k == 5
    assert config.proto_mobile_intention_rerank_schedule_path == ""
    assert config.proto_mobile_intention_rerank_schedule_role == ""
    assert config.proto_mobile_intention_rerank_run_id == ""


def test_load_runtime_config_requires_rerank_schedule(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "mobile_intention_llm_rerank_online_mc")
    with pytest.raises(ValueError, match="SCHEDULE_ROLE"):
        load_runtime_config()

    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_ROLE", "write")
    with pytest.raises(ValueError, match="SCHEDULE_PATH"):
        load_runtime_config()

    monkeypatch.setenv(
        "PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH",
        str(tmp_path / "schedule.jsonl"),
    )
    with pytest.raises(ValueError, match="RUN_ID"):
        load_runtime_config()

    monkeypatch.setenv("PROTO_MOBILE_INTENTION_RERANK_RUN_ID", "run-1")
    config = load_runtime_config()
    assert config.proto_task_entry_mode == "mobile_intention_llm_rerank_online_mc"
    assert config.proto_mobile_intention_rerank_schedule_role == "write"


def test_load_runtime_config_rejects_validation_artifact_paths(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "mobile_intention_rule")
    monkeypatch.setenv(
        "PROTO_MOBILE_INTENTION_CALIBRATION_PATH",
        "/tmp/elder_validation_targets.json",
    )
    with pytest.raises(ValueError, match="validation"):
        load_runtime_config()


def test_world_runner_fingerprint_includes_mobile_entry_env(monkeypatch) -> None:
    payload = _build_config_payload(
        {
            "PROTO_TASK_ENTRY_MODE": "mobile_intention_rule",
            "PROTO_MOBILE_INTENTION_CONFIDENCE_THRESHOLD": "0.70",
            "PROTO_MOBILE_INTENTION_EVAL_INTERVAL_MINUTES": "60",
            "PROTO_MOBILE_INTENTION_RERANK_TOP_K": "5",
            "PROTO_MOBILE_INTENTION_RERANK_RUN_ID": "run-1",
            "PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH": "/tmp/schedule.jsonl",
            "PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_ROLE": "write",
        },
        ["baseline_low_friction"],
    )
    assert payload["PROTO_TASK_ENTRY_MODE"] == "mobile_intention_rule"
    assert payload["PROTO_MOBILE_INTENTION_CONFIDENCE_THRESHOLD"] == "0.70"
    assert payload["PROTO_MOBILE_INTENTION_EVAL_INTERVAL_MINUTES"] == "60"
    assert payload["PROTO_MOBILE_INTENTION_RERANK_TOP_K"] == "5"
    assert payload["PROTO_MOBILE_INTENTION_RERANK_RUN_ID"] == "run-1"
    assert payload["PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_PATH"] == "/tmp/schedule.jsonl"
    assert payload["PROTO_MOBILE_INTENTION_RERANK_SCHEDULE_ROLE"] == "write"


def test_load_runtime_config_exposes_huys_dayan_lite_defaults(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_RHO", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD", raising=False)
    monkeypatch.delenv("PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD", raising=False)

    config = load_runtime_config()

    assert config.proto_huys_dayan_lite_controllability_mode == "off"
    assert config.proto_huys_dayan_lite_confidence_k == 6
    assert config.proto_huys_dayan_lite_min_action_updates == 1
    assert config.proto_huys_dayan_lite_global_update_weight == 0.05
    assert config.proto_huys_dayan_lite_rho == 1.0
    assert config.proto_huys_dayan_lite_use_avoid_in_main_score is False
    assert config.proto_huys_dayan_lite_weight_entropy == 0.25
    assert config.proto_huys_dayan_lite_weight_contrast == 0.25
    assert config.proto_huys_dayan_lite_weight_chi == 0.50
    assert config.proto_huys_dayan_lite_modulation_gate_threshold == 0.50
    assert config.proto_huys_dayan_lite_modulation_max_delta == 0.25
    assert config.proto_huys_dayan_lite_low_c_threshold == 0.45
    assert config.proto_huys_dayan_lite_high_c_threshold == 0.60


def test_load_runtime_config_bayesian_policy_lite_overrides_and_clamps(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_MODE", "gated_lite")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_TAU", "-2")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K", "0")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_RHO", "3")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_WEIGHT", "-4")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE", "theory_v2")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD", "2")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD", "-1")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA", "-0.2")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR", "0.7")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE", "semantic_v2")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM", "2")
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE", "-1")

    config = load_runtime_config()

    assert config.proto_bayesian_policy_lite_mode == "gated_lite"
    assert config.proto_bayesian_policy_lite_tau == 0.000001
    assert config.proto_bayesian_policy_lite_confidence_k == 1
    assert config.proto_bayesian_policy_lite_rho == 1.0
    assert config.proto_bayesian_policy_lite_weight == 0.0
    assert config.proto_bayesian_policy_lite_utility_profile == "theory_v2"
    assert config.proto_bayesian_policy_lite_gate_threshold == 1.0
    assert config.proto_bayesian_policy_lite_entropy_threshold == 0.0
    assert config.proto_bayesian_policy_lite_max_delta == 0.0
    assert config.proto_bayesian_policy_lite_prob_floor == 0.32
    assert config.proto_bayesian_policy_lite_reference_mode == "semantic_v2"
    assert config.proto_bayesian_policy_lite_lambda_llm == 1.0
    assert config.proto_bayesian_policy_lite_min_llm_confidence == 0.0


def test_load_runtime_config_huys_dayan_lite_overrides_and_clamps(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE", "gated_modulate")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K", "0")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES", "-3")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT", "2")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_RHO", "-1")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE", "1")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY", "-4")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST", "0.7")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI", "0.8")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD", "2")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA", "5")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD", "-1")
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD", "3")

    config = load_runtime_config()

    assert config.proto_huys_dayan_lite_controllability_mode == "gated_modulate"
    assert config.proto_huys_dayan_lite_confidence_k == 1
    assert config.proto_huys_dayan_lite_min_action_updates == 0
    assert config.proto_huys_dayan_lite_global_update_weight == 1.0
    assert config.proto_huys_dayan_lite_rho == 0.0
    assert config.proto_huys_dayan_lite_use_avoid_in_main_score is True
    assert config.proto_huys_dayan_lite_weight_entropy == 0.0
    assert config.proto_huys_dayan_lite_weight_contrast == 0.7
    assert config.proto_huys_dayan_lite_weight_chi == 0.8
    assert config.proto_huys_dayan_lite_modulation_gate_threshold == 1.0
    assert config.proto_huys_dayan_lite_modulation_max_delta == 1.0
    assert config.proto_huys_dayan_lite_low_c_threshold == 0.0
    assert config.proto_huys_dayan_lite_high_c_threshold == 1.0


def test_load_runtime_config_accepts_control_centered_modulate(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE",
        "control_centered_modulate",
    )

    config = load_runtime_config()

    assert (
        config.proto_huys_dayan_lite_controllability_mode
        == "control_centered_modulate"
    )


def test_load_runtime_config_rejects_invalid_bayesian_policy_lite_profile(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE", "calibrated_v2")

    with pytest.raises(ValueError):
        load_runtime_config()


def test_load_runtime_config_rejects_invalid_bayesian_policy_lite_reference_mode(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE", "semantic_v9")

    with pytest.raises(ValueError):
        load_runtime_config()


def test_load_runtime_config_rejects_invalid_huys_dayan_lite_mode(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE", "on")

    with pytest.raises(ValueError):
        load_runtime_config()


def test_world_runner_fingerprint_payload_includes_bayesian_env_keys() -> None:
    payload = _build_config_payload(
        {
            "PROTO_BAYESIAN_CONTROL_AUDIT_ENABLED": "1",
            "PROTO_BAYESIAN_CONTROL_RHO": "0.95",
            "PROTO_BAYESIAN_CONTROL_WEIGHT": "0",
            "PROTO_BAYESIAN_POLICY_LITE_MODE": "shadow",
            "PROTO_BAYESIAN_POLICY_LITE_TAU": "0.7",
            "PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K": "5",
            "PROTO_BAYESIAN_POLICY_LITE_RHO": "0.9",
            "PROTO_BAYESIAN_POLICY_LITE_WEIGHT": "1.5",
            "PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE": "theory_v2",
            "PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD": "0.50",
            "PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD": "0.85",
            "PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA": "0.05",
            "PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR": "0.05",
            "PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE": "semantic_v2",
            "PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM": "0.25",
            "PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE": "0.50",
            "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE": "control_centered_modulate",
            "PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K": "6",
            "PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES": "2",
            "PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT": "0.05",
            "PROTO_HUYS_DAYAN_LITE_RHO": "1.0",
            "PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE": "false",
            "PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY": "0.25",
            "PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST": "0.25",
            "PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI": "0.50",
            "PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD": "0.50",
            "PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA": "0.10",
            "PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD": "0.45",
            "PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD": "0.60",
        },
        ["baseline_low_friction"],
    )

    assert payload["PROTO_BAYESIAN_CONTROL_AUDIT_ENABLED"] == "1"
    assert payload["PROTO_BAYESIAN_CONTROL_RHO"] == "0.95"
    assert payload["PROTO_BAYESIAN_CONTROL_WEIGHT"] == "0"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_MODE"] == "shadow"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_TAU"] == "0.7"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_CONFIDENCE_K"] == "5"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_RHO"] == "0.9"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_WEIGHT"] == "1.5"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE"] == "theory_v2"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_GATE_THRESHOLD"] == "0.50"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_ENTROPY_THRESHOLD"] == "0.85"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA"] == "0.05"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_PROB_FLOOR"] == "0.05"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_REFERENCE_MODE"] == "semantic_v2"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_LAMBDA_LLM"] == "0.25"
    assert payload["PROTO_BAYESIAN_POLICY_LITE_MIN_LLM_CONFIDENCE"] == "0.50"
    assert (
        payload["PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE"]
        == "control_centered_modulate"
    )
    assert payload["PROTO_HUYS_DAYAN_LITE_CONFIDENCE_K"] == "6"
    assert payload["PROTO_HUYS_DAYAN_LITE_MIN_ACTION_UPDATES"] == "2"
    assert payload["PROTO_HUYS_DAYAN_LITE_GLOBAL_UPDATE_WEIGHT"] == "0.05"
    assert payload["PROTO_HUYS_DAYAN_LITE_RHO"] == "1.0"
    assert payload["PROTO_HUYS_DAYAN_LITE_USE_AVOID_IN_MAIN_SCORE"] == "false"
    assert payload["PROTO_HUYS_DAYAN_LITE_WEIGHT_ENTROPY"] == "0.25"
    assert payload["PROTO_HUYS_DAYAN_LITE_WEIGHT_CONTRAST"] == "0.25"
    assert payload["PROTO_HUYS_DAYAN_LITE_WEIGHT_CHI"] == "0.50"
    assert payload["PROTO_HUYS_DAYAN_LITE_MODULATION_GATE_THRESHOLD"] == "0.50"
    assert payload["PROTO_HUYS_DAYAN_LITE_MODULATION_MAX_DELTA"] == "0.10"
    assert payload["PROTO_HUYS_DAYAN_LITE_LOW_C_THRESHOLD"] == "0.45"
    assert payload["PROTO_HUYS_DAYAN_LITE_HIGH_C_THRESHOLD"] == "0.60"
