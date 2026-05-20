from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import DigitalTask, TaskFamily

MOBILE_INTENTION_SET: tuple[str, ...] = (
    "check_information",
    "use_payment_or_finance",
    "login_or_verify_account",
    "submit_service_application",
    "upload_or_manage_profile",
    "find_location_or_service",
    "communicate_or_seek_help",
    "browse_entertainment",
    "no_mobile_action",
    "unknown_or_unmapped",
)

MOBILE_INTENTION_TO_TASK_FAMILY: dict[str, TaskFamily] = {
    "check_information": "information_search_judgment",
    "use_payment_or_finance": "payment_risk_confirmation",
    "login_or_verify_account": "account_login_verification",
    "submit_service_application": "service_application_submission",
    "upload_or_manage_profile": "profile_form_upload",
    "find_location_or_service": "navigation_service_location",
}

CONTEXT_ONLY_MOBILE_INTENTIONS: frozenset[str] = frozenset(
    {
        "communicate_or_seek_help",
        "browse_entertainment",
        "no_mobile_action",
        "unknown_or_unmapped",
    }
)


@dataclass(slots=True)
class MobileEntryDecision:
    entry_evaluated: bool
    selected_mobile_intention: str
    entry_status: str
    mapped_task_family: str | None
    mapping_confidence: float
    task_generated: bool
    task: DigitalTask | None = None
    candidate_intentions: dict[str, float] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["task"] = self.task.to_dict() if self.task is not None else None
        return payload

TASK_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "task_family": "navigation_service_location",
        "friction_type": "information_overload",
        "need_type": "service_location",
        "difficulty": 0.58,
        "support_sensitivity": 0.70,
    },
    {
        "task_family": "account_login_verification",
        "friction_type": "verification",
        "need_type": "secure_access",
        "difficulty": 0.64,
        "support_sensitivity": 0.85,
    },
    {
        "task_family": "information_search_judgment",
        "friction_type": "information_overload",
        "need_type": "information_access",
        "difficulty": 0.56,
        "support_sensitivity": 0.62,
    },
    {
        "task_family": "profile_form_upload",
        "friction_type": "form_complexity",
        "need_type": "profile_management",
        "difficulty": 0.61,
        "support_sensitivity": 0.72,
    },
    {
        "task_family": "service_application_submission",
        "friction_type": "form_complexity",
        "need_type": "service_completion",
        "difficulty": 0.63,
        "support_sensitivity": 0.74,
    },
    {
        "task_family": "payment_risk_confirmation",
        "friction_type": "payment_risk_popup",
        "need_type": "daily_transaction",
        "difficulty": 0.67,
        "support_sensitivity": 0.78,
    },
)

_TASK_WINDOW_SECONDS: tuple[int, ...] = (
    9 * 60 * 60,
    14 * 60 * 60,
    19 * 60 * 60,
)
_TASK_WINDOW_TOLERANCE_SECONDS = 120
_CALIBRATION_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_MAPPING_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_DEFAULT_UNCALIBRATED_PRIOR: dict[str, float] = {
    "check_information": 0.18,
    "use_payment_or_finance": 0.10,
    "login_or_verify_account": 0.10,
    "submit_service_application": 0.14,
    "upload_or_manage_profile": 0.08,
    "find_location_or_service": 0.10,
    "communicate_or_seek_help": 0.12,
    "browse_entertainment": 0.10,
    "no_mobile_action": 0.06,
    "unknown_or_unmapped": 0.02,
}


def clamp_score(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def top_mobile_intention_candidates(
    candidate_intentions: dict[str, float],
    *,
    top_k: int = 5,
) -> dict[str, float]:
    limit = max(1, int(top_k))
    normalized = _normalize_distribution(candidate_intentions)
    return {
        key: float(value)
        for key, value in sorted(
            normalized.items(),
            key=lambda item: (-float(item[1]), item[0]),
        )[:limit]
    }


def mobile_intention_candidate_hash(candidate_intentions: dict[str, float]) -> str:
    return _stable_hash(
        {
            key: round(float(value), 12)
            for key, value in sorted(candidate_intentions.items())
        }
    )[:16]


def _artifact_hash(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return ""
    try:
        return hashlib.sha256(Path(normalized).read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def _normalize_distribution(values: dict[str, Any]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for intention in MOBILE_INTENTION_SET:
        try:
            cleaned[intention] = max(0.0, float(values.get(intention, 0.0)))
        except (TypeError, ValueError):
            cleaned[intention] = 0.0
    total = sum(cleaned.values())
    if total <= 0.0:
        return dict(_DEFAULT_UNCALIBRATED_PRIOR)
    return {key: value / total for key, value in cleaned.items()}


def _load_json_artifact(path: str, *, cache: dict[str, tuple[str, dict[str, Any]]]) -> tuple[dict[str, Any], str]:
    normalized = str(path or "").strip()
    if not normalized:
        return {}, ""
    if "validation" in normalized.lower():
        raise ValueError(
            "mobile-intention runtime cannot read validation artifacts; "
            "use elder_reference May1-May3 calibration artifacts only"
        )
    artifact_path = Path(normalized)
    if not artifact_path.exists():
        raise FileNotFoundError(f"mobile-intention artifact not found: {artifact_path}")
    digest = _artifact_hash(normalized)
    cached = cache.get(normalized)
    if cached is not None and cached[0] == digest:
        return cached[1], digest
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"mobile-intention artifact must be a JSON object: {artifact_path}")
    if bool(payload.get("uses_validation_data", False)):
        raise ValueError(
            "mobile-intention runtime cannot read artifacts marked "
            "uses_validation_data=true"
        )
    cache[normalized] = (digest, payload)
    return payload, digest


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bucket_for_profile(profile: dict[str, Any] | None) -> str:
    payload = profile or {}
    age = _safe_int(payload.get("age"), -1)
    if age < 0:
        age_bucket = "unknown"
    elif age < 65:
        age_bucket = "lt65"
    elif age < 75:
        age_bucket = "65_74"
    else:
        age_bucket = "75plus"
    gender = str(payload.get("gender") or payload.get("sex") or "unknown").strip().lower()
    if gender in {"女", "f", "female"}:
        gender_bucket = "female"
    elif gender in {"男", "m", "male"}:
        gender_bucket = "male"
    else:
        gender_bucket = "unknown"
    digital_experience = float(payload.get("digital_experience", 0.5) or 0.5)
    if digital_experience < 0.34:
        digital_bucket = "digital_low"
    elif digital_experience < 0.67:
        digital_bucket = "digital_mid"
    else:
        digital_bucket = "digital_high"
    return f"{age_bucket}|{gender_bucket}|{digital_bucket}"


def _hour_for_tick(tick_seconds: float) -> int:
    return int(round(float(tick_seconds))) // 3600 % 24


def _extract_prior_from_calibration(
    *,
    calibration: dict[str, Any],
    profile: dict[str, Any] | None,
    hour: int,
) -> tuple[dict[str, float], str]:
    if not calibration:
        return dict(_DEFAULT_UNCALIBRATED_PRIOR), "uncalibrated_default"
    bucket = _bucket_for_profile(profile)
    hour_key = str(int(hour))
    candidates = [
        calibration.get("mobile_intention_prior_by_bucket_hour", {})
        if isinstance(calibration.get("mobile_intention_prior_by_bucket_hour"), dict)
        else {},
        calibration.get("priors", {}) if isinstance(calibration.get("priors"), dict) else {},
    ]
    for table in candidates:
        for key in (
            f"{bucket}|hour={hour_key}",
            f"{bucket}|{hour_key}",
            f"{bucket}:{hour_key}",
        ):
            row = table.get(key)
            if isinstance(row, dict):
                values = row.get("p_mobile_intention", row)
                if isinstance(values, dict):
                    return _normalize_distribution(values), f"bucket_hour:{key}"
        row = table.get(bucket)
        if isinstance(row, dict):
            hour_rows = row.get("hours", row)
            if isinstance(hour_rows, dict):
                hour_row = hour_rows.get(hour_key, hour_rows.get(int(hour), None))
                if isinstance(hour_row, dict):
                    values = hour_row.get("p_mobile_intention", hour_row)
                    if isinstance(values, dict):
                        return _normalize_distribution(values), f"bucket:{bucket}:hour:{hour_key}"
    global_hourly = calibration.get("global_hourly_prior", {})
    if isinstance(global_hourly, dict):
        row = global_hourly.get(hour_key, global_hourly.get(int(hour), None))
        if isinstance(row, dict):
            values = row.get("p_mobile_intention", row)
            if isinstance(values, dict):
                return _normalize_distribution(values), f"global_hour:{hour_key}"
    global_prior = calibration.get("global_prior", {})
    if isinstance(global_prior, dict):
        values = global_prior.get("p_mobile_intention", global_prior)
        if isinstance(values, dict):
            return _normalize_distribution(values), "global_prior"
    return dict(_DEFAULT_UNCALIBRATED_PRIOR), "uncalibrated_default"


def _stable_select_intention(
    *,
    priors: dict[str, float],
    seed: int,
    agent_id: int,
    day: int,
    tick_seconds: float,
    profile_bucket: str,
) -> str:
    normalized = _normalize_distribution(priors)
    key = _stable_hash(
        {
            "seed": int(seed),
            "agent_id": int(agent_id),
            "day": int(day),
            "tick": int(round(float(tick_seconds))),
            "profile_bucket": profile_bucket,
            "version": "mobile_intention_rule_v1",
        }
    )
    threshold = int(key[:12], 16) / float(0xFFFFFFFFFFFF)
    cumulative = 0.0
    for intention, probability in normalized.items():
        cumulative += probability
        if threshold <= cumulative:
            return intention
    return "unknown_or_unmapped"


def _task_template_for_family(task_family: str) -> dict[str, Any] | None:
    for template in TASK_LIBRARY:
        if str(template.get("task_family", "")) == str(task_family):
            return template
    return None


def _mapping_confidence_for_intention(
    *,
    intention: str,
    mapping_artifact: dict[str, Any],
) -> tuple[float, str]:
    default = 1.0 if intention in MOBILE_INTENTION_TO_TASK_FAMILY else 0.0
    if not mapping_artifact:
        return default, "default_mapping"
    candidates = mapping_artifact.get("mobile_intention_mapping", mapping_artifact)
    if not isinstance(candidates, dict):
        return default, "default_mapping"
    row = candidates.get(intention)
    if not isinstance(row, dict):
        return default, "default_mapping"
    try:
        return clamp_score(float(row.get("mapping_confidence", default))), "mapping_artifact"
    except (TypeError, ValueError):
        return default, "mapping_artifact_invalid_confidence"


def _entry_audit(
    *,
    entry_mode: str,
    agent_id: int,
    day: int,
    tick_seconds: float,
    hour: int,
    selected_mobile_intention: str,
    entry_status: str,
    mapped_task_family: str | None,
    mapping_confidence: float,
    task_generated: bool,
    candidate_intentions: dict[str, float],
    calibration_hash: str,
    mapping_hash: str,
    reason: str,
    llm_shadow: dict[str, Any] | None = None,
    rerank_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = {
        "agent_id": int(agent_id),
        "day": int(day),
        "tick_seconds": float(tick_seconds),
        "hour": int(hour),
        "entry_mode": str(entry_mode),
        "entry_eval_interval_minutes": None,
        "entry_evaluated": True,
        "candidate_intentions": dict(candidate_intentions),
        "selected_mobile_intention": str(selected_mobile_intention),
        "mapped_task_family": mapped_task_family,
        "mapping_confidence": float(mapping_confidence),
        "entry_status": str(entry_status),
        "task_generated": bool(task_generated),
        "calibration_split": "elder_reference_may1_may3",
        "calibration_artifact_hash": calibration_hash,
        "mapping_artifact_hash": mapping_hash,
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "uses_previous_task_outcome": False,
        "uses_recent_failure_history": False,
        "uses_recent_avoid_ratio": False,
        "uses_recent_help_history": False,
        "uses_helplessness_state": False,
        "uses_self_efficacy_delta": False,
        "uses_controllability_posterior": False,
        "uses_bayesian_posterior": False,
        "uses_phase4_policy": False,
        "uses_phase5c_policy": False,
        "uses_world_specific_env": False,
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "is_avoidance": False,
        "is_help_action": False,
        "helper_triggered": False,
        "reason": str(reason),
        "llm_shadow": llm_shadow or {},
    }
    if rerank_audit:
        audit.update(dict(rerank_audit))
    return audit


def task_pressure_from_env(task_template: dict[str, Any], env: dict[str, Any]) -> float:
    friction = float(env.get("friction_level", 0))
    malicious = float(env.get("malicious_friction_level", 0))
    complexity = float(env.get("complexity_level", 0))
    risk = float(env.get("risk_level", 0))
    accessibility = float(env.get("accessibility_level", 0))
    friction_type = str(task_template.get("friction_type", "verification"))
    if friction_type == "verification":
        raw = (friction + malicious) / 6.0
    elif friction_type == "form_complexity":
        raw = (friction + complexity) / 6.0
    elif friction_type == "payment_risk_popup":
        raw = (risk + malicious) / 6.0
    else:
        raw = (friction + complexity) / 6.0
    adjusted = float(task_template.get("difficulty", 0.5)) + (raw * 0.24) - (
        accessibility * 0.03
    )
    return clamp_score(adjusted)


def _resolve_schedule_seed() -> int:
    raw_pair_seed = str(os.getenv("PARALLEL_PAIR_SEED", "")).strip()
    if raw_pair_seed:
        try:
            return int(raw_pair_seed)
        except ValueError:
            pass
    try:
        return int(str(os.getenv("EXP_SEED", "101")).strip())
    except ValueError:
        return 101


def _window_index_for_tick(tick_seconds: float) -> int | None:
    normalized_tick = int(round(float(tick_seconds)))
    best_match: tuple[int, int] | None = None
    for index, window_tick in enumerate(_TASK_WINDOW_SECONDS):
        delta = abs(normalized_tick - window_tick)
        if delta > _TASK_WINDOW_TOLERANCE_SECONDS:
            continue
        if best_match is None or delta < best_match[1]:
            best_match = (index, delta)
    return None if best_match is None else best_match[0]


def is_task_window_tick(tick_seconds: float) -> bool:
    return _window_index_for_tick(tick_seconds) is not None


def _scheduled_template_for_window(
    *,
    agent_id: int,
    day: int,
    window_index: int,
) -> dict[str, Any]:
    rotation = (_resolve_schedule_seed() + int(agent_id) + int(day)) % len(TASK_LIBRARY)
    ordered_templates = TASK_LIBRARY[rotation:] + TASK_LIBRARY[:rotation]
    return ordered_templates[int(window_index)]


def select_task_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
) -> DigitalTask | None:
    window_index = _window_index_for_tick(tick_seconds)
    if window_index is None:
        return None
    template = _scheduled_template_for_window(
        agent_id=int(agent_id),
        day=int(day),
        window_index=int(window_index),
    )
    assigned_tick = int(day * 100000 + int(round(float(tick_seconds))))
    task_id = f"{template['task_family']}_{agent_id}_{day}_{window_index}"
    return DigitalTask(
        task_id=task_id,
        task_family=template["task_family"],
        friction_type=template["friction_type"],
        difficulty=task_pressure_from_env(template, env),
        need_type=template["need_type"],
        support_sensitivity=float(template["support_sensitivity"]),
        assigned_tick=assigned_tick,
        defer_count=0,
    )


def evaluate_mobile_entry_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    stable_profile: dict[str, Any] | None = None,
    entry_mode: str = "mobile_intention_rule",
    calibration_path: str = "",
    mapping_path: str = "",
    confidence_threshold: float = 0.70,
    llm_shadow_enabled: bool = False,
    llm_shadow_payload: dict[str, Any] | None = None,
    selected_intention_override: str | None = None,
    rerank_audit_payload: dict[str, Any] | None = None,
    rerank_top_k: int = 5,
) -> MobileEntryDecision:
    normalized_mode = str(entry_mode or "mobile_intention_rule").strip().lower()
    if normalized_mode not in {
        "mobile_intention_rule",
        "mobile_intention_llm_shadow",
        "mobile_intention_llm_rerank_online_mc",
    }:
        raise ValueError(
            "mobile entry mode must be one of: mobile_intention_rule, "
            "mobile_intention_llm_shadow, mobile_intention_llm_rerank_online_mc"
        )
    calibration, calibration_hash = _load_json_artifact(
        calibration_path,
        cache=_CALIBRATION_CACHE,
    )
    mapping_artifact, mapping_hash = _load_json_artifact(
        mapping_path,
        cache=_MAPPING_CACHE,
    )
    hour = _hour_for_tick(tick_seconds)
    priors, prior_source = _extract_prior_from_calibration(
        calibration=calibration,
        profile=stable_profile,
        hour=hour,
    )
    profile_bucket = _bucket_for_profile(stable_profile)
    rule_selected = _stable_select_intention(
        priors=priors,
        seed=_resolve_schedule_seed(),
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        profile_bucket=profile_bucket,
    )
    top_candidates = top_mobile_intention_candidates(priors, top_k=rerank_top_k)
    selected = rule_selected
    rerank_audit = dict(rerank_audit_payload or {})
    if normalized_mode == "mobile_intention_llm_rerank_online_mc":
        override = str(selected_intention_override or "").strip()
        if not override:
            raise ValueError(
                "selected_intention_override is required for "
                "mobile_intention_llm_rerank_online_mc"
            )
        if override not in top_candidates:
            raise ValueError(
                "selected_intention_override must be one of top-k candidate intentions"
            )
        selected = override
        rerank_audit.update(
            {
                "rerank_enabled": True,
                "rule_selected_mobile_intention": rule_selected,
                "rerank_selected_mobile_intention": selected,
                "rerank_top_k": int(max(1, rerank_top_k)),
                "rerank_candidate_intentions": dict(top_candidates),
                "rerank_candidate_hash": mobile_intention_candidate_hash(top_candidates),
                "llm_drives_real_entry": True,
                "uses_post_outcome_information": False,
                "does_not_decide_strategy": True,
                "does_not_decide_outcome": True,
                "does_not_update_psychology": True,
            }
        )
    else:
        rerank_audit.update(
            {
                "rerank_enabled": False,
                "rule_selected_mobile_intention": rule_selected,
                "llm_drives_real_entry": False,
            }
        )
    mapped_task_family = MOBILE_INTENTION_TO_TASK_FAMILY.get(selected)
    mapping_confidence, mapping_source = _mapping_confidence_for_intention(
        intention=selected,
        mapping_artifact=mapping_artifact,
    )
    threshold = clamp_score(float(confidence_threshold))
    llm_shadow = dict(llm_shadow_payload or {})
    if normalized_mode == "mobile_intention_llm_shadow" or llm_shadow_enabled:
        llm_shadow.setdefault("llm_shadow_enabled", True)
        llm_shadow.setdefault("llm_parse_status", "not_called")
        llm_shadow.setdefault("llm_affected_real_entry", False)
    else:
        llm_shadow.setdefault("llm_shadow_enabled", False)
        llm_shadow.setdefault("llm_affected_real_entry", False)

    task: DigitalTask | None = None
    if selected in CONTEXT_ONLY_MOBILE_INTENTIONS:
        if selected == "communicate_or_seek_help":
            entry_status = "communicate_context_only"
        elif selected == "browse_entertainment":
            entry_status = "browse_context_only"
        elif selected == "no_mobile_action":
            entry_status = "no_mobile_action_noop"
        else:
            entry_status = "unknown_or_unmapped_noop"
        reason = f"{selected}:context_or_noop"
    elif mapped_task_family is None:
        entry_status = "unknown_or_unmapped_noop"
        reason = f"{selected}:no_task_family_mapping"
    elif mapping_confidence < threshold:
        entry_status = "low_confidence_mapping_noop"
        reason = (
            f"{selected}:mapping_confidence_{mapping_confidence:.3f}_below_"
            f"threshold_{threshold:.3f}"
        )
    else:
        template = _task_template_for_family(mapped_task_family)
        if template is None:
            entry_status = "unknown_or_unmapped_noop"
            reason = f"{selected}:mapped_family_not_in_task_library"
            mapped_task_family = None
        else:
            assigned_tick = int(day * 100000 + int(round(float(tick_seconds))))
            eval_slot = int(round(float(tick_seconds))) // 60
            task_id = (
                f"{normalized_mode}_{mapped_task_family}_{agent_id}_{day}_"
                f"{eval_slot}_{int(round(float(tick_seconds)))}"
            )
            task = DigitalTask(
                task_id=task_id,
                task_family=template["task_family"],
                friction_type=template["friction_type"],
                difficulty=task_pressure_from_env(template, env),
                need_type=template["need_type"],
                support_sensitivity=float(template["support_sensitivity"]),
                assigned_tick=assigned_tick,
                defer_count=0,
            )
            entry_status = "entered_mapped_digital_task"
            reason = f"{selected}:mapped_via_{mapping_source}:prior_{prior_source}"

    audit = _entry_audit(
        entry_mode=normalized_mode,
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        hour=hour,
        selected_mobile_intention=selected,
        entry_status=entry_status,
        mapped_task_family=mapped_task_family,
        mapping_confidence=mapping_confidence,
        task_generated=task is not None,
        candidate_intentions=priors,
        calibration_hash=calibration_hash,
        mapping_hash=mapping_hash,
        reason=reason,
        llm_shadow=llm_shadow,
        rerank_audit=rerank_audit,
    )
    audit["profile_bucket"] = profile_bucket
    audit["prior_source"] = prior_source
    audit["mapping_source"] = mapping_source
    return MobileEntryDecision(
        entry_evaluated=True,
        selected_mobile_intention=selected,
        entry_status=entry_status,
        mapped_task_family=mapped_task_family,
        mapping_confidence=mapping_confidence,
        task_generated=task is not None,
        task=task,
        candidate_intentions=priors,
        audit=audit,
    )


def skipped_mobile_entry_decision(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    entry_mode: str,
    reason: str = "not_evaluation_tick",
) -> MobileEntryDecision:
    audit = {
        "agent_id": int(agent_id),
        "day": int(day),
        "tick_seconds": float(tick_seconds),
        "hour": _hour_for_tick(tick_seconds),
        "entry_mode": str(entry_mode),
        "entry_evaluated": False,
        "entry_status": "skipped_eval",
        "task_generated": False,
        "reason": str(reason),
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "is_avoidance": False,
        "is_help_action": False,
        "helper_triggered": False,
    }
    return MobileEntryDecision(
        entry_evaluated=False,
        selected_mobile_intention="",
        entry_status="skipped_eval",
        mapped_task_family=None,
        mapping_confidence=0.0,
        task_generated=False,
        task=None,
        candidate_intentions={},
        audit=audit,
    )


def encode_task(task: DigitalTask | None) -> str:
    if task is None:
        return ""
    return json.dumps(task.to_dict(), ensure_ascii=False)


def decode_task(raw_value: Any) -> DigitalTask | None:
    if isinstance(raw_value, DigitalTask):
        return raw_value
    if raw_value in (None, "", "null"):
        return None
    if isinstance(raw_value, dict):
        return DigitalTask.from_dict(raw_value)
    if not isinstance(raw_value, str):
        return None
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return DigitalTask.from_dict(payload)
