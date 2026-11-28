from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ..models import DigitalTask, TaskFamily

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

APP_CONTEXT_SET: tuple[str, ...] = (
    "finance_context",
    "finance_candidate_review",
    "public_service_context",
    "health_service_context",
    "shopping_lifestyle_context",
    "navigation_transport_context",
    "communication_social_context",
    "media_entertainment_context",
    "device_tool_context",
    "education_work_context",
    "taxonomy_profile_only",
    "unknown_or_unmapped",
)

# These bins carry observed exposure mass but do not identify a usable application.
AUDIT_ONLY_APP_CONTEXTS = frozenset(
    {"finance_candidate_review", "taxonomy_profile_only", "unknown_or_unmapped"}
)
HISTORICAL_CATEGORY_GUIDANCE = (
    "历史中的 finance_candidate_review、taxonomy_profile_only、unknown_or_unmapped 是待核实或未知类别，"
    "只表明当时观察到了活动，不能据此推断本人想办什么。"
)
ACTIONABLE_APP_CONTEXTS = frozenset(APP_CONTEXT_SET) - AUDIT_ONLY_APP_CONTEXTS

TASK_ELIGIBLE_APP_CONTEXTS: frozenset[str] = frozenset(
    {
        "finance_context",
        "public_service_context",
        "health_service_context",
        "shopping_lifestyle_context",
        "navigation_transport_context",
        "education_work_context",
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
    selected_app_context: str = ""
    candidate_app_contexts: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["task"] = self.task.to_dict() if self.task is not None else None
        return payload


def clamp_score(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _hour_for_tick(tick_seconds: float) -> int:
    return int(round(float(tick_seconds))) // 3600 % 24


def _normalize_distribution_for_keys(
    values: dict[str, Any],
    *,
    keys: tuple[str, ...],
    default: dict[str, float],
) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key in keys:
        try:
            cleaned[key] = max(0.0, float(values.get(key, 0.0)))
        except (TypeError, ValueError):
            cleaned[key] = 0.0
    total = sum(cleaned.values())
    if total <= 0.0:
        return dict(default)
    return {key: value / total for key, value in cleaned.items()}


def _stable_select_from_distribution(
    *,
    values: dict[str, float],
    keys: tuple[str, ...],
    seed: int,
    agent_id: int,
    day: int,
    tick_seconds: float,
    profile_bucket: str,
    version: str,
) -> str:
    key = _stable_hash(
        {
            "seed": int(seed),
            "agent_id": int(agent_id),
            "day": int(day),
            "tick": int(round(float(tick_seconds))),
            "profile_bucket": profile_bucket,
            "version": str(version),
        }
    )
    threshold = int(key[:12], 16) / float(0xFFFFFFFFFFFF)
    cumulative = 0.0
    for item in keys:
        cumulative += max(0.0, float(values.get(item, 0.0)))
        if threshold <= cumulative:
            return item
    return keys[-1]
