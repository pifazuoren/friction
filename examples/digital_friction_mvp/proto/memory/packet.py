from __future__ import annotations

import math
import re
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _compact_status_text(value: Any, default: str = "unknown") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or default


def _compact_status_note(
    value: Any,
    *,
    default: str = "unknown",
    max_chars: int = 160,
) -> str:
    text = _compact_status_text(value, default=default)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text or default


def _known_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def is_prior_episode(row: dict[str, Any], simulation_day: int | None, tick_seconds: float | None) -> bool:
    """Compare known timestamps only; undated legacy rows retain their append order."""
    if simulation_day is None or row.get("day") is None:
        return True
    day = _known_number(row["day"])
    if day is None:
        return False
    if day != simulation_day:
        return day < simulation_day
    if tick_seconds is None:
        return True
    if row.get("tick_seconds") is not None:
        tick = _known_number(row["tick_seconds"])
        return tick is not None and tick < tick_seconds
    if row.get("hour") is not None:
        hour = _known_number(row["hour"])
        return hour is not None and hour < int(tick_seconds // 3600) % 24
    return False


def compact_recent_episodes(
    episodes: Any, *, limit: int = 5, simulation_day: int | None = None,
    tick_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Keep the most recent completed attempts in their original append order."""
    if not isinstance(episodes, list):
        return []
    fields = (
        "episode_id", "task_id", "day", "tick_seconds", "hour", "task_family",
        "requested_strategy_type", "strategy_type", "outcome_type", "avoid_reason",
        "help_used", "help_source", "support_request_id", "support_delivery_status", "support_mode",
        "support_style", "autonomy_preservation", "proxy_completion_level",
        "instruction_quality", "negative_feedback", "event_level_uncontrollability",
        "helplessness_delta", "support_quality", "feedback_valence",
    )
    compact = []
    if limit <= 0:
        return []
    for row in reversed(episodes):
        if not isinstance(row, dict) or not is_prior_episode(row, simulation_day, tick_seconds):
            continue
        record = {}
        for field in fields:
            value = row.get(field)
            # Historical app packets used short keys, older stored episodes the full names.
            if field == "strategy_type" and value is None:
                value = row.get("strategy")
            if field == "outcome_type" and value is None:
                value = row.get("outcome")
            if field == "outcome_type" and value in ("positive", "negative", "neutral"):
                record["feedback_valence"] = value
            elif isinstance(value, str) and value:
                record[field] = value[:160]
            elif isinstance(value, (bool, int, float)):
                record[field] = value
        if record:
            compact.append(record)
            if len(compact) == limit:
                break
    return list(reversed(compact))


def support_snapshot_for_task(
    help_effect_memory: Any,
    task_family: str,
) -> dict[str, Any]:
    if not isinstance(help_effect_memory, dict):
        return {}
    by_task_family = help_effect_memory.get("by_task_family", {})
    by_source = help_effect_memory.get("by_source", {})
    return {
        "overall": (
            help_effect_memory.get("overall", {})
            if isinstance(help_effect_memory.get("overall"), dict)
            else {}
        ),
        "task_family": (
            by_task_family.get(task_family, {})
            if isinstance(by_task_family, dict)
            else {}
        ),
        "source": (
            by_source.get("generic", {})
            if isinstance(by_source, dict)
            else {}
        ),
        "support_response_audit": (
            help_effect_memory.get("support_response_audit", {})
            if isinstance(help_effect_memory.get("support_response_audit"), dict)
            else {}
        ),
    }


def extract_event_log_episodes(
    event_log: Any, *, task_family: str | None = None, limit: int = 5,
    simulation_day: int | None = None, tick_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Recover documented fields from completed legacy log events without inferring outcomes."""
    if not isinstance(event_log, list) or limit <= 0:
        return []
    tail = []
    for item in reversed(event_log):
        if not isinstance(item, dict):
            continue
        decision = item.get("decision")
        if not isinstance(decision, dict):
            decision = {}
        family = item.get("scenario") or decision.get("task_family")
        if not family or (task_family is not None and family != task_family):
            continue
        row = {
            **decision, "task_id": item.get("attempt_uid") or decision.get("task_id"),
            "task_family": family, "day": item.get("day"),
            "tick_seconds": item.get("t", decision.get("tick_seconds")),
        }
        if row["tick_seconds"] is not None:
            tick = _known_number(row["tick_seconds"])
            if tick is None:
                continue
            row["tick_seconds"] = tick
            row["hour"] = int(tick // 3600) % 24
        if not is_prior_episode(row, simulation_day, tick_seconds):
            continue
        # A historical positive/negative tag alone cannot distinguish success with help from success alone.
        if item.get("outcome") in ("positive", "negative", "neutral"):
            row["feedback_valence"] = item["outcome"]
        detail = decision.get("outcome_type") or decision.get("primary_reason")
        if detail in ("success_self", "success_with_help", "failure_after_attempt",
                      "failure_even_with_help", "abandon_midway", "avoid_without_attempt"):
            row["outcome_type"] = detail
        else:
            row.pop("outcome_type", None)
            row.pop("outcome", None)
        tail.append(row)
        if len(tail) >= limit:
            break
    return compact_recent_episodes(list(reversed(tail)), limit=limit)


def extract_same_task_event_tail(*, task_family: str, event_log: Any, limit: int = 3) -> list[dict[str, Any]]:
    return extract_event_log_episodes(event_log, task_family=task_family, limit=limit)


def extract_cross_task_event_tail(
    *,
    task_family: str,
    event_log: Any,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not isinstance(event_log, list):
        return []
    tail: list[dict[str, Any]] = []
    for item in reversed(event_log):
        if not isinstance(item, dict):
            continue
        decision = item.get("decision", {})
        if not isinstance(decision, dict):
            decision = {}
        current_task_family = str(
            item.get("scenario") or decision.get("task_family") or ""
        ).strip()
        if not current_task_family or current_task_family == str(task_family):
            continue
        tail.append(
            {
                "task_family": current_task_family,
                "day": _safe_int(item.get("day"), 0),
                "outcome_type": str(decision.get("primary_reason", "")).strip(),
                "avoid_reason": str(decision.get("avoid_reason", "")).strip(),
                "support_mode": str(decision.get("support_mode", "")).strip(),
                "event_level_uncontrollability": _safe_int(
                    decision.get("event_level_uncontrollability"),
                    0,
                ),
            }
        )
        if len(tail) >= int(limit):
            break
    return list(reversed(tail))


def build_relevant_mastery_summary(
    task_relevant_memory_packet: dict[str, Any],
) -> dict[str, Any]:
    return {
        "same_task_controllable_success_memory": round(
            _safe_float(
                task_relevant_memory_packet.get(
                    "same_task_controllable_success_memory",
                    0.0,
                )
            ),
            4,
        ),
        "has_controllable_success_evidence": bool(
            task_relevant_memory_packet.get("has_controllable_success_evidence", False)
        ),
        "help_success_rate_same_task": round(
            _safe_float(
                task_relevant_memory_packet.get("help_success_rate_same_task", 0.5)
            ),
            4,
        ),
        "recent_same_task_outcomes_tail": list(
            task_relevant_memory_packet.get("recent_same_task_outcomes_tail", [])
        ),
        "same_task_attribution_summary": str(
            task_relevant_memory_packet.get("same_task_attribution_summary", "")
        ).strip(),
    }


def build_task_relevant_memory_packet(
    *,
    task: Any,
    task_domain_memory: Any,
    help_effect_memory: Any,
    recent_episode_summary: Any,
    event_log: Any,
    recent_episode_buffer: Any = None,
    simulation_day: int | None = None,
    tick_seconds: float | None = None,
) -> dict[str, Any]:
    task_state = {}
    if isinstance(task_domain_memory, dict):
        raw_state = task_domain_memory.get(task.task_family)
        if isinstance(raw_state, dict):
            task_state = raw_state
    help_snapshot = support_snapshot_for_task(help_effect_memory, task.task_family)
    family_help = (
        help_snapshot.get("task_family", {})
        if isinstance(help_snapshot.get("task_family"), dict)
        else {}
    )
    recent = recent_episode_summary if isinstance(recent_episode_summary, dict) else {}
    event_tail = extract_event_log_episodes(
        event_log, task_family=task.task_family, limit=3, simulation_day=simulation_day,
        tick_seconds=tick_seconds,
    )
    recent_events = compact_recent_episodes(
        recent_episode_buffer, simulation_day=simulation_day, tick_seconds=tick_seconds,
    ) or extract_event_log_episodes(event_log, simulation_day=simulation_day, tick_seconds=tick_seconds)
    controllable_success_memory = _safe_float(
        task_state.get("controllable_success_memory", 0.0)
    )
    return {
        "task_family": str(task.task_family),
        "same_task_attempt_count": _safe_int(task_state.get("attempt_count"), 0),
        "same_task_success_count": _safe_int(task_state.get("success_count"), 0),
        "same_task_failure_count": _safe_int(task_state.get("failure_count"), 0),
        "same_task_avoid_count": _safe_int(task_state.get("avoid_count"), 0),
        "same_task_failure_streak": _safe_int(
            task_state.get("same_task_failure_streak"),
            0,
        ),
        "same_task_recent_negative_feedback_ema": round(
            _safe_float(task_state.get("recent_negative_feedback_ema", 0.0)),
            4,
        ),
        "same_task_last_outcome": str(task_state.get("last_outcome", "")).strip(),
        "same_task_task_self_efficacy": round(
            _safe_float(task_state.get("task_self_efficacy", 50.0)),
            4,
        ),
        "same_task_controllable_success_memory": round(
            controllable_success_memory,
            4,
        ),
        "same_task_dominant_attribution_stability": str(
            task_state.get("dominant_attribution_stability", "mixed")
        ),
        "same_task_dominant_attribution_scope": str(
            task_state.get("dominant_attribution_scope", "task_specific")
        ),
        "same_task_recent_stable_attribution_ratio": round(
            _safe_float(task_state.get("recent_stable_attribution_ratio", 0.0)),
            4,
        ),
        "same_task_recent_scope_amplitude_ema": round(
            _safe_float(
                task_state.get("recent_scope_amplitude_ema", 0.0)
            ),
            4,
        ),
        "same_task_attribution_summary": str(
            task_state.get("attribution_summary", "")
        ).strip(),
        "same_task_help_attempt_count": _safe_int(
            family_help.get("help_attempt_count"),
            0,
        ),
        "same_task_help_success_count": _safe_int(
            family_help.get("help_success_count"),
            0,
        ),
        "same_task_help_failure_count": _safe_int(
            family_help.get("help_failure_count"),
            0,
        ),
        "help_success_rate_same_task": round(
            _safe_float(family_help.get("help_success_rate_smoothed", 0.5)),
            4,
        ),
        "recent_negative_feedback_ratio": round(
            _safe_float(recent.get("recent_negative_feedback_ratio", 0.0)),
            4,
        ),
        "recent_avoid_ratio": round(
            _safe_float(recent.get("recent_avoid_ratio", 0.0)),
            4,
        ),
        "recent_help_seek_ratio": round(
            _safe_float(recent.get("recent_help_seek_ratio", 0.0)),
            4,
        ),
        "recent_same_task_failure_count": _safe_int(
            recent.get("recent_same_task_failure_count"),
            0,
        ),
        "recent_failure_pressure": round(
            _safe_float(recent.get("recent_failure_pressure", 0.0)),
            4,
        ),
        "recent_same_task_outcomes_tail": [
            item["outcome_type"] for item in event_tail if item.get("outcome_type")
        ],
        "recent_same_task_events_tail": event_tail,
        "recent_task_episodes": recent_events,
        "has_controllable_success_evidence": controllable_success_memory > 0.05,
    }


def compact_support_context(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "same_task_attempt_count": _safe_int(payload.get("same_task_attempt_count"), 0),
        "same_task_failure_count": _safe_int(payload.get("same_task_failure_count"), 0),
        "same_task_failure_streak": _safe_int(
            payload.get("same_task_failure_streak"),
            0,
        ),
        "same_task_last_outcome": _compact_status_text(
            payload.get("same_task_last_outcome"),
            default="",
        ),
        "help_success_rate_same_task": _safe_float(
            payload.get("help_success_rate_same_task"),
            0.5,
        ),
        "same_task_attribution_summary": _compact_status_note(
            payload.get("same_task_attribution_summary"),
            default="",
            max_chars=220,
        ),
        "recent_same_task_outcomes_tail": payload.get(
            "recent_same_task_outcomes_tail",
            [],
        ),
    }
