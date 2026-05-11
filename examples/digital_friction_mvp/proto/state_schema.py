from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

try:
    from agentsociety.agent import MemoryAttribute
except Exception:  # pragma: no cover - lightweight fallback for local tests
    @dataclass
    class MemoryAttribute:
        name: str
        type: type
        default_or_value: Any
        description: str = ""
        whether_embedding: bool = False

from .experience_memory import (
    build_initial_help_effect_memory,
    build_initial_rationale_memory,
    build_initial_recent_episode_buffer,
    build_initial_task_domain_memory,
)
from .bayesian_control import build_initial_bayesian_control_memory
from .llm_psychology import build_initial_digital_emotion_state


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _clamp_ratio(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def build_proto_status_attributes() -> list[MemoryAttribute]:
    return [
        MemoryAttribute(
            name="digital_experience",
            type=float,
            default_or_value=0.5,
            description="digital experience level for proto experiment",
        ),
        MemoryAttribute(
            name="vision_limit",
            type=float,
            default_or_value=0.3,
            description="vision limitation level for proto experiment",
        ),
        MemoryAttribute(
            name="past_fraud_experience",
            type=float,
            default_or_value=0.2,
            description="past fraud exposure level for proto experiment",
        ),
        MemoryAttribute(
            name="helplessness_score",
            type=float,
            default_or_value=35.0,
            description="global digital helplessness score",
        ),
        MemoryAttribute(
            name="trust_in_apps",
            type=float,
            default_or_value=70.0,
            description="trust in digital services",
        ),
        MemoryAttribute(
            name="avoidance_tendency",
            type=float,
            default_or_value=35.0,
            description="digital avoidance tendency",
        ),
        MemoryAttribute(
            name="survey_helplessness_index",
            type=float,
            default_or_value=35.0,
            description="survey-derived helplessness measurement",
        ),
        MemoryAttribute(
            name="survey_withdrawal_index",
            type=float,
            default_or_value=35.0,
            description="survey-derived withdrawal measurement",
        ),
        MemoryAttribute(
            name="tech_acceptance_score",
            type=float,
            default_or_value=0.0,
            description="latest tech acceptance survey score",
        ),
        MemoryAttribute(
            name="survey_self_efficacy_index",
            type=float,
            default_or_value=50.0,
            description="survey-derived self efficacy measurement",
        ),
        MemoryAttribute(
            name="survey_support_index",
            type=float,
            default_or_value=50.0,
            description="survey-derived support measurement",
        ),
        MemoryAttribute(
            name="survey_usefulness_index",
            type=float,
            default_or_value=50.0,
            description="survey-derived usefulness measurement",
        ),
        MemoryAttribute(
            name="survey_anxiety_index",
            type=float,
            default_or_value=40.0,
            description="survey-derived digital anxiety measurement",
        ),
        MemoryAttribute(
            name="behavior_delay_online",
            type=float,
            default_or_value=35.0,
            description="survey measurement for online delay behavior",
        ),
        MemoryAttribute(
            name="helpless_control_loss",
            type=float,
            default_or_value=35.0,
            description="survey item for control loss",
        ),
        MemoryAttribute(
            name="helpless_expect_failure",
            type=float,
            default_or_value=35.0,
            description="survey item for expected failure",
        ),
        MemoryAttribute(
            name="helpless_effort_futile",
            type=float,
            default_or_value=35.0,
            description="survey item for futile effort",
        ),
        MemoryAttribute(
            name="helpless_low_self_efficacy",
            type=float,
            default_or_value=35.0,
            description="survey item for low self-efficacy",
        ),
        MemoryAttribute(
            name="behavior_proxy_reliance",
            type=float,
            default_or_value=35.0,
            description="survey measurement for proxy reliance behavior",
        ),
        MemoryAttribute(
            name="behavior_offline_switch",
            type=float,
            default_or_value=35.0,
            description="survey measurement for offline switching behavior",
        ),
        MemoryAttribute(
            name="last_survey_day",
            type=int,
            default_or_value=-1,
            description="latest survey day marker",
        ),
        MemoryAttribute(
            name="last_survey_t",
            type=float,
            default_or_value=0.0,
            description="latest survey time marker",
        ),
        MemoryAttribute(
            name="negative_event_count",
            type=int,
            default_or_value=0,
            description="stage negative event count",
        ),
        MemoryAttribute(
            name="intercept_count",
            type=int,
            default_or_value=0,
            description="stage intercept count",
        ),
        MemoryAttribute(
            name="help_request_count",
            type=int,
            default_or_value=0,
            description="stage help request count",
        ),
        MemoryAttribute(
            name="success_count",
            type=int,
            default_or_value=0,
            description="stage success count",
        ),
        MemoryAttribute(
            name="failure_count",
            type=int,
            default_or_value=0,
            description="stage failure count",
        ),
        MemoryAttribute(
            name="cumulative_negative_event_count",
            type=int,
            default_or_value=0,
            description="cumulative negative event count",
        ),
        MemoryAttribute(
            name="cumulative_intercept_count",
            type=int,
            default_or_value=0,
            description="cumulative intercept count",
        ),
        MemoryAttribute(
            name="cumulative_help_request_count",
            type=int,
            default_or_value=0,
            description="cumulative help request count",
        ),
        MemoryAttribute(
            name="cumulative_success_count",
            type=int,
            default_or_value=0,
            description="cumulative success count",
        ),
        MemoryAttribute(
            name="cumulative_failure_count",
            type=int,
            default_or_value=0,
            description="cumulative failure count",
        ),
        MemoryAttribute(
            name="event_log",
            type=list,
            default_or_value=[],
            description="proto event log",
        ),
        MemoryAttribute(
            name="friction_step_signal",
            type=dict,
            default_or_value={},
            description="latest friction step signal",
        ),
        MemoryAttribute(
            name="mobility_nudge_pending",
            type=int,
            default_or_value=0,
            description="whether a mobility nudge is pending",
        ),
        MemoryAttribute(
            name="mobility_nudge_sent_day",
            type=int,
            default_or_value=-1,
            description="latest mobility nudge day",
        ),
        MemoryAttribute(
            name="mobility_nudge_sent_t",
            type=float,
            default_or_value=0.0,
            description="latest mobility nudge time",
        ),
        MemoryAttribute(
            name="mobility_nudge_baseline_trips",
            type=int,
            default_or_value=0,
            description="baseline trip count before mobility nudge",
        ),
        MemoryAttribute(
            name="mobility_nudge_baseline_distance",
            type=float,
            default_or_value=0.0,
            description="baseline travel distance before mobility nudge",
        ),
        MemoryAttribute(
            name="mobility_nudge_baseline_time",
            type=float,
            default_or_value=0.0,
            description="baseline travel time before mobility nudge",
        ),
        MemoryAttribute(
            name="digital_todo_pending",
            type=int,
            default_or_value=0,
            description="whether a proto digital task is pending",
        ),
        MemoryAttribute(
            name="digital_todo_active_task_id",
            type=str,
            default_or_value="",
            description="active proto task id",
        ),
        MemoryAttribute(
            name="digital_todo_active_day",
            type=int,
            default_or_value=-1,
            description="day when active proto task was surfaced",
        ),
        MemoryAttribute(
            name="digital_todo_active_t",
            type=float,
            default_or_value=0.0,
            description="time when active proto task was surfaced",
        ),
        MemoryAttribute(
            name="digital_task_hint",
            type=str,
            default_or_value="",
            description="task family hint for proto experiment",
        ),
        MemoryAttribute(
            name="digital_task_hint_need",
            type=str,
            default_or_value="",
            description="need type hint for proto experiment",
        ),
        MemoryAttribute(
            name="digital_task_hint_pending",
            type=int,
            default_or_value=0,
            description="whether a digital task hint is pending",
        ),
        MemoryAttribute(
            name="proto_assigned_task_json",
            type=str,
            default_or_value="",
            description="serialized assigned proto task",
        ),
        MemoryAttribute(
            name="proto_stage_attempt_rows_json",
            type=str,
            default_or_value="[]",
            description="serialized stage attempt rows for proto experiment",
        ),
        MemoryAttribute(
            name="proto_consecutive_failures",
            type=int,
            default_or_value=0,
            description="consecutive failure count for proto experiment",
        ),
        MemoryAttribute(
            name="proto_stage_start_helplessness",
            type=float,
            default_or_value=35.0,
            description="helplessness value captured at the start of a stage",
        ),
        MemoryAttribute(
            name="proto_active_stage_key",
            type=str,
            default_or_value="",
            description="last active proto stage marker",
        ),
        MemoryAttribute(
            name="proto_stage_daily_reflection_count",
            type=int,
            default_or_value=0,
            description="count of daily reflections generated in current stage",
        ),
        MemoryAttribute(
            name="proto_last_housekeeping_day",
            type=int,
            default_or_value=-1,
            description="latest day when proto daily housekeeping ran",
        ),
        MemoryAttribute(
            name="proto_bayesian_control_memory",
            type=dict,
            default_or_value={},
            description="Bayesian-inspired controllability audit memory",
        ),
        MemoryAttribute(
            name="task_domain_memory",
            type=dict,
            default_or_value={},
            description="task-specific experience memory",
        ),
        MemoryAttribute(
            name="help_effect_memory",
            type=dict,
            default_or_value={},
            description="help effectiveness memory",
        ),
        MemoryAttribute(
            name="recent_episode_buffer",
            type=list,
            default_or_value=[],
            description="recent task episode buffer",
        ),
        MemoryAttribute(
            name="rationale_memory",
            type=list,
            default_or_value=[],
            description="short rationale memory",
        ),
        MemoryAttribute(
            name="digital_emotion_state",
            type=dict,
            default_or_value={},
            description="bounded digital task emotion state",
        ),
        MemoryAttribute(
            name="proto_daily_reflection",
            type=dict,
            default_or_value={},
            description="latest daily reflection snapshot",
        ),
        MemoryAttribute(
            name="proto_daily_reflection_history",
            type=list,
            default_or_value=[],
            description="history of daily reflections",
        ),
        MemoryAttribute(
            name="proto_last_reflection_day",
            type=int,
            default_or_value=-1,
            description="latest day already processed for daily reflection",
        ),
        MemoryAttribute(
            name="proto_task_appraisal",
            type=dict,
            default_or_value={},
            description="latest bounded task appraisal snapshot",
        ),
        MemoryAttribute(
            name="proto_strategy_deliberation",
            type=dict,
            default_or_value={},
            description="latest bounded strategy deliberation snapshot",
        ),
        MemoryAttribute(
            name="proto_event_attribution",
            type=dict,
            default_or_value={},
            description="latest event-level attribution snapshot",
        ),
        MemoryAttribute(
            name="proto_stage_interview",
            type=dict,
            default_or_value={},
            description="latest structured stage interview snapshot",
        ),
        MemoryAttribute(
            name="proto_stage_interview_history",
            type=list,
            default_or_value=[],
            description="history of structured stage interviews",
        ),
        MemoryAttribute(
            name="proto_final_interview",
            type=dict,
            default_or_value={},
            description="latest structured final interview snapshot",
        ),
    ]


def derive_initial_proto_scores(
    *,
    digital_experience: float,
    vision_limit: float,
    past_fraud_experience: float,
) -> dict[str, float]:
    digital_experience = _clamp_ratio(digital_experience)
    vision_limit = _clamp_ratio(vision_limit)
    past_fraud_experience = _clamp_ratio(past_fraud_experience)
    helplessness = _clamp(
        20.0 + (1.0 - digital_experience) * 25.0 + past_fraud_experience * 15.0
    )
    trust = _clamp(
        70.0 + digital_experience * 10.0 - past_fraud_experience * 25.0
    )
    avoidance = _clamp(
        20.0 + (1.0 - digital_experience) * 20.0 + vision_limit * 15.0
    )
    return {
        "digital_experience": digital_experience,
        "vision_limit": vision_limit,
        "past_fraud_experience": past_fraud_experience,
        "helplessness_score": helplessness,
        "trust_in_apps": trust,
        "avoidance_tendency": avoidance,
    }


def build_initial_proto_status(
    *,
    digital_experience: float,
    vision_limit: float,
    past_fraud_experience: float,
) -> dict[str, Any]:
    scores = derive_initial_proto_scores(
        digital_experience=digital_experience,
        vision_limit=vision_limit,
        past_fraud_experience=past_fraud_experience,
    )
    helplessness = float(scores["helplessness_score"])
    avoidance = float(scores["avoidance_tendency"])
    trust = float(scores["trust_in_apps"])
    digital_emotion_state = build_initial_digital_emotion_state(
        digital_experience=float(scores["digital_experience"]),
        vision_limit=float(scores["vision_limit"]),
        past_fraud_experience=float(scores["past_fraud_experience"]),
    )
    return {
        "digital_experience": float(scores["digital_experience"]),
        "vision_limit": float(scores["vision_limit"]),
        "past_fraud_experience": float(scores["past_fraud_experience"]),
        "helplessness_score": helplessness,
        "trust_in_apps": trust,
        "avoidance_tendency": avoidance,
        "survey_helplessness_index": helplessness,
        "survey_withdrawal_index": avoidance,
        "survey_self_efficacy_index": _clamp(
            float(digital_emotion_state["confidence"]) * 10.0,
            0.0,
            100.0,
        ),
        "survey_support_index": 50.0,
        "survey_usefulness_index": 50.0,
        "survey_anxiety_index": _clamp(
            float(digital_emotion_state["anxiety"]) * 10.0,
            0.0,
            100.0,
        ),
        "tech_acceptance_score": 0.0,
        "helpless_control_loss": helplessness,
        "helpless_expect_failure": helplessness,
        "helpless_effort_futile": helplessness,
        "helpless_low_self_efficacy": helplessness,
        "behavior_delay_online": avoidance,
        "behavior_proxy_reliance": avoidance,
        "behavior_offline_switch": avoidance,
        "last_survey_day": -1,
        "last_survey_t": 0.0,
        "negative_event_count": 0,
        "intercept_count": 0,
        "help_request_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "cumulative_negative_event_count": 0,
        "cumulative_intercept_count": 0,
        "cumulative_help_request_count": 0,
        "cumulative_success_count": 0,
        "cumulative_failure_count": 0,
        "event_log": [],
        "friction_step_signal": {},
        "mobility_nudge_pending": 0,
        "mobility_nudge_sent_day": -1,
        "mobility_nudge_sent_t": 0.0,
        "mobility_nudge_baseline_trips": 0,
        "mobility_nudge_baseline_distance": 0.0,
        "mobility_nudge_baseline_time": 0.0,
        "digital_todo_pending": 0,
        "digital_todo_active_task_id": "",
        "digital_todo_active_day": -1,
        "digital_todo_active_t": 0.0,
        "digital_task_hint": "",
        "digital_task_hint_need": "",
        "digital_task_hint_pending": 0,
        "proto_assigned_task_json": "",
        "proto_stage_attempt_rows_json": "[]",
        "proto_consecutive_failures": 0,
        "proto_stage_start_helplessness": helplessness,
        "proto_active_stage_key": "",
        "proto_stage_daily_reflection_count": 0,
        "proto_last_housekeeping_day": -1,
        "proto_bayesian_control_memory": build_initial_bayesian_control_memory(),
        "task_domain_memory": build_initial_task_domain_memory(
            digital_experience=float(scores["digital_experience"]),
            vision_limit=float(scores["vision_limit"]),
            past_fraud_experience=float(scores["past_fraud_experience"]),
        ),
        "help_effect_memory": build_initial_help_effect_memory(),
        "recent_episode_buffer": build_initial_recent_episode_buffer(),
        "rationale_memory": build_initial_rationale_memory(),
        "digital_emotion_state": digital_emotion_state,
        "proto_daily_reflection": {},
        "proto_daily_reflection_history": [],
        "proto_last_reflection_day": -1,
        "proto_task_appraisal": {},
        "proto_strategy_deliberation": {},
        "proto_event_attribution": {},
        "proto_stage_interview": {},
        "proto_stage_interview_history": [],
        "proto_final_interview": {},
    }


def build_survey_measurement_updates(
    *,
    values: dict[str, Any],
    derived: dict[str, Any],
    day: int,
    t: float,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "last_survey_day": int(day),
        "last_survey_t": float(t),
    }
    if "tech_acceptance" in values:
        updates["tech_acceptance_score"] = _clamp(
            float(values["tech_acceptance"]),
            0.0,
            100.0,
        )
    if "survey_helplessness_index" in derived:
        updates["survey_helplessness_index"] = _clamp(
            float(derived["survey_helplessness_index"]),
            0.0,
            100.0,
        )
    if "survey_withdrawal_index" in derived:
        updates["survey_withdrawal_index"] = _clamp(
            float(derived["survey_withdrawal_index"]),
            0.0,
            100.0,
        )
    for field in (
        "survey_self_efficacy_index",
        "survey_support_index",
        "survey_usefulness_index",
        "survey_anxiety_index",
    ):
        if field in derived:
            updates[field] = _clamp(float(derived[field]), 0.0, 100.0)
    for field in (
        "helpless_control_loss",
        "helpless_expect_failure",
        "helpless_effort_futile",
        "helpless_low_self_efficacy",
        "behavior_delay_online",
        "behavior_proxy_reliance",
        "behavior_offline_switch",
    ):
        if field in values:
            updates[field] = _clamp(float(values[field]), 0.0, 100.0)
    return copy.deepcopy(updates)
