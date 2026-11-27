from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

from ..llm_psychology import _query_json_payload
from ..llm_trace import trace_record
from .bundle import HourlyAppEntryBundle, derive_primary_context
from .candidate import app_context_candidate_hash
from .intention_contract import (
    COMPACT_PLAN_VERSION,
    COMPACT_PLAN_V2,
    COMPACT_PLAN_V3,
    COMPACT_SCORES,
    compact_menu,
    compact_intent,
    compact_needs,
    compact_observation,
    compact_repair_changed,
    include_required_channels,
    parse_compact_reply,
    read_compact_statement,
    stated_open_channel,
    validate_intent,
)
from .needs import DigitalNeedsResult
from .types import APP_CONTEXT_SET, _stable_hash


APP_ENTRY_PLAN_SCHEMA_VERSION = "app_entry_plan_v2"
APP_ENTRY_PLAN_PROMPT_VERSION = "app_entry_plan_v3"
CALIBRATED_PLAN_VERSION = "app_entry_plan_v4_calibrated"
MAX_APP_ENTRY_PLAN_JSON_ATTEMPTS = 5

APP_ENTRY_PLAN_OUTPUT_KEYS = {
    "active",
    "app_context_counts",
    "attitude",
    "subjective_norm",
    "perceived_control",
    "confidence",
    "reasoning",
}

APP_ENTRY_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AppEntryPlanResult",
    "type": "object",
    "additionalProperties": False,
    "required": sorted(APP_ENTRY_PLAN_OUTPUT_KEYS),
    "properties": {
        "active": {"type": "boolean"},
        "app_context_counts": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0},
        },
        "attitude": {"type": "number", "minimum": 0, "maximum": 1},
        "subjective_norm": {"type": "number", "minimum": 0, "maximum": 1},
        "perceived_control": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
    },
}


def _calibrated_counts(weights: dict[str, int], exposures: int) -> dict[str, int]:
    """Allocate the fixed integer total by largest remainder, breaking ties by name."""
    weight_total = sum(weights.values())
    counts = {}
    remainders = {}
    for context, weight in weights.items():
        counts[context], remainders[context] = divmod(exposures * weight, weight_total)
    unassigned = exposures - sum(counts.values())
    for context in sorted(weights, key=lambda name: (-remainders[name], name))[:unassigned]:
        counts[context] += 1
    return {context: count for context, count in counts.items() if count}


def _score(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise ValueError(f"{field_name} must be in [0, 1]")
    return result


def _strict_json_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a JSON integer")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return int(value)


def _canonical_plan_payload(
    payload: Any,
    *,
    candidate_contexts: dict[str, float],
    active_exposure_cap: int,
    calibrated: bool = False,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("app entry plan output must be a JSON object")
    count_field = "app_context_weights" if calibrated else "app_context_counts"
    if set(payload) != (APP_ENTRY_PLAN_OUTPUT_KEYS - {"app_context_counts"}) | {count_field}:
        raise ValueError("app entry plan output keys do not match the schema")

    active = payload.get("active")
    if not isinstance(active, bool):
        raise ValueError("active must be a JSON boolean")

    raw_counts = payload.get(count_field)
    if not isinstance(raw_counts, dict):
        raise ValueError(f"{count_field} must be a JSON object")

    allowed_contexts = set(candidate_contexts)
    unknown_contexts = sorted(
        str(context)
        for context in raw_counts
        if str(context).strip() not in allowed_contexts
    )
    if unknown_contexts:
        raise ValueError(
            f"{count_field} contains contexts outside candidate pool: "
            + ", ".join(unknown_contexts)
        )

    counts: dict[str, int] = {}
    for raw_context, raw_count in raw_counts.items():
        context = str(raw_context).strip()
        count = _strict_json_int(raw_count, f"{count_field}[{context}]")
        if calibrated and count > 100:
            raise ValueError("relative context weights must be integers from 0 to 100")
        if count > 0:
            counts[context] = count

    if not active:
        if counts or (calibrated and raw_counts):
            raise ValueError("inactive plan must have empty counts")
    else:
        if not counts:
            raise ValueError(f"active plan must include {count_field}")
        if calibrated:
            counts = _calibrated_counts(counts, active_exposure_cap)
        elif sum(counts.values()) > int(active_exposure_cap):
            raise ValueError(
                "derived exposure count exceeds calibration cap "
                f"{int(active_exposure_cap)}"
            )
    exposures = sum(counts.values())

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, str):
        raise ValueError("reasoning must be a string")
    if len(reasoning) > 1200:
        raise ValueError("reasoning is too long")

    return {
        "active": active,
        "active_event_app_exposures": exposures,
        "app_context_counts": counts,
        "attitude": _score(payload.get("attitude"), "attitude"),
        "subjective_norm": _score(
            payload.get("subjective_norm"), "subjective_norm"
        ),
        "perceived_control": _score(
            payload.get("perceived_control"), "perceived_control"
        ),
        "confidence": _score(payload.get("confidence"), "confidence"),
        "reasoning": reasoning,
    }


def sanitize_app_entry_plan_payload(
    payload: Any,
    *,
    candidate_contexts: dict[str, float],
    active_exposure_cap: int,
    min_confidence: float = 0.0,
    diagnostics: dict[str, Any] | None = None,
    calibrated: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    try:
        canonical = _canonical_plan_payload(
            payload,
            candidate_contexts=candidate_contexts,
            active_exposure_cap=active_exposure_cap,
            calibrated=calibrated,
        )
        confidence_floor = _score(min_confidence, "min_confidence")
        if canonical["confidence"] < confidence_floor:
            if diagnostics is not None:
                diagnostics["last_validation_error"] = (
                    f"confidence {canonical['confidence']:.6g} is below "
                    f"minimum {confidence_floor:.6g}"
                )
            return None, "low_confidence"
        return canonical, "ok"
    except ValueError as exc:
        message = str(exc)
        if diagnostics is not None:
            diagnostics["last_validation_error"] = message
        if "confidence" in message:
            return None, "low_confidence"
        if "outside candidate pool" in message:
            return None, "invalid_schema"
        return None, "invalid_schema"


@dataclass(slots=True)
class AppEntryPlanResult:
    active: bool
    active_event_app_exposures: int
    app_context_counts: dict[str, int]
    attitude: float
    subjective_norm: float
    perceived_control: float
    confidence: float
    reasoning: str
    audit: dict[str, Any] = field(default_factory=dict)
    intent: dict[str, Any] | None = None

    @property
    def primary_context(self) -> str:
        return derive_primary_context(self.app_context_counts)

    def to_bundle(
        self,
        *,
        device_id: str,
        day: int,
        hour: int,
        source: str = "llm_memory_rollout",
    ) -> HourlyAppEntryBundle:
        return HourlyAppEntryBundle.from_rollout_payload(
            device_id=device_id,
            day=day,
            hour=hour,
            payload={
                "active": self.active,
                "active_event_app_exposures": self.active_event_app_exposures,
                "app_context_counts": self.app_context_counts,
            },
            source=source,
        )

    def to_dict(self, *, include_audit: bool = True) -> dict[str, Any]:
        payload = {
            "active": self.active,
            "active_event_app_exposures": self.active_event_app_exposures,
            "app_context_counts": dict(self.app_context_counts),
            "primary_context": self.primary_context,
            "attitude": self.attitude,
            "subjective_norm": self.subjective_norm,
            "perceived_control": self.perceived_control,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        if self.intent is not None:
            payload["intent"] = dict(self.intent)
        if include_audit:
            payload["audit"] = dict(self.audit)
        return payload


def _plan_system_prompt(prompt_version: str) -> str:
    if prompt_version == CALIBRATED_PLAN_VERSION:
        return (
            "Decide whether this simulated device is active this hour, using the "
            "observed same-hour active rate, digital needs, habits and app contexts. "
            "Choose relative integer weights (0 to 100) among the allowed app contexts "
            "when active, or an empty object when inactive. Do not output event counts. "
            "The simulator determines exposure volume from this device's first three days. "
            "Do not invent support, future events, or outcomes. Return only the supplied JSON schema. "
            f"Prompt version: {prompt_version}."
        )
    return (
        "You are the DigitalAppEntryPlanBlock in a simulated older-adult mobile-use "
        "model. Return exactly one JSON object matching the supplied schema. The "
        "candidate app contexts are the only contexts you may use. Habit strength "
        "is observed repetition and is not attitude; time fit alone is not "
        "subjective norm. Do not invent obligations, outcomes, support, or future "
        "events. Do not output device_id, day, hour, source, or primary_context. "
        "Follow runtime_output_constraints exactly, including the explicit context "
        "allowlist, exposure cap, confidence floor, and inactive contract. "
        f"Prompt version: {prompt_version}. Schema version: {APP_ENTRY_PLAN_SCHEMA_VERSION}."
    )


def _legacy_plan_prompt(
    prompt_version,
    input_payload,
    needs,
    normalized_candidates,
    intensity_profile,
    cap,
    confidence_floor,
    calibrated,
):
    system_prompt = _plan_system_prompt(str(prompt_version))
    user_payload = {
        "prompt_version": str(prompt_version),
        "schema_version": APP_ENTRY_PLAN_SCHEMA_VERSION,
        "inputs": input_payload,
        "digital_needs": needs.to_dict(include_audit=False),
        "candidate_app_contexts": normalized_candidates,
        "intensity_profile": intensity_profile,
        "runtime_output_constraints": {
            "allowed_app_contexts": sorted(normalized_candidates),
            "active_exposure_minimum": 1,
            "active_exposure_maximum": cap,
            "minimum_confidence": confidence_floor,
            "inactive_contract": {
                "active": False,
                "app_context_counts": {},
            },
            "forbidden_output_keys": [
                "device_id",
                "day",
                "hour",
                "source",
                "primary_context",
            ],
        },
        "output_schema": APP_ENTRY_PLAN_JSON_SCHEMA,
    }
    count_field = "app_context_counts"
    count_constraint = (
        f"when active=true, the sum of app_context_counts must be from 1 through {cap}"
    )
    value_constraint = "every context count must be a non-negative JSON integer"
    if calibrated:
        count_field = "app_context_weights"
        properties = dict(APP_ENTRY_PLAN_JSON_SCHEMA["properties"])
        del properties["app_context_counts"]
        properties[count_field] = {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 0, "maximum": 100},
        }
        user_payload["output_schema"] = {
            **APP_ENTRY_PLAN_JSON_SCHEMA,
            "required": sorted(properties),
            "properties": properties,
        }
        user_payload["schema_version"] = "app_entry_plan_context_weights_v1"
        constraints = user_payload["runtime_output_constraints"]
        del (
            constraints["active_exposure_minimum"],
            constraints["active_exposure_maximum"],
        )
        constraints["inactive_contract"] = {"active": False, count_field: {}}
        constraints["weight_contract"] = (
            "Relative integer weights from 0 to 100. At least one positive weight if active."
        )
        count_constraint = (
            "when active=true, include at least one positive relative weight"
        )
        value_constraint = (
            "each relative weight must be a JSON integer from 0 through 100"
        )
    output_keys = set(user_payload["output_schema"]["required"])
    repair_text = (
        "- output exactly these keys and no others: "
        + ", ".join(sorted(output_keys))
        + "\n- active must be the JSON boolean true or false"
        + f"\n- allowed {count_field} keys are exactly: "
        + json.dumps(sorted(normalized_candidates), ensure_ascii=False)
        + f"\n- {count_constraint}"
        + f"\n- {value_constraint}"
        + f"\n- when active=false, {count_field} must be {{}}"
        + f"\n- confidence must be a number from {confidence_floor:.6g} through 1"
        + "\n- attitude, subjective_norm, and perceived_control must each be numbers from 0 through 1"
        + "\n- do not output primary_context or runtime metadata"
    )
    return system_prompt, user_payload, output_keys, repair_text


def _compact_system_prompt(calibrated: bool) -> str:
    activity = (
        "weights 是各所选频道的相对整数权重（0–100），不使用手机填空对象。实际次数由模拟器确定。"
        if calibrated
        else "选取带 @open: 的行动，就表示亲自打开该频道一次来办理所选目标。additional_apps 只列此外确实要打开的频道，"
        "每多开一次就写一次，可以再开同一频道。其他行动本身不含打开，另做的手机活动全部列在 additional_apps。"
        "没有额外打开填空列表，总打开次数不得超过 exposure_cap。"
    )
    return (
        "你扮演一位老年手机用户。结合此刻需求、前三天习惯、已有经历和待办，自己决定这一小时做什么。"
        "只输出决策 JSON。先决定行为种类；各类同等可选，清单顺序和时点个数不代表偏好或概率。"
        "action 只写一个完整行动，从 actions 或 defer_options 中选取。targets 将选项里的代号对应到真实机会或待办。"
        "engage_goal 接受机会，continue_goal 继续待办，两者须实际使用该目标的 required_channel。"
        "defer_goal 延期、drop_goal 放弃时也可用手机做别的事。habitual_app 日常使用手机，no_app 不用手机。"
        "要延期，自己决定何时再看，原样复制对应时点的完整选项。若时点以区间显示，用该组 prefix 紧接所选范围内的整数小时。"
        + activity
        + "频道只能来自 channels。历史频率仅描述过去。attitude 是本人意愿，subjective_norm 是感到的社会期待，"
        "perceived_control 是自觉把握，confidence 是判断信心，分别给 0 到 1 的数字。reason 写一句本人的原因。"
        "不预设任务结果或帮助。只给下列字段：action、"
        + ("weights" if calibrated else "additional_apps")
        + "、attitude、subjective_norm、perceived_control、confidence、reason。"
    )


def decode_compact_plan(raw: dict, request_body: dict) -> dict:
    """Decode the exact model-selected action and activity from the transmitted contract."""
    calibrated = "exposures_if_active" in request_body
    v4 = request_body["schema_version"] == COMPACT_PLAN_VERSION
    if v4 and calibrated:
        raise ValueError("v4 goal opening tokens require exposure-count mode")
    field = "weights" if calibrated else ("additional_apps" if v4 else "apps")
    required = {"action", field, "reason", *COMPACT_SCORES}
    if request_body["schema_version"] == COMPACT_PLAN_V2:
        required.add("review")
    elif request_body["schema_version"] not in (COMPACT_PLAN_V3, COMPACT_PLAN_VERSION):
        raise ValueError("unsupported compact Plan schema version")
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("expected decision fields: " + ", ".join(sorted(required)))

    intent = compact_intent(raw, request_body)
    apps = raw[field]
    cap = request_body["exposures_if_active" if calibrated else "exposure_cap"]
    if calibrated:
        if not isinstance(apps, dict):
            raise ValueError("weights must be a channel-to-weight object")
        counts = apps
    else:
        if not isinstance(apps, list) or not all(isinstance(a, str) for a in apps):
            raise ValueError(f"{field} must list each channel opening")
        opened = stated_open_channel(raw["action"], request_body)
        if len(apps) + int(opened is not None) > cap:
            raise ValueError(f"total App openings exceed the exposure cap of {cap}")
        counts = {opened: 1} if opened is not None else {}
        for app in apps:
            counts[app] = counts.get(app, 0) + 1
    allowed = dict.fromkeys(request_body["channels"], 1.0)
    # The public legacy validator normalizes whitespace in keys. Here the exact labels are the wire contract.
    if any(channel not in allowed for channel in counts):
        raise ValueError("unknown app channel")
    plan = _canonical_plan_payload(
        {
            "active": bool(counts),
            "app_context_weights" if calibrated else "app_context_counts": counts,
            "reasoning": raw["reason"],
            **{name: raw[name] for name in COMPACT_SCORES},
        },
        candidate_contexts=allowed,
        active_exposure_cap=cap,
        calibrated=calibrated,
    )
    if plan["confidence"] < request_body["minimum_confidence"]:
        raise ValueError("confidence is below the minimum")
    plan["intent"] = validate_intent(intent, plan, request_body["inputs"])
    return plan


def _compact_plan_prompt(
    input_payload, needs, candidates, cap, confidence_floor, calibrated
):
    observation = compact_observation(input_payload)
    version = COMPACT_PLAN_V3 if calibrated else COMPACT_PLAN_VERSION
    body = {
        "schema_version": version,
        "inputs": observation,
        "digital_needs": compact_needs(needs.to_dict(include_audit=False)),
        **compact_menu(observation, version),
        "channels": sorted(candidates),
        "exposures_if_active" if calibrated else "exposure_cap": cap,
        "minimum_confidence": confidence_floor,
    }
    keys = {"action", "weights" if calibrated else "additional_apps", "reason", *COMPACT_SCORES}
    return _compact_system_prompt(calibrated), body, keys, ""


class HourlyIntentionPlanError(ValueError):
    def __init__(self, message: str, audit: dict[str, Any]):
        super().__init__(message)
        self.audit = audit


class DigitalAppEntryPlanBlock:
    """Constrained PlanBlock interface; not registered as an action block."""

    async def forward(
        self,
        *,
        llm: Any,
        needs: DigitalNeedsResult,
        candidate_contexts: dict[str, float],
        input_payload: dict[str, Any],
        intensity_profile: dict[str, Any],
        prompt_version: str = APP_ENTRY_PLAN_PROMPT_VERSION,
        min_confidence: float = 0.0,
        timeout: int = 30,
        retries: int = 1,
        json_attempts: int = 5,
    ) -> AppEntryPlanResult:
        if not isinstance(needs, DigitalNeedsResult):
            raise ValueError("needs must be a DigitalNeedsResult")
        if not isinstance(input_payload, dict):
            raise ValueError("input_payload must be a dictionary")
        with_intent = "available_opportunities" in input_payload
        if not isinstance(candidate_contexts, dict) or (
            not candidate_contexts and not with_intent
        ):
            raise ValueError("candidate_contexts must be a non-empty dictionary")
        normalized_candidates: dict[str, float] = {}
        for context, weight in candidate_contexts.items():
            name = str(context).strip()
            if name not in APP_CONTEXT_SET:
                raise ValueError(f"unknown app context in candidate pool: {name}")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ValueError(f"candidate weight for {name} must be numeric")
            if not math.isfinite(float(weight)) or float(weight) <= 0.0:
                raise ValueError(f"candidate weight for {name} must be positive")
            normalized_candidates[name] = float(weight)

        if with_intent:
            normalized_candidates = include_required_channels(
                normalized_candidates, input_payload
            )
        if not isinstance(intensity_profile, dict):
            raise ValueError("intensity_profile must be a dictionary")
        calibrated = prompt_version == CALIBRATED_PLAN_VERSION
        volume_field = "exposures_if_active" if calibrated else "active_exposure_cap"
        try:
            cap = int(intensity_profile[volume_field])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"intensity_profile.{volume_field} is required") from exc
        if cap < 1:
            raise ValueError(f"{volume_field} must be >= 1")
        confidence_floor = _score(min_confidence, "min_confidence")
        bounded_json_attempts = max(
            1,
            min(MAX_APP_ENTRY_PLAN_JSON_ATTEMPTS, int(json_attempts)),
        )

        if with_intent:
            bounded_json_attempts = 1
            system_prompt, user_payload, output_keys, repair_text = (
                _compact_plan_prompt(
                    input_payload,
                    needs,
                    normalized_candidates,
                    cap,
                    confidence_floor,
                    calibrated,
                )
            )
        else:
            system_prompt, user_payload, output_keys, repair_text = _legacy_plan_prompt(
                prompt_version,
                input_payload,
                needs,
                normalized_candidates,
                intensity_profile,
                cap,
                confidence_floor,
                calibrated,
            )
        audit: dict[str, Any] = {
            "block": "DigitalAppEntryPlanBlock",
            "schema_version": user_payload["schema_version"],
            "prompt_version": str(prompt_version),
            "prompt_hash": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[
                :16
            ],
            "schema_hash": hashlib.sha256(
                _stable_hash(
                    user_payload.get(
                        "output_schema", [user_payload["schema_version"], sorted(output_keys)]
                    )
                ).encode("utf-8")
            ).hexdigest()[:16],
            "candidate_hash": app_context_candidate_hash(normalized_candidates),
            "payload_hash": _stable_hash(user_payload)[:16],
            "parse_status": "not_called",
        }

        statements = {}

        def observe_choice(phase: str, raw: str) -> None:
            statement = read_compact_statement(raw, user_payload)
            statements[phase] = statement
            prefix = "raw_" if phase == "initial" else "repaired_"
            for key in ("choice", "channels", "active", "activity"):
                audit[prefix + key] = statement[key]
            if user_payload["schema_version"] == COMPACT_PLAN_VERSION:
                for key in ("opened_channel", "additional_activity"):
                    audit[prefix + key] = statement[key]
            if phase == "repair":
                audit["repair_changed_choice"] = compact_repair_changed(
                    statements["initial"], statement
                )

        def repair_dialog(raw: str, error: str) -> list[dict]:
            initial = statements["initial"]
            repair = {
                "schema_version": user_payload["schema_version"],
                "error": audit.get("last_validation_error", error),
                "preserve": {
                    k: initial[k]
                    for k in ("action", "choice", "active", "activity")
                    if initial[k] is not None
                },
                "actions": user_payload["actions"],
                "targets": user_payload["targets"],
                "defer_options": user_payload["defer_options"],
                "channels": user_payload["channels"],
                "exposures_if_active" if calibrated else "exposure_cap": cap,
                "minimum_confidence": confidence_floor,
            }
            for key in ("scores", "partial_apps", "partial_weights"):
                if initial[key]:
                    repair["preserve"][key] = initial[key]
            if user_payload["schema_version"] == COMPACT_PLAN_VERSION:
                for key in ("opened_channel", "additional_activity"):
                    if initial[key] is not None:
                        repair["preserve"][key] = initial[key]
                if initial["partial_additional_apps"]:
                    repair["preserve"]["partial_additional_apps"] = initial[
                        "partial_additional_apps"
                    ]
            if initial["choice"] is None:
                # With no identifiable decision, the repair still needs the same evidence.
                # Keep it separate from initially valid choices in the audit.
                repair.update(
                    inputs=user_payload["inputs"],
                    digital_needs=user_payload["digital_needs"],
                )
            else:
                obs = user_payload["inputs"]
                repair["target_constraints"] = {
                    k: obs[k]
                    for k in (
                        "available_opportunities",
                        "current_intention",
                        "monotonic_sim_hour",
                        "max_defer_hours",
                    )
                }
                repair["previous_reply"] = raw[:1200]
            return [
                {
                    "role": "system",
                    "content": system_prompt
                    + "修正上次输出的格式。保留已经表达的选择、目标、复查时间、实际使用量和已给评分。",
                },
                {"role": "user", "content": json.dumps(repair, ensure_ascii=False)},
            ]

        def sanitize_plan(raw: dict) -> tuple[dict | None, str]:
            if with_intent:
                if audit["repair_changed_choice"]:
                    audit["last_validation_error"] = (
                        "format repair changed an identifiable or ambiguous decision, activity, review time, or score"
                    )
                    return None, "changed_intent_on_repair"
                try:
                    return decode_compact_plan(raw, user_payload), "ok"
                except ValueError as exc:
                    audit["last_validation_error"] = str(exc)
                    return None, (
                        "low_confidence"
                        if "confidence is below" in str(exc)
                        else "invalid_intent"
                    )
            return sanitize_app_entry_plan_payload(
                raw,
                candidate_contexts=normalized_candidates,
                active_exposure_cap=cap,
                min_confidence=confidence_floor,
                diagnostics=audit,
                calibrated=calibrated,
            )

        if with_intent:
            audit.update(
                raw_choice=None,
                repaired_choice=None,
                accepted_choice=None,
                repair_changed_choice=False,
                candidate_app_contexts=normalized_candidates,
                input_packet_hash=_stable_hash(user_payload["inputs"])[:16],
                input_episode_ids=[
                    episode["episode_id"]
                    for episode in input_payload["recent_task_episodes"]
                    if episode.get("episode_id")
                ],
            )
        payload, status = await _query_json_payload(
            trace_module="app_plan",
            llm=llm,
            system_prompt=system_prompt,
            user_payload=user_payload,
            output_keys=output_keys,
            repair_schema_text=repair_text,
            sanitize_fn=sanitize_plan,
            timeout=int(timeout),
            retries=int(retries),
            max_tokens=560 if with_intent else 420,
            json_attempts=bounded_json_attempts,
            audit=audit,
            **(
                {
                    "on_raw_response": observe_choice,
                    "repair_dialog_factory": repair_dialog,
                    "parse_response": parse_compact_reply,
                }
                if with_intent
                else {}
            ),
        )
        if with_intent:
            audit["accepted_choice"] = (
                payload.get("intent") if payload is not None else None
            )
            audit["technical_failure"] = payload is None
            audit["rejection_reason"] = (
                audit.get("last_validation_error", status) if payload is None else None
            )
            trace_record("intent_validation", module="app_plan", **audit)
        if payload is None:
            diagnostic = str(audit.get("last_validation_error", "no valid JSON object"))
            message = (
                "DigitalAppEntryPlanBlock JSON output failed after bounded attempts: "
                f"{status}; last_validation_error={diagnostic}; "
                f"json_attempts_used={audit.get('json_attempts_used', 0)}; "
                f"actual_requests={audit.get('actual_requests', 0)}; "
                f"repair_requests={audit.get('repair_requests', 0)}; "
                f"last_raw_response_hash={audit.get('last_raw_response_hash', '')}; "
                f"last_repair_response_hash={audit.get('last_repair_response_hash', '')}"
            )
            if with_intent:
                raise HourlyIntentionPlanError(message, audit)
            raise ValueError(message)
        audit["response_hash"] = _stable_hash(payload)[:16]
        audit["parse_status"] = status
        return AppEntryPlanResult(
            active=bool(payload["active"]),
            active_event_app_exposures=sum(
                int(value) for value in payload["app_context_counts"].values()
            ),
            app_context_counts=dict(payload["app_context_counts"]),
            attitude=float(payload["attitude"]),
            subjective_norm=float(payload["subjective_norm"]),
            perceived_control=float(payload["perceived_control"]),
            confidence=float(payload["confidence"]),
            reasoning=str(payload["reasoning"]),
            audit=audit,
            intent=payload.get("intent"),
        )
