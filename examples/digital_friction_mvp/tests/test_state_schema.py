from __future__ import annotations

from proto.state_schema import (
    build_initial_proto_status,
    build_proto_status_attributes,
    build_survey_measurement_updates,
    derive_initial_proto_scores,
)
from surveys import tech_acceptance_survey


def test_initial_proto_scores_vary_with_profile() -> None:
    low_risk = derive_initial_proto_scores(
        digital_experience=0.9,
        vision_limit=0.1,
        past_fraud_experience=0.0,
    )
    high_risk = derive_initial_proto_scores(
        digital_experience=0.2,
        vision_limit=0.6,
        past_fraud_experience=0.6,
    )
    assert low_risk["helplessness_score"] < high_risk["helplessness_score"]
    assert low_risk["trust_in_apps"] > high_risk["trust_in_apps"]
    assert low_risk["avoidance_tendency"] < high_risk["avoidance_tendency"]


def test_build_initial_proto_status_contains_core_schema_fields() -> None:
    status = build_initial_proto_status(
        digital_experience=0.4,
        vision_limit=0.5,
        past_fraud_experience=0.3,
    )
    for key in (
        "helplessness_score",
        "trust_in_apps",
        "avoidance_tendency",
        "proto_assigned_task_json",
        "proto_consecutive_failures",
        "proto_stage_start_helplessness",
        "friction_step_signal",
        "task_domain_memory",
        "help_effect_memory",
        "recent_episode_buffer",
        "rationale_memory",
        "digital_emotion_state",
        "proto_daily_reflection",
        "proto_daily_reflection_history",
        "proto_last_reflection_day",
        "proto_last_housekeeping_day",
        "proto_bayesian_policy_memory",
        "proto_task_appraisal",
        "proto_strategy_deliberation",
        "proto_stage_interview",
        "proto_stage_interview_history",
        "proto_final_interview",
        "proto_latest_digital_need",
        "proto_latest_app_entry_plan",
        "proto_app_entry_rollout_rows_json",
        "survey_self_efficacy_index",
        "survey_support_index",
        "survey_usefulness_index",
        "survey_anxiety_index",
    ):
        assert key in status
    assert status["digital_emotion_state"]["anxiety"] >= 0.0
    assert status["digital_emotion_state"]["confidence"] >= 0.0
    assert status["survey_anxiety_index"] >= 0.0
    assert status["proto_bayesian_policy_memory"]["version"] == (
        "policy_lite_shadow_v1"
    )
    assert status["proto_latest_digital_need"] == {}
    assert status["proto_latest_app_entry_plan"] == {}
    assert status["proto_app_entry_rollout_rows_json"] == []


def test_survey_measurement_updates_do_not_overwrite_core_proto_state() -> None:
    updates = build_survey_measurement_updates(
        values={
            "tech_acceptance": 76.0,
            "trust_in_apps": 81.0,
            "avoidance_tendency": 44.0,
            "helpless_control_loss": 62.0,
            "behavior_delay_online": 53.0,
        },
        derived={
            "survey_helplessness_index": 61.0,
            "survey_withdrawal_index": 52.0,
            "survey_self_efficacy_index": 57.0,
            "survey_support_index": 63.0,
            "survey_usefulness_index": 71.0,
            "survey_anxiety_index": 46.0,
        },
        day=2,
        t=21601.0,
    )
    assert "helplessness_score" not in updates
    assert "trust_in_apps" not in updates
    assert "avoidance_tendency" not in updates
    assert updates["survey_helplessness_index"] == 61.0
    assert updates["survey_withdrawal_index"] == 52.0
    assert updates["survey_self_efficacy_index"] == 57.0
    assert updates["survey_support_index"] == 63.0
    assert updates["survey_usefulness_index"] == 71.0
    assert updates["survey_anxiety_index"] == 46.0
    assert updates["last_survey_day"] == 2


def test_proto_agent_status_attributes_include_core_proto_fields() -> None:
    names = {attr.name for attr in build_proto_status_attributes()}
    assert {
        "helplessness_score",
        "trust_in_apps",
        "avoidance_tendency",
        "proto_assigned_task_json",
        "friction_step_signal",
        "proto_consecutive_failures",
        "task_domain_memory",
        "help_effect_memory",
        "recent_episode_buffer",
        "rationale_memory",
        "digital_emotion_state",
        "proto_daily_reflection",
        "proto_daily_reflection_history",
        "proto_last_reflection_day",
        "proto_last_housekeeping_day",
        "proto_task_appraisal",
        "proto_strategy_deliberation",
        "proto_stage_interview",
        "proto_stage_interview_history",
        "proto_final_interview",
        "survey_self_efficacy_index",
        "survey_support_index",
        "survey_usefulness_index",
        "survey_anxiety_index",
    }.issubset(names)


def test_digital_anxiety_survey_field_derives_anxiety_index() -> None:
    survey = tech_acceptance_survey()
    question_names = [element.name for element in survey.pages[0].elements]
    assert "digital_anxiety" in question_names
