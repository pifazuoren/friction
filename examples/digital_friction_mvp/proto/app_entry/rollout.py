from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..llm_trace import trace_record
from ..logical_clock import monotonic_sim_hour
from ..memory.packet import compact_recent_episodes, is_prior_episode
from . import DEFAULT_PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V5, RESIDENT_DECISION_PLAN_VERSION
from .bundle import HourlyAppEntryBundle
from .bundle_loader import simulation_day_to_talkingdata_day
from .candidate import build_rollout_app_context_candidates
from .evaluator import evaluate_selected_app_context_bundle_for_agent
from .habit_memory import build_calibrated_intensity_profile, build_rollout_intensity_profile
from .intention_contract import has_actionable_target, intention_observation
from .needs import (
    DIGITAL_NEED_TO_APP_CONTEXTS,
    PHONE_USE_NEEDS_V3,
    PHONE_USE_NEEDS_VERSION,
    DigitalNeedsBlock,
    DigitalNeedsResult,
)
from .phone_policy import replay_activity_counts, resolve_phone_use
from .planner import CALIBRATED_PLAN_VERSION, AppEntryPlanResult, DigitalAppEntryPlanBlock, HourlyIntentionPlanError
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
    "opened_channel",
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

_DEVICE_CONTEXT_LABELS = {
    "communication_social_context": "通讯社交",
    "media_entertainment_context": "影音娱乐",
    "finance_context": "金融",
    "public_service_context": "公共服务",
    "health_service_context": "医疗健康",
    "shopping_lifestyle_context": "购物生活",
    "navigation_transport_context": "导航出行",
    "device_tool_context": "设备工具",
    "education_work_context": "教育办公",
}


def phone_use_habit_fact(hour: int, same_hour_active: dict | None, same_hour_context_counts: dict | None) -> str:
    """Describe observed same-clock replay activity and the most frequent identifiable categories."""
    interval = f"{hour:02d}:00 至 {hour:02d}:59"
    activity = replay_activity_counts(same_hour_active)
    if activity is None:
        return f"前三天 {interval} 的设备资料不足，无法判断这个时段是否有 App 活动。"
    seen, active = activity
    if active == 0:
        return f"前三天 {interval} 有 {seen} 天设备记录，这 {seen} 天均未记录到 App 活动。"
    fact = f"前三天 {interval} 有 {seen} 天设备记录，其中 {active} 天记录到 App 活动。"
    counts = same_hour_context_counts if isinstance(same_hour_context_counts, dict) else {}
    named = {label: counts[key] for key, label in _DEVICE_CONTEXT_LABELS.items()
             if type(counts.get(key)) is int and counts[key] > 0}
    if not named:
        return fact
    highest = max(named.values())
    leaders = [name for name, count in named.items() if count == highest]
    qualifier = "并列最多" if len(leaders) > 1 else "最多"
    return fact + f"在能识别的 App 类别中，这个时段合计记录{qualifier}的是{'、'.join(leaders)}。"


def with_phone_use_habit_fact(inputs: dict, same_hour_context_counts: dict | None) -> dict:
    """Add the same replay fact to a live free-hour observation or its archived V3 counterpart."""
    habit = inputs["day1_3_habit"]
    fact = phone_use_habit_fact(inputs["hour"], habit.get("same_hour_active"), same_hour_context_counts)
    return {**inputs, "day1_3_habit": {**habit, "device_history_fact": fact}}


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
    hourly_intention_mode: str = "legacy",
    available_opportunities: list[dict] | None = None,
    current_intention: dict | None = None,
    goal_review_due: bool = True,
    max_defer_hours: int = 24,
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
    return _with_plan_opportunities(
        packet, hourly_intention_mode, available_opportunities, current_intention,
        goal_review_due, max_defer_hours, recent_task_episodes,
    )


def _with_plan_opportunities(
    base: dict, mode: str, opportunities: list[dict] | None, goal: dict | None,
    review_due: bool, max_defer_hours: int, recent_task_episodes: Any,
) -> dict:
    if mode == "legacy":
        return base
    if mode != "opportunity_v1":
        raise ValueError(f"unsupported hourly_intention_mode: {mode}")
    day, tick = base["simulation_day"], base["hour"] * 3600
    observation = intention_observation(
        opportunities, goal, review_due, monotonic_sim_hour(day, tick), max_defer_hours,
    )
    families = {o["task_family"] for o in observation["available_opportunities"]}
    if observation["current_intention"]:
        families.add(observation["current_intention"]["task_family"])
    episodes = recent_task_episodes if isinstance(recent_task_episodes, list) else []
    related = compact_recent_episodes(
        [row for row in episodes if isinstance(row, dict) and row.get("task_family") in families],
        simulation_day=day, tick_seconds=tick,
    )
    # Include older task-specific evidence without showing a recent experience twice.
    recent = base["recent_task_episodes"]
    packet = {
        **base, **observation,
        "recent_task_episodes": [row for row in related if row not in recent] + recent,
        "related_task_episode_ids": [row["episode_id"] for row in related if row.get("episode_id")],
    }
    _assert_no_forbidden_evidence(packet)
    return packet


def phone_use_observation(needs_packet: dict, plan_observation: dict, *, version: str = DEFAULT_PHONE_USE_NEEDS_VERSION) -> dict:
    """Present the clock, actual same-hour history and preceding simulated activities before any menu."""
    if has_actionable_target(plan_observation):
        raise ValueError("phone-use decision requires an hour without an actionable task")
    context = {"task_opportunity": "none_actionable"}
    goal = plan_observation.get("current_intention") or {}
    review = goal.get("next_review_at_sim_hour")
    if not plan_observation["goal_review_due"] and type(review) is int:
        context.update(next_review_at_sim_hour=review,
                       hours_until_review=review - plan_observation["monotonic_sim_hour"])
    habit = needs_packet["day1_3_habit"]
    if version == PHONE_USE_NEEDS_V5 and any(
        type(day) is not int or not 1 <= day <= 3 for day in habit.get("replay_days", [])
    ):
        raise ValueError("V5 phone-use history may only contain replay days 1..3")
    inputs = {**needs_packet, "phone_use_context": context,
              "day1_3_habit": {k: habit[k] for k in ("replay_days", "same_hour_active") if k in habit}}
    if version == PHONE_USE_NEEDS_V3:
        return inputs
    if version not in (PHONE_USE_NEEDS_VERSION, PHONE_USE_NEEDS_V5):
        raise ValueError("unsupported free-hour phone-use version")
    return with_phone_use_habit_fact(inputs, habit.get("same_hour_context_counts"))


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
    hourly_intention_mode: str = "legacy",
    phone_use_needs_version: str = DEFAULT_PHONE_USE_NEEDS_VERSION,
    paired_environment_seed: int | None = None,
    available_opportunities: list[dict] | None = None,
    current_intention: dict | None = None,
    goal_review_due: bool = True,
    max_defer_hours: int = 24,
) -> AppEntryRolloutResult:
    if llm is None:
        raise ValueError("Day 4-7 app-entry rollout requires an LLM client")
    if not isinstance(day4_snapshot, dict) or not day4_snapshot:
        raise ValueError("Day 4 replay snapshot is required before LLM rollout")
    talkingdata_day = simulation_day_to_talkingdata_day(int(simulation_day))
    if talkingdata_day < 4 or talkingdata_day > 7:
        raise ValueError("LLM app-entry rollout only supports TalkingData days 4..7")
    hour = (
        monotonic_sim_hour(simulation_day, tick_seconds) % 24
        if hourly_intention_mode == "opportunity_v1"
        else int(round(float(tick_seconds))) // 3600 % 24
    )
    if plan_prompt_version == CALIBRATED_PLAN_VERSION:
        intensity_profile = build_calibrated_intensity_profile(habit_memory, hour=hour)
    else:
        intensity_profile = build_rollout_intensity_profile(
            habit_memory, hour=hour, absolute_cap=int(absolute_exposure_cap)
        )
    needs_packet = build_rollout_input_packet(
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
    input_packet = _with_plan_opportunities(
        needs_packet, hourly_intention_mode, available_opportunities, current_intention,
        goal_review_due, max_defer_hours, recent_task_episodes,
    )
    free_hour = (hourly_intention_mode == "opportunity_v1" and plan_prompt_version == RESIDENT_DECISION_PLAN_VERSION
                 and not has_actionable_target(input_packet))
    if free_hour:
        needs_packet = phone_use_observation(needs_packet, input_packet, version=phone_use_needs_version)
        needs_prompt_version = phone_use_needs_version

    failure_identity = f"agent_id={int(agent_id)}, "
    if hourly_intention_mode == "legacy":
        failure_identity += f"device_id={device_id}, "
    try:
        needs = await DigitalNeedsBlock().forward(
            llm=llm,
            input_payload=needs_packet,
            prompt_version=str(needs_prompt_version),
            timeout=int(timeout),
            retries=int(retries),
            json_attempts=int(json_attempts),
        )
    except ValueError as exc:
        raise ValueError(
            "Day 4-7 DigitalNeedsBlock failed for "
            f"{failure_identity}"
            f"talkingdata_day={talkingdata_day}, hour={hour}: {exc}"
        ) from exc
    if free_hour and phone_use_needs_version == PHONE_USE_NEEDS_V5:
        resolution = resolve_phone_use(
            recommendation=needs.phone_use_decision, same_hour_active=needs_packet["day1_3_habit"]["same_hour_active"],
            agent_id=agent_id, talkingdata_day=talkingdata_day, hour=hour, paired_environment_seed=paired_environment_seed,
        )
        needs.phone_use_resolution = resolution
        needs.phone_use_decision = resolution["final_choice"]
        trace_record("phone_use_resolution", module="app_needs", resolution=resolution)
    # Archived policies reuse their historical summaries when advancing a legacy trajectory.
    needs.legacy_tiebreak = hourly_intention_mode == "legacy" or plan_prompt_version == CALIBRATED_PLAN_VERSION
    candidate_contexts = build_rollout_app_context_candidates(
        habit_memory=habit_memory,
        hour=hour,
        need_pressures=needs.need_pressures,
        need_context_mapping=DIGITAL_NEED_TO_APP_CONTEXTS,
        top_k=int(top_k),
        allow_empty=hourly_intention_mode == "opportunity_v1",
        actionable_only=hourly_intention_mode == "opportunity_v1" and plan_prompt_version != CALIBRATED_PLAN_VERSION,
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
    except HourlyIntentionPlanError:
        raise
    except ValueError as exc:
        raise ValueError(
            "Day 4-7 DigitalAppEntryPlanBlock failed for "
            f"{failure_identity}"
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
        "candidate_app_contexts": dict(plan.audit.get("candidate_app_contexts", candidate_contexts)),
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
    if hourly_intention_mode == "opportunity_v1":
        rollout_audit["intention_validation"] = {
            key: plan.audit.get(key) for key in (
                "raw_choice", "repaired_choice", "repair_changed_choice", "accepted_choice",
                "parse_status", "repair_requests", "technical_failure", "rejection_reason",
            )
        }
    handling_goal = plan.intent is not None and plan.intent["kind"] in {"engage_goal", "continue_goal"}
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
        existing_task_pending=bool(existing_task_pending) or handling_goal,
    )
    return AppEntryRolloutResult(
        bundle=bundle,
        needs=needs,
        plan=plan,
        decision=decision,
        input_packet=input_packet,
    )
