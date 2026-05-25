from __future__ import annotations

import copy
import json
from typing import Any, Callable

from config_runtime import load_runtime_config

from .models import (
    AttemptOutcome,
    AttemptStrategy,
    DailyReflection,
    DigitalEmotionState,
    DigitalTask,
    EventAppraisalResult,
    FinalInterviewResult,
    StageInterviewResult,
    StrategyDeliberationResult,
    TaskAppraisalResult,
)
from .profile_buckets import age_bucket, persona_bucket

_TASK_FAMILIES = {
    "navigation_service_location",
    "account_login_verification",
    "information_search_judgment",
    "profile_form_upload",
    "service_application_submission",
    "payment_risk_confirmation",
}
_REFLECTION_SIGNALS = {"success", "struggle", "avoidance", "mixed"}
_EVENT_APPRAISAL_KEYS = {
    "anxiety",
    "frustration",
    "relief",
    "confidence",
    "judge_confidence",
    "reason",
}
_DAILY_REFLECTION_KEYS = {
    "dominant_task_family",
    "help_effective",
    "mastery_signal",
    "text",
    "judge_confidence",
}
_TASK_APPRAISAL_KEYS = {
    "perceived_task_difficulty",
    "perceived_task_risk",
    "felt_control",
    "expected_help_effectiveness",
    "task_value",
    "judge_confidence",
    "reason",
}
_STRATEGY_DELIBERATION_KEYS = {
    "attempt_self_score",
    "seek_help_score",
    "avoid_score",
    "dominant_strategy",
    "judge_confidence",
    "reason",
}
_TRAJECTORY_APPRAISAL_KEYS = {
    "planned_steps",
    "selected_friction_points",
    "friction_encounter_likelihood",
    "cognitive_load",
    "help_need",
    "trajectory_outcome_tendency",
    "trajectory_confidence",
    "reason",
    "does_not_sample_final_outcome",
    "does_not_update_psychology",
}
_STAGE_INTERVIEW_KEYS = {
    "main_difficulty_source",
    "support_comment",
    "future_intention",
    "short_quote",
    "judge_confidence",
}
_FINAL_INTERVIEW_KEYS = {
    "overall_trajectory",
    "main_barrier",
    "support_takeaway",
    "future_orientation",
    "short_quote",
    "judge_confidence",
}
_INTERVIEW_DIFFICULTY_SOURCES = {
    "verification_friction",
    "form_complexity",
    "risk_concern",
    "info_overload",
    "low_control",
    "mixed",
}
_INTERVIEW_SUPPORT_COMMENTS = {"helpful", "limited", "ineffective", "not_used"}
_INTERVIEW_FUTURE_INTENTIONS = {"try_self", "seek_help", "avoid", "mixed"}
_FINAL_TRAJECTORIES = {"improved", "worsened", "mixed", "stable"}
_FINAL_SUPPORT_TAKEAWAYS = {"helpful", "limited", "ineffective", "not_needed"}
_NEUTRAL_EMOTION = {
    "anxiety": 4.0,
    "frustration": 3.0,
    "relief": 2.0,
    "confidence": 5.0,
}
_NEUTRAL_TASK_APPRAISAL = {
    "perceived_task_difficulty": 50.0,
    "perceived_task_risk": 50.0,
    "felt_control": 50.0,
    "expected_help_effectiveness": 50.0,
    "task_value": 50.0,
}
_BLEND_RATIO = 0.70
_EVENT_APPRAISAL_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_TASK_APPRAISAL_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_STRATEGY_DELIBERATION_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_RULE_TEXT_MIXED = "昨天有顺也有卡，我还在慢慢摸索"
_TASK_APPRAISAL_PROMPT_VERSION = "v3_profile_memory_packet_20260406"
_STRATEGY_DELIBERATION_PROMPT_VERSION = "v2_profile_memory_strategy_context_20260518"
_TRAJECTORY_PROMPT_VERSION = "trajectory_v1"
_TRAJECTORY_TAXONOMY_VERSION = "friction_taxonomy_v1"
_CROSS_CUTTING_FRICTION_POINTS = {
    "visual_accessibility_load",
    "small_touch_target",
    "terminology_jargon",
    "navigation_depth",
    "unclear_feedback",
    "error_recovery_uncertainty",
    "session_timeout_pressure",
    "permission_or_privacy_concern",
    "security_or_scam_concern",
    "multi_step_memory_load",
    "authentication_handoff",
    "support_unavailable_or_delayed",
}
_TASK_FRICTION_POINTS = {
    "navigation_service_location": {
        "location_permission_confusion",
        "address_disambiguation",
        "route_choice_overload",
        "map_visual_density",
        "service_filter_confusion",
        "location_accuracy_uncertainty",
    },
    "account_login_verification": {
        "password_memory_failure",
        "otp_delay_or_expiry",
        "captcha_visual_difficulty",
        "account_lockout_anxiety",
        "multi_factor_switching",
        "device_trust_prompt_confusion",
    },
    "information_search_judgment": {
        "query_formulation_difficulty",
        "information_overload",
        "source_credibility_uncertainty",
        "ad_or_sponsored_result_confusion",
        "medical_or_service_jargon",
        "contradictory_information",
    },
    "profile_form_upload": {
        "form_field_ambiguity",
        "document_photo_quality_issue",
        "file_format_or_size_error",
        "upload_progress_uncertainty",
        "privacy_concern_about_documents",
        "required_field_discovery",
    },
    "service_application_submission": {
        "eligibility_rule_confusion",
        "multi_step_form_burden",
        "required_document_uncertainty",
        "submission_confirmation_uncertainty",
        "opaque_error_message",
        "deadline_or_timeout_pressure",
    },
    "payment_risk_confirmation": {
        "risk_popup_anxiety",
        "scam_security_concern",
        "amount_or_fee_confusion",
        "confirm_cancel_button_ambiguity",
        "payment_failure_recovery_uncertainty",
        "authentication_or_bank_handoff",
    },
}
_TRAJECTORY_BANNED_REASON_PHRASES = {
    "because the user is old",
    "because the user is female",
    "because she is female",
    "because he is male",
    "older adults cannot",
    "elderly people are confused",
    "old people are confused",
    "becomes helpless",
    "helplessness_delta",
    "posterior",
    "c_family",
    "c_global",
}


def clear_llm_psychology_caches() -> None:
    _EVENT_APPRAISAL_CACHE.clear()
    _TASK_APPRAISAL_CACHE.clear()
    _STRATEGY_DELIBERATION_CACHE.clear()


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _difficulty_bucket(value: float) -> str:
    if value < 0.35:
        return "low"
    if value < 0.70:
        return "mid"
    return "high"


def _helplessness_bucket(value: float) -> str:
    if value < 40:
        return "lt40"
    if value < 70:
        return "40_69"
    if value < 85:
        return "70_84"
    return "ge85"


def _emotion_bucket(value: float) -> str:
    if value < 3:
        return "low"
    if value < 6:
        return "mid"
    return "high"


def _failure_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    return "2plus"


def _help_rate_bucket(value: float) -> str:
    if value < 0.35:
        return "weak"
    if value > 0.65:
        return "strong"
    return "mid"


def _self_efficacy_bucket(value: float) -> str:
    if value < 35:
        return "low"
    if value < 65:
        return "mid"
    return "high"


def _profile_bucket(value: float) -> str:
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "mid"
    return "high"


def _world_level_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    return "2plus"


def _education_bucket(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    if any(token in text for token in ("小学", "初中")):
        return "low"
    if any(token in text for token in ("高中", "中专", "专科")):
        return "mid"
    if any(token in text for token in ("本科", "研究生", "硕士", "博士")):
        return "high"
    return "mid"


def _appraisal_bucket(value: Any) -> str:
    numeric = _safe_float(value, 50.0)
    if numeric < 35.0:
        return "low"
    if numeric < 65.0:
        return "mid"
    return "high"


def _same_task_history_bucket(task_relevant_memory: Any) -> str:
    packet = task_relevant_memory if isinstance(task_relevant_memory, dict) else {}
    attempt_count = _safe_int(packet.get("same_task_attempt_count", 0), 0)
    failure_count = _safe_int(packet.get("same_task_failure_count", 0), 0)
    failure_streak = _safe_int(packet.get("same_task_failure_streak", 0), 0)
    recent_same_task_failure_count = _safe_int(
        packet.get("recent_same_task_failure_count", 0),
        0,
    )
    controllable_success_memory = _safe_float(
        packet.get("same_task_controllable_success_memory", 0.0),
        0.0,
    )
    if controllable_success_memory > 0.15 and failure_count <= 1:
        return "some_mastery"
    if failure_streak >= 2 or failure_count >= 2 or recent_same_task_failure_count >= 2:
        return "repeated_failure"
    if attempt_count > 0:
        return "some_history"
    return "fresh"


def _recent_outcome_pattern_bucket(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "no_history"
    outcomes = [str(item or "").strip() for item in value if str(item or "").strip()]
    if not outcomes:
        return "no_history"
    if any(outcome == "avoid_without_attempt" for outcome in outcomes):
        return "avoid_heavy"
    failure_like = {
        "failure_after_attempt",
        "failure_even_with_help",
        "abandon_midway",
    }
    if all(outcome in failure_like for outcome in outcomes):
        return "repeated_failure"
    if any(outcome == "success_self" for outcome in outcomes):
        return "recent_mastery"
    if any(outcome == "success_with_help" for outcome in outcomes):
        return "helped_success"
    return "mixed"


def _truncate_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[: max(0, int(limit))]


def _strategy_profile_context(profile_summary: Any) -> dict[str, Any]:
    if not isinstance(profile_summary, dict):
        return {}
    context: dict[str, Any] = {}
    for key, value in profile_summary.items():
        if isinstance(value, str):
            context[str(key)] = _truncate_text(value, 240)
        elif isinstance(value, (int, float, bool)) or value is None:
            context[str(key)] = value
    return context


def _strategy_task_memory_context(task_relevant_memory: Any) -> dict[str, Any]:
    if not isinstance(task_relevant_memory, dict):
        return {}
    context: dict[str, Any] = {}
    for key, value in task_relevant_memory.items():
        if key == "recent_same_task_events_tail":
            continue
        if key == "same_task_attribution_summary":
            context[key] = _truncate_text(value, 300)
        elif isinstance(value, str):
            context[str(key)] = _truncate_text(value, 240)
        elif isinstance(value, (int, float, bool)) or value is None:
            context[str(key)] = value
        elif isinstance(value, list):
            compact_items = []
            for item in value[:8]:
                if isinstance(item, (str, int, float, bool)) or item is None:
                    compact_items.append(item if not isinstance(item, str) else _truncate_text(item, 120))
            context[str(key)] = compact_items
    return context


def _strategy_recent_context(recent_episode_summary: Any) -> dict[str, Any]:
    recent = recent_episode_summary if isinstance(recent_episode_summary, dict) else {}
    return {
        "recent_negative_feedback_ratio": round(
            _safe_float(recent.get("recent_negative_feedback_ratio", 0.0)),
            4,
        ),
        "recent_avoid_ratio": round(_safe_float(recent.get("recent_avoid_ratio", 0.0)), 4),
        "recent_help_seek_ratio": round(
            _safe_float(recent.get("recent_help_seek_ratio", 0.0)),
            4,
        ),
        "recent_same_task_failure_count": _safe_int(
            recent.get("recent_same_task_failure_count"),
            0,
        ),
        "recent_failure_pressure": round(
            _safe_float(recent.get("recent_failure_pressure", 0.0)),
            4,
        ),
    }


def _strategy_retrieved_memory_context(retrieved_episodic_memory: Any) -> dict[str, Any]:
    retrieved = (
        retrieved_episodic_memory
        if isinstance(retrieved_episodic_memory, dict)
        else {}
    )
    return {
        "condition": str(retrieved.get("condition", "structured-only")),
        "status": str(retrieved.get("status", "disabled")),
        "count": _safe_int(retrieved.get("count", 0), 0),
        "hash": str(retrieved.get("hash", "")),
        "text": _truncate_text(retrieved.get("text", "Nothing"), 900) or "Nothing",
    }


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


async def _query_json_payload(
    *,
    llm: Any,
    system_prompt: str,
    user_payload: dict[str, Any],
    output_keys: set[str],
    repair_schema_text: str,
    sanitize_fn: Callable[[Any], tuple[dict[str, Any] | None, str]],
    timeout: int,
    retries: int,
    max_tokens: int = 260,
    json_attempts: int = 1,
    attempt_metadata_key: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    if llm is None:
        return None, "request_error"

    dialog = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Return one JSON object only.\n"
                + json.dumps(user_payload, ensure_ascii=False)
            ),
        },
    ]

    attempts = max(1, int(json_attempts))
    last_error = "parse_failed"
    for attempt_index in range(attempts):
        first_error = "parse_failed"
        try:
            raw = await llm.atext_request(
                dialog=dialog,
                temperature=0.1,
                timeout=timeout,
                retries=retries,
                max_tokens=max_tokens,
            )
        except Exception:
            last_error = "request_error"
            continue

        parsed = _extract_json_object(str(raw))
        if parsed is not None:
            sanitized, status = sanitize_fn(parsed)
            if sanitized is not None:
                if attempt_metadata_key:
                    sanitized[attempt_metadata_key] = attempt_index + 1
                return sanitized, "ok"
            first_error = status
            last_error = status
        else:
            last_error = "parse_failed"

        repair_dialog = [
            {
                "role": "system",
                "content": (
                    "You are a strict JSON reformatter. Return exactly one valid JSON object "
                    f"with keys: {', '.join(sorted(output_keys))}."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Rules:\n"
                    + repair_schema_text
                    + "\nDo not output markdown or extra text.\nOriginal context:\n"
                    + json.dumps(user_payload, ensure_ascii=False)
                    + "\nRaw model output:\n"
                    + str(raw)[:1400]
                ),
            },
        ]
        try:
            repaired = await llm.atext_request(
                dialog=repair_dialog,
                temperature=0.0,
                timeout=timeout,
                retries=1,
                max_tokens=max(220, int(max_tokens)),
            )
        except Exception:
            last_error = "request_error"
            continue

        repaired_payload = _extract_json_object(str(repaired))
        if repaired_payload is None:
            last_error = (
                first_error if first_error == "invalid_schema" else "parse_failed"
            )
            continue
        sanitized, status = sanitize_fn(repaired_payload)
        if sanitized is None:
            last_error = status
            continue
        if attempt_metadata_key:
            sanitized[attempt_metadata_key] = attempt_index + 1
        return sanitized, "ok_repaired"
    return None, last_error


def _fallback_source_for_status(status: str) -> str:
    if status == "invalid_schema":
        return "rule_fallback_invalid_schema"
    if status == "low_confidence":
        return "rule_fallback_low_confidence"
    if status == "parse_failed":
        return "rule_fallback_parse_failed"
    return "rule_fallback_request_error"


def build_initial_digital_emotion_state(
    *,
    digital_experience: float,
    vision_limit: float,
    past_fraud_experience: float,
) -> dict[str, Any]:
    return {
        "anxiety": _clamp(
            4.0
            + 2.0 * float(vision_limit)
            + 1.5 * float(past_fraud_experience)
            - 2.5 * float(digital_experience),
            1.0,
            8.0,
        ),
        "frustration": 3.0,
        "relief": 2.0,
        "confidence": _clamp(
            5.0
            + 3.0 * float(digital_experience)
            - 1.5 * float(vision_limit)
            - 1.5 * float(past_fraud_experience),
            2.0,
            8.0,
        ),
        "last_updated_day": -1,
    }


def normalize_digital_emotion_state(raw_value: Any) -> DigitalEmotionState:
    if not isinstance(raw_value, dict):
        return DigitalEmotionState()
    state = DigitalEmotionState.from_dict(raw_value)
    state.anxiety = _clamp(state.anxiety, 0.0, 10.0)
    state.frustration = _clamp(state.frustration, 0.0, 10.0)
    state.relief = _clamp(state.relief, 0.0, 10.0)
    state.confidence = _clamp(state.confidence, 0.0, 10.0)
    return state


def prepare_digital_emotion_state_for_day(
    raw_value: Any,
    *,
    target_day: int,
) -> DigitalEmotionState:
    state = normalize_digital_emotion_state(raw_value)
    decayed = _decay_emotion_state(state=state, target_day=int(target_day))
    if state.last_updated_day >= 0 and int(target_day) > state.last_updated_day:
        decayed.last_updated_day = int(target_day)
    return decayed


def _decay_emotion_state(
    *,
    state: DigitalEmotionState,
    target_day: int,
) -> DigitalEmotionState:
    if state.last_updated_day >= 0 and target_day > state.last_updated_day:
        day_gap = target_day - state.last_updated_day
        decay = 0.95 ** day_gap
        return DigitalEmotionState(
            anxiety=_clamp(
                _NEUTRAL_EMOTION["anxiety"]
                + (state.anxiety - _NEUTRAL_EMOTION["anxiety"]) * decay,
                0.0,
                10.0,
            ),
            frustration=_clamp(
                _NEUTRAL_EMOTION["frustration"]
                + (state.frustration - _NEUTRAL_EMOTION["frustration"]) * decay,
                0.0,
                10.0,
            ),
            relief=_clamp(
                _NEUTRAL_EMOTION["relief"]
                + (state.relief - _NEUTRAL_EMOTION["relief"]) * decay,
                0.0,
                10.0,
            ),
            confidence=_clamp(
                _NEUTRAL_EMOTION["confidence"]
                + (state.confidence - _NEUTRAL_EMOTION["confidence"]) * decay,
                0.0,
                10.0,
            ),
            last_updated_day=state.last_updated_day,
        )
    return DigitalEmotionState(
        anxiety=state.anxiety,
        frustration=state.frustration,
        relief=state.relief,
        confidence=state.confidence,
        last_updated_day=state.last_updated_day,
    )


def _emotion_dict(state: DigitalEmotionState) -> dict[str, float]:
    return {
        "anxiety": round(float(state.anxiety), 4),
        "frustration": round(float(state.frustration), 4),
        "relief": round(float(state.relief), 4),
        "confidence": round(float(state.confidence), 4),
    }


def _normalize_strategy_score_weights(
    attempt_self_score: float,
    seek_help_score: float,
    avoid_score: float,
) -> dict[str, float]:
    raw = {
        "attempt_self": max(0.0, float(attempt_self_score)),
        "seek_help_then_attempt": max(0.0, float(seek_help_score)),
        "avoid": max(0.0, float(avoid_score)),
    }
    total = sum(raw.values())
    if total <= 1e-9:
        return {
            "attempt_self": 1.0 / 3.0,
            "seek_help_then_attempt": 1.0 / 3.0,
            "avoid": 1.0 / 3.0,
        }
    return {key: value / total for key, value in raw.items()}


def _blend_strategy_weights(
    *,
    rule_weights: dict[str, float],
    llm_weights: dict[str, float],
    blend_ratio: float = _BLEND_RATIO,
) -> dict[str, float]:
    weights: dict[str, float] = {}
    for key in ("attempt_self", "seek_help_then_attempt", "avoid"):
        weights[key] = (
            (1.0 - float(blend_ratio)) * float(rule_weights.get(key, 0.0))
            + float(blend_ratio) * float(llm_weights.get(key, 0.0))
        )
    total = sum(weights.values()) or 1.0
    return {key: float(value) / total for key, value in weights.items()}


def _dominant_strategy_from_weights(weights: dict[str, float]) -> str:
    if not weights:
        return ""
    return max(
        (
            ("attempt_self", float(weights.get("attempt_self", 0.0))),
            (
                "seek_help_then_attempt",
                float(weights.get("seek_help_then_attempt", 0.0)),
            ),
            ("avoid", float(weights.get("avoid", 0.0))),
        ),
        key=lambda item: (item[1], item[0]),
    )[0]


def _rule_emotion_deltas(outcome_type: str) -> dict[str, float]:
    mapping = {
        "success_self": {
            "anxiety": -1.0,
            "frustration": -0.5,
            "relief": 2.0,
            "confidence": 2.0,
        },
        "success_with_help": {
            "anxiety": -0.5,
            "frustration": -0.5,
            "relief": 1.5,
            "confidence": 1.0,
        },
        "failure_after_attempt": {
            "anxiety": 1.5,
            "frustration": 1.5,
            "relief": -0.5,
            "confidence": -1.5,
        },
        "failure_even_with_help": {
            "anxiety": 2.0,
            "frustration": 2.0,
            "relief": -0.5,
            "confidence": -2.0,
        },
        "abandon_midway": {
            "anxiety": 1.0,
            "frustration": 1.0,
            "relief": -0.5,
            "confidence": -1.0,
        },
        "avoid_without_attempt": {
            "anxiety": 0.5,
            "frustration": 0.5,
            "relief": 0.0,
            "confidence": -0.5,
        },
    }
    return copy.deepcopy(mapping.get(outcome_type, {}))


def _apply_rule_emotion_update(
    *,
    state: DigitalEmotionState,
    outcome_type: str,
    day: int,
) -> DigitalEmotionState:
    deltas = _rule_emotion_deltas(outcome_type)
    return DigitalEmotionState(
        anxiety=_clamp(state.anxiety + deltas.get("anxiety", 0.0), 0.0, 10.0),
        frustration=_clamp(
            state.frustration + deltas.get("frustration", 0.0),
            0.0,
            10.0,
        ),
        relief=_clamp(state.relief + deltas.get("relief", 0.0), 0.0, 10.0),
        confidence=_clamp(
            state.confidence + deltas.get("confidence", 0.0),
            0.0,
            10.0,
        ),
        last_updated_day=int(day),
    )


def _sanitize_event_appraisal(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _EVENT_APPRAISAL_KEYS:
        return None, "invalid_schema"

    result: dict[str, Any] = {}
    for field in ("anxiety", "frustration", "relief", "confidence"):
        raw_value = payload.get(field)
        if isinstance(raw_value, bool):
            return None, "invalid_schema"
        try:
            result[field] = _clamp(float(raw_value), 0.0, 10.0)
        except (TypeError, ValueError):
            return None, "invalid_schema"

    confidence = payload.get("judge_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        result["judge_confidence"] = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"

    reason = payload.get("reason")
    if not isinstance(reason, str):
        return None, "invalid_schema"
    result["reason"] = reason.strip()[:120]
    return result, "ok"


def _sanitize_daily_reflection(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _DAILY_REFLECTION_KEYS:
        return None, "invalid_schema"

    help_effective = _as_bool(payload.get("help_effective"))
    if help_effective is None:
        return None, "invalid_schema"
    mastery_signal = str(payload.get("mastery_signal", "")).strip().lower()
    if mastery_signal not in _REFLECTION_SIGNALS:
        return None, "invalid_schema"
    text = str(payload.get("text", "")).strip()
    if not text:
        return None, "invalid_schema"
    confidence = payload.get("judge_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        confidence_value = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"
    dominant_task_family = str(payload.get("dominant_task_family", "")).strip()
    return (
        {
            "dominant_task_family": dominant_task_family[:40],
            "help_effective": help_effective,
            "mastery_signal": mastery_signal,
            "text": text[:40],
            "judge_confidence": confidence_value,
        },
        "ok",
    )


def _sanitize_task_appraisal(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _TASK_APPRAISAL_KEYS:
        return None, "invalid_schema"

    result: dict[str, Any] = {}
    for field in (
        "perceived_task_difficulty",
        "perceived_task_risk",
        "felt_control",
        "expected_help_effectiveness",
        "task_value",
    ):
        raw_value = payload.get(field)
        if isinstance(raw_value, bool):
            return None, "invalid_schema"
        try:
            result[field] = _clamp(float(raw_value), 0.0, 100.0)
        except (TypeError, ValueError):
            return None, "invalid_schema"

    confidence = payload.get("judge_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        result["judge_confidence"] = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"

    reason = payload.get("reason")
    if not isinstance(reason, str):
        return None, "invalid_schema"
    result["reason"] = reason.strip()[:120]
    return result, "ok"


def _sanitize_strategy_deliberation(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _STRATEGY_DELIBERATION_KEYS:
        return None, "invalid_schema"

    result: dict[str, Any] = {}
    score_items = {
        "attempt_self_score": payload.get("attempt_self_score"),
        "seek_help_score": payload.get("seek_help_score"),
        "avoid_score": payload.get("avoid_score"),
    }
    for key, raw_value in score_items.items():
        if isinstance(raw_value, bool):
            return None, "invalid_schema"
        try:
            result[key] = _clamp(float(raw_value), 0.0, 1.0)
        except (TypeError, ValueError):
            return None, "invalid_schema"

    dominant_strategy = str(payload.get("dominant_strategy", "")).strip()
    if dominant_strategy not in {
        "attempt_self",
        "seek_help_then_attempt",
        "avoid",
    }:
        return None, "invalid_schema"
    dominant_by_argmax = max(
        (
            ("attempt_self", float(result["attempt_self_score"])),
            ("seek_help_then_attempt", float(result["seek_help_score"])),
            ("avoid", float(result["avoid_score"])),
        ),
        key=lambda item: (item[1], item[0]),
    )[0]
    if dominant_strategy != dominant_by_argmax:
        return None, "invalid_schema"
    result["dominant_strategy"] = dominant_strategy

    confidence = payload.get("judge_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        result["judge_confidence"] = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"

    reason = payload.get("reason")
    if not isinstance(reason, str):
        return None, "invalid_schema"
    result["reason"] = reason.strip()[:120]
    return result, "ok"


def _trajectory_allowed_outcomes(strategy_type: str) -> tuple[str, ...]:
    if strategy_type == "attempt_self":
        return ("success_self", "failure_after_attempt", "abandon_midway")
    if strategy_type == "seek_help_then_attempt":
        return (
            "success_with_help",
            "failure_even_with_help",
            "failure_after_attempt",
            "abandon_midway",
        )
    return ()


def _trajectory_allowed_friction_points(task_family: str) -> set[str]:
    return set(_CROSS_CUTTING_FRICTION_POINTS) | set(
        _TASK_FRICTION_POINTS.get(task_family, set())
    )


def _contains_banned_trajectory_phrase(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(phrase in text for phrase in _TRAJECTORY_BANNED_REASON_PHRASES)


def _sanitize_trajectory_appraisal_for_context(
    payload: Any,
    *,
    task_family: str,
    strategy_type: str,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _TRAJECTORY_APPRAISAL_KEYS:
        return None, "invalid_schema"
    if strategy_type == "avoid":
        return None, "invalid_strategy"

    planned_steps = payload.get("planned_steps")
    if not isinstance(planned_steps, list) or not (2 <= len(planned_steps) <= 6):
        return None, "invalid_schema"
    sanitized_steps: list[dict[str, Any]] = []
    seen_step_ids: set[int] = set()
    for item in planned_steps:
        if not isinstance(item, dict) or set(item.keys()) != {"step_id", "action"}:
            return None, "invalid_schema"
        step_id = _safe_int(item.get("step_id"), -1)
        action = str(item.get("action", "")).strip()
        if step_id <= 0 or step_id in seen_step_ids or not action:
            return None, "invalid_schema"
        if len(action) > 80 or _contains_banned_trajectory_phrase(action):
            return None, "banned_phrase"
        seen_step_ids.add(step_id)
        sanitized_steps.append({"step_id": step_id, "action": action[:80]})

    allowed_points = _trajectory_allowed_friction_points(task_family)
    selected_points = payload.get("selected_friction_points")
    if not isinstance(selected_points, list) or len(selected_points) > 3:
        return None, "invalid_schema"
    sanitized_points: list[dict[str, Any]] = []
    for item in selected_points:
        if not isinstance(item, dict) or set(item.keys()) != {
            "point",
            "severity",
            "step_id",
        }:
            return None, "invalid_schema"
        point = str(item.get("point", "")).strip()
        if point not in allowed_points:
            return None, "taxonomy_outside"
        step_id = _safe_int(item.get("step_id"), -1)
        if step_id not in seen_step_ids:
            return None, "invalid_schema"
        try:
            severity = _clamp(float(item.get("severity")), 0.0, 1.0)
        except (TypeError, ValueError):
            return None, "invalid_schema"
        sanitized_points.append(
            {
                "point": point,
                "severity": round(float(severity), 4),
                "step_id": int(step_id),
            }
        )

    result: dict[str, Any] = {
        "planned_steps": sanitized_steps,
        "selected_friction_points": sanitized_points,
    }
    for field in ("friction_encounter_likelihood", "cognitive_load", "help_need"):
        raw_value = payload.get(field)
        if isinstance(raw_value, bool):
            return None, "invalid_schema"
        try:
            result[field] = round(_clamp(float(raw_value), 0.0, 1.0), 4)
        except (TypeError, ValueError):
            return None, "invalid_schema"

    allowed_outcomes = _trajectory_allowed_outcomes(strategy_type)
    tendency = payload.get("trajectory_outcome_tendency")
    if not isinstance(tendency, dict) or set(tendency.keys()) != set(allowed_outcomes):
        return None, "invalid_outcome_keys"
    sanitized_tendency: dict[str, float] = {}
    for key in allowed_outcomes:
        raw_value = tendency.get(key)
        if isinstance(raw_value, bool):
            return None, "invalid_schema"
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None, "invalid_schema"
        if value < -0.0001 or value > 1.0001:
            return None, "invalid_schema"
        sanitized_tendency[key] = max(0.0, min(1.0, value))
    total = sum(sanitized_tendency.values())
    if abs(total - 1.0) > 0.02 or total <= 0:
        return None, "invalid_probability_sum"
    result["trajectory_outcome_tendency"] = {
        key: round(sanitized_tendency[key] / total, 6)
        for key in allowed_outcomes
    }

    confidence = payload.get("trajectory_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        result["trajectory_confidence"] = round(_clamp(float(confidence), 0.0, 1.0), 4)
    except (TypeError, ValueError):
        return None, "invalid_schema"

    reason = str(payload.get("reason", "")).strip()
    if not reason:
        return None, "invalid_schema"
    if len(reason) > 180 or _contains_banned_trajectory_phrase(reason):
        return None, "banned_phrase"
    result["reason"] = reason[:180]

    if _as_bool(payload.get("does_not_sample_final_outcome")) is not True:
        return None, "invalid_schema"
    if _as_bool(payload.get("does_not_update_psychology")) is not True:
        return None, "invalid_schema"
    result["does_not_sample_final_outcome"] = True
    result["does_not_update_psychology"] = True
    result["prompt_version"] = _TRAJECTORY_PROMPT_VERSION
    result["taxonomy_version"] = _TRAJECTORY_TAXONOMY_VERSION
    result["status"] = "ok"
    return result, "ok"


def _sanitize_trajectory_appraisal(payload: Any) -> tuple[dict[str, Any] | None, str]:
    context = payload if isinstance(payload, dict) else {}
    task_family = str(context.get("_task_family", "")).strip()
    strategy_type = str(context.get("_strategy_type", "")).strip()
    public_payload = {
        key: value
        for key, value in context.items()
        if not str(key).startswith("_")
    }
    return _sanitize_trajectory_appraisal_for_context(
        public_payload,
        task_family=task_family,
        strategy_type=strategy_type,
    )


def _sanitize_stage_interview(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _STAGE_INTERVIEW_KEYS:
        return None, "invalid_schema"

    main_difficulty_source = str(payload.get("main_difficulty_source", "")).strip()
    support_comment = str(payload.get("support_comment", "")).strip()
    future_intention = str(payload.get("future_intention", "")).strip()
    short_quote = str(payload.get("short_quote", "")).strip()
    if main_difficulty_source not in _INTERVIEW_DIFFICULTY_SOURCES:
        return None, "invalid_schema"
    if support_comment not in _INTERVIEW_SUPPORT_COMMENTS:
        return None, "invalid_schema"
    if future_intention not in _INTERVIEW_FUTURE_INTENTIONS:
        return None, "invalid_schema"
    if not short_quote:
        return None, "invalid_schema"
    confidence = payload.get("judge_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        confidence_value = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"
    return (
        {
            "main_difficulty_source": main_difficulty_source,
            "support_comment": support_comment,
            "future_intention": future_intention,
            "short_quote": short_quote[:120],
            "judge_confidence": confidence_value,
        },
        "ok",
    )


def _sanitize_final_interview(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _FINAL_INTERVIEW_KEYS:
        return None, "invalid_schema"

    overall_trajectory = str(payload.get("overall_trajectory", "")).strip()
    main_barrier = str(payload.get("main_barrier", "")).strip()
    support_takeaway = str(payload.get("support_takeaway", "")).strip()
    future_orientation = str(payload.get("future_orientation", "")).strip()
    short_quote = str(payload.get("short_quote", "")).strip()
    if overall_trajectory not in _FINAL_TRAJECTORIES:
        return None, "invalid_schema"
    if main_barrier not in _INTERVIEW_DIFFICULTY_SOURCES:
        return None, "invalid_schema"
    if support_takeaway not in _FINAL_SUPPORT_TAKEAWAYS:
        return None, "invalid_schema"
    if future_orientation not in _INTERVIEW_FUTURE_INTENTIONS:
        return None, "invalid_schema"
    if not short_quote:
        return None, "invalid_schema"
    confidence = payload.get("judge_confidence")
    if isinstance(confidence, bool):
        return None, "invalid_schema"
    try:
        confidence_value = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"
    return (
        {
            "overall_trajectory": overall_trajectory,
            "main_barrier": main_barrier,
            "support_takeaway": support_takeaway,
            "future_orientation": future_orientation,
            "short_quote": short_quote[:120],
            "judge_confidence": confidence_value,
        },
        "ok",
    )


def _build_event_appraisal_cache_key(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    helplessness_now: float,
    emotion_before: DigitalEmotionState,
    consecutive_failures_before: int,
    pre_event_task_appraisal: Any = None,
    task_relevant_memory_lite: Any = None,
) -> tuple[Any, ...]:
    appraisal = TaskAppraisalResult.from_dict(
        pre_event_task_appraisal if isinstance(pre_event_task_appraisal, dict) else None
    )
    task_memory = (
        task_relevant_memory_lite if isinstance(task_relevant_memory_lite, dict) else {}
    )
    return (
        str(task.task_family),
        str(task.friction_type),
        _difficulty_bucket(float(task.difficulty)),
        str(strategy.strategy_type),
        str(outcome.outcome_type),
        int(outcome.support_quality),
        _helplessness_bucket(float(helplessness_now)),
        _emotion_bucket(float(emotion_before.anxiety)),
        _emotion_bucket(float(emotion_before.confidence)),
        _failure_bucket(int(consecutive_failures_before)),
        _appraisal_bucket(float(appraisal.felt_control)),
        _appraisal_bucket(float(appraisal.perceived_task_risk)),
        _appraisal_bucket(float(appraisal.expected_help_effectiveness)),
        _failure_bucket(int(task_memory.get("same_task_failure_count", 0))),
        _profile_bucket(
            float(task_memory.get("same_task_controllable_success_memory", 0.0))
        ),
        _recent_outcome_pattern_bucket(
            task_memory.get("recent_same_task_outcomes_tail", [])
        ),
    )


def _build_task_appraisal_cache_key(
    *,
    task: DigitalTask,
    stage_key: str,
    world_context: Any,
    profile_summary: Any,
    helplessness_now: float,
    task_self_efficacy: float,
    help_success_rate_smoothed: float,
    recent_episode_summary: Any,
    digital_emotion_state: DigitalEmotionState,
    task_relevant_memory: Any = None,
    retrieved_episodic_memory: Any = None,
) -> tuple[Any, ...]:
    world = world_context if isinstance(world_context, dict) else {}
    profile = profile_summary if isinstance(profile_summary, dict) else {}
    recent = recent_episode_summary if isinstance(recent_episode_summary, dict) else {}
    task_memory = task_relevant_memory if isinstance(task_relevant_memory, dict) else {}
    retrieved = (
        retrieved_episodic_memory
        if isinstance(retrieved_episodic_memory, dict)
        else {}
    )
    return (
        _TASK_APPRAISAL_PROMPT_VERSION,
        str(task.task_family),
        str(task.friction_type),
        _difficulty_bucket(float(task.difficulty)),
        str(stage_key or "none"),
        _world_level_bucket(int(float(world.get("friction_level", 0)))),
        _world_level_bucket(int(float(world.get("risk_level", 0)))),
        _world_level_bucket(
            int(float(world.get("assist_level", 0)))
            + int(float(world.get("human_support_level", 0)))
        ),
        age_bucket(profile.get("age", -1)),
        _education_bucket(profile.get("education", "")),
        persona_bucket(
            profile.get("persona", ""),
            profile.get("background_summary", ""),
        ),
        _profile_bucket(float(profile.get("digital_experience", 0.5))),
        _profile_bucket(float(profile.get("vision_limit", 0.3))),
        _profile_bucket(float(profile.get("past_fraud_experience", 0.2))),
        _helplessness_bucket(float(helplessness_now)),
        _self_efficacy_bucket(float(task_self_efficacy)),
        _help_rate_bucket(float(help_success_rate_smoothed)),
        _failure_bucket(int(recent.get("recent_same_task_failure_count", 0))),
        _failure_bucket(int(float(recent.get("recent_failure_pressure", 0.0)) // 6.0)),
        _help_rate_bucket(float(recent.get("recent_negative_feedback_ratio", 0.0))),
        _same_task_history_bucket(task_memory),
        _profile_bucket(
            float(task_memory.get("same_task_controllable_success_memory", 0.0))
        ),
        _recent_outcome_pattern_bucket(
            task_memory.get("recent_same_task_outcomes_tail", [])
        ),
        _emotion_bucket(float(digital_emotion_state.anxiety)),
        _emotion_bucket(float(digital_emotion_state.confidence)),
        str(retrieved.get("condition", "structured-only")),
        str(retrieved.get("status", "disabled")),
        int(retrieved.get("count", 0) or 0),
        str(retrieved.get("hash", "")),
    )


def _task_appraisal_system_prompt() -> str:
    return (
        "You are a strict JSON-only task appraisal module for a digital-friction "
        "simulation.\n"
        "Role boundary:\n"
        "- Estimate only the agent's current subjective appraisal of the task.\n"
        "- Do not choose strategy.\n"
        "- Do not predict success or failure.\n"
        "- Do not recommend what the agent should do next.\n"
        "Use the labeled information blocks separately rather than collapsing them "
        "into one overall impression.\n"
        "Construct definitions:\n"
        "- perceived_task_difficulty: how effortful, confusing, or complex the task "
        "feels to do right now. This is not the same as risk or value.\n"
        "- perceived_task_risk: how likely the agent feels bad consequences would be "
        "if they continue, such as error, fraud, privacy loss, or financial loss. "
        "This is not the same as inability.\n"
        "- felt_control: whether the agent feels that continued effort can still "
        "change the result in this specific situation right now.\n"
        "- expected_help_effectiveness: whether asking for help now would materially "
        "improve the situation.\n"
        "- task_value: how worthwhile, necessary, or urgent completing the task feels "
        "for the agent.\n"
        "Boundary rules:\n"
        "- 'I cannot do it' is not the same as 'this is risky'.\n"
        "- 'This is risky' is not the same as 'this is not worth doing'.\n"
        "- 'This is not worth doing' is not the same as 'I have no control'.\n"
        "- task_self_efficacy is the agent's background confidence for this task "
        "domain; felt_control is the current situational sense of control.\n"
        "Internal reasoning order:\n"
        "- First decide internally whether the main barrier is closer to "
        "skill_deficit, situational_uncontrollability, risk_concern, low_value, or "
        "mixed.\n"
        "- Do not output that barrier label.\n"
        "- Then score each construct separately.\n"
        "Anti-middle rule:\n"
        "- Use 45-55 only when the evidence is genuinely mixed or unclear.\n"
        "- If the situation clearly points in different directions, spread the scores "
        "instead of keeping everything near the middle.\n"
        "Output rules:\n"
        "- Return exactly one JSON object with the requested keys only.\n"
        "- Keep reason short and focused on the main appraisal pattern.\n"
        "- judge_confidence should reflect confidence in this construct separation.\n"
    )


def _task_appraisal_scale_anchors() -> dict[str, dict[str, str]]:
    return {
        "perceived_task_difficulty": {
            "0-20": "Very easy; almost no subjective barrier.",
            "21-40": "A little inconvenient but mostly manageable.",
            "41-60": "Moderately difficult; requires attention and effort.",
            "61-80": "Clearly difficult; easy to get stuck or confused.",
            "81-100": "Extremely difficult; feels overwhelming or near unmanageable.",
        },
        "perceived_task_risk": {
            "0-20": "Almost no meaningful risk concern.",
            "21-40": "Some concern, but not a main blocker.",
            "41-60": "Moderate risk concern that may affect willingness.",
            "61-80": "Clear fear of mistakes, fraud, loss, or privacy harm.",
            "81-100": "Severe fear of harmful consequences if continuing.",
        },
        "felt_control": {
            "0-20": "Feels that effort will almost not matter; situation seems out of control.",
            "21-40": "Mostly feels unable to control what happens, even if trying.",
            "41-60": "Control feels unstable; some steps seem manageable, others do not.",
            "61-80": "Mostly feels effort can still improve the situation.",
            "81-100": "Clearly feels the situation is controllable and effort should work.",
        },
        "expected_help_effectiveness": {
            "0-20": "Help would almost certainly not improve the situation.",
            "21-40": "Help might do little or only partially help.",
            "41-60": "Help could be somewhat useful but not decisive.",
            "61-80": "Help would likely improve the situation in a meaningful way.",
            "81-100": "Help would very likely unlock or substantially solve the problem.",
        },
        "task_value": {
            "0-20": "Not worth doing now; little need or benefit.",
            "21-40": "Limited value; easy to postpone or skip.",
            "41-60": "Some value, but not strongly important.",
            "61-80": "Clearly worthwhile or important to complete.",
            "81-100": "Highly necessary, urgent, or consequential.",
        },
    }


def _task_appraisal_schema_template() -> dict[str, str]:
    return {
        "perceived_task_difficulty": "<number 0-100>",
        "perceived_task_risk": "<number 0-100>",
        "felt_control": "<number 0-100>",
        "expected_help_effectiveness": "<number 0-100>",
        "task_value": "<number 0-100>",
        "judge_confidence": "<number 0-1>",
        "reason": "<short string up to 120 chars>",
    }


def _task_appraisal_calibration_notes() -> list[str]:
    return [
        "Judge each construct separately instead of shifting all values together.",
        "Difficulty is about effort and complexity, not danger.",
        "Risk is about potential bad consequences, not inability.",
        "Felt control is about whether effort can still change the outcome now.",
        "Task value is about importance or necessity, not difficulty.",
        "Expected help effectiveness should use current support context and past help experience together.",
        "High difficulty can coexist with high value.",
        "High risk can coexist with moderate or high ability.",
        "Low value can coexist with high control.",
        "Use middle values only when signals are truly mixed or missing.",
    ]


def _build_task_appraisal_user_payload(
    *,
    task: DigitalTask,
    stage_key: str,
    world_context: Any,
    profile_summary: Any,
    helplessness_now: float,
    task_self_efficacy: float,
    help_success_rate_smoothed: float,
    recent_episode_summary: Any,
    digital_emotion_state: DigitalEmotionState,
    task_relevant_memory: Any = None,
    retrieved_episodic_memory: Any = None,
) -> dict[str, Any]:
    world = copy.deepcopy(world_context) if isinstance(world_context, dict) else {}
    profile = (
        copy.deepcopy(profile_summary) if isinstance(profile_summary, dict) else {}
    )
    recent = (
        copy.deepcopy(recent_episode_summary)
        if isinstance(recent_episode_summary, dict)
        else {}
    )
    task_memory = (
        copy.deepcopy(task_relevant_memory)
        if isinstance(task_relevant_memory, dict)
        else {}
    )
    retrieved = (
        copy.deepcopy(retrieved_episodic_memory)
        if isinstance(retrieved_episodic_memory, dict)
        else {}
    )
    return {
        "prompt_version": _TASK_APPRAISAL_PROMPT_VERSION,
        "Agent Profile": profile,
        "Current Task": task.to_dict(),
        "World / Stage Context": {
            "stage_key": str(stage_key or "none"),
            **world,
        },
        "Current Status": {
            "helplessness_now_0_100": round(float(helplessness_now), 4),
            "task_self_efficacy_0_100": round(float(task_self_efficacy), 4),
        },
        "Task-Specific Memory": {
            **task_memory,
            "help_success_rate_smoothed_0_1": round(
                float(help_success_rate_smoothed),
                4,
            ),
        },
        "Recent Experience": recent,
        "Retrieved Episodic Memory": str(retrieved.get("text", "Nothing")),
        "Digital Emotion State": _emotion_dict(digital_emotion_state),
        "Internal Scoring Order": [
            "First identify the main barrier internally: skill_deficit, situational_uncontrollability, risk_concern, low_value, or mixed.",
            "Do not output the barrier label.",
            "Then score the five constructs separately.",
        ],
        "Scale Anchors": _task_appraisal_scale_anchors(),
        "Output Schema Template": _task_appraisal_schema_template(),
        "Calibration Notes": _task_appraisal_calibration_notes(),
    }


def _build_strategy_deliberation_cache_key(
    *,
    task: DigitalTask,
    task_appraisal: Any,
    effective_helplessness: float,
    task_self_efficacy: float,
    help_success_rate_smoothed: float,
    recent_negative_feedback_ratio: float,
    recent_same_task_failure_count: int,
    digital_emotion_state: DigitalEmotionState,
    mastery_signal: str,
    profile_summary: Any = None,
    task_relevant_memory: Any = None,
    recent_episode_summary: Any = None,
    retrieved_episodic_memory: Any = None,
) -> tuple[Any, ...]:
    appraisal = TaskAppraisalResult.from_dict(
        task_appraisal if isinstance(task_appraisal, dict) else {}
    )
    profile = profile_summary if isinstance(profile_summary, dict) else {}
    task_memory = task_relevant_memory if isinstance(task_relevant_memory, dict) else {}
    recent = recent_episode_summary if isinstance(recent_episode_summary, dict) else {}
    retrieved = (
        retrieved_episodic_memory
        if isinstance(retrieved_episodic_memory, dict)
        else {}
    )
    return (
        _STRATEGY_DELIBERATION_PROMPT_VERSION,
        str(task.task_family),
        _difficulty_bucket(float(task.difficulty)),
        _helplessness_bucket(float(effective_helplessness)),
        _self_efficacy_bucket(float(task_self_efficacy)),
        _help_rate_bucket(float(help_success_rate_smoothed)),
        _failure_bucket(int(recent_same_task_failure_count)),
        _help_rate_bucket(float(recent_negative_feedback_ratio)),
        _emotion_bucket(float(appraisal.felt_control / 10.0)),
        _emotion_bucket(float(appraisal.expected_help_effectiveness / 10.0)),
        _emotion_bucket(float(appraisal.task_value / 10.0)),
        _emotion_bucket(float(digital_emotion_state.anxiety)),
        _emotion_bucket(float(digital_emotion_state.confidence)),
        str(mastery_signal or "mixed"),
        age_bucket(profile.get("age", -1)),
        _education_bucket(profile.get("education", "")),
        persona_bucket(profile.get("persona", ""), profile.get("background_summary", "")),
        _profile_bucket(_safe_float(profile.get("digital_experience", 0.5), 0.5)),
        _profile_bucket(_safe_float(profile.get("past_fraud_experience", 0.2), 0.2)),
        _same_task_history_bucket(task_memory),
        _profile_bucket(
            _safe_float(task_memory.get("same_task_controllable_success_memory", 0.0), 0.0)
        ),
        _recent_outcome_pattern_bucket(
            task_memory.get("recent_same_task_outcomes_tail", [])
        ),
        _help_rate_bucket(_safe_float(recent.get("recent_avoid_ratio", 0.0), 0.0)),
        _help_rate_bucket(_safe_float(recent.get("recent_help_seek_ratio", 0.0), 0.0)),
        _failure_bucket(
            int(_safe_float(recent.get("recent_failure_pressure", 0.0), 0.0) // 6.0)
        ),
        str(retrieved.get("condition", "structured-only")),
        str(retrieved.get("status", "disabled")),
        _safe_int(retrieved.get("count", 0), 0),
        str(retrieved.get("hash", "")),
    )


async def resolve_task_appraisal(
    *,
    llm: Any,
    task: DigitalTask,
    stage_key: str,
    world_context: Any,
    profile_summary: Any,
    helplessness_now: float,
    task_self_efficacy: float,
    help_success_rate_smoothed: float,
    recent_episode_summary: Any,
    digital_emotion_state: Any,
    task_relevant_memory: Any = None,
    retrieved_episodic_memory: Any = None,
) -> TaskAppraisalResult:
    config = load_runtime_config()
    mode = str(config.proto_llm_psychology_mode)
    neutral_payload = copy.deepcopy(_NEUTRAL_TASK_APPRAISAL)
    normalized_emotion = normalize_digital_emotion_state(digital_emotion_state)

    if mode != "hybrid" or not bool(config.proto_llm_task_appraisal_enabled):
        return TaskAppraisalResult(
            mode=mode,
            status="disabled",
            source="rule",
            confidence=0.0,
            reason="",
            cache_hit=False,
            **neutral_payload,
        )

    cache_hit = False
    payload: dict[str, Any] | None = None
    cache_key = _build_task_appraisal_cache_key(
        task=task,
        stage_key=stage_key,
        world_context=world_context,
        profile_summary=profile_summary,
        helplessness_now=helplessness_now,
        task_self_efficacy=task_self_efficacy,
        help_success_rate_smoothed=help_success_rate_smoothed,
        recent_episode_summary=recent_episode_summary,
        digital_emotion_state=normalized_emotion,
        task_relevant_memory=task_relevant_memory,
        retrieved_episodic_memory=retrieved_episodic_memory,
    )
    if bool(config.proto_llm_psychology_cache_enabled):
        payload = _TASK_APPRAISAL_CACHE.get(cache_key)
        cache_hit = payload is not None

    status = "ok"
    if payload is None:
        llm_payload, status = await _query_json_payload(
            llm=llm,
            system_prompt=_task_appraisal_system_prompt(),
            user_payload=_build_task_appraisal_user_payload(
                task=task,
                stage_key=stage_key,
                world_context=world_context,
                profile_summary=profile_summary,
                helplessness_now=helplessness_now,
                task_self_efficacy=task_self_efficacy,
                help_success_rate_smoothed=help_success_rate_smoothed,
                recent_episode_summary=recent_episode_summary,
                digital_emotion_state=normalized_emotion,
                task_relevant_memory=task_relevant_memory,
                retrieved_episodic_memory=retrieved_episodic_memory,
            ),
            output_keys=_TASK_APPRAISAL_KEYS,
            repair_schema_text=(
                "- perceived_task_difficulty/perceived_task_risk/felt_control/"
                "expected_help_effectiveness/task_value must be numbers in [0,100]\n"
                "- judge_confidence must be a float in [0,1]\n"
                "- reason must be <= 120 chars"
            ),
            sanitize_fn=_sanitize_task_appraisal,
            timeout=int(config.proto_llm_psychology_timeout),
            retries=int(config.proto_llm_psychology_retries),
        )
        if llm_payload is None:
            return TaskAppraisalResult(
                mode=mode,
                status=status,
                source=_fallback_source_for_status(status),
                confidence=0.0,
                reason="",
                cache_hit=False,
                **neutral_payload,
            )
        payload = llm_payload
        if bool(config.proto_llm_psychology_cache_enabled):
            _TASK_APPRAISAL_CACHE[cache_key] = payload

    confidence = float(payload["judge_confidence"])
    reason = str(payload["reason"]).strip()[:120]
    if confidence < float(config.proto_llm_psychology_min_confidence):
        return TaskAppraisalResult(
            mode=mode,
            status="low_confidence",
            source="rule_fallback_low_confidence",
            confidence=confidence,
            reason=reason,
            cache_hit=cache_hit,
            **neutral_payload,
        )

    return TaskAppraisalResult(
        mode=mode,
        status=status,
        source="llm",
        confidence=confidence,
        reason=reason,
        cache_hit=cache_hit,
        perceived_task_difficulty=float(payload["perceived_task_difficulty"]),
        perceived_task_risk=float(payload["perceived_task_risk"]),
        felt_control=float(payload["felt_control"]),
        expected_help_effectiveness=float(payload["expected_help_effectiveness"]),
        task_value=float(payload["task_value"]),
    )


async def resolve_event_appraisal(
    *,
    llm: Any,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    helplessness_now: float,
    consecutive_failures_before: int,
    digital_emotion_state: Any,
    task_domain_snapshot: Any,
    help_effect_snapshot: Any,
    recent_episode_summary: Any,
    day: int,
    pre_event_task_appraisal: Any = None,
    task_relevant_memory_lite: Any = None,
) -> EventAppraisalResult:
    config = load_runtime_config()
    raw_state = normalize_digital_emotion_state(digital_emotion_state)
    decayed_state = _decay_emotion_state(state=raw_state, target_day=int(day))
    rule_after_state = _apply_rule_emotion_update(
        state=decayed_state,
        outcome_type=outcome.outcome_type,
        day=int(day),
    )
    emotion_before = _emotion_dict(decayed_state)
    rule_after = _emotion_dict(rule_after_state)
    mode = str(config.proto_llm_psychology_mode)

    if mode != "hybrid" or not bool(config.proto_llm_event_appraisal_enabled):
        return EventAppraisalResult(
            mode=mode,
            status="disabled",
            source="rule",
            confidence=0.0,
            reason="",
            cache_hit=False,
            emotion_before=emotion_before,
            rule_after=rule_after,
            llm_after=None,
            final_after=rule_after,
        )

    cache_hit = False
    payload: dict[str, Any] | None = None
    cache_key = _build_event_appraisal_cache_key(
        task=task,
        strategy=strategy,
        outcome=outcome,
        helplessness_now=helplessness_now,
        emotion_before=decayed_state,
        consecutive_failures_before=consecutive_failures_before,
        pre_event_task_appraisal=pre_event_task_appraisal,
        task_relevant_memory_lite=task_relevant_memory_lite,
    )
    if bool(config.proto_llm_psychology_cache_enabled):
        payload = _EVENT_APPRAISAL_CACHE.get(cache_key)
        cache_hit = payload is not None

    status = "ok"
    if payload is None:
        llm_payload, status = await _query_json_payload(
            llm=llm,
            system_prompt=(
                "You are a strict JSON-only calibrator for post-event psychological "
                "appraisal in a digital-friction simulation. Compare the actual outcome "
                "with the agent's pre-event expectations and recent same-task history. "
                "Stay close to the rule baseline unless there is strong evidence to "
                "deviate."
            ),
            user_payload={
                "current_event": {
                    "task_family": task.task_family,
                    "friction_type": task.friction_type,
                    "difficulty": round(float(task.difficulty), 4),
                    "strategy_type": strategy.strategy_type,
                    "outcome_type": outcome.outcome_type,
                    "support_quality": int(outcome.support_quality),
                    "friction_tier": int(outcome.friction_tier),
                },
                "current_state": {
                    "helplessness_now": round(float(helplessness_now), 4),
                    "consecutive_failures_before": int(consecutive_failures_before),
                    "digital_emotion_before": emotion_before,
                },
                "pre_event_appraisal": copy.deepcopy(pre_event_task_appraisal)
                if isinstance(pre_event_task_appraisal, dict)
                else {},
                "same_task_recent_context": copy.deepcopy(task_relevant_memory_lite)
                if isinstance(task_relevant_memory_lite, dict)
                else {},
                "task_domain_snapshot": copy.deepcopy(task_domain_snapshot)
                if isinstance(task_domain_snapshot, dict)
                else {},
                "help_effect_snapshot": copy.deepcopy(help_effect_snapshot)
                if isinstance(help_effect_snapshot, dict)
                else {},
                "recent_episode_summary": copy.deepcopy(recent_episode_summary)
                if isinstance(recent_episode_summary, dict)
                else {},
                "comparison_rules": [
                    "If pre-event felt_control was already low, a failure can raise frustration and lower confidence more.",
                    "If expected_help_effectiveness was high but help still failed, confidence loss can be stronger.",
                    "If recent same-task history includes controllable success evidence, avoid overreacting to one bad event.",
                    "Do not move anxiety, frustration, relief, and confidence together unless the evidence supports all of them.",
                ],
                "rule_baseline_after": rule_after,
                "output_schema_example": {
                    "anxiety": rule_after["anxiety"],
                    "frustration": rule_after["frustration"],
                    "relief": rule_after["relief"],
                    "confidence": rule_after["confidence"],
                    "judge_confidence": 0.72,
                    "reason": "Failure after meaningful friction suggests higher anxiety and lower confidence.",
                },
            },
            output_keys=_EVENT_APPRAISAL_KEYS,
            repair_schema_text=(
                "- anxiety/frustration/relief/confidence must be numbers in [0,10]\n"
                "- judge_confidence must be a float in [0,1]\n"
                "- reason must be <= 120 chars"
            ),
            sanitize_fn=_sanitize_event_appraisal,
            timeout=int(config.proto_llm_psychology_timeout),
            retries=int(config.proto_llm_psychology_retries),
        )
        if llm_payload is None:
            return EventAppraisalResult(
                mode=mode,
                status=status,
                source=_fallback_source_for_status(status),
                confidence=0.0,
                reason="",
                cache_hit=False,
                emotion_before=emotion_before,
                rule_after=rule_after,
                llm_after=None,
                final_after=rule_after,
            )
        payload = llm_payload
        if bool(config.proto_llm_psychology_cache_enabled):
            _EVENT_APPRAISAL_CACHE[cache_key] = payload

    confidence = float(payload["judge_confidence"])
    reason = str(payload["reason"]).strip()[:120]
    llm_after = {
        "anxiety": round(float(payload["anxiety"]), 4),
        "frustration": round(float(payload["frustration"]), 4),
        "relief": round(float(payload["relief"]), 4),
        "confidence": round(float(payload["confidence"]), 4),
    }
    if confidence < float(config.proto_llm_psychology_min_confidence):
        return EventAppraisalResult(
            mode=mode,
            status="low_confidence",
            source="rule_fallback_low_confidence",
            confidence=confidence,
            reason=reason,
            cache_hit=cache_hit,
            emotion_before=emotion_before,
            rule_after=rule_after,
            llm_after=llm_after,
            final_after=rule_after,
        )

    final_after: dict[str, float] = {}
    for field in ("anxiety", "frustration", "relief", "confidence"):
        diff = float(llm_after[field]) - float(rule_after[field])
        final_after[field] = round(
            _clamp(float(rule_after[field]) + _clamp(diff, -2.0, 2.0), 0.0, 10.0),
            4,
        )
    source = "llm_confirmed" if final_after == rule_after else "hybrid_shifted"
    return EventAppraisalResult(
        mode=mode,
        status=status,
        source=source,
        confidence=confidence,
        reason=reason,
        cache_hit=cache_hit,
        emotion_before=emotion_before,
        rule_after=rule_after,
        llm_after=llm_after,
        final_after=final_after,
    )


def _extract_reflection_day_events(
    *,
    target_day: int,
    event_log: Any,
) -> list[dict[str, Any]]:
    if not isinstance(event_log, list):
        return []
    return [
        copy.deepcopy(item)
        for item in event_log
        if isinstance(item, dict) and _safe_int(item.get("day"), -999999) == int(target_day)
    ]


def _build_reflection_summary(
    *,
    target_day: int,
    day_events: list[dict[str, Any]],
) -> dict[str, Any]:
    task_counts: dict[str, int] = {}
    success_self_count = 0
    success_with_help_count = 0
    help_failure_count = 0
    avoid_count = 0
    negative_count = 0
    last_outcome = ""

    for item in day_events:
        task_family = str(
            item.get("scenario")
            or item.get("decision", {}).get("task_family")
            or ""
        ).strip()
        if task_family:
            task_counts[task_family] = task_counts.get(task_family, 0) + 1
        outcome_type = str(
            item.get("decision", {}).get("primary_reason")
            or item.get("message", "")
        ).strip()
        if ":" in outcome_type:
            outcome_type = outcome_type.split(":")[-1]
        last_outcome = outcome_type or last_outcome
        if outcome_type == "success_self":
            success_self_count += 1
        elif outcome_type == "success_with_help":
            success_with_help_count += 1
        elif outcome_type in {"failure_even_with_help", "abandon_midway"}:
            help_failure_count += 1
        elif outcome_type == "avoid_without_attempt":
            avoid_count += 1
        if outcome_type in {
            "failure_after_attempt",
            "failure_even_with_help",
            "abandon_midway",
        }:
            negative_count += 1

    dominant_task_family = (
        max(task_counts.items(), key=lambda item: (item[1], item[0]))[0]
        if task_counts
        else ""
    )
    success_count = success_self_count + success_with_help_count
    help_effective = success_with_help_count > help_failure_count
    if avoid_count > 0 and avoid_count >= max(success_count, negative_count):
        mastery_signal = "avoidance"
    elif success_self_count > 0 and negative_count == 0 and avoid_count == 0:
        mastery_signal = "success"
    elif negative_count > success_count:
        mastery_signal = "struggle"
    else:
        mastery_signal = "mixed"
    return {
        "day": int(target_day),
        "event_count": len(day_events),
        "dominant_task_family": dominant_task_family,
        "task_counts": task_counts,
        "success_self_count": success_self_count,
        "success_with_help_count": success_with_help_count,
        "help_failure_count": help_failure_count,
        "avoid_count": avoid_count,
        "negative_count": negative_count,
        "help_effective": help_effective,
        "mastery_signal": mastery_signal,
        "last_outcome": last_outcome,
    }


def _fallback_reflection_text(summary: dict[str, Any]) -> str:
    if int(summary.get("help_failure_count", 0)) > 0:
        return "昨天有人帮也没做成，我还是没底"
    if str(summary.get("mastery_signal")) == "success":
        return "昨天自己做成了一次，我感觉能学会"
    if str(summary.get("mastery_signal")) == "avoidance":
        return "昨天还是有点怕，我总想先躲开"
    if int(summary.get("negative_count", 0)) >= 2:
        return "昨天这类任务总卡住，我还是发怵"
    return _RULE_TEXT_MIXED


async def maybe_generate_daily_reflection(
    *,
    llm: Any,
    current_day: int,
    last_reflection_day: int,
    event_log: Any,
    digital_emotion_state: Any,
    task_domain_memory: Any,
    help_effect_memory: Any,
    reflection_history: Any,
) -> tuple[dict[str, Any], DailyReflection | None]:
    target_day = int(current_day) - 1
    if target_day < 0 or int(last_reflection_day) >= target_day:
        return {}, None

    history = [
        DailyReflection.from_dict(item).to_dict()
        for item in (reflection_history if isinstance(reflection_history, list) else [])
        if isinstance(item, dict)
    ][-7:]
    day_events = _extract_reflection_day_events(target_day=target_day, event_log=event_log)
    if not day_events:
        return {"proto_last_reflection_day": target_day}, None

    summary = _build_reflection_summary(target_day=target_day, day_events=day_events)
    current_emotion = normalize_digital_emotion_state(digital_emotion_state)
    mode = str(load_runtime_config().proto_llm_psychology_mode)
    config = load_runtime_config()

    reflection: DailyReflection
    if mode != "hybrid" or not bool(config.proto_llm_daily_reflection_enabled):
        reflection = DailyReflection(
            day=target_day,
            dominant_task_family=str(summary["dominant_task_family"]),
            help_effective=bool(summary["help_effective"]),
            mastery_signal=str(summary["mastery_signal"]),
            text=_fallback_reflection_text(summary)[:40],
            confidence=0.0,
            source="rule",
            status="disabled",
        )
    else:
        payload, status = await _query_json_payload(
            llm=llm,
            system_prompt=(
                "You are a strict JSON-only daily reflection summarizer for a digital "
                "task simulation. Be brief, concrete, and grounded in the provided day summary."
            ),
            user_payload={
                "task": "Summarize the previous day into one short reflection.",
                "previous_day_summary": summary,
                "digital_emotion_state": _emotion_dict(current_emotion),
                "task_domain_memory": copy.deepcopy(task_domain_memory)
                if isinstance(task_domain_memory, dict)
                else {},
                "help_effect_memory": copy.deepcopy(help_effect_memory)
                if isinstance(help_effect_memory, dict)
                else {},
                "output_schema_example": {
                    "dominant_task_family": str(summary["dominant_task_family"]),
                    "help_effective": bool(summary["help_effective"]),
                    "mastery_signal": str(summary["mastery_signal"]),
                    "text": _fallback_reflection_text(summary)[:40],
                    "judge_confidence": 0.76,
                },
            },
            output_keys=_DAILY_REFLECTION_KEYS,
            repair_schema_text=(
                "- dominant_task_family must be a short string\n"
                "- help_effective must be true or false\n"
                "- mastery_signal must be one of success, struggle, avoidance, mixed\n"
                "- text must be <= 40 Chinese chars\n"
                "- judge_confidence must be a float in [0,1]"
            ),
            sanitize_fn=_sanitize_daily_reflection,
            timeout=int(config.proto_llm_psychology_timeout),
            retries=int(config.proto_llm_psychology_retries),
        )
        if payload is None or float(payload["judge_confidence"]) < float(
            config.proto_llm_psychology_min_confidence
        ):
            reflection = DailyReflection(
                day=target_day,
                dominant_task_family=str(summary["dominant_task_family"]),
                help_effective=bool(summary["help_effective"]),
                mastery_signal=str(summary["mastery_signal"]),
                text=_fallback_reflection_text(summary)[:40],
                confidence=float(payload["judge_confidence"]) if payload else 0.0,
                source=_fallback_source_for_status(
                    "low_confidence" if payload is not None else status
                ),
                status="low_confidence" if payload is not None else status,
            )
        else:
            reflection = DailyReflection(
                day=target_day,
                dominant_task_family=str(payload["dominant_task_family"])[:40]
                or str(summary["dominant_task_family"]),
                help_effective=bool(payload["help_effective"]),
                mastery_signal=str(payload["mastery_signal"]),
                text=str(payload["text"])[:40],
                confidence=float(payload["judge_confidence"]),
                source="llm",
                status=status,
            )

    history.append(reflection.to_dict())
    return (
        {
            "proto_last_reflection_day": target_day,
            "proto_daily_reflection": reflection.to_dict(),
            "proto_daily_reflection_history": history[-7:],
        },
        reflection,
    )


async def resolve_strategy_deliberation(
    *,
    llm: Any,
    task: DigitalTask,
    task_appraisal: Any,
    effective_helplessness: float,
    task_self_efficacy: float,
    help_success_rate_smoothed: float,
    recent_negative_feedback_ratio: float,
    recent_same_task_failure_count: int,
    digital_emotion_state: Any,
    daily_reflection: Any,
    rule_weights: dict[str, float],
    profile_summary: Any = None,
    task_relevant_memory: Any = None,
    recent_episode_summary: Any = None,
    retrieved_episodic_memory: Any = None,
) -> StrategyDeliberationResult:
    config = load_runtime_config()
    mode = str(config.proto_llm_psychology_mode)
    normalized_emotion = normalize_digital_emotion_state(digital_emotion_state)
    reflection = DailyReflection.from_dict(
        daily_reflection if isinstance(daily_reflection, dict) else {}
    )
    appraisal = TaskAppraisalResult.from_dict(
        task_appraisal if isinstance(task_appraisal, dict) else {}
    )
    normalized_rule_weights = {
        key: float(rule_weights.get(key, 0.0))
        for key in ("attempt_self", "seek_help_then_attempt", "avoid")
    }
    profile_context = _strategy_profile_context(profile_summary)
    task_memory_context = _strategy_task_memory_context(task_relevant_memory)
    recent_context = _strategy_recent_context(recent_episode_summary)
    retrieved_context = _strategy_retrieved_memory_context(retrieved_episodic_memory)

    if mode != "hybrid" or not bool(config.proto_llm_strategy_deliberation_enabled):
        return StrategyDeliberationResult(
            mode=mode,
            status="disabled",
            source="rule",
            confidence=0.0,
            reason="",
            cache_hit=False,
            dominant_strategy=_dominant_strategy_from_weights(normalized_rule_weights),
            rule_weights=normalized_rule_weights,
            final_weights=copy.deepcopy(normalized_rule_weights),
        )

    cache_hit = False
    payload: dict[str, Any] | None = None
    cache_key = _build_strategy_deliberation_cache_key(
        task=task,
        task_appraisal=appraisal.to_dict(),
        effective_helplessness=effective_helplessness,
        task_self_efficacy=task_self_efficacy,
        help_success_rate_smoothed=help_success_rate_smoothed,
        recent_negative_feedback_ratio=recent_negative_feedback_ratio,
        recent_same_task_failure_count=recent_same_task_failure_count,
        digital_emotion_state=normalized_emotion,
        mastery_signal=reflection.mastery_signal,
        profile_summary=profile_summary,
        task_relevant_memory=task_relevant_memory,
        recent_episode_summary=recent_episode_summary,
        retrieved_episodic_memory=retrieved_episodic_memory,
    )
    if bool(config.proto_llm_psychology_cache_enabled):
        payload = _STRATEGY_DELIBERATION_CACHE.get(cache_key)
        cache_hit = payload is not None

    status = "ok"
    if payload is None:
        llm_payload, status = await _query_json_payload(
            llm=llm,
            system_prompt=(
                "You are a strict JSON-only bounded strategy deliberation module. "
                "You must reason only over these three allowed strategies: attempt_self, "
                "seek_help_then_attempt, avoid. You must not invent new actions. "
                "Use profile and memory context only to score the three allowed strategies. "
                "Treat task_appraisal as the authoritative current appraisal summary. "
                "Do not re-score task difficulty, risk, felt control, help effectiveness, "
                "or task value. Do not output helplessness, self-efficacy, controllability, "
                "posterior updates, recommendations outside the JSON schema, or state deltas."
            ),
            user_payload={
                "prompt_version": _STRATEGY_DELIBERATION_PROMPT_VERSION,
                "task": task.to_dict(),
                "task_appraisal": appraisal.to_dict(),
                "agent_profile": profile_context,
                "task_relevant_memory": task_memory_context,
                "recent_episode_summary": recent_context,
                "retrieved_episodic_memory": retrieved_context,
                "effective_helplessness": round(float(effective_helplessness), 4),
                "task_self_efficacy": round(float(task_self_efficacy), 4),
                "help_success_rate_smoothed": round(
                    float(help_success_rate_smoothed), 4
                ),
                "recent_negative_feedback_ratio": round(
                    float(recent_negative_feedback_ratio), 4
                ),
                "recent_same_task_failure_count": int(
                    recent_same_task_failure_count
                ),
                "digital_emotion_state": _emotion_dict(normalized_emotion),
                "daily_reflection": reflection.to_dict(),
                "rule_weights": normalized_rule_weights,
                "allowed_strategies": [
                    "attempt_self",
                    "seek_help_then_attempt",
                    "avoid",
                ],
                "decision_dimensions": [
                    (
                        "task appraisal as authoritative summary: difficulty, risk, "
                        "felt control, help effectiveness, task value"
                    ),
                    (
                        "agent profile: age, digital experience, fraud/risk "
                        "background, persona"
                    ),
                    "task-specific memory: same-family failure/success/help history",
                    (
                        "recent experience: negative feedback, avoidance, "
                        "help-seeking, failure pressure"
                    ),
                    "emotional state and daily reflection",
                    "rule weights as baseline, not as a command",
                ],
                "output_schema_example": {
                    "attempt_self_score": 0.18,
                    "seek_help_score": 0.57,
                    "avoid_score": 0.25,
                    "dominant_strategy": "seek_help_then_attempt",
                    "judge_confidence": 0.80,
                    "reason": "Low control and decent support history make help-seeking the most acceptable option.",
                },
            },
            output_keys=_STRATEGY_DELIBERATION_KEYS,
            repair_schema_text=(
                "- attempt_self_score/seek_help_score/avoid_score must be numbers in [0,1]\n"
                "- dominant_strategy must be one of attempt_self, seek_help_then_attempt, avoid\n"
                "- dominant_strategy must match the highest score\n"
                "- judge_confidence must be a float in [0,1]\n"
                "- reason must be <= 120 chars"
            ),
            sanitize_fn=_sanitize_strategy_deliberation,
            timeout=int(config.proto_llm_psychology_timeout),
            retries=int(config.proto_llm_psychology_retries),
        )
        if llm_payload is None:
            return StrategyDeliberationResult(
                mode=mode,
                status=status,
                source=_fallback_source_for_status(status),
                confidence=0.0,
                reason="",
                cache_hit=False,
                dominant_strategy=_dominant_strategy_from_weights(
                    normalized_rule_weights
                ),
                rule_weights=normalized_rule_weights,
                final_weights=copy.deepcopy(normalized_rule_weights),
            )
        payload = llm_payload
        if bool(config.proto_llm_psychology_cache_enabled):
            _STRATEGY_DELIBERATION_CACHE[cache_key] = payload

    confidence = float(payload["judge_confidence"])
    reason = str(payload["reason"]).strip()[:120]
    llm_weights = _normalize_strategy_score_weights(
        float(payload["attempt_self_score"]),
        float(payload["seek_help_score"]),
        float(payload["avoid_score"]),
    )
    if confidence < float(config.proto_llm_psychology_min_confidence):
        return StrategyDeliberationResult(
            mode=mode,
            status="low_confidence",
            source="rule_fallback_low_confidence",
            confidence=confidence,
            reason=reason,
            cache_hit=cache_hit,
            dominant_strategy=_dominant_strategy_from_weights(normalized_rule_weights),
            attempt_self_score=float(payload["attempt_self_score"]),
            seek_help_score=float(payload["seek_help_score"]),
            avoid_score=float(payload["avoid_score"]),
            rule_weights=normalized_rule_weights,
            llm_weights=llm_weights,
            final_weights=copy.deepcopy(normalized_rule_weights),
        )

    final_weights = _blend_strategy_weights(
        rule_weights=normalized_rule_weights,
        llm_weights=llm_weights,
        blend_ratio=_BLEND_RATIO,
    )
    return StrategyDeliberationResult(
        mode=mode,
        status=status,
        source="hybrid_blended",
        confidence=confidence,
        reason=reason,
        cache_hit=cache_hit,
        dominant_strategy=str(payload["dominant_strategy"]),
        attempt_self_score=float(payload["attempt_self_score"]),
        seek_help_score=float(payload["seek_help_score"]),
        avoid_score=float(payload["avoid_score"]),
        rule_weights=normalized_rule_weights,
        llm_weights=llm_weights,
        final_weights=final_weights,
    )


def _trajectory_profile_context(profile_summary: Any) -> dict[str, Any]:
    profile = profile_summary if isinstance(profile_summary, dict) else {}
    return {
        "digital_experience_bucket": _profile_bucket(
            _safe_float(profile.get("digital_experience"), 0.5)
        ),
        "vision_accessibility_constraint": _profile_bucket(
            _safe_float(profile.get("vision_limit"), 0.3)
        ),
        "fraud_risk_background": _profile_bucket(
            _safe_float(profile.get("past_fraud_experience"), 0.2)
        ),
        "persona_bucket": persona_bucket(profile.get("persona", "")),
    }


def _trajectory_memory_context(memory_features: Any) -> dict[str, Any]:
    memory = memory_features if isinstance(memory_features, dict) else {}
    if hasattr(memory_features, "to_dict"):
        try:
            memory = memory_features.to_dict()
        except Exception:
            memory = {}
    return {
        "effective_helplessness_bucket": _helplessness_bucket(
            _safe_float(memory.get("effective_helplessness"), 50.0)
        ),
        "task_self_efficacy_bucket": _self_efficacy_bucket(
            _safe_float(memory.get("task_self_efficacy"), 50.0)
        ),
        "controllable_success_memory_bucket": _profile_bucket(
            _safe_float(memory.get("controllable_success_memory"), 0.0)
        ),
        "recent_same_task_failure_count": min(
            _safe_int(memory.get("recent_same_task_failure_count"), 0),
            3,
        ),
        "recent_negative_feedback_ratio_bucket": _profile_bucket(
            _safe_float(memory.get("recent_negative_feedback_ratio"), 0.0)
        ),
    }


def _trajectory_env_context(env: Any) -> dict[str, Any]:
    env_dict = env if isinstance(env, dict) else {}
    return {
        "friction_level_bucket": _world_level_bucket(
            _safe_int(env_dict.get("friction_level"), 0)
        ),
        "malicious_friction_level_bucket": _world_level_bucket(
            _safe_int(env_dict.get("malicious_friction_level"), 0)
        ),
        "risk_level_bucket": _world_level_bucket(_safe_int(env_dict.get("risk_level"), 0)),
        "complexity_level_bucket": _world_level_bucket(
            _safe_int(env_dict.get("complexity_level"), 0)
        ),
        "accessibility_level_bucket": _world_level_bucket(
            _safe_int(env_dict.get("accessibility_level"), 0)
        ),
    }


async def resolve_trajectory_appraisal(
    *,
    llm: Any,
    task: DigitalTask,
    strategy: AttemptStrategy,
    task_appraisal: Any,
    memory_features: Any,
    env: Any,
    profile_summary: Any = None,
    run_context: Any = None,
) -> dict[str, Any]:
    config = load_runtime_config()
    mode = str(config.proto_llm_psychology_mode)
    strategy_type = str(strategy.strategy_type)
    prompt_version = str(
        getattr(config, "proto_outcome_trajectory_prompt_version", _TRAJECTORY_PROMPT_VERSION)
    )
    taxonomy_version = str(
        getattr(
            config,
            "proto_outcome_trajectory_taxonomy_version",
            _TRAJECTORY_TAXONOMY_VERSION,
        )
    )
    if strategy_type == "avoid":
        return {
            "status": "not_called_strategy_avoid",
            "invalid_reason": "",
            "trajectory_confidence": 0.0,
            "prompt_version": prompt_version,
            "taxonomy_version": taxonomy_version,
        }
    if mode != "hybrid":
        return {
            "status": "disabled",
            "invalid_reason": "proto_llm_psychology_mode_not_hybrid",
            "trajectory_confidence": 0.0,
            "prompt_version": prompt_version,
            "taxonomy_version": taxonomy_version,
        }

    appraisal = TaskAppraisalResult.from_dict(
        task_appraisal if isinstance(task_appraisal, dict) else (
            task_appraisal.to_dict() if hasattr(task_appraisal, "to_dict") else None
        )
    )
    allowed_outcomes = _trajectory_allowed_outcomes(strategy_type)
    if not allowed_outcomes:
        return {
            "status": "invalid_strategy",
            "invalid_reason": "unsupported_strategy_for_trajectory",
            "trajectory_confidence": 0.0,
            "prompt_version": prompt_version,
            "taxonomy_version": taxonomy_version,
        }

    allowed_points = sorted(_trajectory_allowed_friction_points(task.task_family))

    def _sanitize_for_this_episode(payload: Any) -> tuple[dict[str, Any] | None, str]:
        return _sanitize_trajectory_appraisal_for_context(
            payload,
            task_family=str(task.task_family),
            strategy_type=strategy_type,
        )

    payload, status = await _query_json_payload(
        llm=llm,
        system_prompt=(
            "You are a strict JSON-only constrained cognitive walkthrough module "
            "for a digital task simulation. Produce a pre-outcome task trajectory "
            "appraisal only. Do not decide the final sampled outcome. Do not output "
            "helplessness, self-efficacy, controllability, posterior, C_family, "
            "C_global, policy weights, or state updates. Use capability descriptors "
            "and task context; do not attribute difficulty to age or gender."
        ),
        user_payload={
            "prompt_version": prompt_version,
            "taxonomy_version": taxonomy_version,
            "task": {
                "task_family": task.task_family,
                "friction_type": task.friction_type,
                "difficulty_bucket": _difficulty_bucket(float(task.difficulty)),
                "support_sensitivity_bucket": _profile_bucket(
                    float(task.support_sensitivity)
                ),
            },
            "selected_strategy": strategy_type,
            "task_appraisal": {
                "perceived_task_difficulty": _appraisal_bucket(
                    appraisal.perceived_task_difficulty
                ),
                "perceived_task_risk": _appraisal_bucket(appraisal.perceived_task_risk),
                "felt_control": _appraisal_bucket(appraisal.felt_control),
                "expected_help_effectiveness": _appraisal_bucket(
                    appraisal.expected_help_effectiveness
                ),
                "task_value": _appraisal_bucket(appraisal.task_value),
            },
            "memory_features": _trajectory_memory_context(memory_features),
            "env": _trajectory_env_context(env),
            "capability_profile": _trajectory_profile_context(profile_summary),
            "run_context": run_context if isinstance(run_context, dict) else {},
            "allowed_friction_points": allowed_points,
            "allowed_outcome_keys": list(allowed_outcomes),
            "rules": [
                "planned_steps must describe actions only, not final results",
                "select 0 to 3 friction points only from allowed_friction_points",
                "trajectory_outcome_tendency must use exactly allowed_outcome_keys",
                "does_not_sample_final_outcome must be true",
                "does_not_update_psychology must be true",
            ],
            "output_schema_example": {
                "planned_steps": [
                    {"step_id": 1, "action": "open the relevant app page"},
                    {"step_id": 2, "action": "read the main instruction"},
                ],
                "selected_friction_points": [
                    {
                        "point": allowed_points[0] if allowed_points else "navigation_depth",
                        "severity": 0.45,
                        "step_id": 2,
                    }
                ],
                "friction_encounter_likelihood": 0.50,
                "cognitive_load": 0.50,
                "help_need": 0.30,
                "trajectory_outcome_tendency": {
                    key: round(1.0 / len(allowed_outcomes), 6)
                    for key in allowed_outcomes
                },
                "trajectory_confidence": 0.75,
                "reason": "Task steps contain moderate friction but no final outcome is sampled.",
                "does_not_sample_final_outcome": True,
                "does_not_update_psychology": True,
            },
        },
        output_keys=_TRAJECTORY_APPRAISAL_KEYS,
        repair_schema_text=(
            "- Return exactly the required keys and no extra keys\n"
            "- planned_steps must be 2-6 objects with step_id and action\n"
            "- selected_friction_points must be 0-3 objects with point/severity/step_id\n"
            "- friction point must come from allowed_friction_points\n"
            "- trajectory_outcome_tendency keys must exactly match allowed_outcome_keys\n"
            "- all probabilities and confidence must be in [0,1]\n"
            "- trajectory_outcome_tendency must sum to 1\n"
            "- does_not_sample_final_outcome and does_not_update_psychology must be true"
        ),
        sanitize_fn=_sanitize_for_this_episode,
        timeout=int(config.proto_llm_psychology_timeout),
        retries=int(config.proto_llm_psychology_retries),
        max_tokens=760,
        json_attempts=int(
            getattr(config, "proto_outcome_trajectory_json_attempts", 1)
        ),
        attempt_metadata_key="_json_attempts_used",
    )
    if payload is None:
        return {
            "status": status,
            "invalid_reason": status,
            "trajectory_confidence": 0.0,
            "prompt_version": prompt_version,
            "taxonomy_version": taxonomy_version,
            "trajectory_json_attempts_configured": int(
                getattr(config, "proto_outcome_trajectory_json_attempts", 1)
            ),
            "trajectory_json_attempts_used": int(
                getattr(config, "proto_outcome_trajectory_json_attempts", 1)
            ),
        }
    json_attempts_used = int(payload.pop("_json_attempts_used", 1) or 1)
    confidence = float(payload.get("trajectory_confidence", 0.0))
    min_confidence = float(
        getattr(config, "proto_outcome_trajectory_min_confidence", 0.65)
    )
    if confidence < min_confidence:
        payload = {
            **payload,
            "status": "low_confidence",
            "invalid_reason": "low_confidence",
        }
    else:
        payload = {**payload, "status": status, "invalid_reason": ""}
    payload["prompt_version"] = prompt_version
    payload["taxonomy_version"] = taxonomy_version
    payload["trajectory_json_attempts_configured"] = int(
        getattr(config, "proto_outcome_trajectory_json_attempts", 1)
    )
    payload["trajectory_json_attempts_used"] = json_attempts_used
    return payload


async def resolve_stage_interview(
    *,
    llm: Any,
    stage_name: str,
    stage_index: int,
    stage_summary_memory: str,
    survey_summary: Any,
    latest_task_appraisal: Any,
    latest_digital_emotion: Any,
    latest_daily_reflection: Any,
    event_log_summary: Any = None,
    latest_event_attribution: Any = None,
) -> StageInterviewResult:
    config = load_runtime_config()
    mode = str(config.proto_llm_psychology_mode)
    fallback = StageInterviewResult(
        stage_name=str(stage_name),
        stage_index=int(stage_index),
        main_difficulty_source="mixed",
        support_comment="not_used",
        future_intention="mixed",
        short_quote="这一阶段有卡顿，我还在慢慢适应。",
        confidence=0.0,
        source="rule",
        status="disabled",
    )
    if mode != "hybrid":
        return fallback

    payload, status = await _query_json_payload(
        llm=llm,
        system_prompt=(
            "You are a strict JSON-only stage-end interview summarizer for a "
            "digital-friction simulation. Do not modify state. Only summarize the "
            "agent's own explanation of the stage."
        ),
        user_payload={
            "stage_name": str(stage_name),
            "stage_index": int(stage_index),
            "stage_summary_memory": str(stage_summary_memory)[:800],
            "survey_summary": copy.deepcopy(survey_summary)
            if isinstance(survey_summary, dict)
            else {},
            "latest_task_appraisal": copy.deepcopy(latest_task_appraisal)
            if isinstance(latest_task_appraisal, dict)
            else {},
            "latest_digital_emotion": copy.deepcopy(latest_digital_emotion)
            if isinstance(latest_digital_emotion, dict)
            else {},
            "latest_daily_reflection": copy.deepcopy(latest_daily_reflection)
            if isinstance(latest_daily_reflection, dict)
            else {},
            "latest_event_attribution": copy.deepcopy(latest_event_attribution)
            if isinstance(latest_event_attribution, dict)
            else {},
            "event_log_summary": copy.deepcopy(event_log_summary)
            if isinstance(event_log_summary, dict)
            else {},
            "output_schema_example": {
                "main_difficulty_source": "verification_friction",
                "support_comment": "limited",
                "future_intention": "seek_help",
                "short_quote": "如果有人先帮我看一眼，我会更敢继续。",
                "judge_confidence": 0.82,
            },
        },
        output_keys=_STAGE_INTERVIEW_KEYS,
        repair_schema_text=(
            "- main_difficulty_source must be one of verification_friction, form_complexity, "
            "risk_concern, info_overload, low_control, mixed\n"
            "- support_comment must be one of helpful, limited, ineffective, not_used\n"
            "- future_intention must be one of try_self, seek_help, avoid, mixed\n"
            "- short_quote must be a short natural sentence\n"
            "- judge_confidence must be a float in [0,1]"
        ),
        sanitize_fn=_sanitize_stage_interview,
        timeout=int(config.proto_llm_psychology_timeout),
        retries=int(config.proto_llm_psychology_retries),
    )
    if payload is None:
        fallback_payload = fallback.to_dict()
        fallback_payload.update(
            {
                "status": status,
                "source": _fallback_source_for_status(status),
            }
        )
        return StageInterviewResult(
            **fallback_payload,
        )
    if float(payload["judge_confidence"]) < float(config.proto_llm_psychology_min_confidence):
        fallback_payload = fallback.to_dict()
        fallback_payload.update(
            {
                "confidence": float(payload["judge_confidence"]),
                "status": "low_confidence",
                "source": "rule_fallback_low_confidence",
            }
        )
        return StageInterviewResult(
            **fallback_payload,
        )
    return StageInterviewResult(
        stage_name=str(stage_name),
        stage_index=int(stage_index),
        main_difficulty_source=str(payload["main_difficulty_source"]),
        support_comment=str(payload["support_comment"]),
        future_intention=str(payload["future_intention"]),
        short_quote=str(payload["short_quote"])[:120],
        confidence=float(payload["judge_confidence"]),
        source="llm",
        status=status,
    )


async def resolve_final_interview(
    *,
    llm: Any,
    stage_interview_history: Any,
    latest_digital_emotion: Any,
    latest_daily_reflection: Any,
    survey_summary: Any,
    event_log_summary: Any = None,
    latest_event_attribution: Any = None,
) -> FinalInterviewResult:
    config = load_runtime_config()
    mode = str(config.proto_llm_psychology_mode)
    fallback = FinalInterviewResult(
        overall_trajectory="mixed",
        main_barrier="mixed",
        support_takeaway="limited",
        future_orientation="mixed",
        short_quote="我不是完全不会，只是有些时候还是会发怵。",
        confidence=0.0,
        source="rule",
        status="disabled",
    )
    if mode != "hybrid":
        return fallback

    payload, status = await _query_json_payload(
        llm=llm,
        system_prompt=(
            "You are a strict JSON-only final interview summarizer for a digital-friction "
            "simulation. Summarize the agent's overall trajectory, barriers, and future orientation."
        ),
        user_payload={
            "stage_interview_history": copy.deepcopy(stage_interview_history)
            if isinstance(stage_interview_history, list)
            else [],
            "latest_digital_emotion": copy.deepcopy(latest_digital_emotion)
            if isinstance(latest_digital_emotion, dict)
            else {},
            "latest_daily_reflection": copy.deepcopy(latest_daily_reflection)
            if isinstance(latest_daily_reflection, dict)
            else {},
            "latest_event_attribution": copy.deepcopy(latest_event_attribution)
            if isinstance(latest_event_attribution, dict)
            else {},
            "survey_summary": copy.deepcopy(survey_summary)
            if isinstance(survey_summary, dict)
            else {},
            "event_log_summary": copy.deepcopy(event_log_summary)
            if isinstance(event_log_summary, dict)
            else {},
            "output_schema_example": {
                "overall_trajectory": "mixed",
                "main_barrier": "risk_concern",
                "support_takeaway": "helpful",
                "future_orientation": "seek_help",
                "short_quote": "我不是完全不会，只是怕再踩坑。",
                "judge_confidence": 0.79,
            },
        },
        output_keys=_FINAL_INTERVIEW_KEYS,
        repair_schema_text=(
            "- overall_trajectory must be one of improved, worsened, mixed, stable\n"
            "- main_barrier must be one of verification_friction, form_complexity, risk_concern, "
            "info_overload, low_control, mixed\n"
            "- support_takeaway must be one of helpful, limited, ineffective, not_needed\n"
            "- future_orientation must be one of try_self, seek_help, avoid, mixed\n"
            "- short_quote must be a short natural sentence\n"
            "- judge_confidence must be a float in [0,1]"
        ),
        sanitize_fn=_sanitize_final_interview,
        timeout=int(config.proto_llm_psychology_timeout),
        retries=int(config.proto_llm_psychology_retries),
    )
    if payload is None:
        fallback_payload = fallback.to_dict()
        fallback_payload.update(
            {
                "status": status,
                "source": _fallback_source_for_status(status),
            }
        )
        return FinalInterviewResult(
            **fallback_payload,
        )
    if float(payload["judge_confidence"]) < float(config.proto_llm_psychology_min_confidence):
        fallback_payload = fallback.to_dict()
        fallback_payload.update(
            {
                "confidence": float(payload["judge_confidence"]),
                "status": "low_confidence",
                "source": "rule_fallback_low_confidence",
            }
        )
        return FinalInterviewResult(
            **fallback_payload,
        )
    return FinalInterviewResult(
        overall_trajectory=str(payload["overall_trajectory"]),
        main_barrier=str(payload["main_barrier"]),
        support_takeaway=str(payload["support_takeaway"]),
        future_orientation=str(payload["future_orientation"]),
        short_quote=str(payload["short_quote"])[:120],
        confidence=float(payload["judge_confidence"]),
        source="llm",
        status=status,
    )
