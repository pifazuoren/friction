from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..llm_psychology import _extract_json_object, _query_json_payload
from ..llm_trace import trace_record
from . import PHONE_USE_NEEDS_V3, PHONE_USE_NEEDS_V5, PHONE_USE_NEEDS_VERSION
from .phone_policy import replay_activity_counts
from .types import HISTORICAL_CATEGORY_GUIDANCE, _stable_hash
from .wire import parse_compact_reply, response_fields


DIGITAL_NEEDS_SCHEMA_VERSION = "digital_needs_v1"
DIGITAL_NEEDS_PROMPT_VERSION = "digital_needs_v1"
COMPACT_NEEDS_PROMPT_VERSION = "digital_needs_compact_v2"
PHONE_USE_NEEDS_V1 = "digital_needs_phone_use_v1"
PHONE_USE_NEEDS_V2 = "digital_needs_phone_use_v2"
NULLABLE_INTENSITY_VERSIONS = (PHONE_USE_NEEDS_V3, PHONE_USE_NEEDS_VERSION)
PHONE_USE_NEEDS_VERSIONS = (PHONE_USE_NEEDS_V1, PHONE_USE_NEEDS_V2, *NULLABLE_INTENSITY_VERSIONS, PHONE_USE_NEEDS_V5)
PHONE_USE_OPTIONS = ("leave_phone", "use_phone")
PHONE_RECOMMENDATIONS = (*PHONE_USE_OPTIONS, "follow_habit")
OBSERVED_HABIT_KEY = "habital_check_need"
HABIT_KEY = "habitual_check_need"
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


def _canonical_need_payload(
    payload: Any, *, require_phone_decision: bool = False, allow_unused_intensity: bool = False,
    phone_options: tuple[str, ...] = PHONE_USE_OPTIONS, unmeasured_intensity: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("digital needs output must be a JSON object")
    extra = {"phone_use_decision"} if require_phone_decision else set()
    if set(payload) != DIGITAL_NEEDS_OUTPUT_KEYS | extra:
        raise ValueError("digital needs output keys do not match the schema")
    if require_phone_decision and payload["phone_use_decision"] not in phone_options:
        raise ValueError("an explicit phone-use decision is required")
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
    # intensity_hint describes how intensely the resident would use the phone.
    # V5 asks for a recommendation before the final action. Intensity can be unmeasured for any advice.
    unused = (require_phone_decision and payload["intensity_hint"] is None
              and (unmeasured_intensity or (allow_unused_intensity and payload["phone_use_decision"] == "leave_phone")))
    return {
        "need_pressures": pressures,
        "active_intent": _score(payload.get("active_intent"), "active_intent"),
        "intensity_hint": None if unused else _score(payload["intensity_hint"], "intensity_hint"),
        "confidence": _score(payload.get("confidence"), "confidence"),
        "reasoning": reasoning,
        **({"phone_use_decision": payload["phone_use_decision"]} if require_phone_decision else {}),
    }


def sanitize_digital_needs_payload(
    payload: Any, *, require_phone_decision: bool = False, allow_observed_pressure_alias: bool = False,
    allow_unused_intensity: bool = False, phone_options: tuple[str, ...] = PHONE_USE_OPTIONS,
    unmeasured_intensity: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    # Preserve the original provider payload. Only the documented V2 key spelling can be normalized.
    if require_phone_decision and allow_observed_pressure_alias and isinstance(payload, dict):
        pressures = payload.get("need_pressures")
        if isinstance(pressures, dict) and OBSERVED_HABIT_KEY in pressures and HABIT_KEY not in pressures:
            payload = {**payload, "need_pressures": {
                HABIT_KEY if key == OBSERVED_HABIT_KEY else key: value for key, value in pressures.items()
            }}
    try:
        return _canonical_need_payload(payload, require_phone_decision=require_phone_decision,
                                       allow_unused_intensity=allow_unused_intensity, phone_options=phone_options,
                                       unmeasured_intensity=unmeasured_intensity), "ok"
    except ValueError:
        return None, "invalid_schema"


def sanitize_phone_needs(
    payload: Any, schema_version: str, *, allow_follow_habit: bool = True,
) -> tuple[dict[str, Any] | None, str]:
    if schema_version not in PHONE_USE_NEEDS_VERSIONS:
        raise ValueError("unknown phone-use Needs schema")
    return sanitize_digital_needs_payload(
        payload, require_phone_decision=True, allow_observed_pressure_alias=schema_version != PHONE_USE_NEEDS_V1,
        allow_unused_intensity=schema_version in NULLABLE_INTENSITY_VERSIONS,
        unmeasured_intensity=schema_version == PHONE_USE_NEEDS_V5,
        phone_options=PHONE_RECOMMENDATIONS if schema_version == PHONE_USE_NEEDS_V5 and allow_follow_habit else PHONE_USE_OPTIONS,
    )


def stated_phone_use_decision(raw: str, *, allow_follow_habit: bool = False) -> str | None:
    fields, _, ambiguous = response_fields(raw)
    if ambiguous:
        return "ambiguous"
    choice = fields.get("phone_use_decision")
    options = PHONE_RECOMMENDATIONS if allow_follow_habit else PHONE_USE_OPTIONS
    return choice if choice in options else None


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
    intensity_hint: float | None
    confidence: float
    reasoning: str
    audit: dict[str, Any] = field(default_factory=dict)
    legacy_tiebreak: bool = False
    phone_use_decision: str | None = None
    phone_use_resolution: dict | None = None

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
        version = (audit or {}).get("schema_version")
        canonical = _canonical_need_payload(
            payload, require_phone_decision="phone_use_decision" in payload,
            allow_unused_intensity=version in NULLABLE_INTENSITY_VERSIONS,
            phone_options=PHONE_RECOMMENDATIONS if version == PHONE_USE_NEEDS_V5 else PHONE_USE_OPTIONS,
            unmeasured_intensity=version == PHONE_USE_NEEDS_V5,
        )
        return cls(
            need_pressures=dict(canonical["need_pressures"]),
            active_intent=float(canonical["active_intent"]),
            intensity_hint=canonical["intensity_hint"],
            confidence=float(canonical["confidence"]),
            reasoning=str(canonical["reasoning"]),
            audit=dict(audit or {}),
            phone_use_decision=canonical.get("phone_use_decision"),
        )

    def to_dict(self, *, include_audit: bool = True, legacy_tiebreak: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "need_pressures": dict(self.need_pressures),
            "dominant_need": self.dominant_need if legacy_tiebreak is None else strongest_need(
                self.need_pressures, legacy_tiebreak=legacy_tiebreak
            ),
            "active_intent": float(self.active_intent),
            "intensity_hint": self.intensity_hint,
            "confidence": float(self.confidence),
            "reasoning": self.reasoning,
        }
        if self.phone_use_decision is not None:
            payload["phone_use_decision"] = self.phone_use_decision
        if self.phone_use_resolution is not None:
            payload["phone_use_resolution"] = dict(self.phone_use_resolution)
        if include_audit:
            payload["audit"] = dict(self.audit)
        return payload


def _hash_payload(payload: Any) -> str:
    return _stable_hash(payload)[:16]


def _needs_system_prompt(prompt_version: str) -> str:
    if prompt_version == PHONE_USE_NEEDS_V5:
        return (
            "你是资料中的居民。前三天同一钟点的设备活动将用于估计本小时日常用手机的概率。"
            "请只判断今天眼前的处境是否让你比平时更想或更不想用手机。不要把历史习惯再算一次。"
            "没有到时可办的任务本身并不改变日常习惯。不要编造通知、作息或线下活动。"
            "从 recommendation_options 中选一项填入 phone_use_decision。有同钟点记录时，"
            "有具体理由比平时更想用选 use_phone，更不想用选 leave_phone，没有偏离平时的明确理由选 follow_habit。"
            "若无可用同钟点记录，就按当前处境直接选用或不用。本步不用选 App。"
            "只回复一个 JSON 对象，给六个字段。phone_use_decision 填建议，reasoning 用一句话说依据，"
            "need_pressures 按 pressure_keys 逐项填九个分数，active_intent 填使用意愿，"
            "intensity_hint 填若使用时的强度（无法估计须填 null），confidence 填判断把握。所有分数在 0 到 1 之间。"
        )
    if prompt_version in (PHONE_USE_NEEDS_V2, *NULLABLE_INTENSITY_VERSIONS):
        prompt = (
            "你是资料中的居民，这一小时没有到时可办的任务。你可以主动查看信息、联络他人或处理日常事项，"
            "也可以继续手头的线下活动。根据人物和钟点决定这一小时是否用手机，本步无需选择 App。"
            "day1_3_habit.same_hour_active 是前三天同钟点的设备记录，seen 是观察天数，active 是有活动的天数。"
            "recent_simulated_bundles 是此前的模拟活动。两者都只描述过去。只依据给出的观察，不编造作息或通知。"
            "只回复一个 JSON 对象，字段为 phone_use_decision（use_phone 或 leave_phone）、reasoning（一句理由）、"
            "need_pressures（对象，照抄 pressure_keys 给出的九个键，每个给一个数值）、active_intent（意愿）、"
            "intensity_hint（若使用时的强度）、confidence（判断把握）。数值均为 0 到 1。"
        )
        if prompt_version in NULLABLE_INTENSITY_VERSIONS:
            prompt += "选择 leave_phone 时仍须填写 intensity_hint，若强度不适用可填 null；选择 use_phone 时须填写数值。"
        return prompt
    if prompt_version == PHONE_USE_NEEDS_V1:
        return (
            "你是资料中的居民。这一小时没有到时可办的任务。先决定这小时是否用手机，具体 App 留到下一步再选。"
            "考虑当下有无值得拿起手机的理由，也可以继续线下活动或休息；不要编造作息、通知或任务。"
            "day1_3_habit.same_hour_active 是前三天同钟点的设备记录，seen 是观察天数，active 是其中有活动的天数；"
            "recent_simulated_bundles 是你此前在模拟中的行为，已经查看过手机本身不代表现在有新消息。两种选择都可行。"
            "只返回一个 JSON 对象：phone_use_decision 选 use_phone（用手机）或 leave_phone（不用手机）；"
            "reasoning 给出此刻的一句理由；need_pressures 分别给出九项需求 "
            + ", ".join(DIGITAL_NEED_LABELS)
            + "；active_intent、intensity_hint、confidence 分别给出使用意愿、若使用时的强度、判断把握。"
            "数值在 0 到 1 之间。"
        )
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
        phone_first = prompt_version in PHONE_USE_NEEDS_VERSIONS
        habit_policy = prompt_version == PHONE_USE_NEEDS_V5
        same_hour = input_payload.get("day1_3_habit", {}).get("same_hour_active") if habit_policy else None
        allow_follow_habit = habit_policy and replay_activity_counts(same_hour) is not None
        phone_options = PHONE_RECOMMENDATIONS if allow_follow_habit else PHONE_USE_OPTIONS
        allow_observed_pressure_alias = phone_first and prompt_version != PHONE_USE_NEEDS_V1
        compact = prompt_version == COMPACT_NEEDS_PROMPT_VERSION or phone_first
        if compact:
            # Keep observations auditable and the output contract in the system message.
            user_payload = {"inputs": input_payload}
        output_keys = DIGITAL_NEEDS_OUTPUT_KEYS
        schema = DIGITAL_NEEDS_JSON_SCHEMA
        if phone_first:
            user_payload["schema_version"] = prompt_version
            if habit_policy:
                user_payload["recommendation_options"] = list(phone_options)
            if allow_observed_pressure_alias:
                user_payload["pressure_keys"] = list(DIGITAL_NEED_LABELS)
            output_keys = DIGITAL_NEEDS_OUTPUT_KEYS | {"phone_use_decision"}
            schema = {**schema, "required": sorted(output_keys),
                      "properties": {**schema["properties"], "phone_use_decision": {"enum": list(phone_options)}}}
            if habit_policy or prompt_version in NULLABLE_INTENSITY_VERSIONS:
                schema["properties"]["intensity_hint"] = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
            if prompt_version in NULLABLE_INTENSITY_VERSIONS:
                schema["if"] = {"properties": {"phone_use_decision": {"const": "use_phone"}}}
                schema["then"] = {"properties": {"intensity_hint": {"type": "number"}}}
        audit: dict[str, Any] = {
            "block": "DigitalNeedsBlock",
            "schema_version": prompt_version if phone_first else DIGITAL_NEEDS_SCHEMA_VERSION,
            "prompt_version": str(prompt_version),
            "prompt_hash": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest()[:16],
            "schema_hash": _hash_payload(schema),
            "payload_hash": _hash_payload(user_payload),
            "parse_status": "not_called",
        }
        bounded_json_attempts = max(
            1,
            min(MAX_DIGITAL_NEEDS_JSON_ATTEMPTS, int(json_attempts)),
        )
        compact_options = {}
        original_phone_choice = None
        reply_phase = None

        def observe_phone_choice(phase: str, raw: str) -> None:
            nonlocal original_phone_choice, reply_phase
            reply_phase = phase
            if phase == "initial":
                original_phone_choice = stated_phone_use_decision(raw, allow_follow_habit=allow_follow_habit)

        def validate_needs(raw: Any):
            parsed, status = (sanitize_phone_needs(raw, prompt_version, allow_follow_habit=allow_follow_habit)
                              if phone_first else sanitize_digital_needs_payload(raw))
            if parsed is not None and original_phone_choice not in (None, parsed.get("phone_use_decision")):
                return None, "changed_phone_use_decision"
            if parsed is not None and allow_observed_pressure_alias and OBSERVED_HABIT_KEY in raw["need_pressures"]:
                mapping = dict(phase=reply_phase, from_key=OBSERVED_HABIT_KEY, to_key=HABIT_KEY)
                audit["pressure_key_normalized"] = mapping
                trace_record("pressure_key_normalized", module="app_needs", **mapping)
            return parsed, status

        if compact:
            if compact_repair_version not in {COMPACT_NEEDS_REPAIR_V1, COMPACT_NEEDS_REPAIR_VERSION}:
                raise ValueError("Unknown compact Needs repair version")
            audit["repair_prompt_version"] = compact_repair_version

            def repair_dialog(raw: str, error: str) -> list[dict]:
                # Same observation as the first request; an echoed packet contains no need judgment.
                detail = _pressure_key_feedback(raw) if compact_repair_version == COMPACT_NEEDS_REPAIR_VERSION else ""
                instruction = "请根据同一份观察给出五个字段的需求评估。"
                if phone_first:
                    instruction = "按同一份观察补全六个字段。"
                    if original_phone_choice in phone_options:
                        instruction += f"保留已经表达的 phone_use_decision={original_phone_choice}。"
                dialog = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "上次回复未通过输出校验（" + error
                     + "）。" + detail + instruction + "\n"
                     + json.dumps(user_payload, ensure_ascii=False)},
                ]
                audit["repair_prompt_hash"] = _hash_payload(dialog)
                trace_record("repair_prompt", module="app_needs",
                             repair_prompt_version=compact_repair_version,
                             repair_prompt_hash=audit["repair_prompt_hash"])
                return dialog

            compact_options = {"repair_dialog_factory": repair_dialog}
            if phone_first:
                compact_options.update(on_raw_response=observe_phone_choice, parse_response=parse_compact_reply)
            bounded_json_attempts = 1
        payload, status = await _query_json_payload(
            trace_module="app_needs",
            llm=llm,
            system_prompt=system_prompt,
            user_payload=user_payload,
            output_keys=output_keys,
            repair_schema_text=(
                "- need_pressures must contain exactly the nine supplied need labels\n"
                "- every score must be a number in [0,1]\n"
                "- active_intent, intensity_hint, and confidence must be in [0,1]\n"
                "- do not include primary_context or app_context_counts"
            ),
            sanitize_fn=validate_needs,
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
