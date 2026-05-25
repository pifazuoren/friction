from __future__ import annotations

import hashlib
import json
import os
import random
import re
from pathlib import Path
from typing import Any

from agentsociety.cityagent import SocietyAgent
from config_runtime import load_runtime_config

from .attempt_strategy import choose_attempt_strategy, compute_rule_strategy_weights
from .attribution_inference import infer_event_attribution
from .bayesian_control import update_bayesian_control_memory
from .bayesian_controllability_lite import (
    apply_controllability_gated_modulation,
    combine_huys_dayan_lite_audits,
    compute_huys_dayan_lite_after_event_audit,
    compute_huys_dayan_lite_before_event_audit,
)
from .bayesian_policy_lite import (
    build_semantic_reference_policy,
    combine_bayesian_policy_audits,
    compute_bayesian_policy_shadow,
    update_bayesian_policy_memory,
)
from .compat import apply_compatibility_updates
from .experience_memory import (
    extract_memory_features,
    update_experience_memory,
)
from .models import HelplessnessUpdateInput
from .llm_psychology import (
    _extract_json_object,
    _query_json_payload,
    maybe_generate_daily_reflection,
    prepare_digital_emotion_state_for_day,
    resolve_event_appraisal,
    resolve_final_interview,
    resolve_stage_interview,
    resolve_strategy_deliberation,
    resolve_task_appraisal,
    resolve_trajectory_appraisal,
)
from .logical_clock import is_proto_logical_clock_enabled
from .outcome_model import (
    infer_avoid_reason,
    infer_support_mode,
    resolve_attempt_outcome,
    support_quality_from_env,
)
from .profile_buckets import age_bucket, persona_bucket
from .runtime import assign_task_with_entry_decision, build_stage_transition_updates
from .state_schema import build_proto_status_attributes
from .state_update import apply_helplessness_update
from .support_protocol import SupportRequest, SupportResponse
from .task_assignment import (
    MobileEntryDecision,
    decode_task,
    encode_task,
    is_task_window_tick,
    mobile_intention_candidate_hash,
    skipped_mobile_entry_decision,
    top_mobile_intention_candidates,
)
from .uncontrollability_calibrator import calibrate_uncontrollability


_STAGE_INTERVIEW_MARKER = re.compile(
    r"^\[PROTO_STAGE_INTERVIEW_V1\]\[stage=(?P<stage_name>[^\]]+)\]\[index=(?P<stage_index>\d+)\]"
)
_FINAL_INTERVIEW_MARKER = "[PROTO_FINAL_INTERVIEW_V1]"
_SURVEY_SUMMARY_FIELDS = (
    "survey_helplessness_index",
    "survey_withdrawal_index",
    "survey_self_efficacy_index",
    "survey_support_index",
    "survey_usefulness_index",
    "survey_anxiety_index",
)
_MOBILE_ENTRY_LLM_SHADOW_KEYS = {
    "selected_mobile_intention",
    "confidence",
    "reason",
}
SUPPORT_HELPER_REGISTRY_ATTRIBUTE = "_support_helper_registry"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _compact_status_text(value: Any, default: str = "unknown") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or default


def _compact_status_note(
    value: Any,
    *,
    default: str = "unknown",
    max_chars: int = 160,
) -> str:
    text = _compact_status_text(value, default=default)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text or default


def _stream_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _stream_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def _stream_uncontrollability(value: Any) -> str:
    normalized = max(0.0, min(1.0, _safe_float(value) / 2.0))
    return f"{normalized:.2f}"


def _stream_task_label(task_family: Any) -> str:
    labels = {
        "navigation_service_location": "navigation and service location",
        "account_login_verification": "account login and identity verification",
        "information_search_judgment": "information search and judgment",
        "profile_form_upload": "profile forms and material upload",
        "service_application_submission": "service application and submission",
        "payment_risk_confirmation": "payment and risk confirmation",
    }
    task_family_text = str(task_family or "")
    return labels.get(task_family_text, task_family_text.replace("_", " "))


def _stream_packet_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _stream_search_count(text: str) -> int:
    if not text or str(text).strip() == "Nothing":
        return 0
    return sum(1 for line in str(text).splitlines() if line.strip().startswith("- ["))


def _sanitize_mobile_entry_shadow(
    payload: Any,
    *,
    allowed_intentions: set[str],
    min_confidence: float,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    selected = str(payload.get("selected_mobile_intention", "")).strip()
    if selected not in allowed_intentions:
        return None, "out_of_set_intention"
    confidence = _clamp(
        _safe_float(payload.get("confidence"), 0.0),
        0.0,
        1.0,
    )
    reason = _compact_status_note(payload.get("reason", ""), default="", max_chars=120)
    return (
        {
            "selected_mobile_intention": selected,
            "confidence": confidence,
            "reason": reason,
        },
        "ok",
    )


def _append_mobile_entry_rerank_schedule(path: str, payload: dict[str, Any]) -> None:
    schedule_path = str(path or "").strip()
    if not schedule_path:
        return
    target = Path(schedule_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _stream_appraisal_condition(runtime_config: Any) -> str:
    if bool(
        getattr(runtime_config, "proto_stream_task_appraisal_retrieval_enabled", False)
    ):
        return "stream-appraisal"
    if bool(getattr(runtime_config, "proto_stream_episode_recording_enabled", True)):
        return "stream-record-only"
    return "structured-only"


def _stream_attribution_condition(runtime_config: Any) -> str:
    recording_enabled = bool(
        getattr(runtime_config, "proto_stream_episode_recording_enabled", True)
    )
    appraisal_enabled = bool(
        getattr(runtime_config, "proto_stream_task_appraisal_retrieval_enabled", False)
    )
    attribution_enabled = bool(
        getattr(runtime_config, "proto_stream_attribution_retrieval_enabled", False)
    )
    if attribution_enabled and appraisal_enabled:
        return "stream-appraisal-attribution"
    if attribution_enabled:
        return "stream-attribution-only"
    if appraisal_enabled:
        return "stream-appraisal"
    if recording_enabled:
        return "stream-record-only"
    return "structured-only"


def _format_status_time_hhmm(value: Any, default: str = "unknown") -> str:
    text = str(value or "").strip()
    match = re.search(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})", text)
    if not match:
        return default
    hour = _safe_int(match.group("hour"), -1)
    minute = _safe_int(match.group("minute"), -1)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return f"{hour:02d}:{minute:02d}"


def _decode_json_list(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    if raw_value in (None, "", "null"):
        return []
    if isinstance(raw_value, str):
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    return []


def _support_snapshot_for_task(
    help_effect_memory: Any,
    task_family: str,
) -> dict[str, Any]:
    if not isinstance(help_effect_memory, dict):
        return {}
    by_task_family = help_effect_memory.get("by_task_family", {})
    by_source = help_effect_memory.get("by_source", {})
    return {
        "overall": (
            help_effect_memory.get("overall", {})
            if isinstance(help_effect_memory.get("overall"), dict)
            else {}
        ),
        "task_family": (
            by_task_family.get(task_family, {})
            if isinstance(by_task_family, dict)
            else {}
        ),
        "source": (
            by_source.get("generic", {})
            if isinstance(by_source, dict)
            else {}
        ),
        "support_response_audit": (
            help_effect_memory.get("support_response_audit", {})
            if isinstance(help_effect_memory.get("support_response_audit"), dict)
            else {}
        ),
    }


def _summarize_event_log_for_interview(event_log: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "event_count": 0,
        "negative_count": 0,
        "success_count": 0,
        "avoid_count": 0,
        "help_used_count": 0,
        "mean_scope_amplitude": 0.0,
        "top_task_family": "",
        "top_outcome_type": "",
        "dominant_attribution_locus": "not_applicable",
        "dominant_attribution_stability": "not_applicable",
        "dominant_attribution_scope": "not_applicable",
    }
    if not event_log:
        return summary
    task_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    attribution_locus_counts: dict[str, int] = {}
    attribution_stability_counts: dict[str, int] = {}
    attribution_scope_counts: dict[str, int] = {}
    scope_amplitude_values: list[float] = []
    for item in event_log:
        summary["event_count"] += 1
        decision = item.get("decision", {}) if isinstance(item, dict) else {}
        task_family = str(
            item.get("scenario")
            or (decision.get("task_family") if isinstance(decision, dict) else "")
            or ""
        ).strip()
        outcome_type = str(
            (decision.get("primary_reason") if isinstance(decision, dict) else "")
            or ""
        ).strip()
        if task_family:
            task_counts[task_family] = task_counts.get(task_family, 0) + 1
        if outcome_type:
            outcome_counts[outcome_type] = outcome_counts.get(outcome_type, 0) + 1
        locus = str(
            decision.get("event_attribution_locus", "")
            if isinstance(decision, dict)
            else ""
        ).strip()
        stability = str(
            decision.get("event_attribution_stability", "")
            if isinstance(decision, dict)
            else ""
        ).strip()
        scope = str(
            decision.get("event_attribution_scope", "")
            if isinstance(decision, dict)
            else ""
        ).strip()
        scope_amplitude = _safe_float(
            decision.get("event_attribution_scope_amplitude", 0.0)
            if isinstance(decision, dict)
            else 0.0
        )
        if locus and locus != "not_applicable":
            attribution_locus_counts[locus] = attribution_locus_counts.get(locus, 0) + 1
        if stability and stability != "not_applicable":
            attribution_stability_counts[stability] = (
                attribution_stability_counts.get(stability, 0) + 1
            )
        if scope and scope != "not_applicable":
            attribution_scope_counts[scope] = attribution_scope_counts.get(scope, 0) + 1
        if scope_amplitude > 0.0:
            scope_amplitude_values.append(scope_amplitude)
        if outcome_type in {"success_self", "success_with_help"}:
            summary["success_count"] += 1
        if outcome_type == "avoid_without_attempt":
            summary["avoid_count"] += 1
        if outcome_type in {
            "failure_after_attempt",
            "failure_even_with_help",
            "abandon_midway",
        }:
            summary["negative_count"] += 1
        if str(decision.get("strategy_type", "")).strip() == "seek_help_then_attempt":
            summary["help_used_count"] += 1
    if task_counts:
        summary["top_task_family"] = max(
            task_counts.items(), key=lambda item: (item[1], item[0])
        )[0]
    if outcome_counts:
        summary["top_outcome_type"] = max(
            outcome_counts.items(), key=lambda item: (item[1], item[0])
        )[0]
    if attribution_locus_counts:
        summary["dominant_attribution_locus"] = max(
            attribution_locus_counts.items(), key=lambda item: (item[1], item[0])
        )[0]
    if attribution_stability_counts:
        summary["dominant_attribution_stability"] = max(
            attribution_stability_counts.items(), key=lambda item: (item[1], item[0])
        )[0]
    if attribution_scope_counts:
        summary["dominant_attribution_scope"] = max(
            attribution_scope_counts.items(), key=lambda item: (item[1], item[0])
        )[0]
    if scope_amplitude_values:
        summary["mean_scope_amplitude"] = round(
            sum(scope_amplitude_values) / float(len(scope_amplitude_values)),
            4,
        )
    return summary


_BACKGROUND_PRIORITY_KEYWORDS = (
    "线下",
    "验证码",
    "支付",
    "挂号",
    "风险",
    "诈骗",
    "被骗",
    "视力",
    "复杂",
    "小字",
    "求助",
    "帮助",
    "家人",
    "志愿者",
    "不敢",
    "焦虑",
    "放弃",
    "尝试",
)


def _compress_background_story(background_story: Any, max_chars: int = 120) -> str:
    text = re.sub(r"\s+", "", str(background_story or "")).strip()
    if not text:
        return ""
    sentences = [
        sentence.strip("，,；;。")
        for sentence in re.split(r"[。！？!?]", text)
        if str(sentence).strip()
    ]
    prioritized = [
        sentence
        for sentence in sentences
        if any(keyword in sentence for keyword in _BACKGROUND_PRIORITY_KEYWORDS)
    ]
    ordered: list[str] = []
    for sentence in prioritized + sentences:
        if sentence and sentence not in ordered:
            ordered.append(sentence)
        candidate = "。".join(ordered)
        if len(candidate) >= max_chars:
            break
    summary = "。".join(ordered[:3]).strip("。")
    if not summary:
        summary = text[:max_chars]
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip("，,；;。")
    return summary


def _extract_same_task_event_tail(
    *,
    task_family: str,
    event_log: Any,
    limit: int = 3,
) -> list[dict[str, Any]]:
    if not isinstance(event_log, list):
        return []
    tail: list[dict[str, Any]] = []
    for item in reversed(event_log):
        if not isinstance(item, dict):
            continue
        decision = item.get("decision", {})
        if not isinstance(decision, dict):
            decision = {}
        current_task_family = str(
            item.get("scenario") or decision.get("task_family") or ""
        ).strip()
        if current_task_family != str(task_family):
            continue
        tail.append(
            {
                "day": _safe_int(item.get("day"), 0),
                "outcome_type": str(decision.get("primary_reason", "")).strip(),
                "strategy_type": str(decision.get("strategy_type", "")).strip(),
                "avoid_reason": str(decision.get("avoid_reason", "")).strip(),
                "support_quality": _safe_int(decision.get("support_quality"), 0),
                "event_level_uncontrollability": _safe_int(
                    decision.get("event_level_uncontrollability"),
                    0,
                ),
            }
        )
        if len(tail) >= int(limit):
            break
    return list(reversed(tail))


def _extract_cross_task_event_tail(
    *,
    task_family: str,
    event_log: Any,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not isinstance(event_log, list):
        return []
    tail: list[dict[str, Any]] = []
    for item in reversed(event_log):
        if not isinstance(item, dict):
            continue
        decision = item.get("decision", {})
        if not isinstance(decision, dict):
            decision = {}
        current_task_family = str(
            item.get("scenario") or decision.get("task_family") or ""
        ).strip()
        if not current_task_family or current_task_family == str(task_family):
            continue
        tail.append(
            {
                "task_family": current_task_family,
                "day": _safe_int(item.get("day"), 0),
                "outcome_type": str(decision.get("primary_reason", "")).strip(),
                "avoid_reason": str(decision.get("avoid_reason", "")).strip(),
                "support_mode": str(decision.get("support_mode", "")).strip(),
                "event_level_uncontrollability": _safe_int(
                    decision.get("event_level_uncontrollability"),
                    0,
                ),
            }
        )
        if len(tail) >= int(limit):
            break
    return list(reversed(tail))


def _build_relevant_mastery_summary(
    task_relevant_memory_packet: dict[str, Any],
) -> dict[str, Any]:
    return {
        "same_task_controllable_success_memory": round(
            _safe_float(
                task_relevant_memory_packet.get(
                    "same_task_controllable_success_memory",
                    0.0,
                )
            ),
            4,
        ),
        "has_controllable_success_evidence": bool(
            task_relevant_memory_packet.get("has_controllable_success_evidence", False)
        ),
        "help_success_rate_same_task": round(
            _safe_float(
                task_relevant_memory_packet.get("help_success_rate_same_task", 0.5)
            ),
            4,
        ),
        "recent_same_task_outcomes_tail": list(
            task_relevant_memory_packet.get("recent_same_task_outcomes_tail", [])
        ),
        "same_task_attribution_summary": str(
            task_relevant_memory_packet.get("same_task_attribution_summary", "")
        ).strip(),
    }


def _latest_stage_quote(stage_interview_history: Any) -> str:
    if not isinstance(stage_interview_history, list):
        return ""
    for item in reversed(stage_interview_history):
        if not isinstance(item, dict):
            continue
        quote = str(item.get("short_quote", "")).strip()
        if quote:
            return quote[:120]
    return ""


def _build_task_relevant_memory_packet(
    *,
    task: Any,
    task_domain_memory: Any,
    help_effect_memory: Any,
    recent_episode_summary: Any,
    event_log: Any,
) -> dict[str, Any]:
    task_state = {}
    if isinstance(task_domain_memory, dict):
        raw_state = task_domain_memory.get(task.task_family)
        if isinstance(raw_state, dict):
            task_state = raw_state
    help_snapshot = _support_snapshot_for_task(help_effect_memory, task.task_family)
    family_help = (
        help_snapshot.get("task_family", {})
        if isinstance(help_snapshot.get("task_family"), dict)
        else {}
    )
    recent = recent_episode_summary if isinstance(recent_episode_summary, dict) else {}
    event_tail = _extract_same_task_event_tail(
        task_family=task.task_family,
        event_log=event_log,
        limit=3,
    )
    controllable_success_memory = _safe_float(
        task_state.get("controllable_success_memory", 0.0)
    )
    return {
        "task_family": str(task.task_family),
        "same_task_attempt_count": _safe_int(task_state.get("attempt_count"), 0),
        "same_task_success_count": _safe_int(task_state.get("success_count"), 0),
        "same_task_failure_count": _safe_int(task_state.get("failure_count"), 0),
        "same_task_avoid_count": _safe_int(task_state.get("avoid_count"), 0),
        "same_task_failure_streak": _safe_int(
            task_state.get("same_task_failure_streak"),
            0,
        ),
        "same_task_recent_negative_feedback_ema": round(
            _safe_float(task_state.get("recent_negative_feedback_ema", 0.0)),
            4,
        ),
        "same_task_last_outcome": str(task_state.get("last_outcome", "")).strip(),
        "same_task_task_self_efficacy": round(
            _safe_float(task_state.get("task_self_efficacy", 50.0)),
            4,
        ),
        "same_task_controllable_success_memory": round(
            controllable_success_memory,
            4,
        ),
        "same_task_dominant_attribution_stability": str(
            task_state.get("dominant_attribution_stability", "mixed")
        ),
        "same_task_dominant_attribution_scope": str(
            task_state.get("dominant_attribution_scope", "task_specific")
        ),
        "same_task_recent_stable_attribution_ratio": round(
            _safe_float(task_state.get("recent_stable_attribution_ratio", 0.0)),
            4,
        ),
        "same_task_recent_scope_amplitude_ema": round(
            _safe_float(
                task_state.get("recent_scope_amplitude_ema", 0.0)
            ),
            4,
        ),
        "same_task_attribution_summary": str(
            task_state.get("attribution_summary", "")
        ).strip(),
        "same_task_help_attempt_count": _safe_int(
            family_help.get("help_attempt_count"),
            0,
        ),
        "same_task_help_success_count": _safe_int(
            family_help.get("help_success_count"),
            0,
        ),
        "same_task_help_failure_count": _safe_int(
            family_help.get("help_failure_count"),
            0,
        ),
        "help_success_rate_same_task": round(
            _safe_float(family_help.get("help_success_rate_smoothed", 0.5)),
            4,
        ),
        "recent_negative_feedback_ratio": round(
            _safe_float(recent.get("recent_negative_feedback_ratio", 0.0)),
            4,
        ),
        "recent_avoid_ratio": round(
            _safe_float(recent.get("recent_avoid_ratio", 0.0)),
            4,
        ),
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
        "recent_same_task_outcomes_tail": [
            str(item.get("outcome_type", "")).strip() for item in event_tail
        ],
        "recent_same_task_events_tail": event_tail,
        "has_controllable_success_evidence": controllable_success_memory > 0.05,
    }


def _compact_support_context(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "same_task_attempt_count": _safe_int(payload.get("same_task_attempt_count"), 0),
        "same_task_failure_count": _safe_int(payload.get("same_task_failure_count"), 0),
        "same_task_failure_streak": _safe_int(
            payload.get("same_task_failure_streak"),
            0,
        ),
        "same_task_last_outcome": _compact_status_text(
            payload.get("same_task_last_outcome"),
            default="",
        ),
        "help_success_rate_same_task": _safe_float(
            payload.get("help_success_rate_same_task"),
            0.5,
        ),
        "same_task_attribution_summary": _compact_status_note(
            payload.get("same_task_attribution_summary"),
            default="",
            max_chars=220,
        ),
        "recent_same_task_outcomes_tail": payload.get(
            "recent_same_task_outcomes_tail",
            [],
        ),
    }


class DigitalHelplessnessAgent(SocietyAgent):
    StatusAttributes = SocietyAgent.StatusAttributes + build_proto_status_attributes()
    survey_recent_alignment = True

    async def before_forward(self) -> None:
        if is_proto_logical_clock_enabled(getattr(self, "environment", None)):
            # Keep simulator motion/status sync for framework persistence, but skip
            # the heavier SocietyAgent context preparation in logical clock mode.
            await self.update_motion()
            return
        await super().before_forward()

    async def _run_minimal_daily_housekeeping(
        self,
        *,
        current_day: int,
        env: dict[str, Any],
    ) -> None:
        normalized_day = int(current_day)
        last_housekeeping_day = _safe_int(
            await self.memory.status.get("proto_last_housekeeping_day", -1),
            -1,
        )
        if last_housekeeping_day == normalized_day:
            return
        raw_digital_emotion_state = await self.memory.status.get(
            "digital_emotion_state", {}
        )
        digital_emotion_state = prepare_digital_emotion_state_for_day(
            raw_digital_emotion_state,
            target_day=normalized_day,
        )
        if digital_emotion_state.to_dict() != (
            raw_digital_emotion_state
            if isinstance(raw_digital_emotion_state, dict)
            else {}
        ):
            await self.memory.status.update(
                "digital_emotion_state",
                digital_emotion_state.to_dict(),
            )
        helplessness = _clamp(
            _safe_float(await self.memory.status.get("helplessness_score", 0.0))
        )
        current_stage_key = str(
            env.get("digital_stage") or env.get("stage_name") or ""
        ).strip()
        previous_stage_key = str(
            await self.memory.status.get("proto_active_stage_key", "")
        ).strip()
        stage_updates, _ = build_stage_transition_updates(
            current_stage_key=current_stage_key,
            previous_stage_key=previous_stage_key,
            helplessness=helplessness,
        )
        for key, value in stage_updates.items():
            await self.memory.status.update(key, value)
        await self.memory.status.update("proto_last_housekeeping_day", normalized_day)

    async def _write_idle_step_state(self) -> None:
        await DigitalHelplessnessAgent._write_mobile_entry_idle_state(self)

    def set_support_helper_registry(self, registry: dict[int, Any]) -> None:
        setattr(self, SUPPORT_HELPER_REGISTRY_ATTRIBUTE, dict(registry))

    async def _resolve_family_support_response(
        self,
        *,
        task: Any,
        strategy: Any,
        task_appraisal: Any,
        task_relevant_memory_packet: dict[str, Any],
        env: dict[str, Any],
        profile_summary: dict[str, Any],
        day: int,
        tick: float,
    ) -> tuple[SupportRequest | None, SupportResponse | None, str]:
        runtime_config = load_runtime_config()
        if runtime_config.proto_support_ecology_mode == "off":
            return None, None, "off"
        if strategy.strategy_type != "seek_help_then_attempt":
            return None, None, "not_requested"
        helper_id = _safe_int(
            await self.memory.status.get("family_helper_agent_id", -1),
            -1,
        )
        registry = getattr(self, SUPPORT_HELPER_REGISTRY_ATTRIBUTE, {})
        helper = registry.get(helper_id) if isinstance(registry, dict) else None
        request = SupportRequest(
            request_id=f"{int(self.id)}-{int(day)}-{int(float(tick))}-{task.task_id}",
            requester_agent_id=int(self.id),
            helper_agent_id=helper_id if helper_id >= 0 else None,
            day=int(day),
            tick=float(tick),
            task_id=str(task.task_id),
            task_family=str(task.task_family),
            friction_type=str(task.friction_type),
            difficulty=float(task.difficulty),
            need_type=str(task.need_type),
            support_sensitivity=float(task.support_sensitivity),
            strategy_type=str(strategy.strategy_type),
            support_need="help me complete the digital task while preserving my ability to learn",
            task_appraisal={
                "perceived_task_difficulty": float(
                    getattr(task_appraisal, "perceived_task_difficulty", 50.0)
                ),
                "perceived_task_risk": float(
                    getattr(task_appraisal, "perceived_task_risk", 50.0)
                ),
                "felt_control": float(getattr(task_appraisal, "felt_control", 50.0)),
                "expected_help_effectiveness": float(
                    getattr(task_appraisal, "expected_help_effectiveness", 50.0)
                ),
                "task_value": float(getattr(task_appraisal, "task_value", 50.0)),
            },
            memory_context=_compact_support_context(task_relevant_memory_packet),
            env_context={
                "digital_stage": str(env.get("digital_stage") or env.get("stage_name") or ""),
                "friction_level": _safe_int(env.get("friction_level", 0), 0),
                "complexity_level": _safe_int(env.get("complexity_level", 0), 0),
                "risk_level": _safe_int(env.get("risk_level", 0), 0),
                "assist_level": _safe_int(env.get("assist_level", 0), 0),
                "human_support_level": _safe_int(env.get("human_support_level", 0), 0),
                "accessibility_level": _safe_int(env.get("accessibility_level", 0), 0),
            },
            profile_summary={
                "age_bucket": age_bucket(profile_summary.get("age", -1)),
                "persona_tag": persona_bucket(profile_summary.get("persona", "")),
                "education": _compact_status_text(
                    profile_summary.get("education"),
                    default="unknown",
                ),
            },
            relationship={
                "relationship_type": "family",
                "mapped_helper_agent_id": helper_id,
            },
        )
        if helper is None or not hasattr(helper, "provide_support"):
            return (
                request,
                SupportResponse.unavailable(
                    request=request,
                    source="helper_unavailable",
                    audit_status="helper_not_found",
                ),
                "helper_not_found",
            )
        try:
            response = await helper.provide_support(request)
        except Exception as exc:
            return (
                request,
                SupportResponse.unavailable(
                    request=request,
                    source="helper_unavailable",
                    audit_status="request_error",
                    rationale=str(exc)[:300],
                ),
                "request_error",
            )
        return request, response, str(response.audit_status)

    async def _write_mobile_entry_idle_state(
        self,
        entry_decision: MobileEntryDecision | None = None,
    ) -> None:
        status_text = "No mobile digital activity entered"
        payload = {
            "step_type": "idle",
            "step_intention": status_text,
            "step_outcome": "none",
            "status_text": status_text,
            "mobile_entry_evaluated": False,
            "entry_status": "skipped_eval",
            "selected_mobile_intention": "",
            "mapped_task_family": None,
            "task_generated": False,
        }
        if entry_decision is not None:
            payload.update(
                {
                    "mobile_entry_evaluated": bool(entry_decision.entry_evaluated),
                    "entry_status": entry_decision.entry_status,
                    "selected_mobile_intention": (
                        entry_decision.selected_mobile_intention
                    ),
                    "mapped_task_family": entry_decision.mapped_task_family,
                    "mapping_confidence": float(entry_decision.mapping_confidence),
                    "task_generated": bool(entry_decision.task_generated),
                    "entry_audit": entry_decision.audit,
                }
            )
            await self.memory.status.update(
                "proto_mobile_entry_decision",
                entry_decision.to_dict(),
            )
        await self.memory.status.update(
            "current_intention", status_text
        )
        await self.memory.status.update("friction_step_signal", payload)

    async def status_summary(self) -> None:
        try:
            day_value, time_value = self.environment.get_datetime(format_time=True)
        except Exception:
            day_value, time_value = 0, "unknown"
        stage = _compact_status_text(
            await self.memory.status.get("proto_active_stage_key", ""),
            default="",
        )
        if not stage:
            env = getattr(self.environment, "environment", {})
            if not isinstance(env, dict):
                env = {}
            stage = _compact_status_text(
                env.get("digital_stage") or env.get("stage_name"),
                default="unknown",
            )
        friction_step_signal = await self.memory.status.get("friction_step_signal", {})
        if not isinstance(friction_step_signal, dict):
            friction_step_signal = {}
        summary = (
            f"day={_safe_int(day_value, 0)} "
            f"time={_format_status_time_hhmm(time_value)} "
            f"stage={stage or 'unknown'} "
            f"step={_compact_status_text(friction_step_signal.get('step_type'), default='unknown')} "
            f"intention={_compact_status_text(await self.memory.status.get('current_intention', ''), default='unknown')} "
            f"outcome={_compact_status_text(friction_step_signal.get('step_outcome'), default='none')} "
            f"helplessness={_clamp(_safe_float(await self.memory.status.get('helplessness_score', 0.0))):.1f} "
            f"trust={_clamp(_safe_float(await self.memory.status.get('trust_in_apps', 0.0))):.1f} "
            f"avoidance={_clamp(_safe_float(await self.memory.status.get('avoidance_tendency', 0.0))):.1f} "
            f"note={_compact_status_note(friction_step_signal.get('status_text'), default='unknown')}"
        )
        await self.memory.status.update("status_summary", summary)

    async def _build_task_appraisal_profile_summary(self) -> dict[str, Any]:
        background_story = str(
            await self.memory.status.get("background_story", "")
        ).strip()
        persona = str(await self.memory.status.get("persona", "")).strip()
        if not persona:
            persona = str(await self.memory.status.get("personality", "")).strip()
        return {
            "age": _safe_int(await self.memory.status.get("age", -1), -1),
            "education": str(
                await self.memory.status.get("education", "unknown")
            ).strip(),
            "occupation": str(
                await self.memory.status.get("occupation", "unknown")
            ).strip(),
            "persona": persona,
            "background_summary": _compress_background_story(background_story),
            "digital_experience": _clamp(
                _safe_float(await self.memory.status.get("digital_experience", 0.5)),
                0.0,
                1.0,
            ),
            "vision_limit": _clamp(
                _safe_float(await self.memory.status.get("vision_limit", 0.3)),
                0.0,
                1.0,
            ),
            "past_fraud_experience": _clamp(
                _safe_float(
                    await self.memory.status.get("past_fraud_experience", 0.2)
                ),
                0.0,
                1.0,
            ),
        }

    async def _build_stable_mobile_entry_profile(self) -> dict[str, Any]:
        profile = await self._build_task_appraisal_profile_summary()
        gender = str(await self.memory.status.get("gender", "unknown")).strip()
        profile["gender"] = gender or "unknown"
        return profile

    def _is_mobile_entry_eval_tick(
        self,
        *,
        tick_seconds: float,
        interval_minutes: int,
    ) -> bool:
        interval_seconds = max(60, int(interval_minutes) * 60)
        normalized_tick = int(round(float(tick_seconds)))
        if normalized_tick % interval_seconds == 0:
            return True
        # The logical clock records decision ticks one second after the wall-clock
        # boundary, e.g. 3601 instead of 3600. Treat that offset as the same slot.
        return normalized_tick > 0 and (normalized_tick - 1) % interval_seconds == 0

    async def _build_mobile_entry_llm_shadow(
        self,
        *,
        entry_decision: MobileEntryDecision,
        runtime_config: Any,
        stable_profile: dict[str, Any] | None,
        day: int,
        tick_seconds: float,
    ) -> dict[str, Any]:
        candidates = {
            key: float(value)
            for key, value in sorted(
                entry_decision.candidate_intentions.items(),
                key=lambda item: float(item[1]),
                reverse=True,
            )[:5]
        }
        allowed_intentions = set(candidates)
        payload = {
            "llm_shadow_enabled": True,
            "llm_prompt_version": str(
                runtime_config.proto_mobile_intention_llm_prompt_version
            ),
            "llm_cache_key": hashlib.sha256(
                json.dumps(
                    {
                        "prompt_version": (
                            runtime_config.proto_mobile_intention_llm_prompt_version
                        ),
                        "agent_id": int(self.id),
                        "day": int(day),
                        "tick_seconds": int(round(float(tick_seconds))),
                        "profile_bucket": entry_decision.audit.get("profile_bucket", ""),
                        "candidate_intentions": candidates,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:16],
            "llm_cache_hit": False,
            "llm_parse_status": "not_called",
            "llm_selected_intention_raw": "",
            "llm_confidence": 0.0,
            "llm_response_hash": "",
            "llm_agrees_with_rule": False,
            "llm_affected_real_entry": False,
        }
        if not candidates:
            payload["llm_parse_status"] = "no_candidates"
            return payload
        if getattr(self, "llm", None) is None:
            payload["llm_parse_status"] = "request_error"
            return payload
        llm_payload, status = await _query_json_payload(
            llm=getattr(self, "llm", None),
            system_prompt=(
                "You are a JSON-only shadow evaluator for a constrained mobile "
                "intention entry layer. Choose exactly one intention from the "
                "provided candidate_intentions. Do not invent intentions, tasks, "
                "strategies, outcomes, help actions, or psychological state updates."
            ),
            user_payload={
                "prompt_version": (
                    runtime_config.proto_mobile_intention_llm_prompt_version
                ),
                "day": int(day),
                "tick_seconds": float(tick_seconds),
                "hour": entry_decision.audit.get("hour"),
                "agent_profile": stable_profile or {},
                "profile_bucket": entry_decision.audit.get("profile_bucket", ""),
                "candidate_intentions": candidates,
                "rule_selected_mobile_intention": (
                    entry_decision.selected_mobile_intention
                ),
                "allowed_intentions": list(candidates),
                "output_schema_example": {
                    "selected_mobile_intention": "check_information",
                    "confidence": 0.80,
                    "reason": "Information use best matches the strongest prior.",
                },
            },
            output_keys=_MOBILE_ENTRY_LLM_SHADOW_KEYS,
            repair_schema_text=(
                "- selected_mobile_intention must be one of allowed_intentions\n"
                "- confidence must be a float in [0,1]\n"
                "- reason must be <= 120 chars\n"
                "- Do not output task, strategy, outcome, or psychological updates"
            ),
            sanitize_fn=lambda raw: _sanitize_mobile_entry_shadow(
                raw,
                allowed_intentions=allowed_intentions,
                min_confidence=(
                    runtime_config.proto_mobile_intention_llm_min_confidence
                ),
            ),
            timeout=int(getattr(runtime_config, "proto_llm_psychology_timeout", 30)),
            retries=int(getattr(runtime_config, "proto_llm_psychology_retries", 0)),
        )
        payload["llm_parse_status"] = status
        if llm_payload is None:
            return payload
        selected = str(llm_payload.get("selected_mobile_intention", "")).strip()
        confidence = _clamp(_safe_float(llm_payload.get("confidence"), 0.0), 0.0, 1.0)
        if confidence < float(runtime_config.proto_mobile_intention_llm_min_confidence):
            payload["llm_parse_status"] = "low_confidence"
        payload.update(
            {
                "llm_selected_intention_raw": selected,
                "llm_confidence": confidence,
                "llm_reason": str(llm_payload.get("reason", ""))[:120],
                "llm_response_hash": hashlib.sha256(
                    json.dumps(
                        llm_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()[:16],
                "llm_agrees_with_rule": (
                    selected == entry_decision.selected_mobile_intention
                ),
            }
        )
        return payload

    async def _build_mobile_entry_llm_rerank(
        self,
        *,
        entry_decision: MobileEntryDecision,
        runtime_config: Any,
        stable_profile: dict[str, Any] | None,
        day: int,
        tick_seconds: float,
    ) -> dict[str, Any]:
        candidates = top_mobile_intention_candidates(
            entry_decision.candidate_intentions,
            top_k=int(runtime_config.proto_mobile_intention_rerank_top_k),
        )
        allowed_intentions = set(candidates)
        prompt_version = str(runtime_config.proto_mobile_intention_llm_prompt_version)
        candidate_hash = mobile_intention_candidate_hash(candidates)
        payload = {
            "rerank_enabled": True,
            "rerank_run_id": str(
                getattr(runtime_config, "proto_mobile_intention_rerank_run_id", "")
            ),
            "rerank_prompt_version": prompt_version,
            "rerank_top_k": int(runtime_config.proto_mobile_intention_rerank_top_k),
            "rerank_json_attempts_configured": int(
                getattr(runtime_config, "proto_mobile_intention_rerank_json_attempts", 5)
            ),
            "rerank_json_attempts_used": 0,
            "rerank_candidate_intentions": dict(candidates),
            "rerank_candidate_hash": candidate_hash,
            "rule_selected_mobile_intention": (
                entry_decision.selected_mobile_intention
            ),
            "rerank_selected_mobile_intention": "",
            "rerank_parse_status": "not_called",
            "rerank_confidence": 0.0,
            "rerank_reason": "",
            "rerank_response_hash": "",
            "llm_drives_real_entry": True,
            "uses_post_outcome_information": False,
            "does_not_decide_strategy": True,
            "does_not_decide_outcome": True,
            "does_not_update_psychology": True,
        }
        if not candidates:
            payload["rerank_parse_status"] = "no_candidates"
            raise ValueError("mobile-intention LLM rerank has no candidates")
        if getattr(self, "llm", None) is None:
            payload["rerank_parse_status"] = "request_error"
            raise ValueError("mobile-intention LLM rerank requires an LLM client")
        user_payload = {
            "prompt_version": prompt_version,
            "day": int(day),
            "tick_seconds": float(tick_seconds),
            "hour": entry_decision.audit.get("hour"),
            "agent_profile": stable_profile or {},
            "profile_bucket": entry_decision.audit.get("profile_bucket", ""),
            "candidate_intentions": candidates,
            "rule_selected_mobile_intention": (
                entry_decision.selected_mobile_intention
            ),
            "allowed_intentions": list(candidates),
            "output_schema_example": {
                "selected_mobile_intention": "check_information",
                "confidence": 0.80,
                "reason": "This candidate best matches the context and priors.",
            },
        }
        def _sanitize_for_this_rerank(value: Any) -> tuple[dict[str, Any] | None, str]:
            return _sanitize_mobile_entry_shadow(
                value,
                allowed_intentions=allowed_intentions,
                min_confidence=runtime_config.proto_mobile_intention_llm_min_confidence,
            )

        llm_payload, status = await _query_json_payload(
            llm=getattr(self, "llm"),
            system_prompt=(
                "You are a JSON-only reranker for a constrained mobile intention "
                "entry layer. Choose exactly one intention from candidate_intentions. "
                "Do not invent intentions, tasks, strategies, outcomes, help actions, "
                "or psychological state updates."
            ),
            user_payload=user_payload,
            output_keys=_MOBILE_ENTRY_LLM_SHADOW_KEYS,
            repair_schema_text=(
                "- Return exactly selected_mobile_intention, confidence, and reason\n"
                "- selected_mobile_intention must be one of allowed_intentions\n"
                "- confidence must be a number in [0,1]\n"
                "- reason must be a short explanation and must not include task outcomes, "
                "strategies, or psychological state updates"
            ),
            sanitize_fn=_sanitize_for_this_rerank,
            timeout=int(getattr(runtime_config, "proto_llm_psychology_timeout", 30)),
            retries=int(getattr(runtime_config, "proto_llm_psychology_retries", 0)),
            max_tokens=260,
            json_attempts=int(
                getattr(runtime_config, "proto_mobile_intention_rerank_json_attempts", 5)
            ),
            attempt_metadata_key="_rerank_json_attempts_used",
        )
        payload["rerank_parse_status"] = status
        if llm_payload is None:
            raise ValueError(f"mobile-intention LLM rerank failed: {status}")
        json_attempts_used = int(llm_payload.pop("_rerank_json_attempts_used", 1) or 1)
        payload["rerank_json_attempts_used"] = json_attempts_used
        selected = str(llm_payload.get("selected_mobile_intention", "")).strip()
        confidence = _clamp(_safe_float(llm_payload.get("confidence"), 0.0), 0.0, 1.0)
        if confidence < float(runtime_config.proto_mobile_intention_llm_min_confidence):
            low_confidence_policy = str(
                getattr(
                    runtime_config,
                    "proto_mobile_intention_rerank_low_confidence_policy",
                    "fail_run",
                )
            ).strip().lower()
            payload["rerank_parse_status"] = (
                "low_confidence_accepted"
                if low_confidence_policy == "accept_with_audit"
                else "low_confidence"
            )
            if low_confidence_policy != "accept_with_audit":
                raise ValueError(
                    "mobile-intention LLM rerank confidence below threshold"
                )
        payload.update(
            {
                "rerank_selected_mobile_intention": selected,
                "rerank_confidence": confidence,
                "rerank_reason": str(llm_payload.get("reason", ""))[:120],
                "rerank_response_hash": hashlib.sha256(
                    json.dumps(
                        llm_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()[:16],
            }
        )
        return payload

    async def _resolve_mobile_entry_rerank_override(
        self,
        *,
        entry_decision: MobileEntryDecision,
        runtime_config: Any,
        stable_profile: dict[str, Any] | None,
        day: int,
        tick_seconds: float,
    ) -> tuple[str, dict[str, Any]]:
        run_id = str(getattr(runtime_config, "proto_mobile_intention_rerank_run_id", ""))
        schedule_path = str(
            getattr(runtime_config, "proto_mobile_intention_rerank_schedule_path", "")
        )
        candidates = top_mobile_intention_candidates(
            entry_decision.candidate_intentions,
            top_k=int(runtime_config.proto_mobile_intention_rerank_top_k),
        )
        candidate_hash = mobile_intention_candidate_hash(candidates)
        audit = await DigitalHelplessnessAgent._build_mobile_entry_llm_rerank(
            self,
            entry_decision=entry_decision,
            runtime_config=runtime_config,
            stable_profile=stable_profile,
            day=int(day),
            tick_seconds=float(tick_seconds),
        )
        selected = str(audit.get("rerank_selected_mobile_intention", "")).strip()
        row = {
            "run_id": run_id,
            "agent_id": int(self.id),
            "day": int(day),
            "tick_seconds": float(tick_seconds),
            "profile_bucket": entry_decision.audit.get("profile_bucket", ""),
            "prompt_version": str(runtime_config.proto_mobile_intention_llm_prompt_version),
            "candidate_hash": candidate_hash,
            "candidate_intentions": dict(candidates),
            "rule_selected_mobile_intention": entry_decision.selected_mobile_intention,
            "selected_mobile_intention": selected,
            "confidence": float(audit.get("rerank_confidence", 0.0)),
            "parse_status": str(audit.get("rerank_parse_status", "")),
            "json_attempts_configured": int(
                audit.get("rerank_json_attempts_configured", 1) or 1
            ),
            "json_attempts_used": int(audit.get("rerank_json_attempts_used", 1) or 1),
            "reason": str(audit.get("rerank_reason", ""))[:120],
            "response_hash": str(audit.get("rerank_response_hash", "")),
        }
        _append_mobile_entry_rerank_schedule(schedule_path, row)
        return selected, audit

    async def _build_survey_summary(self) -> dict[str, float]:
        summary: dict[str, float] = {}
        for field_name in _SURVEY_SUMMARY_FIELDS:
            summary[field_name] = _clamp(
                _safe_float(await self.memory.status.get(field_name, 0.0))
            )
        return summary

    async def _persist_proto_decision_state(
        self,
        *,
        task_appraisal: Any,
        strategy_deliberation: Any,
        event_attribution: Any,
    ) -> None:
        await self.memory.status.update("proto_task_appraisal", task_appraisal.to_dict())
        await self.memory.status.update(
            "proto_strategy_deliberation",
            strategy_deliberation.to_dict(),
        )
        await self.memory.status.update(
            "proto_event_attribution",
            event_attribution.to_dict(),
        )

    async def _record_event_attribution_stream(
        self,
        *,
        task: Any,
        outcome: Any,
        event_attribution: Any,
    ) -> None:
        if str(getattr(event_attribution, "status", "")) != "ok":
            return
        description = (
            f"[{task.task_family}] "
            f"{outcome.outcome_type}; "
            f"locus={event_attribution.event_attribution_locus}; "
            f"stability={event_attribution.event_attribution_stability}; "
            f"scope={event_attribution.event_attribution_scope}; "
            f"scope_amplitude={float(event_attribution.event_attribution_scope_amplitude):.2f}; "
            f"{str(event_attribution.event_attribution_explanation).strip()[:180]}"
        ).strip()
        try:
            await self.memory.stream.add(
                topic="digital_failure_attribution",
                description=description[:600],
            )
        except Exception:
            return

    async def _record_task_episode_stream(
        self,
        *,
        task: Any,
        strategy: Any,
        outcome: Any,
    ) -> dict[str, Any]:
        task_label = _stream_task_label(getattr(task, "task_family", ""))
        if bool(getattr(outcome, "success", False)):
            result_text = "completed it"
        elif bool(getattr(outcome, "negative_feedback", False)):
            result_text = "could not complete it"
        else:
            result_text = "did not finish it"
        control_text = (
            "The experience made the task feel hard to control."
            if _safe_int(getattr(outcome, "event_level_uncontrollability", 0)) > 0
            else "The experience still felt manageable."
        )
        description = (
            f"[digital_task_episode]"
            f"[family={_stream_text(getattr(task, 'task_family', 'unknown'))}]"
            f"[friction={_stream_text(getattr(task, 'friction_type', 'unknown'))}]"
            f"[outcome={_stream_text(getattr(outcome, 'outcome_type', 'unknown'))}]"
            f"[strategy={_stream_text(getattr(strategy, 'strategy_type', 'unknown'))}]"
            f"[help={_stream_bool(getattr(outcome, 'help_used', False))}]"
            f"[negative={_stream_bool(getattr(outcome, 'negative_feedback', False))}]"
            f"[uncontrollability={_stream_uncontrollability(getattr(outcome, 'event_level_uncontrollability', 0))}] "
            f"I tried {task_label} and {result_text}. {control_text}"
        )
        memory_id = await self.memory.stream.add(
            topic="digital_task_episode",
            description=description[:600],
        )
        return {"topic": "digital_task_episode", "memory_id": memory_id, "status": "ok"}

    async def _record_help_episode_stream(
        self,
        *,
        task: Any,
        strategy: Any,
        outcome: Any,
    ) -> dict[str, Any] | None:
        help_attempted = bool(getattr(outcome, "help_used", False)) or (
            str(getattr(strategy, "strategy_type", "")) == "seek_help_then_attempt"
        )
        if not help_attempted:
            return None
        task_label = _stream_task_label(getattr(task, "task_family", ""))
        support_mode = _stream_text(getattr(outcome, "support_mode", "not_applicable"))
        if str(getattr(outcome, "outcome_type", "")) == "success_with_help":
            help_text = "the help was useful enough for me to complete the task"
        elif support_mode == "enabling_support":
            help_text = "the help gave me some guidance, but the task was still difficult"
        else:
            help_text = "the help was limited and did not fully solve the problem"
        description = (
            f"[digital_help_episode]"
            f"[family={_stream_text(getattr(task, 'task_family', 'unknown'))}]"
            f"[outcome={_stream_text(getattr(outcome, 'outcome_type', 'unknown'))}]"
            f"[support_quality={_safe_int(getattr(outcome, 'support_quality', 0))}]"
            f"[support_mode={support_mode}] "
            f"I sought help for {task_label}, and {help_text}."
        )
        memory_id = await self.memory.stream.add(
            topic="digital_help_episode",
            description=description[:600],
        )
        return {"topic": "digital_help_episode", "memory_id": memory_id, "status": "ok"}

    async def _record_recovery_episode_stream(
        self,
        *,
        task: Any,
        strategy: Any,
        outcome: Any,
        memory_features: Any,
    ) -> dict[str, Any] | None:
        recent_failures = _safe_int(
            getattr(memory_features, "recent_same_task_failure_count", 0)
        )
        outcome_type = str(getattr(outcome, "outcome_type", ""))
        support_mode = str(getattr(outcome, "support_mode", "not_applicable"))
        self_recovery = outcome_type == "success_self" and recent_failures >= 2
        help_recovery = (
            outcome_type == "success_with_help"
            and support_mode == "enabling_support"
            and recent_failures >= 1
        )
        if not (self_recovery or help_recovery):
            return None
        task_label = _stream_task_label(getattr(task, "task_family", ""))
        recovery_text = (
            "After earlier failures, I completed it by myself and felt this task could still be learned."
            if self_recovery
            else "After earlier failures, useful guidance helped me complete it and regain some confidence."
        )
        description = (
            f"[digital_recovery_episode]"
            f"[family={_stream_text(getattr(task, 'task_family', 'unknown'))}]"
            f"[outcome={_stream_text(getattr(outcome, 'outcome_type', 'unknown'))}]"
            f"[strategy={_stream_text(getattr(strategy, 'strategy_type', 'unknown'))}]"
            f"[support_mode={_stream_text(getattr(outcome, 'support_mode', 'not_applicable'))}] "
            f"I recovered in {task_label}. {recovery_text}"
        )
        memory_id = await self.memory.stream.add(
            topic="digital_recovery_episode",
            description=description[:600],
        )
        return {
            "topic": "digital_recovery_episode",
            "memory_id": memory_id,
            "status": "ok",
        }

    async def _record_phase0_stream_episodes(
        self,
        *,
        runtime_config: Any,
        task: Any,
        strategy: Any,
        outcome: Any,
        memory_features: Any,
    ) -> dict[str, Any]:
        enabled = bool(
            getattr(runtime_config, "proto_stream_episode_recording_enabled", True)
        )
        if not enabled:
            return {
                "enabled": False,
                "condition": "structured-only",
                "records": [],
                "error_count": 0,
            }
        records = [
            await self._record_task_episode_stream(
                task=task,
                strategy=strategy,
                outcome=outcome,
            )
        ]
        help_record = await self._record_help_episode_stream(
            task=task,
            strategy=strategy,
            outcome=outcome,
        )
        if help_record is not None:
            records.append(help_record)
        recovery_record = await self._record_recovery_episode_stream(
            task=task,
            strategy=strategy,
            outcome=outcome,
            memory_features=memory_features,
        )
        if recovery_record is not None:
            records.append(recovery_record)
        return {
            "enabled": True,
            "condition": "stream-record-only",
            "records": records,
            "error_count": 0,
        }

    async def _retrieve_task_episodic_memory(
        self,
        *,
        runtime_config: Any,
        task: Any,
    ) -> dict[str, Any]:
        topics = [
            "digital_task_episode",
            "digital_help_episode",
            "digital_recovery_episode",
        ]
        condition = _stream_appraisal_condition(runtime_config)
        query = (
            f"{getattr(task, 'task_family', '')} "
            f"{_stream_task_label(getattr(task, 'task_family', ''))} "
            "failure success help"
        ).strip()
        if condition != "stream-appraisal":
            text = "Nothing"
            return {
                "text": text,
                "ids": [],
                "hash": _stream_packet_hash(text),
                "count": 0,
                "query": query,
                "topics": topics,
                "condition": condition,
                "status": "disabled",
            }
        topic_limits = {
            "digital_task_episode": 3,
            "digital_help_episode": 1,
            "digital_recovery_episode": 1,
        }
        chunks: list[str] = []
        for topic in topics:
            try:
                result = await self.memory.stream.search(
                    query=query,
                    topic=topic,
                    top_k=topic_limits[topic],
                )
            except Exception as exc:
                text = "Nothing"
                return {
                    "text": text,
                    "ids": [],
                    "hash": _stream_packet_hash(text),
                    "count": 0,
                    "query": query,
                    "topics": topics,
                    "condition": condition,
                    "status": "error",
                    "error": _compact_status_note(exc, max_chars=120),
                }
            result_text = str(result or "").strip()
            if result_text and result_text != "Nothing":
                chunks.append(result_text)
        text = "\n".join(chunks).strip() or "Nothing"
        count = _stream_search_count(text)
        return {
            "text": text,
            "ids": [],
            "hash": _stream_packet_hash(text),
            "count": count,
            "query": query,
            "topics": topics,
            "condition": condition,
            "status": "ok" if count > 0 else "empty",
        }

    async def _retrieve_attribution_episodic_memory(
        self,
        *,
        runtime_config: Any,
        task: Any,
    ) -> dict[str, Any]:
        topics = [
            "digital_task_episode",
            "digital_help_episode",
            "digital_recovery_episode",
        ]
        condition = _stream_attribution_condition(runtime_config)
        query = (
            f"{getattr(task, 'task_family', '')} "
            f"{_stream_task_label(getattr(task, 'task_family', ''))} "
            "failure recovery help similar setback"
        ).strip()
        if condition not in {"stream-appraisal-attribution", "stream-attribution-only"}:
            text = "Nothing"
            return {
                "text": text,
                "ids": [],
                "hash": _stream_packet_hash(text),
                "count": 0,
                "query": query,
                "topics": topics,
                "condition": condition,
                "status": "disabled",
            }
        topic_limits = {
            "digital_task_episode": 3,
            "digital_help_episode": 1,
            "digital_recovery_episode": 1,
        }
        chunks: list[str] = []
        for topic in topics:
            try:
                result = await self.memory.stream.search(
                    query=query,
                    topic=topic,
                    top_k=topic_limits[topic],
                )
            except Exception as exc:
                text = "Nothing"
                return {
                    "text": text,
                    "ids": [],
                    "hash": _stream_packet_hash(text),
                    "count": 0,
                    "query": query,
                    "topics": topics,
                    "condition": condition,
                    "status": "error",
                    "error": _compact_status_note(exc, max_chars=120),
                }
            result_text = str(result or "").strip()
            if result_text and result_text != "Nothing":
                chunks.append(result_text)
        text = "\n".join(chunks).strip() or "Nothing"
        count = _stream_search_count(text)
        return {
            "text": text,
            "ids": [],
            "hash": _stream_packet_hash(text),
            "count": count,
            "query": query,
            "topics": topics,
            "condition": condition,
            "status": "ok" if count > 0 else "empty",
        }

    async def do_interview(self, question: str) -> str:
        stage_match = _STAGE_INTERVIEW_MARKER.match(str(question or "").strip())
        if stage_match:
            stage_name = str(stage_match.group("stage_name") or "").strip()
            stage_index = _safe_int(stage_match.group("stage_index"), 0)
            try:
                stage_summary_memory = await self.stream.search(
                    f"[{stage_name}] digital_friction_stage_summary",
                    top_k=3,
                )
            except Exception:
                stage_summary_memory = ""
            survey_summary = await self._build_survey_summary()
            latest_task_appraisal = await self.memory.status.get(
                "proto_task_appraisal", {}
            )
            latest_digital_emotion = await self.memory.status.get(
                "digital_emotion_state", {}
            )
            latest_daily_reflection = await self.memory.status.get(
                "proto_daily_reflection", {}
            )
            latest_event_attribution = await self.memory.status.get(
                "proto_event_attribution", {}
            )
            event_log = _decode_json_list(await self.memory.status.get("event_log", []))
            result = await resolve_stage_interview(
                llm=getattr(self, "llm", None),
                stage_name=stage_name,
                stage_index=stage_index,
                stage_summary_memory=str(stage_summary_memory),
                survey_summary=survey_summary,
                latest_task_appraisal=latest_task_appraisal,
                latest_digital_emotion=latest_digital_emotion,
                latest_daily_reflection=latest_daily_reflection,
                latest_event_attribution=latest_event_attribution,
                event_log_summary=_summarize_event_log_for_interview(event_log),
            )
            return json.dumps(result.to_dict(), ensure_ascii=False)

        if str(question or "").strip().startswith(_FINAL_INTERVIEW_MARKER):
            survey_summary = await self._build_survey_summary()
            latest_digital_emotion = await self.memory.status.get(
                "digital_emotion_state", {}
            )
            latest_daily_reflection = await self.memory.status.get(
                "proto_daily_reflection", {}
            )
            latest_event_attribution = await self.memory.status.get(
                "proto_event_attribution", {}
            )
            stage_interview_history = await self.memory.status.get(
                "proto_stage_interview_history", []
            )
            event_log = _decode_json_list(await self.memory.status.get("event_log", []))
            result = await resolve_final_interview(
                llm=getattr(self, "llm", None),
                stage_interview_history=stage_interview_history,
                latest_digital_emotion=latest_digital_emotion,
                latest_daily_reflection=latest_daily_reflection,
                latest_event_attribution=latest_event_attribution,
                survey_summary=survey_summary,
                event_log_summary=_summarize_event_log_for_interview(event_log),
            )
            return json.dumps(result.to_dict(), ensure_ascii=False)

        return await super().do_interview(question)

    async def forward(self):
        self.step_count += 1
        day, t = self.environment.get_datetime()
        env = dict(self.environment.environment)
        current_day = int(day)
        existing_task_raw = await self.memory.status.get("proto_assigned_task_json", "")
        has_existing_task = existing_task_raw not in (None, "", "null")
        runtime_config = load_runtime_config()
        entry_mode = runtime_config.proto_task_entry_mode
        is_entry_tick = (
            is_task_window_tick(float(t))
            if entry_mode == "fixed_assignment"
            else self._is_mobile_entry_eval_tick(
                tick_seconds=float(t),
                interval_minutes=(
                    runtime_config.proto_mobile_intention_eval_interval_minutes
                ),
            )
        )
        if not has_existing_task and not is_entry_tick:
            await self._run_minimal_daily_housekeeping(
                current_day=current_day,
                env=env,
            )
            decision = (
                skipped_mobile_entry_decision(
                    agent_id=int(self.id),
                    day=int(day),
                    tick_seconds=float(t),
                    entry_mode=entry_mode,
                )
                if entry_mode != "fixed_assignment"
                else None
            )
            await DigitalHelplessnessAgent._write_mobile_entry_idle_state(
                self,
                decision,
            )
            return 0.0
        helplessness = _clamp(
            _safe_float(await self.memory.status.get("helplessness_score", 0.0))
        )
        trust = _clamp(_safe_float(await self.memory.status.get("trust_in_apps", 0.0)))
        avoidance = _clamp(
            _safe_float(await self.memory.status.get("avoidance_tendency", 0.0))
        )
        survey_summary = await self._build_survey_summary()
        survey_helplessness_index = float(
            survey_summary["survey_helplessness_index"]
        )
        survey_withdrawal_index = float(survey_summary["survey_withdrawal_index"])
        survey_self_efficacy_index = float(
            survey_summary["survey_self_efficacy_index"]
        )
        survey_support_index = float(survey_summary["survey_support_index"])
        survey_usefulness_index = float(survey_summary["survey_usefulness_index"])
        survey_anxiety_index = float(survey_summary["survey_anxiety_index"])
        event_log = _decode_json_list(await self.memory.status.get("event_log", []))
        task_domain_memory = await self.memory.status.get("task_domain_memory", {})
        help_effect_memory = await self.memory.status.get("help_effect_memory", {})
        recent_episode_buffer = await self.memory.status.get("recent_episode_buffer", [])
        rationale_memory = await self.memory.status.get("rationale_memory", [])
        raw_digital_emotion_state = await self.memory.status.get(
            "digital_emotion_state", {}
        )
        digital_emotion_state = prepare_digital_emotion_state_for_day(
            raw_digital_emotion_state,
            target_day=current_day,
        )
        if digital_emotion_state.to_dict() != (
            raw_digital_emotion_state if isinstance(raw_digital_emotion_state, dict) else {}
        ):
            await self.memory.status.update(
                "digital_emotion_state",
                digital_emotion_state.to_dict(),
            )
        current_stage_key = str(
            env.get("digital_stage") or env.get("stage_name") or ""
        ).strip()
        previous_stage_key = str(
            await self.memory.status.get("proto_active_stage_key", "")
        ).strip()
        stage_updates, stage_changed = build_stage_transition_updates(
            current_stage_key=current_stage_key,
            previous_stage_key=previous_stage_key,
            helplessness=helplessness,
        )
        for key, value in stage_updates.items():
            await self.memory.status.update(key, value)
        reflection_updates, generated_reflection = await maybe_generate_daily_reflection(
            llm=getattr(self, "llm", None),
            current_day=current_day,
            last_reflection_day=_safe_int(
                await self.memory.status.get("proto_last_reflection_day", -1),
                -1,
            ),
            event_log=event_log,
            digital_emotion_state=digital_emotion_state.to_dict(),
            task_domain_memory=task_domain_memory,
            help_effect_memory=help_effect_memory,
            reflection_history=await self.memory.status.get(
                "proto_daily_reflection_history", []
            ),
        )
        for key, value in reflection_updates.items():
            await self.memory.status.update(key, value)
        await self.memory.status.update("proto_last_housekeeping_day", current_day)
        current_daily_reflection = (
            reflection_updates.get("proto_daily_reflection")
            if reflection_updates.get("proto_daily_reflection") is not None
            else await self.memory.status.get("proto_daily_reflection", {})
        )
        if stage_changed:
            event_log = []
        if generated_reflection is not None:
            current_reflection_count = _safe_int(
                await self.memory.status.get("proto_stage_daily_reflection_count", 0),
                0,
            )
            await self.memory.status.update(
                "proto_stage_daily_reflection_count",
                current_reflection_count + 1,
            )
        task = decode_task(existing_task_raw)
        entry_profile = (
            await self._build_stable_mobile_entry_profile()
            if runtime_config.proto_task_entry_mode != "fixed_assignment"
            else None
        )
        task, task_updates, _, entry_decision = assign_task_with_entry_decision(
            existing_task=task,
            agent_id=int(self.id),
            day=int(day),
            tick_seconds=float(t),
            env=env,
            entry_mode=(
                "mobile_intention_rule"
                if runtime_config.proto_task_entry_mode
                == "mobile_intention_llm_rerank_online_mc"
                else runtime_config.proto_task_entry_mode
            ),
            stable_profile=entry_profile,
            calibration_path=(
                runtime_config.proto_mobile_intention_calibration_path
            ),
            mapping_path=runtime_config.proto_mobile_intention_mapping_path,
            confidence_threshold=(
                runtime_config.proto_mobile_intention_confidence_threshold
            ),
        )
        if (
            entry_decision is not None
            and runtime_config.proto_task_entry_mode
            == "mobile_intention_llm_rerank_online_mc"
        ):
            selected_override, rerank_audit = (
                await self._resolve_mobile_entry_rerank_override(
                    entry_decision=entry_decision,
                    runtime_config=runtime_config,
                    stable_profile=entry_profile,
                    day=int(day),
                    tick_seconds=float(t),
                )
            )
            task, task_updates, _, entry_decision = assign_task_with_entry_decision(
                existing_task=None,
                agent_id=int(self.id),
                day=int(day),
                tick_seconds=float(t),
                env=env,
                entry_mode=runtime_config.proto_task_entry_mode,
                stable_profile=entry_profile,
                calibration_path=(
                    runtime_config.proto_mobile_intention_calibration_path
                ),
                mapping_path=runtime_config.proto_mobile_intention_mapping_path,
                confidence_threshold=(
                    runtime_config.proto_mobile_intention_confidence_threshold
                ),
                selected_intention_override=selected_override,
                rerank_audit_payload=rerank_audit,
                rerank_top_k=int(runtime_config.proto_mobile_intention_rerank_top_k),
            )
        if entry_decision is not None:
            if runtime_config.proto_task_entry_mode == "mobile_intention_llm_shadow":
                entry_decision.audit["llm_shadow"] = (
                    await self._build_mobile_entry_llm_shadow(
                        entry_decision=entry_decision,
                        runtime_config=runtime_config,
                        stable_profile=entry_profile,
                        day=int(day),
                        tick_seconds=float(t),
                    )
                )
            entry_decision.audit["entry_eval_interval_minutes"] = (
                runtime_config.proto_mobile_intention_eval_interval_minutes
            )
            await self.memory.status.update(
                "proto_mobile_entry_decision",
                entry_decision.to_dict(),
            )
        for key, value in task_updates.items():
            await self.memory.status.update(key, value)
        if task is None:
            await self._write_mobile_entry_idle_state(entry_decision)
            return 0.0

        consecutive_failures = _safe_int(
            await self.memory.status.get("proto_consecutive_failures", 0)
        )
        support_quality = support_quality_from_env(env)
        baseline_memory_features = extract_memory_features(
            task=task,
            helplessness_score=helplessness,
            task_domain_memory=task_domain_memory,
            help_effect_memory=help_effect_memory,
            recent_episode_buffer=recent_episode_buffer,
            digital_emotion_state=digital_emotion_state.to_dict(),
            psychology_mode=runtime_config.proto_llm_psychology_mode,
        )
        profile_summary = await self._build_task_appraisal_profile_summary()
        recent_episode_summary = {
            "recent_negative_feedback_ratio": baseline_memory_features.recent_negative_feedback_ratio,
            "recent_avoid_ratio": baseline_memory_features.recent_avoid_ratio,
            "recent_help_seek_ratio": baseline_memory_features.recent_help_seek_ratio,
            "recent_same_task_failure_count": baseline_memory_features.recent_same_task_failure_count,
            "recent_failure_pressure": baseline_memory_features.recent_failure_pressure,
        }
        task_relevant_memory_packet = _build_task_relevant_memory_packet(
            task=task,
            task_domain_memory=task_domain_memory,
            help_effect_memory=help_effect_memory,
            recent_episode_summary=recent_episode_summary,
            event_log=event_log,
        )
        cross_task_recent_context = {
            "recent_cross_task_events_tail": _extract_cross_task_event_tail(
                task_family=task.task_family,
                event_log=event_log,
                limit=4,
            )
        }
        relevant_mastery_summary = _build_relevant_mastery_summary(
            task_relevant_memory_packet
        )
        stage_interview_history = await self.memory.status.get(
            "proto_stage_interview_history",
            [],
        )
        latest_stage_quote = _latest_stage_quote(stage_interview_history)
        world_context = {
            "digital_stage": current_stage_key,
            "friction_level": _safe_int(env.get("friction_level", 0), 0),
            "malicious_friction_level": _safe_int(
                env.get("malicious_friction_level", 0), 0
            ),
            "complexity_level": _safe_int(env.get("complexity_level", 0), 0),
            "risk_level": _safe_int(env.get("risk_level", 0), 0),
            "assist_level": _safe_int(env.get("assist_level", 0), 0),
            "accessibility_level": _safe_int(env.get("accessibility_level", 0), 0),
            "human_support_level": _safe_int(env.get("human_support_level", 0), 0),
        }
        task_appraisal_retrieval_packet = await self._retrieve_task_episodic_memory(
            runtime_config=runtime_config,
            task=task,
        )
        task_appraisal = await resolve_task_appraisal(
            llm=getattr(self, "llm", None),
            task=task,
            stage_key=current_stage_key,
            world_context=world_context,
            profile_summary=profile_summary,
            task_relevant_memory=task_relevant_memory_packet,
            helplessness_now=helplessness,
            task_self_efficacy=baseline_memory_features.task_self_efficacy,
            help_success_rate_smoothed=baseline_memory_features.help_success_rate_smoothed,
            recent_episode_summary=recent_episode_summary,
            digital_emotion_state=digital_emotion_state.to_dict(),
            retrieved_episodic_memory=task_appraisal_retrieval_packet,
        )
        memory_features = extract_memory_features(
            task=task,
            helplessness_score=helplessness,
            task_domain_memory=task_domain_memory,
            help_effect_memory=help_effect_memory,
            recent_episode_buffer=recent_episode_buffer,
            digital_emotion_state=digital_emotion_state.to_dict(),
            task_appraisal_result=task_appraisal.to_dict(),
            psychology_mode=runtime_config.proto_llm_psychology_mode,
        )
        rule_strategy_weights = compute_rule_strategy_weights(
            effective_helplessness=memory_features.effective_helplessness,
            support_quality=support_quality,
            task_difficulty=task.difficulty,
            consecutive_failures=consecutive_failures,
            task_self_efficacy=memory_features.task_self_efficacy,
            help_success_rate_smoothed=memory_features.help_success_rate_smoothed,
            recent_negative_feedback_ratio=memory_features.recent_negative_feedback_ratio,
            recent_same_task_failure_count=memory_features.recent_same_task_failure_count,
        )
        strategy_deliberation = await resolve_strategy_deliberation(
            llm=getattr(self, "llm", None),
            task=task,
            task_appraisal=task_appraisal.to_dict(),
            effective_helplessness=memory_features.effective_helplessness,
            task_self_efficacy=memory_features.task_self_efficacy,
            help_success_rate_smoothed=memory_features.help_success_rate_smoothed,
            recent_negative_feedback_ratio=memory_features.recent_negative_feedback_ratio,
            recent_same_task_failure_count=memory_features.recent_same_task_failure_count,
            digital_emotion_state=digital_emotion_state.to_dict(),
            daily_reflection=current_daily_reflection,
            rule_weights=rule_strategy_weights,
            profile_summary=profile_summary,
            task_relevant_memory=task_relevant_memory_packet,
            recent_episode_summary=recent_episode_summary,
            retrieved_episodic_memory=task_appraisal_retrieval_packet,
        )
        bayesian_policy_reference_audit = build_semantic_reference_policy(
            reference_mode=runtime_config.proto_bayesian_policy_lite_reference_mode,
            hybrid_reference=strategy_deliberation.final_weights,
            llm_weights=strategy_deliberation.llm_weights,
            llm_confidence=strategy_deliberation.confidence,
            llm_reason=strategy_deliberation.reason,
            llm_status=strategy_deliberation.status,
            llm_source=strategy_deliberation.source,
            rule_weights=rule_strategy_weights,
            lambda_llm=runtime_config.proto_bayesian_policy_lite_lambda_llm,
            min_llm_confidence=(
                runtime_config.proto_bayesian_policy_lite_min_llm_confidence
            ),
        )
        bayesian_policy_memory_pre, bayesian_policy_pre_audit = (
            compute_bayesian_policy_shadow(
                raw_memory=await self.memory.status.get(
                    "proto_bayesian_policy_memory",
                    {},
                ),
                mode=runtime_config.proto_bayesian_policy_lite_mode,
                task_family=task.task_family,
                strategy_reference=bayesian_policy_reference_audit.get("pi_ref"),
                task_difficulty=task.difficulty,
                env=env,
                task_appraisal=task_appraisal.to_dict(),
                tau=runtime_config.proto_bayesian_policy_lite_tau,
                confidence_k=runtime_config.proto_bayesian_policy_lite_confidence_k,
                rho=runtime_config.proto_bayesian_policy_lite_rho,
                weight=runtime_config.proto_bayesian_policy_lite_weight,
                utility_profile=(
                    runtime_config.proto_bayesian_policy_lite_utility_profile
                ),
                gate_threshold=(
                    runtime_config.proto_bayesian_policy_lite_gate_threshold
                ),
                entropy_threshold=(
                    runtime_config.proto_bayesian_policy_lite_entropy_threshold
                ),
                max_delta=runtime_config.proto_bayesian_policy_lite_max_delta,
                prob_floor=runtime_config.proto_bayesian_policy_lite_prob_floor,
                day=int(day),
            )
        )
        bayesian_policy_pre_audit.update(bayesian_policy_reference_audit)
        huys_dayan_memory_pre, huys_dayan_before_audit = (
            compute_huys_dayan_lite_before_event_audit(
                raw_policy_memory=bayesian_policy_memory_pre,
                raw_controllability_memory=await self.memory.status.get(
                    "proto_bayesian_controllability_lite_memory",
                    {},
                ),
                mode=runtime_config.proto_huys_dayan_lite_controllability_mode,
                task_family=task.task_family,
                confidence_k=runtime_config.proto_huys_dayan_lite_confidence_k,
                min_action_updates=(
                    runtime_config.proto_huys_dayan_lite_min_action_updates
                ),
                use_avoid_in_main_score=(
                    runtime_config.proto_huys_dayan_lite_use_avoid_in_main_score
                ),
                weight_entropy=runtime_config.proto_huys_dayan_lite_weight_entropy,
                weight_contrast=runtime_config.proto_huys_dayan_lite_weight_contrast,
                weight_chi=runtime_config.proto_huys_dayan_lite_weight_chi,
                utility_profile=(
                    runtime_config.proto_bayesian_policy_lite_utility_profile
                ),
                day=int(day),
                env=env,
                task_appraisal=task_appraisal.to_dict(),
            )
        )
        exp_seed = _safe_int(os.getenv("EXP_SEED", "101"), 101)
        pair_seed = _safe_int(os.getenv("PARALLEL_PAIR_SEED", str(exp_seed)), exp_seed)
        world_name = str(os.getenv("WORLD_NAME", "baseline_low_friction"))
        base_rng_seed = (
            exp_seed * 10000019
            + pair_seed * 1000033
            + int(self.id) * 1000003
            + int(day) * 10007
            + int(float(t))
            + sum(ord(ch) for ch in task.task_id)
            + 31 * sum(ord(ch) for ch in world_name)
        )
        strategy_rng = random.Random(base_rng_seed + 17)
        gated_lite_final_weights = None
        if runtime_config.proto_bayesian_policy_lite_mode == "gated_lite":
            candidate_weights = bayesian_policy_pre_audit.get("pi_final")
            if isinstance(candidate_weights, dict):
                gated_lite_final_weights = candidate_weights
        huys_dayan_final_weights, huys_dayan_modulation_audit = (
            apply_controllability_gated_modulation(
                mode=runtime_config.proto_huys_dayan_lite_controllability_mode,
                pi_base=gated_lite_final_weights,
                pi_ref=bayesian_policy_pre_audit.get("pi_ref"),
                q_bayes=bayesian_policy_pre_audit.get("q_bayes"),
                before_event_audit=huys_dayan_before_audit,
                gate_threshold=(
                    runtime_config
                    .proto_huys_dayan_lite_modulation_gate_threshold
                ),
                max_delta=(
                    runtime_config.proto_huys_dayan_lite_modulation_max_delta
                ),
                low_c_threshold=runtime_config.proto_huys_dayan_lite_low_c_threshold,
                high_c_threshold=(
                    runtime_config.proto_huys_dayan_lite_high_c_threshold
                ),
                prob_floor=runtime_config.proto_bayesian_policy_lite_prob_floor,
            )
        )
        if huys_dayan_final_weights is not None:
            gated_lite_final_weights = huys_dayan_final_weights
        strategy = choose_attempt_strategy(
            effective_helplessness=memory_features.effective_helplessness,
            support_quality=support_quality,
            task_difficulty=task.difficulty,
            consecutive_failures=consecutive_failures,
            task_self_efficacy=memory_features.task_self_efficacy,
            help_success_rate_smoothed=memory_features.help_success_rate_smoothed,
            recent_negative_feedback_ratio=memory_features.recent_negative_feedback_ratio,
            recent_same_task_failure_count=memory_features.recent_same_task_failure_count,
            strategy_deliberation_result=strategy_deliberation,
            precomputed_final_weights=gated_lite_final_weights,
            rng=strategy_rng,
        )
        support_request, support_response, support_ecology_status = (
            await self._resolve_family_support_response(
                task=task,
                strategy=strategy,
                task_appraisal=task_appraisal,
                task_relevant_memory_packet=task_relevant_memory_packet,
                env=env,
                profile_summary=profile_summary,
                day=int(day),
                tick=float(t),
            )
        )
        trajectory_result: dict[str, Any] | None = None
        outcome_model_mode = str(runtime_config.proto_outcome_model_mode)
        if (
            outcome_model_mode
            in {"trajectory_shadow", "trajectory_bounded_online_mc"}
            and strategy.strategy_type != "avoid"
        ):
            trajectory_result = await resolve_trajectory_appraisal(
                llm=getattr(self, "llm", None),
                task=task,
                strategy=strategy,
                task_appraisal=task_appraisal.to_dict(),
                memory_features=memory_features.to_dict(),
                env=env,
                profile_summary=profile_summary,
                run_context={
                    "agent_id": int(self.id),
                    "day": int(day),
                    "tick": float(t),
                    "world_name": world_name,
                    "parallel_pair_index": int(
                        os.getenv("PARALLEL_PAIR_INDEX", "0")
                    ),
                    "parallel_world_order": int(
                        os.getenv("PARALLEL_WORLD_ORDER", "0")
                    ),
                },
            )
            if outcome_model_mode == "trajectory_bounded_online_mc" and str(
                trajectory_result.get("status", "")
            ) not in {"ok", "ok_repaired"}:
                raise ValueError(
                    "trajectory_bounded_online_mc requires valid trajectory appraisal: "
                    + str(trajectory_result.get("invalid_reason") or trajectory_result.get("status"))
                )
        outcome = resolve_attempt_outcome(
            task=task,
            strategy=strategy,
            helplessness=helplessness,
            env=env,
            consecutive_failures=consecutive_failures,
            rng=random.Random(base_rng_seed + 29),
            outcome_model_mode=outcome_model_mode,
            task_appraisal=task_appraisal.to_dict(),
            memory_features=memory_features.to_dict(),
            trajectory_result=trajectory_result,
            trajectory_config={
                "alpha": runtime_config.proto_outcome_trajectory_alpha,
                "max_outcome_shift": (
                    runtime_config.proto_outcome_trajectory_max_outcome_shift
                ),
                "max_tvd": runtime_config.proto_outcome_trajectory_max_tvd,
                "min_confidence": (
                    runtime_config.proto_outcome_trajectory_min_confidence
                ),
            },
            support_response=support_response,
        )
        outcome.support_ecology_status = str(support_ecology_status)
        if support_response is not None:
            outcome.support_response_json = json.dumps(
                support_response.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
            )
            outcome.helper_agent_id = int(support_response.helper_agent_id or -1)
        calibration = await calibrate_uncontrollability(
            llm=getattr(self, "llm", None),
            task=task,
            strategy=strategy,
            outcome=outcome,
            env=env,
            helplessness_now=helplessness,
            consecutive_failures_before=consecutive_failures,
            pre_event_task_appraisal=task_appraisal.to_dict(),
            task_relevant_memory=task_relevant_memory_packet,
        )
        outcome.event_level_uncontrollability = calibration.final_value
        outcome.rule_event_level_uncontrollability = calibration.rule_value
        outcome.uncontrollability_source = calibration.source
        outcome.uncontrollability_llm_value = calibration.llm_value
        outcome.uncontrollability_llm_confidence = calibration.confidence
        outcome.uncontrollability_llm_reason = calibration.reason
        outcome.uncontrollability_status = calibration.status
        outcome.uncontrollability_cache_hit = calibration.cache_hit
        avoid_reason_result: dict[str, Any] | None = None
        if outcome.outcome_type == "avoid_without_attempt":
            avoid_reason_result = infer_avoid_reason(
                task=task,
                env=env,
                helplessness=helplessness,
                recent_same_task_failure_count=memory_features.recent_same_task_failure_count,
                task_self_efficacy=memory_features.task_self_efficacy,
                felt_control=task_appraisal.felt_control,
                perceived_task_risk=task_appraisal.perceived_task_risk,
                task_value=task_appraisal.task_value,
            )
            outcome.avoid_reason = str(avoid_reason_result["label"])
            outcome.avoid_reason_source = str(avoid_reason_result["source"])
            outcome.avoid_reason_confidence = float(avoid_reason_result["confidence"])
            outcome.avoid_reason_note = str(avoid_reason_result["note"])
        support_mode_result: dict[str, Any] | None = None
        if outcome.help_used:
            support_mode_result = infer_support_mode(
                outcome_type=outcome.outcome_type,
                support_quality=outcome.support_quality,
                felt_control=task_appraisal.felt_control,
                expected_help_effectiveness=task_appraisal.expected_help_effectiveness,
                support_response=support_response,
            )
            outcome.support_mode = str(support_mode_result["label"])
            outcome.support_mode_source = str(support_mode_result["source"])
        attribution_retrieval_packet = await self._retrieve_attribution_episodic_memory(
            runtime_config=runtime_config,
            task=task,
        )
        event_attribution = await infer_event_attribution(
            llm=getattr(self, "llm", None),
            task=task,
            outcome=outcome,
            task_self_efficacy=memory_features.task_self_efficacy,
            felt_control=task_appraisal.felt_control,
            recent_same_task_failure_count=memory_features.recent_same_task_failure_count,
            helplessness_now=helplessness,
            trust_now=trust,
            avoidance_now=avoidance,
            profile_summary=profile_summary,
            same_task_recent_context=task_relevant_memory_packet,
            cross_task_recent_context=cross_task_recent_context,
            relevant_mastery_summary=relevant_mastery_summary,
            latest_daily_reflection=current_daily_reflection,
            latest_stage_quote=latest_stage_quote,
            retrieved_similar_episodes=attribution_retrieval_packet,
        )
        outcome.event_attribution_locus = event_attribution.event_attribution_locus
        outcome.event_attribution_stability = (
            event_attribution.event_attribution_stability
        )
        outcome.event_attribution_scope = event_attribution.event_attribution_scope
        outcome.event_attribution_scope_amplitude = (
            event_attribution.event_attribution_scope_amplitude
        )
        outcome.event_attribution_explanation = (
            event_attribution.event_attribution_explanation
        )
        outcome.event_attribution_confidence = event_attribution.judge_confidence
        outcome.event_attribution_source = event_attribution.source
        outcome.event_attribution_status = event_attribution.status
        outcome.event_attribution_cache_hit = event_attribution.cache_hit
        current_task_snapshot = (
            task_domain_memory.get(task.task_family, {})
            if isinstance(task_domain_memory, dict)
            else {}
        )
        current_help_snapshot = _support_snapshot_for_task(
            help_effect_memory, task.task_family
        )
        pre_update_recent_summary = {
            "recent_negative_feedback_ratio": memory_features.recent_negative_feedback_ratio,
            "recent_avoid_ratio": memory_features.recent_avoid_ratio,
            "recent_help_seek_ratio": memory_features.recent_help_seek_ratio,
            "recent_same_task_failure_count": memory_features.recent_same_task_failure_count,
            "recent_failure_pressure": memory_features.recent_failure_pressure,
            "emotion_pressure": memory_features.emotion_pressure,
        }
        event_appraisal = await resolve_event_appraisal(
            llm=getattr(self, "llm", None),
            task=task,
            strategy=strategy,
            outcome=outcome,
            helplessness_now=helplessness,
            consecutive_failures_before=consecutive_failures,
            digital_emotion_state=digital_emotion_state.to_dict(),
            task_domain_snapshot=current_task_snapshot,
            help_effect_snapshot=current_help_snapshot,
            recent_episode_summary=pre_update_recent_summary,
            pre_event_task_appraisal=task_appraisal.to_dict(),
            task_relevant_memory_lite={
                "same_task_last_outcome": task_relevant_memory_packet.get(
                    "same_task_last_outcome", ""
                ),
                "same_task_failure_count": task_relevant_memory_packet.get(
                    "same_task_failure_count",
                    0,
                ),
                "same_task_failure_streak": task_relevant_memory_packet.get(
                    "same_task_failure_streak",
                    0,
                ),
                "same_task_controllable_success_memory": task_relevant_memory_packet.get(
                    "same_task_controllable_success_memory",
                    0.0,
                ),
                "help_success_rate_same_task": task_relevant_memory_packet.get(
                    "help_success_rate_same_task",
                    0.5,
                ),
                "recent_same_task_outcomes_tail": task_relevant_memory_packet.get(
                    "recent_same_task_outcomes_tail",
                    [],
                ),
            },
            day=current_day,
        )
        updated_digital_emotion_state = {
            **event_appraisal.final_after,
            "last_updated_day": current_day,
        }
        update_result = apply_helplessness_update(
            HelplessnessUpdateInput(
                helplessness_now=helplessness,
                outcome_type=outcome.outcome_type,
                consecutive_failures=consecutive_failures,
                support_quality=outcome.support_quality,
                event_level_uncontrollability=outcome.event_level_uncontrollability,
                task_self_efficacy=memory_features.task_self_efficacy,
                felt_control=task_appraisal.felt_control,
                expected_help_effectiveness=task_appraisal.expected_help_effectiveness,
                avoid_reason=outcome.avoid_reason,
                controllable_success_memory=memory_features.controllable_success_memory,
                support_mode=outcome.support_mode,
                helplessness_update_mode=(
                    runtime_config.proto_helplessness_update_mode
                ),
                event_attribution_locus=outcome.event_attribution_locus,
                event_attribution_stability=outcome.event_attribution_stability,
                event_attribution_scope=outcome.event_attribution_scope,
                event_attribution_confidence=outcome.event_attribution_confidence,
            )
        )
        compat = apply_compatibility_updates(
            trust_now=trust,
            avoidance_now=avoidance,
            outcome_type=outcome.outcome_type,
            help_used=outcome.help_used,
            avoid_reason=outcome.avoid_reason,
        )
        memory_update = update_experience_memory(
            task=task,
            strategy=strategy,
            outcome=outcome,
            day=int(day),
            helplessness_delta=float(update_result.delta),
            task_domain_memory=task_domain_memory,
            help_effect_memory=help_effect_memory,
            recent_episode_buffer=recent_episode_buffer,
            rationale_memory=rationale_memory,
            task_appraisal_result=task_appraisal.to_dict(),
            support_response=support_response,
        )
        bayesian_control_memory, bayesian_control_audit = (
            update_bayesian_control_memory(
                raw_memory=await self.memory.status.get(
                    "proto_bayesian_control_memory",
                    {},
                ),
                enabled=runtime_config.proto_bayesian_control_audit_enabled,
                task_family=task.task_family,
                outcome_type=outcome.outcome_type,
                support_mode=outcome.support_mode,
                avoid_reason=outcome.avoid_reason,
                event_level_uncontrollability=(
                    outcome.event_level_uncontrollability
                ),
                uncontrollability_source=outcome.uncontrollability_source,
                rho=runtime_config.proto_bayesian_control_rho,
                weight=runtime_config.proto_bayesian_control_weight,
                day=int(day),
            )
        )
        bayesian_policy_memory, bayesian_policy_update_audit = (
            update_bayesian_policy_memory(
                raw_memory=bayesian_policy_memory_pre,
                mode=runtime_config.proto_bayesian_policy_lite_mode,
                task_family=task.task_family,
                actual_strategy=strategy.strategy_type,
                outcome_type=outcome.outcome_type,
                event_level_uncontrollability=(
                    outcome.event_level_uncontrollability
                ),
                support_mode=outcome.support_mode,
                avoid_reason=outcome.avoid_reason,
                event_attribution_locus=outcome.event_attribution_locus,
                event_attribution_stability=outcome.event_attribution_stability,
                event_attribution_scope=outcome.event_attribution_scope,
                rho=runtime_config.proto_bayesian_policy_lite_rho,
                weight=runtime_config.proto_bayesian_policy_lite_weight,
                day=int(day),
            )
        )
        bayesian_policy_audit = combine_bayesian_policy_audits(
            pre_audit=bayesian_policy_pre_audit,
            update_audit=bayesian_policy_update_audit,
            actual_strategy=strategy.strategy_type,
        )
        huys_dayan_memory, huys_dayan_after_audit = (
            compute_huys_dayan_lite_after_event_audit(
                raw_policy_memory=bayesian_policy_memory,
                raw_controllability_memory=huys_dayan_memory_pre,
                mode=runtime_config.proto_huys_dayan_lite_controllability_mode,
                task_family=task.task_family,
                confidence_k=runtime_config.proto_huys_dayan_lite_confidence_k,
                min_action_updates=(
                    runtime_config.proto_huys_dayan_lite_min_action_updates
                ),
                use_avoid_in_main_score=(
                    runtime_config.proto_huys_dayan_lite_use_avoid_in_main_score
                ),
                weight_entropy=runtime_config.proto_huys_dayan_lite_weight_entropy,
                weight_contrast=runtime_config.proto_huys_dayan_lite_weight_contrast,
                weight_chi=runtime_config.proto_huys_dayan_lite_weight_chi,
                utility_profile=(
                    runtime_config.proto_bayesian_policy_lite_utility_profile
                ),
                global_update_weight=(
                    runtime_config.proto_huys_dayan_lite_global_update_weight
                ),
                rho=runtime_config.proto_huys_dayan_lite_rho,
                day=int(day),
            )
        )
        huys_dayan_audit = combine_huys_dayan_lite_audits(
            before_audit=huys_dayan_before_audit,
            modulation_audit=huys_dayan_modulation_audit,
            after_audit=huys_dayan_after_audit,
        )
        stream_episode_recording = await self._record_phase0_stream_episodes(
            runtime_config=runtime_config,
            task=task,
            strategy=strategy,
            outcome=outcome,
            memory_features=memory_features,
        )
        stage_name = str(env.get("digital_stage") or env.get("stage_name") or "stage")
        positive_event = outcome.outcome_type in {"success_self", "success_with_help"}
        decision = {
            "primary_reason": outcome.outcome_type,
            "reason_tags": (
                ["success_experience"]
                if positive_event
                else ["negative_feedback"]
                if outcome.negative_feedback
                else ["avoidance"]
            ),
            "task_family": task.task_family,
            "friction_type": task.friction_type,
            "strategy_type": strategy.strategy_type,
            "support_quality": outcome.support_quality,
            "event_level_uncontrollability": outcome.event_level_uncontrollability,
            "rule_event_level_uncontrollability": (
                outcome.rule_event_level_uncontrollability
            ),
            "uncontrollability_source": outcome.uncontrollability_source,
            "uncontrollability_llm_confidence": outcome.uncontrollability_llm_confidence,
            "avoid_reason": outcome.avoid_reason,
            "avoid_reason_source": outcome.avoid_reason_source,
            "avoid_reason_confidence": outcome.avoid_reason_confidence,
            "support_mode": outcome.support_mode,
            "support_mode_source": outcome.support_mode_source,
            "helper_agent_id": int(outcome.helper_agent_id),
            "support_ecology_status": str(support_ecology_status),
            "support_request": (
                support_request.to_dict() if support_request is not None else {}
            ),
            "support_response": (
                support_response.to_dict() if support_response is not None else {}
            ),
            "event_attribution_locus": outcome.event_attribution_locus,
            "event_attribution_stability": outcome.event_attribution_stability,
            "event_attribution_scope": outcome.event_attribution_scope,
            "event_attribution_scope_amplitude": float(
                outcome.event_attribution_scope_amplitude
            ),
            "event_attribution_confidence": outcome.event_attribution_confidence,
            "event_attribution_source": outcome.event_attribution_source,
            "scope_spillover_total": float(outcome.scope_spillover_total),
            "scope_spillover_targets_json": str(outcome.scope_spillover_targets_json),
            "event_appraisal_source": event_appraisal.source,
            "event_appraisal_confidence": event_appraisal.confidence,
            "pre_event_felt_control": float(task_appraisal.felt_control),
            "pre_event_task_risk": float(task_appraisal.perceived_task_risk),
            "pre_event_help_effectiveness": float(
                task_appraisal.expected_help_effectiveness
            ),
            "same_task_failure_count": int(
                task_relevant_memory_packet.get("same_task_failure_count", 0)
            ),
            "same_task_controllable_success_memory": float(
                task_relevant_memory_packet.get(
                    "same_task_controllable_success_memory",
                    0.0,
                )
            ),
            "task_appraisal_profile_age_bucket": age_bucket(
                profile_summary.get("age", -1)
            ),
            "task_appraisal_profile_persona_tag": persona_bucket(
                profile_summary.get("persona", "")
            ),
            "rationale": strategy.rationale,
            "strategy_weights": dict(strategy.weights),
            "effective_helplessness": memory_features.effective_helplessness,
            "memory_features": memory_features.to_dict(),
            "outcome_model_mode": outcome.outcome_model_mode,
            "trajectory_status": outcome.trajectory_status,
            "trajectory_confidence": float(outcome.trajectory_confidence),
            "trajectory_tvd_from_rule": float(outcome.trajectory_tvd_from_rule),
            "retrieved_episodic_memory_hash": task_appraisal_retrieval_packet["hash"],
            "retrieved_episodic_memory_count": task_appraisal_retrieval_packet["count"],
            "retrieved_episodic_memory_status": task_appraisal_retrieval_packet[
                "status"
            ],
            "retrieval_condition": task_appraisal_retrieval_packet["condition"],
            "retrieved_attribution_episodic_memory_hash": attribution_retrieval_packet[
                "hash"
            ],
            "retrieved_attribution_episodic_memory_count": attribution_retrieval_packet[
                "count"
            ],
            "retrieved_attribution_episodic_memory_status": (
                attribution_retrieval_packet["status"]
            ),
            "attribution_retrieval_condition": attribution_retrieval_packet[
                "condition"
            ],
        }
        event_log.append(
            {
                "day": int(day),
                "t": float(t),
                "attempt_uid": task.task_id,
                "scenario": task.task_family,
                "outcome": "positive"
                if positive_event
                else "negative"
                if outcome.negative_feedback
                else "neutral",
                "message": f"{task.task_family}:{outcome.outcome_type}",
                "roll": outcome.success_probability,
                "decision": decision,
            }
        )
        attempt_rows = _decode_json_list(
            await self.memory.status.get("proto_stage_attempt_rows_json", "[]")
        )
        attempt_row = {
            "agent_id": int(self.id),
            "day": int(day),
            "t": float(t),
            "step": int(day * 100000 + float(t)),
            "stage_name": stage_name,
            "task_id": task.task_id,
            "task_family": task.task_family,
            "friction_type": task.friction_type,
            "strategy_type": strategy.strategy_type,
            "outcome_type": outcome.outcome_type,
            "support_quality": int(outcome.support_quality),
            "event_level_uncontrollability": int(
                outcome.event_level_uncontrollability
            ),
            "rule_event_level_uncontrollability": int(
                outcome.rule_event_level_uncontrollability
            ),
            "uncontrollability_source": str(outcome.uncontrollability_source),
            "uncontrollability_llm_confidence": float(
                outcome.uncontrollability_llm_confidence
            ),
            "event_attribution_scope_amplitude": float(
                outcome.event_attribution_scope_amplitude
            ),
            "scope_spillover_total": float(outcome.scope_spillover_total),
            "scope_spillover_targets_json": str(outcome.scope_spillover_targets_json),
            "helplessness_before": float(update_result.helplessness_before),
            "helplessness_after": float(update_result.helplessness_after),
            "helplessness_delta": float(update_result.delta),
            "help_used": bool(outcome.help_used),
            "negative_feedback": bool(outcome.negative_feedback),
            "outcome_model_mode": str(outcome.outcome_model_mode),
            "trajectory_status": str(outcome.trajectory_status),
            "trajectory_confidence": float(outcome.trajectory_confidence),
            "trajectory_tvd_from_rule": float(outcome.trajectory_tvd_from_rule),
            "strategy_weights_json": json.dumps(strategy.weights, ensure_ascii=False),
            "payload_json": json.dumps(
                {
                    "task": task.to_dict(),
                    "strategy": strategy.to_dict(),
                    "outcome": outcome.to_dict(),
                    "support_request": (
                        support_request.to_dict()
                        if support_request is not None
                        else {}
                    ),
                    "support_response": (
                        support_response.to_dict()
                        if support_response is not None
                        else {}
                    ),
                    "profile_summary": profile_summary,
                    "task_relevant_memory": task_relevant_memory_packet,
                    "retrieved_episodic_memory": task_appraisal_retrieval_packet,
                    "retrieved_attribution_episodic_memory": (
                        attribution_retrieval_packet
                    ),
                    "task_appraisal": task_appraisal.to_dict(),
                    "strategy_deliberation": strategy_deliberation.to_dict(),
                    "uncontrollability_calibration": calibration.to_dict(),
                    "psychology_mode": event_appraisal.mode,
                    "event_appraisal": event_appraisal.to_dict(),
                    "update": update_result.to_dict(),
                    "compat": compat.to_dict(),
                    "memory_features": memory_features.to_dict(),
                    "task_domain_snapshot": memory_update["task_domain_snapshot"],
                    "help_effect_snapshot": memory_update["help_effect_snapshot"],
                    "recent_episode_summary": memory_update["recent_episode_summary"],
                    "paper_backed_core": {
                        "helplessness": {
                            "before": float(update_result.helplessness_before),
                            "after": float(update_result.helplessness_after),
                            "delta": float(update_result.delta),
                        },
                        "update_breakdown": {
                            "mode": str(update_result.mode),
                            "status": str(update_result.status),
                            "base_delta": float(update_result.base_delta),
                            "base_failure_signal": float(
                                update_result.base_failure_signal
                            ),
                            "uncontrollability_delta": float(
                                update_result.uncontrollability_delta
                            ),
                            "noncontingency_harm": float(
                                update_result.noncontingency_harm
                            ),
                            "efficacy_loss_term": float(
                                update_result.efficacy_loss_term
                            ),
                            "self_efficacy_harm": float(
                                update_result.self_efficacy_harm
                            ),
                            "affective_distress_harm": float(
                                update_result.affective_distress_harm
                            ),
                            "mastery_recovery_term": float(
                                update_result.mastery_recovery_term
                            ),
                            "attribution_multiplier": float(
                                update_result.attribution_multiplier
                            ),
                            "attribution_recovery_multiplier": float(
                                update_result.attribution_recovery_multiplier
                            ),
                            "raw_delta_before_damping": float(
                                update_result.raw_delta_before_damping
                            ),
                            "damping_factor": float(update_result.damping_factor),
                            "avoid_reason_multiplier": float(
                                update_result.avoid_reason_multiplier
                            ),
                            "controllable_success_protection": float(
                                update_result.controllable_success_protection
                            ),
                            "rule_fallback_reason": str(
                                update_result.rule_fallback_reason
                            ),
                            "effective_delta": float(update_result.delta),
                        },
                        "avoid_reason": {
                            "label": str(outcome.avoid_reason),
                            "source": str(outcome.avoid_reason_source),
                            "confidence": float(outcome.avoid_reason_confidence),
                            "note": str(outcome.avoid_reason_note),
                            "scores": (
                                avoid_reason_result["scores"]
                                if isinstance(avoid_reason_result, dict)
                                else {}
                            ),
                        },
                        "event_level_uncontrollability": {
                            "final": int(outcome.event_level_uncontrollability),
                            "rule": int(outcome.rule_event_level_uncontrollability),
                            "source": str(outcome.uncontrollability_source),
                            "llm_confidence": float(
                                outcome.uncontrollability_llm_confidence
                            ),
                        },
                        "event_attribution": event_attribution.to_dict(),
                        "task_specific_self_efficacy": float(
                            memory_features.task_self_efficacy
                        ),
                        "controllable_success_memory": float(
                            memory_features.controllable_success_memory
                        ),
                        "task_appraisal": {
                            "perceived_task_difficulty": float(
                                task_appraisal.perceived_task_difficulty
                            ),
                            "perceived_task_risk": float(
                                task_appraisal.perceived_task_risk
                            ),
                            "felt_control": float(task_appraisal.felt_control),
                            "expected_help_effectiveness": float(
                                task_appraisal.expected_help_effectiveness
                            ),
                            "task_value": float(task_appraisal.task_value),
                            "task_appraisal_shift": float(
                                memory_features.task_appraisal_shift
                            ),
                            "source": str(task_appraisal.source),
                            "confidence": float(task_appraisal.confidence),
                        },
                        "support_effectiveness": {
                            "help_success_rate_smoothed": float(
                                memory_features.help_success_rate_smoothed
                            ),
                            "support_quality": int(outcome.support_quality),
                            "support_mode": str(outcome.support_mode),
                            "support_mode_source": str(outcome.support_mode_source),
                            "support_ecology_status": str(support_ecology_status),
                            "helper_agent_id": int(outcome.helper_agent_id),
                            "support_style": (
                                support_response.support_style
                                if support_response is not None
                                else "not_applicable"
                            ),
                            "instruction_quality": (
                                support_response.instruction_quality
                                if support_response is not None
                                else "not_applicable"
                            ),
                            "autonomy_preservation": (
                                support_response.autonomy_preservation
                                if support_response is not None
                                else "not_applicable"
                            ),
                            "proxy_completion_level": (
                                support_response.proxy_completion_level
                                if support_response is not None
                                else "not_applicable"
                            ),
                            "mode_note": (
                                str(support_mode_result["note"])
                                if isinstance(support_mode_result, dict)
                                else ""
                            ),
                        },
                        "recent_negative_experience": {
                            "recent_negative_feedback_ratio": float(
                                memory_features.recent_negative_feedback_ratio
                            ),
                            "recent_same_task_failure_count": int(
                                memory_features.recent_same_task_failure_count
                            ),
                            "recent_failure_pressure": float(
                                memory_features.recent_failure_pressure
                            ),
                        },
                        "digital_emotion_primary": {
                            "anxiety_before": float(
                                event_appraisal.emotion_before.get("anxiety", 0.0)
                            ),
                            "anxiety_after": float(
                                event_appraisal.final_after.get("anxiety", 0.0)
                            ),
                            "confidence_before": float(
                                event_appraisal.emotion_before.get("confidence", 0.0)
                            ),
                            "confidence_after": float(
                                event_appraisal.final_after.get("confidence", 0.0)
                            ),
                            "emotion_pressure": float(
                                memory_features.emotion_pressure
                            ),
                        },
                        "survey_measurements": {
                            "survey_helplessness_index": float(
                                survey_helplessness_index
                            ),
                            "survey_withdrawal_index": float(
                                survey_withdrawal_index
                            ),
                            "survey_self_efficacy_index": float(
                                survey_self_efficacy_index
                            ),
                            "survey_support_index": float(survey_support_index),
                            "survey_usefulness_index": float(
                                survey_usefulness_index
                            ),
                            "survey_anxiety_index": float(survey_anxiety_index),
                        },
                    },
                    "auxiliary_audit": {
                        "daily_reflection_role": "audit_exploratory",
                        "daily_reflection": current_daily_reflection,
                        "bounded_hybrid_decision_role": "optional_hybrid",
                        "strategy_deliberation_enabled": bool(
                            runtime_config.proto_llm_strategy_deliberation_enabled
                        ),
                        "strategy_deliberation": strategy_deliberation.to_dict(),
                        "rationale_snapshot": memory_update["rationale_snapshot"],
                        "bayesian_control": bayesian_control_audit,
                        "bayesian_policy_lite": bayesian_policy_audit,
                        "huys_dayan_lite_controllability": huys_dayan_audit,
                        "stream_episode_recording": stream_episode_recording,
                        "stream_appraisal_retrieval": {
                            "condition": task_appraisal_retrieval_packet["condition"],
                            "status": task_appraisal_retrieval_packet["status"],
                            "hash": task_appraisal_retrieval_packet["hash"],
                            "count": task_appraisal_retrieval_packet["count"],
                            "query": task_appraisal_retrieval_packet["query"],
                            "topics": task_appraisal_retrieval_packet["topics"],
                        },
                        "stream_attribution_retrieval": {
                            "condition": attribution_retrieval_packet["condition"],
                            "status": attribution_retrieval_packet["status"],
                            "hash": attribution_retrieval_packet["hash"],
                            "count": attribution_retrieval_packet["count"],
                            "query": attribution_retrieval_packet["query"],
                            "topics": attribution_retrieval_packet["topics"],
                        },
                        "digital_emotion_secondary": {
                            "frustration_before": float(
                                event_appraisal.emotion_before.get(
                                    "frustration", 0.0
                                )
                            ),
                            "frustration_after": float(
                                event_appraisal.final_after.get(
                                    "frustration", 0.0
                                )
                            ),
                            "relief_before": float(
                                event_appraisal.emotion_before.get("relief", 0.0)
                            ),
                            "relief_after": float(
                                event_appraisal.final_after.get("relief", 0.0)
                            ),
                        },
                    },
                },
                ensure_ascii=False,
            ),
        }
        attempt_rows.append(attempt_row)

        negative_event_count = _safe_int(
            await self.memory.status.get("negative_event_count", 0)
        ) + compat.negative_event_increment
        help_request_count = _safe_int(
            await self.memory.status.get("help_request_count", 0)
        ) + compat.help_request_increment
        success_count = _safe_int(await self.memory.status.get("success_count", 0)) + compat.success_increment
        failure_count = _safe_int(await self.memory.status.get("failure_count", 0)) + compat.failure_increment
        intercept_count = _safe_int(await self.memory.status.get("intercept_count", 0)) + compat.intercept_increment

        cumulative_negative = _safe_int(
            await self.memory.status.get("cumulative_negative_event_count", 0)
        ) + compat.negative_event_increment
        cumulative_help = _safe_int(
            await self.memory.status.get("cumulative_help_request_count", 0)
        ) + compat.help_request_increment
        cumulative_success = _safe_int(
            await self.memory.status.get("cumulative_success_count", 0)
        ) + compat.success_increment
        cumulative_failure = _safe_int(
            await self.memory.status.get("cumulative_failure_count", 0)
        ) + compat.failure_increment
        cumulative_intercept = _safe_int(
            await self.memory.status.get("cumulative_intercept_count", 0)
        ) + compat.intercept_increment

        await self.memory.status.update("helplessness_score", update_result.helplessness_after)
        await self.memory.status.update("trust_in_apps", compat.trust_in_apps)
        await self.memory.status.update("avoidance_tendency", compat.avoidance_tendency)
        await self.memory.status.update(
            "survey_helplessness_index", update_result.helplessness_after
        )
        await self.memory.status.update(
            "proto_consecutive_failures", update_result.next_consecutive_failures
        )
        await self.memory.status.update("negative_event_count", negative_event_count)
        await self.memory.status.update("help_request_count", help_request_count)
        await self.memory.status.update("success_count", success_count)
        await self.memory.status.update("failure_count", failure_count)
        await self.memory.status.update("intercept_count", intercept_count)
        await self.memory.status.update(
            "cumulative_negative_event_count", cumulative_negative
        )
        await self.memory.status.update(
            "cumulative_help_request_count", cumulative_help
        )
        await self.memory.status.update("cumulative_success_count", cumulative_success)
        await self.memory.status.update("cumulative_failure_count", cumulative_failure)
        await self.memory.status.update(
            "cumulative_intercept_count", cumulative_intercept
        )
        await self.memory.status.update("event_log", event_log)
        await self.memory.status.update(
            "digital_emotion_state", updated_digital_emotion_state
        )
        await self._persist_proto_decision_state(
            task_appraisal=task_appraisal,
            strategy_deliberation=strategy_deliberation,
            event_attribution=event_attribution,
        )
        await self._record_event_attribution_stream(
            task=task,
            outcome=outcome,
            event_attribution=event_attribution,
        )
        await self.memory.status.update(
            "task_domain_memory", memory_update["task_domain_memory"]
        )
        await self.memory.status.update(
            "help_effect_memory", memory_update["help_effect_memory"]
        )
        await self.memory.status.update(
            "recent_episode_buffer", memory_update["recent_episode_buffer"]
        )
        await self.memory.status.update(
            "rationale_memory", memory_update["rationale_memory"]
        )
        if bayesian_control_audit.get("status") == "updated":
            await self.memory.status.update(
                "proto_bayesian_control_memory",
                bayesian_control_memory,
            )
        if bayesian_policy_audit.get("status") == "updated":
            await self.memory.status.update(
                "proto_bayesian_policy_memory",
                bayesian_policy_memory,
            )
        if huys_dayan_after_audit.get("status") == "updated":
            await self.memory.status.update(
                "proto_bayesian_controllability_lite_memory",
                huys_dayan_memory,
            )
        await self.memory.status.update(
            "proto_stage_attempt_rows_json", json.dumps(attempt_rows, ensure_ascii=False)
        )
        await self.memory.status.update(
            "current_intention", f"{task.task_family}:{strategy.strategy_type}"
        )
        await self.memory.status.update(
            "friction_step_signal",
            {
                "step_type": "digital_task",
                "step_intention": f"{task.task_family}:{strategy.strategy_type}",
                "step_outcome": outcome.outcome_type,
                "status_text": outcome.note,
            },
        )
        should_defer = (
            outcome.outcome_type == "avoid_without_attempt" and int(task.defer_count) < 1
        )
        if should_defer:
            task.defer_count += 1
            await self.memory.status.update("proto_assigned_task_json", encode_task(task))
            await self.memory.status.update("digital_todo_pending", 1)
            await self.memory.status.update("digital_todo_active_task_id", task.task_id)
        else:
            await self.memory.status.update("proto_assigned_task_json", "")
            await self.memory.status.update("digital_todo_pending", 0)
            await self.memory.status.update("digital_todo_active_task_id", "")
            await self.memory.status.update("digital_todo_active_day", -1)
            await self.memory.status.update("digital_todo_active_t", 0.0)
            await self.memory.status.update("digital_task_hint", "")
            await self.memory.status.update("digital_task_hint_need", "")
            await self.memory.status.update("digital_task_hint_pending", 0)
        return float(update_result.delta)
