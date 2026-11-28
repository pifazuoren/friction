from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..llm_psychology import _extract_json_object, _query_json_payload
from ..llm_trace import trace_record
from .types import HISTORICAL_CATEGORY_GUIDANCE, _stable_hash


DIGITAL_NEEDS_SCHEMA_VERSION = "digital_needs_v1"
DIGITAL_NEEDS_PROMPT_VERSION = "digital_needs_v1"
COMPACT_NEEDS_PROMPT_VERSION = "digital_needs_compact_v2"
COMPACT_NEEDS_REPAIR_V1 = "needs_repair_v1"
COMPACT_NEEDS_REPAIR_VERSION = "needs_repair_v2"
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


def _pressure_key_feedback(raw: str) -> str:
    previous = _extract_json_object(raw)
    pressures = previous.get("need_pressures") if previous else None
    if not isinstance(pressures, dict):
        return ""
    missing = [label for label in DIGITAL_NEED_LABELS if label not in pressures]
    extra = sorted(pressures.keys() - set(DIGITAL_NEED_LABELS))
    messages = []
    if missing:
        messages.append("缺少必填键 " + "、".join(missing))
    if extra:
        # Only quote short identifiers in instructions; a model can put arbitrary text in a key.
        labels = [key if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,47}", key) else "（无效键名）" for key in extra[:9]]
        messages.append("含有未定义键 " + "、".join(labels))
    return "need_pressures " + "；".join(messages) + "。" if messages else ""


def strongest_need(pressures: dict[str, float], *, legacy_tiebreak: bool = False) -> str | None:
    maximum = max(pressures.values())
    leaders = [name for name, score in pressures.items() if score == maximum]
    if len(leaders) == 1:
        return leaders[0]
    return max(leaders) if legacy_tiebreak else None


@dataclass(slots=True)
class DigitalNeedsResult:
    need_pressures: dict[str, float]
    active_intent: float
    intensity_hint: float
    confidence: float
    reasoning: str
    audit: dict[str, Any] = field(default_factory=dict)
    legacy_tiebreak: bool = False

    @property
    def dominant_need(self) -> str | None:
        return strongest_need(self.need_pressures, legacy_tiebreak=self.legacy_tiebreak)

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

    def to_dict(self, *, include_audit: bool = True, legacy_tiebreak: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "need_pressures": dict(self.need_pressures),
            "dominant_need": self.dominant_need if legacy_tiebreak is None else strongest_need(
                self.need_pressures, legacy_tiebreak=legacy_tiebreak
            ),
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
    if prompt_version == COMPACT_NEEDS_PROMPT_VERSION:
        return (
            "你扮演这位居民，根据本小时开始前的观察，评估此刻的手机使用需求。"
            "输入的 inputs 是观察信息；不要复述它，不要编造提醒、任务、帮助或结果。"
            "直接回答一个 JSON 对象，从 need_pressures 开始，仅给这五个字段："
            "need_pressures（对象，逐项填写以下九种需求各自的强度："
            + ", ".join(DIGITAL_NEED_LABELS)
            + "），active_intent（现在使用手机的意愿），intensity_hint（若使用时的使用强度），"
            "confidence（评估把握），reasoning（一句自己的理由）。"
            "所有评分独立取 0 到 1 的数值。历史使用或没有使用手机都是参考，当前可以有不同判断。"
            + HISTORICAL_CATEGORY_GUIDANCE
        )
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
        compact_repair_version: str = COMPACT_NEEDS_REPAIR_VERSION,
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
        compact = prompt_version == COMPACT_NEEDS_PROMPT_VERSION
        if compact:
            # Keep observations auditable and the output contract in the system message.
            user_payload = {"inputs": input_payload}
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
        compact_options = {}
        if compact:
            if compact_repair_version not in {COMPACT_NEEDS_REPAIR_V1, COMPACT_NEEDS_REPAIR_VERSION}:
                raise ValueError("Unknown compact Needs repair version")
            audit["repair_prompt_version"] = compact_repair_version

            def repair_dialog(raw: str, error: str) -> list[dict]:
                # Same observation as the first request; an echoed packet contains no need judgment.
                detail = _pressure_key_feedback(raw) if compact_repair_version == COMPACT_NEEDS_REPAIR_VERSION else ""
                dialog = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "上次回复未通过输出校验（" + error
                     + "）。" + detail + "请根据同一份观察给出五个字段的需求评估。\n"
                     + json.dumps(user_payload, ensure_ascii=False)},
                ]
                audit["repair_prompt_hash"] = _hash_payload(dialog)
                trace_record("repair_prompt", module="app_needs",
                             repair_prompt_version=compact_repair_version,
                             repair_prompt_hash=audit["repair_prompt_hash"])
                return dialog

            compact_options = {"repair_dialog_factory": repair_dialog}
            bounded_json_attempts = 1
        payload, status = await _query_json_payload(
            trace_module="app_needs",
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
            **compact_options,
        )
        if payload is None:
            raise ValueError(
                f"DigitalNeedsBlock JSON output failed after bounded attempts: {status}"
            )
        audit["response_hash"] = _hash_payload(payload)
        audit["parse_status"] = status
        return DigitalNeedsResult.from_sanitized(payload, audit=audit)
