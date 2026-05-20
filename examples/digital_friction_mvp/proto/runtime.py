from __future__ import annotations

from typing import Any

from .models import DigitalTask
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
    confidence_threshold: float = 0.70,
    selected_intention_override: str | None = None,
    rerank_audit_payload: dict[str, Any] | None = None,
    rerank_top_k: int = 5,
) -> tuple[DigitalTask | None, dict[str, Any], bool, MobileEntryDecision | None]:
    if existing_task is not None:
        return existing_task, {}, False, None
    normalized_mode = str(entry_mode or "fixed_assignment").strip().lower()
    if normalized_mode == "fixed_assignment":
        task, updates, seeded = assign_task_if_missing(
            existing_task=None,
            agent_id=int(agent_id),
            day=int(day),
            tick_seconds=float(tick_seconds),
            env=env,
        )
        return task, updates, seeded, None
    decision = evaluate_mobile_entry_for_agent(
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        env=env,
        stable_profile=stable_profile,
        entry_mode=normalized_mode,
        calibration_path=calibration_path,
        mapping_path=mapping_path,
        confidence_threshold=float(confidence_threshold),
        llm_shadow_enabled=normalized_mode == "mobile_intention_llm_shadow",
        selected_intention_override=selected_intention_override,
        rerank_audit_payload=rerank_audit_payload,
        rerank_top_k=int(rerank_top_k),
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
