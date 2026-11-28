"""Ask the resident when to revisit a particular, already settled, unfinished task."""

from __future__ import annotations

import json

from .app_entry.intention_contract import parse_compact_reply
from .llm_trace import LLMQueryTrace, LLMRunInterrupted, TraceWriteError


LEGACY_RETRY_REVIEW_VERSION = "retry_review_v1"
RETRY_REVIEW_VERSION = "retry_review_v2"
RETRY_REVIEW_VERSIONS = frozenset({LEGACY_RETRY_REVIEW_VERSION, RETRY_REVIEW_VERSION})
_SYSTEM = (
    "你是刚刚遇到这次办事经历的居民。根据自己此刻的情况、办理结果、"
    "已经为这件事作过多少次决定和操作、事情是否有已知截止时间，"
    "决定哪一天几点再考虑这件事。届时仍可重新选择办不办。"
    "从 earliest 至 latest 之间任选一个整点，含两端；可以很快再看，也可以隔久一点。"
    "day 从第1天计，hour 用0至23的整数。不要编造截止时间或外部提醒。"
    "只输出一个完整 JSON 对象，以左花括号开头、右花括号结尾。"
    "对象有两个字段，review_day 填选定的日期数字，review_hour 填选定的整点数字，均为整数。"
)


def _clock(sim_hour: int) -> dict:
    day, hour = divmod(sim_hour, 24)
    return {"day": day + 1, "hour": hour}


def parse_review_time(raw, earliest: int, latest: int, *, version: str = RETRY_REVIEW_VERSION) -> tuple[dict, int] | None:
    if version not in RETRY_REVIEW_VERSIONS:
        raise ValueError(f"Unsupported retry review version: {version}")
    if not isinstance(raw, str):
        return None
    content = raw.strip()
    # GLM can prepend a dangling quote and colon to an otherwise complete object.
    if version == RETRY_REVIEW_VERSION and content.startswith('":'):
        content = content[2:].lstrip()
        if not content.startswith("{"):
            return None
    payload = parse_compact_reply(content)
    if payload is None or payload.keys() != {"review_day", "review_hour"}:
        return None
    day, hour = payload["review_day"], payload["review_hour"]
    if type(day) is not int or type(hour) is not int or day < 1 or not 0 <= hour < 24:
        return None
    sim_hour = (day - 1) * 24 + hour
    return (payload, sim_hour) if earliest <= sim_hour <= latest else None


async def choose_retry_review(*, llm, goal: dict, episode: dict, resident: dict,
                              sim_hour: int, max_defer_hours: int, timeout: int) -> dict:
    """Use the completed decision's factual outcome. A missing answer schedules nothing."""
    result = {"version": RETRY_REVIEW_VERSION, "status": "not_needed", "next_review_at_sim_hour": None}
    if goal["status"] == "completed":
        return result
    if goal["status"] != "needs_review" or goal["last_episode_ids"][-1:] != [episode["episode_id"]]:
        raise ValueError("retry review requires the goal's latest settled, unfinished episode")
    earliest = sim_hour + 1
    latest = sim_hour + max_defer_hours
    deadline = goal["known_deadline_sim_hour"]
    if deadline is not None:
        latest = min(latest, deadline)
    if earliest > latest:
        return {**result, "status": "no_future_hour"}
    if llm is None:
        return {**result, "status": "missing_llm"}
    packet = {
        "schema_version": RETRY_REVIEW_VERSION,
        "now": _clock(sim_hour), "earliest": _clock(earliest), "latest": _clock(latest),
        "resident": resident,
        "task": {
            "goal_id": goal["goal_id"], "task_id": goal["linked_task_id"],
            "description": goal["visible_description"], "known_deadline_sim_hour": deadline,
            "decision_count": goal["decision_index"], "operation_count": goal["operation_attempt_count"],
        },
        "outcome": {
            **{key: episode[key] for key in ("episode_id", "outcome_type", "strategy_type", "help_used")},
            "operation_started": episode["outcome_type"] != "avoid_without_attempt",
            **{key: episode[key] for key in ("requested_support_style", "support_style", "proxy_completion_level")
               if episode.get(key) is not None},
        },
    }
    dialog = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": json.dumps(packet, ensure_ascii=False)}]
    trace = LLMQueryTrace("retry_review", llm)
    try:
        raw = await trace.request("initial", 1, dialog=dialog, temperature=0.2, max_tokens=80, timeout=timeout, retries=1)
    except (LLMRunInterrupted, TraceWriteError):
        raise
    except Exception:
        return {**result, "status": "request_error"}
    choice = parse_review_time(raw, earliest, latest)
    if choice is None:
        trace.parsed("invalid_response")
        return {**result, "status": "invalid_response"}
    payload, next_hour = choice
    trace.parsed("ok", payload)
    return {**result, "status": "scheduled", "next_review_at_sim_hour": next_hour}
