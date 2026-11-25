from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .types import APP_CONTEXT_SET, TASK_ELIGIBLE_APP_CONTEXTS

NO_APP_CONTEXT = "no_app_context"
PRIMARY_CONTEXT_RULE_VERSION = "primary_context_max_count_lexical_v1"


def derive_primary_context(app_context_counts: dict[str, int]) -> str:
    """Derive the task-facing context without letting the LLM choose it.

    The lexical tie-break makes generated bundles deterministic. Stored TalkingData
    replay rows keep their original primary_context for backward compatibility.
    """
    if not app_context_counts:
        return NO_APP_CONTEXT
    return max(
        app_context_counts.items(),
        key=lambda item: (int(item[1]), str(item[0])),
    )[0]


ROLLOUT_BUNDLE_METADATA_KEYS = {
    "device_id",
    "day",
    "hour",
    "source",
    "primary_context",
}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _safe_int(value: Any, field_name: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _strict_nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a JSON integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return int(value)


def _parse_context_counts(raw_value: Any) -> dict[str, int]:
    if isinstance(raw_value, dict):
        payload = raw_value
    else:
        text = str(raw_value or "{}").strip()
        payload = json.loads(text or "{}")
    if not isinstance(payload, dict):
        raise ValueError("app_context_counts must be a JSON object")
    counts: dict[str, int] = {}
    for key, value in payload.items():
        context = str(key).strip()
        count = _safe_int(value, f"app_context_counts[{context}]")
        if count < 0:
            raise ValueError(f"app_context_counts[{context}] must be >= 0")
        if count > 0:
            counts[context] = count
    return counts


@dataclass(frozen=True, slots=True)
class HourlyAppEntryBundle:
    device_id: str
    day: int
    hour: int
    active: bool
    active_event_app_exposures: int
    app_context_counts: dict[str, int]
    primary_context: str
    source: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "HourlyAppEntryBundle":
        bundle = cls(
            device_id=str(row.get("device_id", "")).strip(),
            day=_safe_int(row.get("day_index", row.get("day")), "day"),
            hour=_safe_int(row.get("hour"), "hour"),
            active=_parse_bool(row.get("active")),
            active_event_app_exposures=_safe_int(
                row.get("active_event_app_exposures", 0),
                "active_event_app_exposures",
            ),
            app_context_counts=_parse_context_counts(
                row.get("app_context_counts_json", row.get("app_context_counts", {}))
            ),
            primary_context=str(row.get("primary_context", "")).strip(),
            source=str(row.get("source", "")).strip(),
        )
        bundle.validate()
        return bundle

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HourlyAppEntryBundle":
        bundle = cls(
            device_id=str(payload.get("device_id", "")).strip(),
            day=_safe_int(payload.get("day"), "day"),
            hour=_safe_int(payload.get("hour"), "hour"),
            active=_parse_bool(payload.get("active")),
            active_event_app_exposures=_safe_int(
                payload.get("active_event_app_exposures", 0),
                "active_event_app_exposures",
            ),
            app_context_counts=_parse_context_counts(
                payload.get("app_context_counts", {})
            ),
            primary_context=str(payload.get("primary_context", "")).strip(),
            source=str(payload.get("source", "")).strip(),
        )
        bundle.validate()
        return bundle

    @classmethod
    def from_rollout_payload(
        cls,
        *,
        device_id: str,
        day: int,
        hour: int,
        payload: dict[str, Any],
        source: str = "llm_memory_rollout",
    ) -> "HourlyAppEntryBundle":
        """Build a bundle from a sanitized PlanBlock response.

        Runtime metadata and primary_context are deliberately injected/derived in
        code. The LLM never gets to choose either field.
        """
        if not isinstance(payload, dict):
            raise ValueError("rollout payload must be a dictionary")
        forbidden = sorted(set(payload) & ROLLOUT_BUNDLE_METADATA_KEYS)
        if forbidden:
            raise ValueError(
                "rollout payload must not contain runtime metadata: "
                + ", ".join(forbidden)
            )
        active = payload.get("active")
        if not isinstance(active, bool):
            raise ValueError("active must be a JSON boolean")
        exposures = _strict_nonnegative_int(
            payload.get("active_event_app_exposures"),
            "active_event_app_exposures",
        )
        raw_counts = payload.get("app_context_counts")
        if not isinstance(raw_counts, dict):
            raise ValueError("app_context_counts must be a JSON object")
        counts: dict[str, int] = {}
        for raw_context, raw_count in raw_counts.items():
            context = str(raw_context).strip()
            count = _strict_nonnegative_int(
                raw_count,
                f"app_context_counts[{context}]",
            )
            if count > 0:
                counts[context] = count
        bundle = cls(
            device_id=str(device_id).strip(),
            day=int(day),
            hour=int(hour),
            active=active,
            active_event_app_exposures=exposures,
            app_context_counts=counts,
            primary_context=derive_primary_context(counts),
            source=str(source),
        )
        bundle.validate()
        return bundle

    def validate(self) -> None:
        if not self.device_id:
            raise ValueError("device_id is required")
        if self.day < 1 or self.day > 7:
            raise ValueError("day must be in TalkingData day range 1..7")
        if self.hour < 0 or self.hour > 23:
            raise ValueError("hour must be in range 0..23")
        if self.active_event_app_exposures < 0:
            raise ValueError("active_event_app_exposures must be >= 0")
        unknown_contexts = sorted(set(self.app_context_counts) - set(APP_CONTEXT_SET))
        if unknown_contexts:
            raise ValueError(
                "app_context_counts contains unknown contexts: "
                + ", ".join(unknown_contexts)
            )
        total = sum(int(value) for value in self.app_context_counts.values())
        if total != int(self.active_event_app_exposures):
            raise ValueError(
                "sum(app_context_counts) must equal active_event_app_exposures"
            )
        if not self.active:
            if self.active_event_app_exposures != 0:
                raise ValueError("inactive hour must have zero exposures")
            if self.app_context_counts:
                raise ValueError("inactive hour must not have app_context_counts")
            if self.primary_context != NO_APP_CONTEXT:
                raise ValueError("inactive hour must use no_app_context")
            return
        if self.active_event_app_exposures <= 0:
            raise ValueError("active hour must have positive exposures")
        if not self.app_context_counts:
            raise ValueError("active hour must include app_context_counts")
        if self.primary_context == NO_APP_CONTEXT:
            raise ValueError("active hour cannot use no_app_context")
        if self.primary_context not in self.app_context_counts:
            raise ValueError("active hour primary_context must appear in counts")

    def is_active(self) -> bool:
        return bool(self.active)

    def is_task_eligible_primary(self) -> bool:
        return self.primary_context in TASK_ELIGIBLE_APP_CONTEXTS

    def context_share_distribution(self) -> dict[str, float]:
        total = sum(self.app_context_counts.values())
        if total <= 0:
            return {}
        return {
            context: float(count) / float(total)
            for context, count in sorted(self.app_context_counts.items())
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "day": int(self.day),
            "hour": int(self.hour),
            "active": bool(self.active),
            "active_event_app_exposures": int(self.active_event_app_exposures),
            "app_context_counts": dict(self.app_context_counts),
            "primary_context": self.primary_context,
            "primary_context_task_eligible": self.is_task_eligible_primary(),
            "source": self.source,
        }
