from __future__ import annotations

import json
import re
from typing import Any

from config_runtime import load_runtime_config

from .models import AttemptOutcome, DigitalTask, EventAttributionResult

ATTRIBUTABLE_OUTCOMES = {
    "failure_after_attempt",
    "failure_even_with_help",
    "abandon_midway",
}
_EXPECTED_KEYS = {
    "event_attribution_locus",
    "event_attribution_stability",
    "event_attribution_scope_amplitude",
    "event_attribution_explanation",
    "judge_confidence",
}
_LOCUS_LABELS = {"self", "mixed", "situation"}
_STABILITY_LABELS = {"transient", "mixed", "stable"}
_SCOPE_LABELS = {"task_specific", "mixed", "family_generalizing"}
_ATTRIBUTION_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_PROMPT_VERSION = "v4_six_family_scope_amplitude_20260429"
_TASK_FAMILY_DESCRIPTIONS = {
    "navigation_service_location": (
        "finding the correct service entry point, understanding page structure, "
        "and avoiding navigation dead ends"
    ),
    "account_login_verification": (
        "account access, password or code entry, identity checks, and security verification"
    ),
    "information_search_judgment": (
        "searching, filtering, reading, and judging whether digital information is trustworthy"
    ),
    "profile_form_upload": (
        "entering personal details, matching required formats, and uploading photos or files"
    ),
    "service_application_submission": (
        "choosing service options and completing a multi-step application, booking, or submission"
    ),
    "payment_risk_confirmation": (
        "checking amount, payee, payment method, and handling money-related risk warnings"
    ),
}


def clear_event_attribution_cache() -> None:
    _ATTRIBUTION_CACHE.clear()


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bucket(value: float, low: float, high: float) -> str:
    if value < low:
        return "low"
    if value < high:
        return "mid"
    return "high"


def _compact_text(value: Any, max_chars: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def _normalize_block(value: Any, max_chars: int = 240) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return _compact_text(value, max_chars=max_chars)


def _stable_json_text(value: Any, max_chars: int = 320) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    else:
        text = str(value)
    return _compact_text(text, max_chars=max_chars)


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


def _fallback_result(
    *,
    mode: str,
    status: str,
    source: str,
    cache_hit: bool,
) -> EventAttributionResult:
    return EventAttributionResult(
        mode=mode,
        status=status,
        source=source,
        event_attribution_locus="not_applicable",
        event_attribution_stability="not_applicable",
        event_attribution_scope="not_applicable",
        event_attribution_scope_amplitude=0.0,
        event_attribution_explanation="",
        judge_confidence=0.0,
        cache_hit=cache_hit,
    )


def _not_applicable_result(mode: str) -> EventAttributionResult:
    return EventAttributionResult(
        mode=mode,
        status="not_applicable",
        source="not_applicable",
        event_attribution_locus="not_applicable",
        event_attribution_stability="not_applicable",
        event_attribution_scope="not_applicable",
        event_attribution_scope_amplitude=0.0,
        event_attribution_explanation="",
        judge_confidence=0.0,
        cache_hit=False,
    )


def _scope_label_from_amplitude(value: float) -> str:
    amplitude = _clamp(value, 0.0, 1.0)
    if amplitude < 0.20:
        return "task_specific"
    if amplitude < 0.60:
        return "mixed"
    return "family_generalizing"


def _sanitize_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or set(payload.keys()) != _EXPECTED_KEYS:
        return None

    locus = str(payload.get("event_attribution_locus", "")).strip()
    stability = str(payload.get("event_attribution_stability", "")).strip()
    explanation = payload.get("event_attribution_explanation")
    amplitude = payload.get("event_attribution_scope_amplitude")
    confidence = payload.get("judge_confidence")

    if locus not in _LOCUS_LABELS or stability not in _STABILITY_LABELS:
        return None
    if not isinstance(explanation, str):
        return None
    try:
        amplitude_value = _clamp(float(amplitude), 0.0, 1.0)
        confidence_value = _clamp(float(confidence), 0.0, 1.0)
    except (TypeError, ValueError):
        return None

    return {
        "event_attribution_locus": locus,
        "event_attribution_stability": stability,
        "event_attribution_scope_amplitude": amplitude_value,
        "event_attribution_explanation": explanation.strip()[:160],
        "judge_confidence": confidence_value,
    }


def _apply_enabling_support_guard(
    *,
    payload: dict[str, Any],
    outcome: AttemptOutcome,
) -> tuple[dict[str, Any], bool]:
    if outcome.outcome_type not in {"failure_even_with_help", "abandon_midway"}:
        return payload, False
    if str(outcome.support_mode) != "enabling_support":
        return payload, False

    adjusted = dict(payload)
    changed = False
    if str(adjusted.get("event_attribution_stability")) == "stable":
        adjusted["event_attribution_stability"] = "mixed"
        changed = True
    if float(adjusted.get("event_attribution_scope_amplitude", 0.0)) >= 0.60:
        adjusted["event_attribution_scope_amplitude"] = 0.50
        changed = True
    if not changed:
        return payload, False

    explanation = str(adjusted.get("event_attribution_explanation", "")).strip()
    if explanation:
        explanation = f"{explanation} Support preserved some agency."
    else:
        explanation = "Support preserved some agency, so the setback is treated as less stable and less generalizing."
    adjusted["event_attribution_explanation"] = explanation[:160]
    return adjusted, True


def _build_cache_key(
    *,
    task: DigitalTask,
    outcome: AttemptOutcome,
    task_self_efficacy: float,
    felt_control: float,
    recent_same_task_failure_count: int,
    helplessness_now: float,
    trust_now: float,
    avoidance_now: float,
    profile_summary: Any,
    same_task_recent_context: Any,
    cross_task_recent_context: Any,
    relevant_mastery_summary: Any,
    latest_daily_reflection: Any,
    latest_stage_quote: Any,
    retrieved_similar_episodes: Any = None,
) -> tuple[Any, ...]:
    retrieved = (
        retrieved_similar_episodes
        if isinstance(retrieved_similar_episodes, dict)
        else {}
    )
    return (
        _PROMPT_VERSION,
        str(task.task_family),
        str(task.friction_type),
        str(outcome.outcome_type),
        int(outcome.event_level_uncontrollability),
        int(outcome.friction_tier),
        str(outcome.support_mode),
        _bucket(helplessness_now, 35.0, 65.0),
        _bucket(task_self_efficacy, 35.0, 65.0),
        _bucket(felt_control, 35.0, 65.0),
        _bucket(trust_now, 35.0, 65.0),
        _bucket(avoidance_now, 35.0, 65.0),
        min(max(int(recent_same_task_failure_count), 0), 4),
        _stable_json_text(profile_summary, 220),
        _stable_json_text(same_task_recent_context, 320),
        _stable_json_text(cross_task_recent_context, 320),
        _stable_json_text(relevant_mastery_summary, 220),
        _stable_json_text(latest_daily_reflection, 220),
        _compact_text(latest_stage_quote, 120),
        str(retrieved.get("condition", "structured-only")),
        str(retrieved.get("status", "disabled")),
        int(retrieved.get("count", 0) or 0),
        str(retrieved.get("hash", "")),
    )


def _build_user_payload(
    *,
    task: DigitalTask,
    outcome: AttemptOutcome,
    task_self_efficacy: float,
    felt_control: float,
    recent_same_task_failure_count: int,
    helplessness_now: float,
    trust_now: float,
    avoidance_now: float,
    profile_summary: Any,
    same_task_recent_context: Any,
    cross_task_recent_context: Any,
    relevant_mastery_summary: Any,
    latest_daily_reflection: Any,
    latest_stage_quote: Any,
    retrieved_similar_episodes: Any = None,
) -> dict[str, Any]:
    retrieved = (
        retrieved_similar_episodes
        if isinstance(retrieved_similar_episodes, dict)
        else {}
    )
    return {
        "prompt_version": _PROMPT_VERSION,
        "task": (
            "Infer the agent's event-level attribution after this negative "
            "digital event."
        ),
        "goal": (
            "Estimate how the agent would explain this setback to themself on "
            "three dimensions: who caused it, whether it will continue, and "
            "how strongly it may spread to similar digital tasks."
        ),
        "dimension_definitions": {
            "event_attribution_locus": {
                "question": "Who does the agent mainly blame right now?",
                "labels": {
                    "self": (
                        "The agent mainly thinks their own ability, understanding, "
                        "confidence, or competence caused the setback."
                    ),
                    "mixed": (
                        "Both the agent's own limitations and the situation are "
                        "clearly active in the explanation."
                    ),
                    "situation": (
                        "The agent mainly thinks the interface, process, risk, "
                        "support conditions, or external setup caused the setback."
                    ),
                },
            },
            "event_attribution_stability": {
                "question": (
                    "Does the agent think this kind of difficulty will continue "
                    "for them?"
                ),
                "labels": {
                    "transient": (
                        "The setback feels temporary, improvable, or not likely "
                        "to persist."
                    ),
                    "mixed": (
                        "The agent is uncertain whether this difficulty will persist."
                    ),
                    "stable": (
                        "The agent feels this kind of difficulty is likely to keep "
                        "happening."
                    ),
                },
            },
            "event_attribution_scope_amplitude": {
                "question": (
                    "How strongly does the agent think this problem may spread "
                    "from this task to similar digital tasks?"
                ),
                "scale": {
                    "0.0": "No spillover beyond the current task or situation.",
                    "0.5": "Some spillover to similar digital tasks, but not broad generalization.",
                    "1.0": "Clear expectation that similar digital tasks may also go wrong.",
                },
            },
        },
        "decision_rules": [
            (
                "Use self only when the evidence mainly supports an internal "
                "explanation such as lack of ability, understanding, confidence, "
                "or competence."
            ),
            (
                "Use situation only when the evidence mainly supports an external "
                "explanation such as confusing design, risky environment, low-quality "
                "support, or difficult procedures."
            ),
            (
                "Use mixed only when both internal and external causes are clearly "
                "supported by the evidence."
            ),
            (
                "Use transient when the setback looks temporary, buffered by support, "
                "or outweighed by recent mastery evidence."
            ),
            (
                "Use stable when repeated evidence suggests the agent expects similar "
                "failure again."
            ),
            (
                "Set event_attribution_scope_amplitude near 0 only when the problem "
                "looks limited to this task or situation."
            ),
            (
                "Set event_attribution_scope_amplitude near 1 only when there is "
                "clear evidence that the agent is extending this belief to similar digital tasks."
            ),
            "A single failure should not automatically imply high scope amplitude.",
            (
                "Recent controllable success should keep scope amplitude lower unless strong contrary evidence exists."
            ),
            (
                "Failure even with support can increase stability, but enabling support "
                "can still preserve some sense of agency."
            ),
            (
                "If support was enabling rather than substituting, avoid very high scope amplitude unless repeated evidence still strongly supports it."
            ),
            (
                "Low felt control and low task self-efficacy can strengthen stable "
                "interpretations, but they do not force self blame."
            ),
            "When cross-task evidence is absent, keep scope amplitude low.",
            (
                "Repeated similar failures in Retrieved Similar Episodes can increase "
                "stability and scope amplitude."
            ),
            (
                "Similar recovery or enabling help in Retrieved Similar Episodes can "
                "reduce stability and scope amplitude."
            ),
            (
                "Empty Retrieved Similar Episodes means there is no extra episodic "
                "evidence from stream memory."
            ),
            (
                "Retrieved Similar Episodes are evidence for attribution only, not "
                "direct numeric updates."
            ),
            "Return a single best amplitude based on the evidence; do not hedge with text outside the JSON.",
        ],
        "context_blocks": {
            "agent_profile": _normalize_block(profile_summary, max_chars=320),
            "current_state": {
                "helplessness_now": round(float(helplessness_now), 4),
                "task_self_efficacy": round(float(task_self_efficacy), 4),
                "felt_control": round(float(felt_control), 4),
                "trust_now": round(float(trust_now), 4),
                "avoidance_now": round(float(avoidance_now), 4),
                "recent_same_task_failure_count": int(recent_same_task_failure_count),
            },
            "current_event": {
                "task_family": task.task_family,
                "friction_type": task.friction_type,
                "outcome_type": outcome.outcome_type,
                "friction_tier": int(outcome.friction_tier),
                "event_level_uncontrollability": int(
                    outcome.event_level_uncontrollability
                ),
                "support_mode": str(outcome.support_mode),
            },
            "task_family_reference": _TASK_FAMILY_DESCRIPTIONS,
            "memory_query_1": (
                "What recent experiences has the agent had with this same task?"
            ),
            "memory_retrieval_1": _normalize_block(
                same_task_recent_context,
                max_chars=400,
            ),
            "memory_query_2": (
                "What recent experiences has the agent had with similar digital tasks?"
            ),
            "memory_retrieval_2": _normalize_block(
                cross_task_recent_context,
                max_chars=400,
            ),
            "memory_query_3": (
                "What recent controllable successes or failures are most relevant "
                "for interpreting this event?"
            ),
            "memory_retrieval_3": _normalize_block(
                relevant_mastery_summary,
                max_chars=320,
            ),
            "recent_reflection": _normalize_block(
                latest_daily_reflection,
                max_chars=240,
            ),
            "recent_stage_quote": _compact_text(latest_stage_quote, 160),
            "Retrieved Similar Episodes": str(retrieved.get("text", "Nothing")),
        },
        "reference_cases": [
            {
                "case_name": (
                    "Single confusing setback with otherwise decent recent experience"
                ),
                "evidence": (
                    "A first-time verification failure happened in a confusing interface. "
                    "Other recent digital tasks went reasonably well. The agent still has "
                    "some felt control."
                ),
                "preferred_labels": {
                    "event_attribution_locus": "situation",
                    "event_attribution_stability": "transient",
                    "event_attribution_scope_amplitude": 0.10,
                },
            },
            {
                "case_name": (
                    "Repeated failure across similar tasks with growing helplessness"
                ),
                "evidence": (
                    "The agent has repeatedly failed in payment, verification, and "
                    "appointment tasks, shows low self-efficacy, low felt control, "
                    "and increasing avoidance, with little recent mastery evidence."
                ),
                "preferred_labels": {
                    "event_attribution_locus": "self",
                    "event_attribution_stability": "stable",
                    "event_attribution_scope_amplitude": 0.85,
                },
            },
            {
                "case_name": (
                    "Failure with enabling support but agency partly preserved"
                ),
                "evidence": (
                    "The event failed even though support was available, but the support "
                    "helped the agent understand part of the task and preserved some agency."
                ),
                "preferred_labels": {
                    "event_attribution_locus": "mixed",
                    "event_attribution_stability": "mixed",
                    "event_attribution_scope_amplitude": 0.25,
                },
            },
        ],
        "output_requirements": [
            "Return exactly one JSON object.",
            "Use only the allowed labels.",
            (
                "event_attribution_explanation must be short, concrete, and grounded "
                "in the evidence."
            ),
            "judge_confidence must be a float between 0 and 1.",
            "Do not include any extra keys.",
            "Do not output markdown, commentary, or natural language outside JSON.",
        ],
        "json_schema_template": {
            "event_attribution_locus": "<self|mixed|situation>",
            "event_attribution_stability": "<transient|mixed|stable>",
            "event_attribution_scope_amplitude": 0.0,
            "event_attribution_explanation": "<short concrete explanation>",
            "judge_confidence": 0.0,
        },
    }


async def _query_llm_payload(
    *,
    llm: Any,
    payload: dict[str, Any],
    timeout: int,
    retries: int,
) -> dict[str, Any] | None:
    if llm is None:
        return None

    dialog = [
        {
            "role": "system",
            "content": (
                "You are the bounded self-explanation module for an older adult agent "
                "in a digital-friction simulation.\n\n"
                "Your job is to infer how the agent would explain this setback to "
                "themself immediately after the event, using only the evidence "
                "provided in the profile, current state, event, and memory blocks.\n\n"
                "Important rules:\n"
                "- Infer the agent's own explanation, not an outside research diagnosis.\n"
                "- Stay grounded in the provided evidence only.\n"
                "- Do not invent missing experiences or hidden causes.\n"
                "- Do not default to mixed when one side is clearly stronger.\n"
                "- A single setback should not automatically become stable or "
                "high-scope.\n"
                "- Empty or missing blocks mean there is no reliable evidence from "
                "that source.\n"
                "- Return exactly one JSON object and nothing else."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]
    try:
        raw = await llm.atext_request(
            dialog=dialog,
            temperature=0.1,
            timeout=timeout,
            retries=retries,
            max_tokens=220,
        )
    except Exception:
        return None

    parsed = _extract_json_object(str(raw))
    if parsed is None:
        return None
    return _sanitize_payload(parsed)


async def infer_event_attribution(
    *,
    llm: Any,
    task: DigitalTask,
    outcome: AttemptOutcome,
    task_self_efficacy: float,
    felt_control: float,
    recent_same_task_failure_count: int,
    helplessness_now: float = 0.0,
    trust_now: float = 0.0,
    avoidance_now: float = 0.0,
    profile_summary: Any = None,
    same_task_recent_context: Any = None,
    cross_task_recent_context: Any = None,
    relevant_mastery_summary: Any = None,
    latest_daily_reflection: Any = None,
    latest_stage_quote: Any = "",
    retrieved_similar_episodes: Any = None,
) -> EventAttributionResult:
    config = load_runtime_config()
    mode = str(config.proto_llm_psychology_mode)

    if outcome.outcome_type not in ATTRIBUTABLE_OUTCOMES:
        return _not_applicable_result(mode)

    if mode != "hybrid":
        return _fallback_result(
            mode=mode,
            status="disabled",
            source="conservative_fallback_disabled",
            cache_hit=False,
        )
    if llm is None:
        return _fallback_result(
            mode=mode,
            status="unavailable",
            source="conservative_fallback_unavailable",
            cache_hit=False,
        )

    cache_hit = False
    payload: dict[str, Any] | None = None
    cache_key = _build_cache_key(
        task=task,
        outcome=outcome,
        task_self_efficacy=task_self_efficacy,
        felt_control=felt_control,
        recent_same_task_failure_count=recent_same_task_failure_count,
        helplessness_now=helplessness_now,
        trust_now=trust_now,
        avoidance_now=avoidance_now,
        profile_summary=profile_summary,
        same_task_recent_context=same_task_recent_context,
        cross_task_recent_context=cross_task_recent_context,
        relevant_mastery_summary=relevant_mastery_summary,
        latest_daily_reflection=latest_daily_reflection,
        latest_stage_quote=latest_stage_quote,
        retrieved_similar_episodes=retrieved_similar_episodes,
    )
    if bool(config.proto_llm_psychology_cache_enabled):
        payload = _ATTRIBUTION_CACHE.get(cache_key)
        cache_hit = payload is not None

    if payload is None:
        payload = await _query_llm_payload(
            llm=llm,
            payload=_build_user_payload(
                task=task,
                outcome=outcome,
                task_self_efficacy=task_self_efficacy,
                felt_control=felt_control,
                recent_same_task_failure_count=recent_same_task_failure_count,
                helplessness_now=helplessness_now,
                trust_now=trust_now,
                avoidance_now=avoidance_now,
                profile_summary=profile_summary,
                same_task_recent_context=same_task_recent_context,
                cross_task_recent_context=cross_task_recent_context,
                relevant_mastery_summary=relevant_mastery_summary,
                latest_daily_reflection=latest_daily_reflection,
                latest_stage_quote=latest_stage_quote,
                retrieved_similar_episodes=retrieved_similar_episodes,
            ),
            timeout=int(config.proto_llm_psychology_timeout),
            retries=int(config.proto_llm_psychology_retries),
        )
        if payload is None:
            return _fallback_result(
                mode=mode,
                status="request_error",
                source="conservative_fallback_request_error",
                cache_hit=False,
            )
        if bool(config.proto_llm_psychology_cache_enabled):
            _ATTRIBUTION_CACHE[cache_key] = payload

    confidence = float(payload["judge_confidence"])
    if confidence < float(config.proto_llm_psychology_min_confidence):
        return _fallback_result(
            mode=mode,
            status="low_confidence",
            source="conservative_fallback_low_confidence",
            cache_hit=cache_hit,
        )

    payload, support_guard_applied = _apply_enabling_support_guard(
        payload=payload,
        outcome=outcome,
    )
    confidence = float(payload["judge_confidence"])

    return EventAttributionResult(
        mode=mode,
        status="ok",
        source=(
            "llm_classified_support_guarded"
            if support_guard_applied
            else "llm_classified"
        ),
        event_attribution_locus=str(payload["event_attribution_locus"]),
        event_attribution_stability=str(payload["event_attribution_stability"]),
        event_attribution_scope=_scope_label_from_amplitude(
            float(payload["event_attribution_scope_amplitude"])
        ),
        event_attribution_scope_amplitude=float(
            payload["event_attribution_scope_amplitude"]
        ),
        event_attribution_explanation=str(
            payload["event_attribution_explanation"]
        ).strip()[:160],
        judge_confidence=confidence,
        cache_hit=cache_hit,
    )
