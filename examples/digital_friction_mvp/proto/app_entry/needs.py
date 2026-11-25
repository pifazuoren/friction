from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

from ..llm_psychology import _query_json_payload
from .types import _stable_hash


DIGITAL_NEEDS_SCHEMA_VERSION = "digital_needs_v1"
DIGITAL_NEEDS_PROMPT_VERSION = "digital_needs_v1"
MAX_DIGITAL_NEEDS_JSON_ATTEMPTS = 5

DIGITAL_NEED_LABELS: tuple[str, ...] = (
    "social_need",
    "entertainment_need",
    "finance_need",
    "tool_need",
    "health_need",
    "habitual_check_need",
    "idle_browse_need",
    "avoidance_need",
    "no_app_need",
)

# Conservative v1 mapping: only direct taxonomy correspondences are included.
# Habitual, avoidance, and no-app pressures affect planning without inventing a
# context that is not supported by the agent's Day 1-3 exposure history.
DIGITAL_NEED_TO_APP_CONTEXTS: dict[str, tuple[str, ...]] = {
    "social_need": ("communication_social_context",),
    "entertainment_need": ("media_entertainment_context",),
    "finance_need": ("finance_context", "finance_candidate_review"),
    "tool_need": ("device_tool_context",),
    "health_need": ("health_service_context",),
    "habitual_check_need": (),
    "idle_browse_need": ("media_entertainment_context",),
    "avoidance_need": (),
    "no_app_need": (),
}

DIGITAL_NEEDS_OUTPUT_KEYS = {
    "need_pressures",
    "active_intent",
    "intensity_hint",
    "confidence",
    "reasoning",
}

DIGITAL_NEEDS_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DigitalNeedsResult",
    "type": "object",
    "additionalProperties": False,
    "required": sorted(DIGITAL_NEEDS_OUTPUT_KEYS),
    "properties": {
        "need_pressures": {
            "type": "object",
            "additionalProperties": False,
            "required": list(DIGITAL_NEED_LABELS),
            "properties": {
                label: {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                }
                for label in DIGITAL_NEED_LABELS
            },
        },
        "active_intent": {"type": "number", "minimum": 0, "maximum": 1},
        "intensity_hint": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
    },
}


def _score(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise ValueError(f"{field_name} must be in [0, 1]")
    return result


def _canonical_need_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("digital needs output must be a JSON object")
    if set(payload) != DIGITAL_NEEDS_OUTPUT_KEYS:
        raise ValueError("digital needs output keys do not match the schema")
    raw_pressures = payload.get("need_pressures")
    if not isinstance(raw_pressures, dict):
        raise ValueError("need_pressures must be a JSON object")
    if set(raw_pressures) != set(DIGITAL_NEED_LABELS):
        raise ValueError("need_pressures keys do not match the schema")
    pressures = {
        label: _score(raw_pressures[label], f"need_pressures.{label}")
        for label in DIGITAL_NEED_LABELS
    }
    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, str):
        raise ValueError("reasoning must be a string")
    if len(reasoning) > 1200:
        raise ValueError("reasoning is too long")
    return {
        "need_pressures": pressures,
        "active_intent": _score(payload.get("active_intent"), "active_intent"),
        "intensity_hint": _score(payload.get("intensity_hint"), "intensity_hint"),
        "confidence": _score(payload.get("confidence"), "confidence"),
        "reasoning": reasoning,
    }


def sanitize_digital_needs_payload(
    payload: Any,
) -> tuple[dict[str, Any] | None, str]:
    try:
        return _canonical_need_payload(payload), "ok"
    except ValueError:
        return None, "invalid_schema"


@dataclass(slots=True)
class DigitalNeedsResult:
    need_pressures: dict[str, float]
    active_intent: float
    intensity_hint: float
    confidence: float
    reasoning: str
    audit: dict[str, Any] = field(default_factory=dict)

    @property
    def dominant_need(self) -> str:
        return max(
            self.need_pressures.items(),
            key=lambda item: (float(item[1]), str(item[0])),
        )[0]

    @classmethod
    def from_sanitized(
        cls,
        payload: dict[str, Any],
        *,
        audit: dict[str, Any] | None = None,
    ) -> "DigitalNeedsResult":
        canonical = _canonical_need_payload(payload)
        return cls(
            need_pressures=dict(canonical["need_pressures"]),
            active_intent=float(canonical["active_intent"]),
            intensity_hint=float(canonical["intensity_hint"]),
            confidence=float(canonical["confidence"]),
            reasoning=str(canonical["reasoning"]),
            audit=dict(audit or {}),
        )

    def to_dict(self, *, include_audit: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "need_pressures": dict(self.need_pressures),
            "dominant_need": self.dominant_need,
            "active_intent": float(self.active_intent),
            "intensity_hint": float(self.intensity_hint),
            "confidence": float(self.confidence),
            "reasoning": self.reasoning,
        }
        if include_audit:
            payload["audit"] = dict(self.audit)
        return payload


def _hash_payload(payload: Any) -> str:
    return _stable_hash(payload)[:16]


def _schema_hash() -> str:
    return _hash_payload(DIGITAL_NEEDS_JSON_SCHEMA)


def _needs_system_prompt(prompt_version: str) -> str:
    return (
        "You are the DigitalNeedsBlock in a simulated older-adult mobile-use model. "
        "Return exactly one JSON object matching the supplied schema. Digital needs "
        "are latent usage pressures, not observed TalkingData labels. Do not invent "
        "appointments, bills, family reminders, obligations, tasks, outcomes, support, "
        "or app contexts. Do not output primary_context or app_context_counts. "
        f"Prompt version: {prompt_version}. Schema version: {DIGITAL_NEEDS_SCHEMA_VERSION}."
    )


class DigitalNeedsBlock:
    """LLM-backed digital-needs interface, separate from city-life NeedsBlock."""

    async def forward(
        self,
        *,
        llm: Any,
        input_payload: dict[str, Any],
        prompt_version: str = DIGITAL_NEEDS_PROMPT_VERSION,
        timeout: int = 30,
        retries: int = 1,
        json_attempts: int = 5,
    ) -> DigitalNeedsResult:
        if not isinstance(input_payload, dict):
            raise ValueError("DigitalNeedsBlock input_payload must be a dictionary")
        system_prompt = _needs_system_prompt(str(prompt_version))
        user_payload = {
            "prompt_version": str(prompt_version),
            "schema_version": DIGITAL_NEEDS_SCHEMA_VERSION,
            "inputs": input_payload,
            "output_schema": DIGITAL_NEEDS_JSON_SCHEMA,
        }
        audit: dict[str, Any] = {
            "block": "DigitalNeedsBlock",
            "schema_version": DIGITAL_NEEDS_SCHEMA_VERSION,
            "prompt_version": str(prompt_version),
            "prompt_hash": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest()[:16],
            "schema_hash": _schema_hash(),
            "payload_hash": _hash_payload(user_payload),
            "parse_status": "not_called",
        }
        bounded_json_attempts = max(
            1,
            min(MAX_DIGITAL_NEEDS_JSON_ATTEMPTS, int(json_attempts)),
        )
        payload, status = await _query_json_payload(
            llm=llm,
            system_prompt=system_prompt,
            user_payload=user_payload,
            output_keys=DIGITAL_NEEDS_OUTPUT_KEYS,
            repair_schema_text=(
                "- need_pressures must contain exactly the nine supplied need labels\n"
                "- every score must be a number in [0,1]\n"
                "- active_intent, intensity_hint, and confidence must be in [0,1]\n"
                "- do not include primary_context or app_context_counts"
            ),
            sanitize_fn=sanitize_digital_needs_payload,
            timeout=int(timeout),
            retries=int(retries),
            max_tokens=420,
            json_attempts=bounded_json_attempts,
            audit=audit,
        )
        if payload is None:
            raise ValueError(
                f"DigitalNeedsBlock JSON output failed after bounded attempts: {status}"
            )
        audit["response_hash"] = _hash_payload(payload)
        audit["parse_status"] = status
        return DigitalNeedsResult.from_sanitized(payload, audit=audit)
