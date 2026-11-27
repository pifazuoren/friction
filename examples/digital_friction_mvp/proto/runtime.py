from __future__ import annotations

from typing import Any

from .models import DigitalTask
from .app_entry.bundle_loader import (
    get_replay_source,
    simulation_day_to_talkingdata_day,
)
from .app_entry.replay import evaluate_replay_bundle_for_agent
from .app_entry.task_templates import _build_task_from_template
from .app_entry.types import _hour_for_tick
from .task_assignment import (
    MobileEntryDecision,
    encode_task,
    evaluate_mobile_entry_for_agent,
    select_task_for_agent,
)


def build_task_surface_updates(
    *,
    task: DigitalTask,
    day: int,
    tick_seconds: float,
) -> dict[str, Any]:
    return {
        "proto_assigned_task_json": encode_task(task),
        "digital_todo_pending": 1,
        "digital_todo_active_task_id": task.task_id,
        "digital_todo_active_day": int(day),
        "digital_todo_active_t": float(tick_seconds),
        "digital_task_hint": task.task_family,
        "digital_task_hint_need": task.need_type,
        "digital_task_hint_pending": 1,
    }


def clear_task_surface_updates() -> dict[str, Any]:
    return {
        "proto_assigned_task_json": "", "digital_todo_pending": 0,
        "digital_todo_active_task_id": "", "digital_todo_active_day": -1,
        "digital_todo_active_t": 0.0, "digital_task_hint": "",
        "digital_task_hint_need": "", "digital_task_hint_pending": 0,
    }


def scheduled_login_difficulty_delta(difficulty_arm: str | None, talkingdata_day: int) -> float:
    """Only the exposure days of the elevated arm receive a harder login."""
    return 0.20 if difficulty_arm == "elevated" and talkingdata_day in (4, 5, 6) else 0.0


def scheduled_login_for_day(
    *, hour: int, agent_id: int, day: int, tick_seconds: float, env: dict[str, Any],
    existing_task: DigitalTask | None, last_scheduled_day: int, difficulty_arm: str | None = None,
) -> DigitalTask | None:
    """Offer the first free slot after the scheduled hour; the two-arm study runs through day 7."""
    talkingdata_day = simulation_day_to_talkingdata_day(day)
    scheduled_days = (4, 5) if difficulty_arm is None else (4, 5, 6, 7)
    if (talkingdata_day not in scheduled_days or _hour_for_tick(tick_seconds) < hour
            or existing_task is not None or last_scheduled_day == day):
        return None
    task = _build_task_from_template(
        normalized_mode="scheduled_login", mapped_task_family="account_login_verification",
        agent_id=agent_id, day=day, tick_seconds=tick_seconds, env=env,
    )
    if task is not None and difficulty_arm is not None:
        task.difficulty = min(1.0, task.difficulty + scheduled_login_difficulty_delta(difficulty_arm, talkingdata_day))
    return task


def assign_task_if_missing(
    *,
    existing_task: DigitalTask | None,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
) -> tuple[DigitalTask | None, dict[str, Any], bool]:
    if existing_task is not None:
        return existing_task, {}, False
    task = select_task_for_agent(
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        env=env,
    )
    if task is None:
        return None, {}, False
    return (
        task,
        build_task_surface_updates(
            task=task,
            day=int(day),
            tick_seconds=float(tick_seconds),
        ),
        True,
    )


def assign_task_with_entry_decision(
    *,
    existing_task: DigitalTask | None,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    entry_mode: str,
    stable_profile: dict[str, Any] | None = None,
    calibration_path: str = "",
    mapping_path: str = "",
    app_context_prior_path: str = "",
    task_opportunity_mapping_path: str = "",
    confidence_threshold: float = 0.70,
    selected_intention_override: str | None = None,
    rerank_audit_payload: dict[str, Any] | None = None,
    rerank_top_k: int = 5,
    task_occurrence_gate_enabled: bool = False,
    task_occurrence_prior_path: str = "",
    task_occurrence_gate_multiplier: float = 1.0,
    replay_bundle_path: str = "",
    replay_device_path: str = "",
    replay_days: tuple[int, ...] | str = (1, 2, 3),
    replay_device_id: str = "",
    replay_selected_rank: int = 0,
) -> tuple[DigitalTask | None, dict[str, Any], bool, MobileEntryDecision | None]:
    normalized_mode = str(entry_mode or "fixed_assignment").strip().lower()
    if existing_task is not None and normalized_mode != "app_context_replay_bundle":
        return existing_task, {}, False, None
    if normalized_mode == "fixed_assignment":
        task, updates, seeded = assign_task_if_missing(
            existing_task=None,
            agent_id=int(agent_id),
            day=int(day),
            tick_seconds=float(tick_seconds),
            env=env,
        )
        return task, updates, seeded, None
    if normalized_mode == "app_context_replay_bundle":
        device_id = str(replay_device_id or "").strip()
        if not device_id:
            raise ValueError(
                "replay_device_id is required for app_context_replay_bundle"
            )
        source = get_replay_source(
            bundle_path=replay_bundle_path,
            device_mapping_path=replay_device_path,
            replay_days=replay_days,
        )
        hour = _hour_for_tick(float(tick_seconds))
        bundle = source.bundle_for_device(
            device_id=device_id,
            talkingdata_day=simulation_day_to_talkingdata_day(int(day)),
            hour=hour,
        )
        decision = evaluate_replay_bundle_for_agent(
            agent_id=int(agent_id),
            day=int(day),
            tick_seconds=float(tick_seconds),
            env=env,
            stable_profile=stable_profile,
            bundle=bundle,
            selected_rank=int(replay_selected_rank),
            bundle_hash=source.bundle_hash,
            device_mapping_hash=source.device_mapping_hash,
            task_opportunity_mapping_path=task_opportunity_mapping_path,
            task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
            task_occurrence_prior_path=task_occurrence_prior_path,
            task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
            existing_task_pending=existing_task is not None,
        )
        if existing_task is not None:
            return existing_task, {}, False, decision
        if decision.task is None:
            return None, {}, False, decision
        return (
            decision.task,
            build_task_surface_updates(
                task=decision.task,
                day=int(day),
                tick_seconds=float(tick_seconds),
            ),
            True,
            decision,
        )
    decision = evaluate_mobile_entry_for_agent(
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        env=env,
        stable_profile=stable_profile,
        entry_mode=normalized_mode,
        calibration_path=(
            app_context_prior_path
            if normalized_mode.startswith("app_context")
            else calibration_path
        ),
        mapping_path=(
            task_opportunity_mapping_path
            if normalized_mode.startswith("app_context")
            else mapping_path
        ),
        confidence_threshold=float(confidence_threshold),
        llm_shadow_enabled=normalized_mode == "mobile_intention_llm_shadow",
        selected_intention_override=selected_intention_override,
        rerank_audit_payload=rerank_audit_payload,
        rerank_top_k=int(rerank_top_k),
        task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
        task_occurrence_prior_path=task_occurrence_prior_path,
        task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
    )
    if decision.task is None:
        return None, {}, False, decision
    return (
        decision.task,
        build_task_surface_updates(
            task=decision.task,
            day=int(day),
            tick_seconds=float(tick_seconds),
        ),
        True,
        decision,
    )


def build_stage_transition_updates(
    *,
    current_stage_key: str,
    previous_stage_key: str,
    helplessness: float,
) -> tuple[dict[str, Any], bool]:
    normalized_current = str(current_stage_key or "").strip()
    normalized_previous = str(previous_stage_key or "").strip()
    if not normalized_current or normalized_current == normalized_previous:
        return {}, False
    return (
        {
            "proto_active_stage_key": normalized_current,
            "event_log": [],
            "proto_stage_attempt_rows_json": "[]",
            "proto_stage_start_helplessness": float(helplessness),
            "proto_stage_daily_reflection_count": 0,
        },
        True,
    )
