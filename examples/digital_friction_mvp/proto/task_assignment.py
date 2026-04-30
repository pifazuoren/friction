from __future__ import annotations

import json
import os
from typing import Any

from .models import DigitalTask

TASK_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "task_family": "navigation_service_location",
        "friction_type": "information_overload",
        "need_type": "service_location",
        "difficulty": 0.58,
        "support_sensitivity": 0.70,
    },
    {
        "task_family": "account_login_verification",
        "friction_type": "verification",
        "need_type": "secure_access",
        "difficulty": 0.64,
        "support_sensitivity": 0.85,
    },
    {
        "task_family": "information_search_judgment",
        "friction_type": "information_overload",
        "need_type": "information_access",
        "difficulty": 0.56,
        "support_sensitivity": 0.62,
    },
    {
        "task_family": "profile_form_upload",
        "friction_type": "form_complexity",
        "need_type": "profile_management",
        "difficulty": 0.61,
        "support_sensitivity": 0.72,
    },
    {
        "task_family": "service_application_submission",
        "friction_type": "form_complexity",
        "need_type": "service_completion",
        "difficulty": 0.63,
        "support_sensitivity": 0.74,
    },
    {
        "task_family": "payment_risk_confirmation",
        "friction_type": "payment_risk_popup",
        "need_type": "daily_transaction",
        "difficulty": 0.67,
        "support_sensitivity": 0.78,
    },
)

_TASK_WINDOW_SECONDS: tuple[int, ...] = (
    9 * 60 * 60,
    14 * 60 * 60,
    19 * 60 * 60,
)
_TASK_WINDOW_TOLERANCE_SECONDS = 120


def clamp_score(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def task_pressure_from_env(task_template: dict[str, Any], env: dict[str, Any]) -> float:
    friction = float(env.get("friction_level", 0))
    malicious = float(env.get("malicious_friction_level", 0))
    complexity = float(env.get("complexity_level", 0))
    risk = float(env.get("risk_level", 0))
    accessibility = float(env.get("accessibility_level", 0))
    friction_type = str(task_template.get("friction_type", "verification"))
    if friction_type == "verification":
        raw = (friction + malicious) / 6.0
    elif friction_type == "form_complexity":
        raw = (friction + complexity) / 6.0
    elif friction_type == "payment_risk_popup":
        raw = (risk + malicious) / 6.0
    else:
        raw = (friction + complexity) / 6.0
    adjusted = float(task_template.get("difficulty", 0.5)) + (raw * 0.24) - (
        accessibility * 0.03
    )
    return clamp_score(adjusted)


def _resolve_schedule_seed() -> int:
    raw_pair_seed = str(os.getenv("PARALLEL_PAIR_SEED", "")).strip()
    if raw_pair_seed:
        try:
            return int(raw_pair_seed)
        except ValueError:
            pass
    try:
        return int(str(os.getenv("EXP_SEED", "101")).strip())
    except ValueError:
        return 101


def _window_index_for_tick(tick_seconds: float) -> int | None:
    normalized_tick = int(round(float(tick_seconds)))
    best_match: tuple[int, int] | None = None
    for index, window_tick in enumerate(_TASK_WINDOW_SECONDS):
        delta = abs(normalized_tick - window_tick)
        if delta > _TASK_WINDOW_TOLERANCE_SECONDS:
            continue
        if best_match is None or delta < best_match[1]:
            best_match = (index, delta)
    return None if best_match is None else best_match[0]


def is_task_window_tick(tick_seconds: float) -> bool:
    return _window_index_for_tick(tick_seconds) is not None


def _scheduled_template_for_window(
    *,
    agent_id: int,
    day: int,
    window_index: int,
) -> dict[str, Any]:
    rotation = (_resolve_schedule_seed() + int(agent_id) + int(day)) % len(TASK_LIBRARY)
    ordered_templates = TASK_LIBRARY[rotation:] + TASK_LIBRARY[:rotation]
    return ordered_templates[int(window_index)]


def select_task_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
) -> DigitalTask | None:
    window_index = _window_index_for_tick(tick_seconds)
    if window_index is None:
        return None
    template = _scheduled_template_for_window(
        agent_id=int(agent_id),
        day=int(day),
        window_index=int(window_index),
    )
    assigned_tick = int(day * 100000 + int(round(float(tick_seconds))))
    task_id = f"{template['task_family']}_{agent_id}_{day}_{window_index}"
    return DigitalTask(
        task_id=task_id,
        task_family=template["task_family"],
        friction_type=template["friction_type"],
        difficulty=task_pressure_from_env(template, env),
        need_type=template["need_type"],
        support_sensitivity=float(template["support_sensitivity"]),
        assigned_tick=assigned_tick,
        defer_count=0,
    )


def encode_task(task: DigitalTask | None) -> str:
    if task is None:
        return ""
    return json.dumps(task.to_dict(), ensure_ascii=False)


def decode_task(raw_value: Any) -> DigitalTask | None:
    if isinstance(raw_value, DigitalTask):
        return raw_value
    if raw_value in (None, "", "null"):
        return None
    if isinstance(raw_value, dict):
        return DigitalTask.from_dict(raw_value)
    if not isinstance(raw_value, str):
        return None
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return DigitalTask.from_dict(payload)
