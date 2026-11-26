from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..memory.packet import compact_recent_episodes, is_prior_episode
from .bundle import HourlyAppEntryBundle
from .bundle_loader import simulation_day_to_talkingdata_day
from .candidate import build_rollout_app_context_candidates
from .evaluator import evaluate_selected_app_context_bundle_for_agent
from .habit_memory import build_calibrated_intensity_profile, build_rollout_intensity_profile
from .needs import (
    DIGITAL_NEED_TO_APP_CONTEXTS,
    DigitalNeedsBlock,
    DigitalNeedsResult,
)
from .planner import CALIBRATED_PLAN_VERSION, AppEntryPlanResult, DigitalAppEntryPlanBlock
from .types import MobileEntryDecision, _stable_hash


ROLLOUT_AUDIT_SCHEMA_VERSION = "app_entry_llm_rollout_audit_v1"
ROLLOUT_ENTRY_MODE = "app_context_replay_then_llm_rollout"
ROLLOUT_SOURCE = "llm_memory_rollout"

_PROFILE_KEYS = (
    "age",
    "gender",
    "digital_experience",
    "vision_limit",
    "past_fraud_experience",
    "education",
    "phone_price",
)
_ENVIRONMENT_CUE_KEYS = (
    "friction_level",
    "malicious_friction_level",
    "complexity_level",
    "risk_level",
    "assist_level",
    "accessibility_level",
    "human_support_level",
)
_REFLECTION_KEYS = (
    "day",
    "dominant_task_family",
    "help_effective",
    "mastery_signal",
    "text",
)
_RECENT_ROLLOUT_KEYS = (
    "talkingdata_day",
    "hour",
    "active",
    "active_event_app_exposures",
    "app_context_counts",
    "primary_context",
    "dominant_need",
    "entry_status",
    "task_generated",
)
_FORBIDDEN_KEY_FRAGMENTS = (
    "validation",
    "heldout",
    "held_out",
    "future_outcome",
    "current_hour_outcome",
    "world_name",
)


def _compact_mapping(
    value: Any,
    *,
    allowed_keys: tuple[str, ...],
    text_limit: int = 240,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in value:
            continue
        item = value[key]
        result[key] = str(item)[:text_limit] if isinstance(item, str) else item
    return result


def _assert_no_forbidden_evidence(value: Any, *, path: str = "input") -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if any(fragment in key for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError(f"forbidden rollout evidence at {path}.{raw_key}")
            _assert_no_forbidden_evidence(item, path=f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_forbidden_evidence(item, path=f"{path}[{index}]")


def _compact_recent_rollout_rows(value: Any, day: int, hour: int) -> list[dict[str, Any]]:
    rows = list(value) if isinstance(value, list) else []
    compacted: list[dict[str, Any]] = []
    for index, row in enumerate(reversed(rows)):
        if not isinstance(row, dict):
            continue
        if bool(row.get("uses_validation_data", False)):
            raise ValueError(
                f"forbidden rollout evidence at recent_rollout_rows[{index}]."
                "uses_validation_data"
            )
        non_audit_row = {
            key: item for key, item in row.items() if key != "uses_validation_data"
        }
        _assert_no_forbidden_evidence(
            non_audit_row,
            path=f"recent_rollout_rows[{index}]",
        )
        if not is_prior_episode({"day": row.get("talkingdata_day"), "hour": row.get("hour")}, day, hour * 3600):
            continue
        compacted.append(_compact_mapping(row, allowed_keys=_RECENT_ROLLOUT_KEYS))
        if len(compacted) == 6:
            break
    return list(reversed(compacted))


def build_rollout_input_packet(
    *,
    simulation_day: int,
    talkingdata_day: int,
    hour: int,
    stable_profile: dict[str, Any] | None,
    habit_memory: dict[str, Any],
    recent_rollout_rows: Any,
    recent_task_episodes: Any,
    latest_reflection: Any,
    helplessness: float,
    trust: float,
    avoidance: float,
    environment: dict[str, Any],
    intensity_profile: dict[str, Any],
) -> dict[str, Any]:
    hour_key = str(int(hour))
    active_row = habit_memory.get("active_by_hour", {}).get(hour_key, {})
    context_by_hour = habit_memory.get("context_by_hour", {}).get(hour_key, {})
    primary_by_hour = habit_memory.get("primary_context_by_hour", {}).get(
        hour_key, {}
    )
    packet = {
        "simulation_day": int(simulation_day),
        "talkingdata_day": int(talkingdata_day),
        "hour": int(hour),
        "stable_profile": _compact_mapping(
            stable_profile or {},
            allowed_keys=_PROFILE_KEYS,
        ),
        "day1_3_habit": {
            "replay_days": list(habit_memory.get("replay_days", [])),
            "same_hour_active": dict(active_row) if isinstance(active_row, dict) else {},
            "same_hour_context_counts": (
                dict(context_by_hour) if isinstance(context_by_hour, dict) else {}
            ),
            "same_hour_primary_counts": (
                dict(primary_by_hour) if isinstance(primary_by_hour, dict) else {}
            ),
            "overall_context_counts": dict(
                habit_memory.get("context_total_counts", {})
            ),
            "intensity_profile": dict(intensity_profile),
        },
        "recent_simulated_bundles": _compact_recent_rollout_rows(
            recent_rollout_rows, talkingdata_day, hour
        ),
        "recent_task_episodes": compact_recent_episodes(
            recent_task_episodes, simulation_day=simulation_day, tick_seconds=hour * 3600,
        ),
        "latest_reflection": _compact_mapping(
            latest_reflection,
            allowed_keys=_REFLECTION_KEYS,
        ),
        "pre_hour_psychology": {
            "helplessness": float(helplessness),
            "trust_in_apps": float(trust),
            "avoidance_tendency": float(avoidance),
        },
        "environment_cues": _compact_mapping(
            environment,
            allowed_keys=_ENVIRONMENT_CUE_KEYS,
        ),
    }
    _assert_no_forbidden_evidence(packet)
    return packet


@dataclass(slots=True)
class AppEntryRolloutResult:
    bundle: HourlyAppEntryBundle
    needs: DigitalNeedsResult
    plan: AppEntryPlanResult
    decision: MobileEntryDecision
    input_packet: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle.to_dict(),
            "needs": self.needs.to_dict(),
            "plan": self.plan.to_dict(),
            "decision": self.decision.to_dict(),
            "input_packet_hash": _stable_hash(self.input_packet)[:16],
        }


async def run_app_entry_rollout_hour(
    *,
    llm: Any,
    agent_id: int,
    simulation_day: int,
    tick_seconds: float,
    environment: dict[str, Any],
    stable_profile: dict[str, Any] | None,
    device_id: str,
    selected_rank: int,
    habit_memory: dict[str, Any],
    day4_snapshot: dict[str, Any],
    recent_rollout_rows: Any,
    recent_task_episodes: Any,
    latest_reflection: Any,
    helplessness: float,
    trust: float,
    avoidance: float,
    needs_prompt_version: str,
    plan_prompt_version: str,
    json_attempts: int,
    min_confidence: float,
    top_k: int,
    absolute_exposure_cap: int,
    timeout: int,
    retries: int,
    task_opportunity_mapping_path: str = "",
    task_occurrence_gate_enabled: bool = False,
    task_occurrence_prior_path: str = "",
    task_occurrence_gate_multiplier: float = 1.0,
    existing_task_pending: bool = False,
) -> AppEntryRolloutResult:
    if llm is None:
        raise ValueError("Day 4-7 app-entry rollout requires an LLM client")
    if not isinstance(day4_snapshot, dict) or not day4_snapshot:
        raise ValueError("Day 4 replay snapshot is required before LLM rollout")
    talkingdata_day = simulation_day_to_talkingdata_day(int(simulation_day))
    if talkingdata_day < 4 or talkingdata_day > 7:
        raise ValueError("LLM app-entry rollout only supports TalkingData days 4..7")
    hour = int(round(float(tick_seconds))) // 3600 % 24
    if plan_prompt_version == CALIBRATED_PLAN_VERSION:
        intensity_profile = build_calibrated_intensity_profile(habit_memory, hour=hour)
    else:
        intensity_profile = build_rollout_intensity_profile(
            habit_memory, hour=hour, absolute_cap=int(absolute_exposure_cap)
        )
    input_packet = build_rollout_input_packet(
        simulation_day=int(simulation_day),
        talkingdata_day=talkingdata_day,
        hour=hour,
        stable_profile=stable_profile,
        habit_memory=habit_memory,
        recent_rollout_rows=recent_rollout_rows,
        recent_task_episodes=recent_task_episodes,
        latest_reflection=latest_reflection,
        helplessness=float(helplessness),
        trust=float(trust),
        avoidance=float(avoidance),
        environment=environment,
        intensity_profile=intensity_profile,
    )

    try:
        needs = await DigitalNeedsBlock().forward(
            llm=llm,
            input_payload=input_packet,
            prompt_version=str(needs_prompt_version),
            timeout=int(timeout),
            retries=int(retries),
            json_attempts=int(json_attempts),
        )
    except ValueError as exc:
        raise ValueError(
            "Day 4-7 DigitalNeedsBlock failed for "
            f"agent_id={int(agent_id)}, device_id={str(device_id)}, "
            f"talkingdata_day={talkingdata_day}, hour={hour}: {exc}"
        ) from exc
    candidate_contexts = build_rollout_app_context_candidates(
        habit_memory=habit_memory,
        hour=hour,
        need_pressures=needs.need_pressures,
        need_context_mapping=DIGITAL_NEED_TO_APP_CONTEXTS,
        top_k=int(top_k),
    )
    try:
        plan = await DigitalAppEntryPlanBlock().forward(
            llm=llm,
            needs=needs,
            candidate_contexts=candidate_contexts,
            input_payload=input_packet,
            intensity_profile=intensity_profile,
            prompt_version=str(plan_prompt_version),
            min_confidence=float(min_confidence),
            timeout=int(timeout),
            retries=int(retries),
            json_attempts=int(json_attempts),
        )
    except ValueError as exc:
        raise ValueError(
            "Day 4-7 DigitalAppEntryPlanBlock failed for "
            f"agent_id={int(agent_id)}, device_id={str(device_id)}, "
            f"talkingdata_day={talkingdata_day}, hour={hour}: {exc}"
        ) from exc
    bundle = plan.to_bundle(
        device_id=str(device_id),
        day=talkingdata_day,
        hour=hour,
        source=ROLLOUT_SOURCE,
    )
    rollout_audit = {
        "rollout_audit_schema_version": ROLLOUT_AUDIT_SCHEMA_VERSION,
        "entry_mode": ROLLOUT_ENTRY_MODE,
        "entry_phase": "llm_rollout",
        "entry_layer": "hourly_app_entry_bundle",
        "source": ROLLOUT_SOURCE,
        "forced_replay": False,
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "app_entry_does_not_update_psychology": True,
        "agent_id": int(agent_id),
        "device_id": str(device_id),
        "selected_rank": int(selected_rank),
        "simulation_day": int(simulation_day),
        "talkingdata_day": int(talkingdata_day),
        "hour": int(hour),
        "active": bool(bundle.active),
        "active_event_app_exposures": int(bundle.active_event_app_exposures),
        "app_context_counts": dict(bundle.app_context_counts),
        "primary_context": bundle.primary_context,
        "selected_app_context": bundle.primary_context,
        "candidate_app_contexts": dict(candidate_contexts),
        "needs": needs.to_dict(include_audit=False),
        "plan": plan.to_dict(include_audit=False),
        "needs_hash": _stable_hash(needs.to_dict(include_audit=False))[:16],
        "plan_hash": _stable_hash(plan.to_dict(include_audit=False))[:16],
        "needs_prompt_version": needs.audit.get("prompt_version", ""),
        "needs_prompt_hash": needs.audit.get("prompt_hash", ""),
        "needs_json_attempts_used": int(
            needs.audit.get("json_attempts_used", 0)
        ),
        "needs_actual_requests": int(needs.audit.get("actual_requests", 0)),
        "needs_repair_requests": int(needs.audit.get("repair_requests", 0)),
        "plan_prompt_version": plan.audit.get("prompt_version", ""),
        "plan_prompt_hash": plan.audit.get("prompt_hash", ""),
        "plan_json_attempts_used": int(plan.audit.get("json_attempts_used", 0)),
        "plan_actual_requests": int(plan.audit.get("actual_requests", 0)),
        "plan_repair_requests": int(plan.audit.get("repair_requests", 0)),
        "input_packet_hash": _stable_hash(input_packet)[:16],
        "primary_context_rule_version": "primary_context_max_count_lexical_v1",
    }
    decision = evaluate_selected_app_context_bundle_for_agent(
        agent_id=int(agent_id),
        day=int(simulation_day),
        tick_seconds=float(tick_seconds),
        env=environment,
        stable_profile=stable_profile,
        bundle=bundle,
        entry_mode=ROLLOUT_ENTRY_MODE,
        prior_source=ROLLOUT_SOURCE,
        audit_payload=rollout_audit,
        calibration_hash=rollout_audit["input_packet_hash"],
        task_opportunity_mapping_path=task_opportunity_mapping_path,
        task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
        task_occurrence_prior_path=task_occurrence_prior_path,
        task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
        existing_task_pending=bool(existing_task_pending),
    )
    return AppEntryRolloutResult(
        bundle=bundle,
        needs=needs,
        plan=plan,
        decision=decision,
        input_packet=input_packet,
    )
