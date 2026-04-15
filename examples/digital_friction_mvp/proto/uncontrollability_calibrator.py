from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from config_runtime import load_runtime_config

from .models import AttemptOutcome, AttemptStrategy, DigitalTask

CALIBRATABLE_OUTCOMES = {
    "failure_after_attempt",
    "failure_even_with_help",
    "abandon_midway",
    "avoid_without_attempt",
}
SUCCESS_OUTCOMES = {"success_self", "success_with_help"}
_EXPECTED_KEYS = {
    "perceived_uncontrollability",
    "confidence",
    "reason",
}
_CALIBRATION_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_CALIBRATION_PROMPT_VERSION = "v2_contextual_action_outcome_20260406"


@dataclass(slots=True)
class UncontrollabilityCalibrationResult:
    mode: str
    rule_value: int
    llm_value: int | None
    final_value: int
    confidence: float
    reason: str
    status: str
    source: str
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clear_uncontrollability_calibration_cache() -> None:
    _CALIBRATION_CACHE.clear()


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


def _failure_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    return "2plus"


def _appraisal_bucket(value: Any) -> str:
    numeric = _safe_float(value, 50.0)
    if numeric < 35.0:
        return "low"
    if numeric < 65.0:
        return "mid"
    return "high"


def _memory_bucket(value: Any) -> str:
    numeric = _safe_float(value, 0.0)
    if numeric < 0.10:
        return "none"
    if numeric < 0.35:
        return "some"
    return "strong"


def _avoid_reason_bucket(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"helpless_avoid", "risk_avoid", "low_value_avoid"}:
        return text
    return "not_applicable"


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


def _consecutive_failures_after_event(
    outcome_type: str,
    consecutive_failures_before: int,
) -> int:
    if outcome_type in SUCCESS_OUTCOMES:
        return 0
    if outcome_type == "avoid_without_attempt":
        return int(consecutive_failures_before)
    return int(consecutive_failures_before) + 1


def _build_cache_key(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    helplessness_now: float,
    consecutive_failures_before: int,
    rule_value: int,
    pre_event_task_appraisal: Any = None,
    task_relevant_memory: Any = None,
) -> tuple[Any, ...]:
    appraisal = (
        pre_event_task_appraisal if isinstance(pre_event_task_appraisal, dict) else {}
    )
    task_memory = task_relevant_memory if isinstance(task_relevant_memory, dict) else {}
    return (
        _CALIBRATION_PROMPT_VERSION,
        str(task.task_family),
        str(task.friction_type),
        _difficulty_bucket(float(task.difficulty)),
        str(strategy.strategy_type),
        str(outcome.outcome_type),
        int(outcome.support_quality),
        int(outcome.friction_tier),
        _helplessness_bucket(float(helplessness_now)),
        _failure_bucket(int(consecutive_failures_before)),
        int(rule_value),
        _appraisal_bucket(appraisal.get("felt_control", 50.0)),
        _appraisal_bucket(appraisal.get("expected_help_effectiveness", 50.0)),
        _failure_bucket(int(task_memory.get("same_task_failure_count", 0))),
        _memory_bucket(task_memory.get("same_task_controllable_success_memory", 0.0)),
        _avoid_reason_bucket(getattr(outcome, "avoid_reason", "not_applicable")),
        _recent_outcome_pattern_bucket(
            task_memory.get("recent_same_task_outcomes_tail", [])
        ),
    )


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


def _sanitize_payload(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if set(payload.keys()) != _EXPECTED_KEYS:
        return None, "invalid_schema"

    perceived = payload.get("perceived_uncontrollability")
    if isinstance(perceived, bool):
        return None, "invalid_schema"
    try:
        perceived_value = int(perceived)
    except (TypeError, ValueError):
        return None, "invalid_schema"
    if perceived_value not in {0, 1, 2}:
        return None, "invalid_schema"

    confidence_raw = payload.get("confidence")
    if isinstance(confidence_raw, bool):
        return None, "invalid_schema"
    try:
        confidence = _clamp(float(confidence_raw), 0.0, 1.0)
    except (TypeError, ValueError):
        return None, "invalid_schema"

    reason_raw = payload.get("reason")
    if not isinstance(reason_raw, str):
        return None, "invalid_schema"

    return (
        {
            "perceived_uncontrollability": perceived_value,
            "confidence": confidence,
            "reason": reason_raw.strip()[:120],
        },
        "ok",
    )


def _build_user_payload(
    *,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    env: dict[str, Any],
    helplessness_now: float,
    consecutive_failures_before: int,
    consecutive_failures_after_event: int,
    rule_value: int,
    pre_event_task_appraisal: Any = None,
    task_relevant_memory: Any = None,
) -> dict[str, Any]:
    appraisal = (
        pre_event_task_appraisal if isinstance(pre_event_task_appraisal, dict) else {}
    )
    task_memory = task_relevant_memory if isinstance(task_relevant_memory, dict) else {}
    return {
        "prompt_version": _CALIBRATION_PROMPT_VERSION,
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
            "consecutive_failures_after_event": int(consecutive_failures_after_event),
        },
        "world_env_levels": {
            "friction_level": int(float(env.get("friction_level", 0))),
            "malicious_friction_level": int(
                float(env.get("malicious_friction_level", 0))
            ),
            "complexity_level": int(float(env.get("complexity_level", 0))),
            "risk_level": int(float(env.get("risk_level", 0))),
            "assist_level": int(float(env.get("assist_level", 0))),
            "accessibility_level": int(float(env.get("accessibility_level", 0))),
            "human_support_level": int(float(env.get("human_support_level", 0))),
        },
        "pre_event_appraisal": {
            "felt_control": round(_safe_float(appraisal.get("felt_control", 50.0)), 4),
            "perceived_task_risk": round(
                _safe_float(appraisal.get("perceived_task_risk", 50.0)),
                4,
            ),
            "expected_help_effectiveness": round(
                _safe_float(appraisal.get("expected_help_effectiveness", 50.0)),
                4,
            ),
            "task_value": round(_safe_float(appraisal.get("task_value", 50.0)), 4),
        },
        "same_task_history": {
            "same_task_attempt_count": int(
                _safe_int(task_memory.get("same_task_attempt_count", 0), 0)
            ),
            "same_task_failure_count": int(
                _safe_int(task_memory.get("same_task_failure_count", 0), 0)
            ),
            "same_task_failure_streak": int(
                _safe_int(task_memory.get("same_task_failure_streak", 0), 0)
            ),
            "same_task_last_outcome": str(
                task_memory.get("same_task_last_outcome", "")
            ).strip(),
            "same_task_controllable_success_memory": round(
                _safe_float(
                    task_memory.get("same_task_controllable_success_memory", 0.0)
                ),
                4,
            ),
            "help_success_rate_same_task": round(
                _safe_float(task_memory.get("help_success_rate_same_task", 0.5)),
                4,
            ),
            "has_controllable_success_evidence": bool(
                task_memory.get("has_controllable_success_evidence", False)
            ),
            "recent_same_task_outcomes_tail": [
                str(item or "").strip()
                for item in task_memory.get("recent_same_task_outcomes_tail", [])
                if str(item or "").strip()
            ],
        },
        "rule_baseline_uncontrollability": int(rule_value),
    }


async def _query_llm_payload(
    *,
    llm: Any,
    payload: dict[str, Any],
    timeout: int,
    retries: int,
) -> tuple[dict[str, Any] | None, str]:
    if llm is None:
        return None, "request_error"

    system_prompt = (
        "You are a strict JSON-only calibrator for perceived uncontrollability in a "
        "digital-friction simulation. Judge whether this event makes the person feel "
        "that continued effort can no longer change the result. Output exactly one "
        "valid JSON object and nothing else."
    )
    user_prompt = {
        "task": "Estimate perceived_uncontrollability for this single event.",
        "scale_definition": {
            "0": "low uncontrollability: the problem feels clear, recoverable, and still manageable",
            "1": "medium uncontrollability: noticeable obstacle or uncertainty, but not total loss of control",
            "2": "high uncontrollability: the person strongly feels the situation is out of control, especially under high friction, repeated failures, or failure even with help",
        },
        "constraints": {
            "perceived_uncontrollability": [0, 1, 2],
            "confidence": [0.0, 1.0],
            "reason_max_chars": 120,
            "guideline": "Stay close to the rule baseline unless there is strong evidence to deviate.",
        },
        "judging_rules": [
            "Focus on whether action and outcome feel decoupled, not merely whether the event was unpleasant.",
            "Risk-based avoidance does not automatically mean high uncontrollability.",
            "Low-value avoidance does not automatically mean high uncontrollability.",
            "Recent controllable success on the same task is counter-evidence against high uncontrollability.",
            "Failure even with help can increase uncontrollability when it supports the feeling that effort no longer works.",
        ],
        "context": payload,
        "output_schema_example": {
            "perceived_uncontrollability": 1,
            "confidence": 0.72,
            "reason": "Repeated failure under meaningful friction suggests moderate loss of control.",
        },
    }
    dialog = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Return one JSON object only.\n"
                + json.dumps(user_prompt, ensure_ascii=False)
            ),
        },
    ]

    first_error = "parse_failed"
    try:
        raw = await llm.atext_request(
            dialog=dialog,
            temperature=0.1,
            timeout=timeout,
            retries=retries,
            max_tokens=220,
        )
    except Exception:
        return None, "request_error"

    parsed = _extract_json_object(str(raw))
    if parsed is not None:
        sanitized, status = _sanitize_payload(parsed)
        if sanitized is not None:
            return sanitized, "ok"
        first_error = status

    repair_dialog = [
        {
            "role": "system",
            "content": (
                "You are a strict JSON reformatter. Return exactly one valid JSON object "
                "with keys: perceived_uncontrollability, confidence, reason."
            ),
        },
        {
            "role": "user",
            "content": (
                "Rules:\n"
                "- perceived_uncontrollability must be 0, 1, or 2\n"
                "- confidence must be a float in [0,1]\n"
                "- reason must be <= 120 chars\n"
                "- Do not output markdown or extra text\n"
                "Original context:\n"
                + json.dumps(payload, ensure_ascii=False)
                + "\nRaw model output:\n"
                + str(raw)[:1200]
            ),
        },
    ]
    try:
        repaired = await llm.atext_request(
            dialog=repair_dialog,
            temperature=0.0,
            timeout=timeout,
            retries=1,
            max_tokens=160,
        )
    except Exception:
        return None, "request_error"

    repaired_payload = _extract_json_object(str(repaired))
    if repaired_payload is None:
        return None, first_error if first_error == "invalid_schema" else "parse_failed"
    sanitized, status = _sanitize_payload(repaired_payload)
    if sanitized is None:
        return None, status
    return sanitized, "ok_repaired"


def _fallback_source_for_status(status: str) -> str:
    if status == "invalid_schema":
        return "rule_fallback_invalid_schema"
    if status == "low_confidence":
        return "rule_fallback_low_confidence"
    if status == "parse_failed":
        return "rule_fallback_parse_failed"
    return "rule_fallback_request_error"


async def calibrate_uncontrollability(
    *,
    llm: Any,
    task: DigitalTask,
    strategy: AttemptStrategy,
    outcome: AttemptOutcome,
    env: dict[str, Any],
    helplessness_now: float,
    consecutive_failures_before: int,
    pre_event_task_appraisal: Any = None,
    task_relevant_memory: Any = None,
) -> UncontrollabilityCalibrationResult:
    config = load_runtime_config()
    mode = str(config.proto_llm_uncontrollability_mode)
    rule_value = int(
        getattr(outcome, "rule_perceived_uncontrollability", outcome.perceived_uncontrollability)
    )

    if mode != "hybrid":
        return UncontrollabilityCalibrationResult(
            mode=mode,
            rule_value=rule_value,
            llm_value=None,
            final_value=rule_value,
            confidence=0.0,
            reason="",
            status="disabled",
            source="rule",
            cache_hit=False,
        )

    if outcome.outcome_type in SUCCESS_OUTCOMES:
        return UncontrollabilityCalibrationResult(
            mode=mode,
            rule_value=rule_value,
            llm_value=None,
            final_value=rule_value,
            confidence=0.0,
            reason="",
            status="success_short_circuit",
            source="rule_success_short_circuit",
            cache_hit=False,
        )

    if outcome.outcome_type not in CALIBRATABLE_OUTCOMES:
        return UncontrollabilityCalibrationResult(
            mode=mode,
            rule_value=rule_value,
            llm_value=None,
            final_value=rule_value,
            confidence=0.0,
            reason="",
            status="not_applicable",
            source="rule",
            cache_hit=False,
        )

    cache_hit = False
    payload: dict[str, Any] | None = None
    status = "ok"
    cache_key = _build_cache_key(
        task=task,
        strategy=strategy,
        outcome=outcome,
        helplessness_now=helplessness_now,
        consecutive_failures_before=consecutive_failures_before,
        rule_value=rule_value,
        pre_event_task_appraisal=pre_event_task_appraisal,
        task_relevant_memory=task_relevant_memory,
    )

    if bool(config.proto_llm_uncontrollability_cache_enabled):
        payload = _CALIBRATION_CACHE.get(cache_key)
        cache_hit = payload is not None

    if payload is None:
        consecutive_after = _consecutive_failures_after_event(
            outcome.outcome_type,
            consecutive_failures_before,
        )
        llm_payload, status = await _query_llm_payload(
            llm=llm,
            payload=_build_user_payload(
                task=task,
                strategy=strategy,
                outcome=outcome,
                env=env,
                helplessness_now=helplessness_now,
                consecutive_failures_before=consecutive_failures_before,
                consecutive_failures_after_event=consecutive_after,
                rule_value=rule_value,
                pre_event_task_appraisal=pre_event_task_appraisal,
                task_relevant_memory=task_relevant_memory,
            ),
            timeout=int(config.proto_llm_uncontrollability_timeout),
            retries=int(config.proto_llm_uncontrollability_retries),
        )
        if llm_payload is None:
            return UncontrollabilityCalibrationResult(
                mode=mode,
                rule_value=rule_value,
                llm_value=None,
                final_value=rule_value,
                confidence=0.0,
                reason="",
                status=status,
                source=_fallback_source_for_status(status),
                cache_hit=False,
            )
        payload = llm_payload
        if bool(config.proto_llm_uncontrollability_cache_enabled):
            _CALIBRATION_CACHE[cache_key] = payload

    llm_value = int(payload["perceived_uncontrollability"])
    confidence = _clamp(payload["confidence"], 0.0, 1.0)
    reason = str(payload["reason"]).strip()[:120]
    if confidence < float(config.proto_llm_uncontrollability_min_confidence):
        return UncontrollabilityCalibrationResult(
            mode=mode,
            rule_value=rule_value,
            llm_value=llm_value,
            final_value=rule_value,
            confidence=confidence,
            reason=reason,
            status="low_confidence",
            source="rule_fallback_low_confidence",
            cache_hit=cache_hit,
        )

    max_shift = int(config.proto_llm_uncontrollability_max_shift)
    diff = llm_value - rule_value
    shifted = max(-max_shift, min(max_shift, diff))
    final_value = int(_clamp(rule_value + shifted, 0, 2))
    source = "llm_confirmed" if final_value == rule_value else "hybrid_shifted"
    return UncontrollabilityCalibrationResult(
        mode=mode,
        rule_value=rule_value,
        llm_value=llm_value,
        final_value=final_value,
        confidence=confidence,
        reason=reason,
        status=status,
        source=source,
        cache_hit=cache_hit,
    )
