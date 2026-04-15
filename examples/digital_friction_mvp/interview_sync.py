from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from proto.models import FinalInterviewResult, StageInterviewResult

_LAST_INTERVIEW_SYNC_ROWID: int | None = None
_STAGE_INTERVIEW_PREFIX = "[PROTO_STAGE_INTERVIEW_V1]"
_FINAL_INTERVIEW_PREFIX = "[PROTO_FINAL_INTERVIEW_V1]"
_STAGE_INTERVIEW_PATTERN = re.compile(
    r"^\[PROTO_STAGE_INTERVIEW_V1\]\[stage=(?P<stage_name>[^\]]+)\]\[index=(?P<stage_index>\d+)\]"
)


def _clean_intention(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _extract_json_object(raw_text: Any) -> dict[str, Any] | None:
    text = _clean_intention(raw_text)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


def build_stage_interview_message(stage_name: str, stage_index: int) -> str:
    return (
        f"{_STAGE_INTERVIEW_PREFIX}[stage={stage_name}][index={int(stage_index)}] "
        "请你只返回一段 JSON，概括这一阶段里你最难的地方、帮助是否有用，以及接下来更想自己试、求助还是回避。"
    )


def build_final_interview_message() -> str:
    return (
        f"{_FINAL_INTERVIEW_PREFIX} "
        "请你只返回一段 JSON，总结整个实验里的变化轨迹、主要障碍、帮助体验，以及未来面对数字任务时的总体倾向。"
    )


def _parse_stage_interview_payload(
    payload: dict[str, Any] | None,
    *,
    stage_name: str,
    stage_index: int,
    raw_answer: str,
) -> StageInterviewResult:
    payload = payload or {}
    main_difficulty_source = _clean_intention(payload.get("main_difficulty_source"))
    support_comment = _clean_intention(payload.get("support_comment"))
    future_intention = _clean_intention(payload.get("future_intention"))
    short_quote = _clean_intention(payload.get("short_quote"))[:120]
    confidence = _clamp(
        _safe_float(payload.get("judge_confidence", payload.get("confidence", 0.0)), 0.0),
        0.0,
        1.0,
    )
    valid = (
        main_difficulty_source
        in {
            "verification_friction",
            "form_complexity",
            "risk_concern",
            "info_overload",
            "low_control",
            "mixed",
        }
        and support_comment in {"helpful", "limited", "ineffective", "not_used"}
        and future_intention in {"try_self", "seek_help", "avoid", "mixed"}
        and bool(short_quote)
    )
    if not valid:
        return StageInterviewResult(
            stage_name=stage_name,
            stage_index=int(stage_index),
            main_difficulty_source="",
            support_comment="",
            future_intention="",
            short_quote="",
            confidence=0.0,
            source="stored_raw",
            status="parse_failed",
            raw_answer=_clean_intention(raw_answer)[:600],
        )
    return StageInterviewResult(
        stage_name=stage_name,
        stage_index=int(stage_index),
        main_difficulty_source=main_difficulty_source,
        support_comment=support_comment,
        future_intention=future_intention,
        short_quote=short_quote,
        confidence=confidence,
        source=_clean_intention(payload.get("source")) or "llm",
        status=_clean_intention(payload.get("status")) or "ok",
        raw_answer="",
    )


def _parse_final_interview_payload(
    payload: dict[str, Any] | None,
    *,
    raw_answer: str,
) -> FinalInterviewResult:
    payload = payload or {}
    overall_trajectory = _clean_intention(payload.get("overall_trajectory"))
    main_barrier = _clean_intention(payload.get("main_barrier"))
    support_takeaway = _clean_intention(payload.get("support_takeaway"))
    future_orientation = _clean_intention(payload.get("future_orientation"))
    short_quote = _clean_intention(payload.get("short_quote"))[:120]
    confidence = _clamp(
        _safe_float(payload.get("judge_confidence", payload.get("confidence", 0.0)), 0.0),
        0.0,
        1.0,
    )
    valid = (
        overall_trajectory in {"improved", "worsened", "mixed", "stable"}
        and main_barrier
        in {
            "verification_friction",
            "form_complexity",
            "risk_concern",
            "info_overload",
            "low_control",
            "mixed",
        }
        and support_takeaway in {"helpful", "limited", "ineffective", "not_needed"}
        and future_orientation in {"try_self", "seek_help", "avoid", "mixed"}
        and bool(short_quote)
    )
    if not valid:
        return FinalInterviewResult(
            overall_trajectory="",
            main_barrier="",
            support_takeaway="",
            future_orientation="",
            short_quote="",
            confidence=0.0,
            source="stored_raw",
            status="parse_failed",
            raw_answer=_clean_intention(raw_answer)[:600],
        )
    return FinalInterviewResult(
        overall_trajectory=overall_trajectory,
        main_barrier=main_barrier,
        support_takeaway=support_takeaway,
        future_orientation=future_orientation,
        short_quote=short_quote,
        confidence=confidence,
        source=_clean_intention(payload.get("source")) or "llm",
        status=_clean_intention(payload.get("status")) or "ok",
        raw_answer="",
    )


async def sync_interview_feedback(simulation: Any):
    global _LAST_INTERVIEW_SYNC_ROWID
    db_writer = getattr(simulation, "_database_writer", None)
    if db_writer is None:
        return
    sqlite_path = getattr(db_writer, "_sqlite_path", None)
    if sqlite_path is None:
        return
    table_name = f"as_{db_writer.exp_id.replace('-', '_')}_agent_dialog"
    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()
    table_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if not table_exists:
        conn.close()
        return
    if _LAST_INTERVIEW_SYNC_ROWID is None:
        rows = cur.execute(
            f"SELECT rowid, id, day, t, speaker, content FROM {table_name} ORDER BY rowid"
        ).fetchall()
    else:
        rows = cur.execute(
            f"""
            SELECT rowid, id, day, t, speaker, content
            FROM {table_name}
            WHERE rowid > ?
            ORDER BY rowid
            """,
            (_LAST_INTERVIEW_SYNC_ROWID,),
        ).fetchall()
    conn.close()
    if not rows:
        return

    pending_by_agent: dict[int, dict[str, Any]] = {}
    latest_stage_by_agent: dict[int, StageInterviewResult] = {}
    latest_final_by_agent: dict[int, FinalInterviewResult] = {}
    stage_results: list[StageInterviewResult] = []
    final_results: list[FinalInterviewResult] = []

    for rowid, agent_id, _day, _t, speaker, content in rows:
        agent_key = int(agent_id)
        speaker_text = _clean_intention(speaker)
        content_text = _clean_intention(content)
        stage_match = _STAGE_INTERVIEW_PATTERN.match(content_text)
        if speaker_text == "user" and stage_match:
            pending_by_agent[agent_key] = {
                "kind": "stage",
                "stage_name": _clean_intention(stage_match.group("stage_name")),
                "stage_index": _safe_int(stage_match.group("stage_index"), 0),
            }
            _LAST_INTERVIEW_SYNC_ROWID = int(rowid)
            continue
        if speaker_text == "user" and content_text.startswith(_FINAL_INTERVIEW_PREFIX):
            pending_by_agent[agent_key] = {"kind": "final"}
            _LAST_INTERVIEW_SYNC_ROWID = int(rowid)
            continue
        if speaker_text or agent_key not in pending_by_agent:
            _LAST_INTERVIEW_SYNC_ROWID = int(rowid)
            continue

        pending = pending_by_agent.pop(agent_key)
        payload = _extract_json_object(content_text)
        if pending["kind"] == "stage":
            parsed_result = _parse_stage_interview_payload(
                payload,
                stage_name=str(pending["stage_name"]),
                stage_index=int(pending["stage_index"]),
                raw_answer=content_text,
            )
            latest_stage_by_agent[agent_key] = parsed_result
            stage_results.append(parsed_result)
        else:
            parsed_result = _parse_final_interview_payload(
                payload,
                raw_answer=content_text,
            )
            latest_final_by_agent[agent_key] = parsed_result
            final_results.append(parsed_result)
        _LAST_INTERVIEW_SYNC_ROWID = int(rowid)

    if latest_stage_by_agent:
        history_map = await simulation.gather(
            "proto_stage_interview_history",
            list(latest_stage_by_agent.keys()),
            keep_id=True,
        )
        for agent_id, result in latest_stage_by_agent.items():
            history = (
                [item for item in history_map.get(agent_id, []) if isinstance(item, dict)]
                if isinstance(history_map.get(agent_id), list)
                else []
            )
            history.append(result.to_dict())
            await simulation.update([agent_id], "proto_stage_interview", result.to_dict())
            await simulation.update(
                [agent_id],
                "proto_stage_interview_history",
                history[-8:],
            )

    if latest_final_by_agent:
        for agent_id, result in latest_final_by_agent.items():
            await simulation.update([agent_id], "proto_final_interview", result.to_dict())

    step_day, step_t = simulation.environment.get_datetime()
    step = int(step_day * 100000 + step_t)
    metrics: list[tuple[str, float, int]] = []
    stage_name = _clean_intention(
        simulation.environment.environment.get("digital_stage")
        or simulation.environment.environment.get("stage_name")
    ) or "stage"
    valid_stage_results = [
        result for result in stage_results if result.status != "parse_failed"
    ]
    if valid_stage_results:
        stage_total = float(len(valid_stage_results))
        metrics.extend(
            [
                (f"{stage_name}.stage_interview_count", stage_total, step),
                (
                    f"{stage_name}.stage_future_try_self_rate",
                    float(
                        sum(
                            1
                            for result in valid_stage_results
                            if result.future_intention == "try_self"
                        )
                    )
                    / stage_total,
                    step,
                ),
                (
                    f"{stage_name}.stage_future_seek_help_rate",
                    float(
                        sum(
                            1
                            for result in valid_stage_results
                            if result.future_intention == "seek_help"
                        )
                    )
                    / stage_total,
                    step,
                ),
                (
                    f"{stage_name}.stage_future_avoid_rate",
                    float(
                        sum(
                            1
                            for result in valid_stage_results
                            if result.future_intention == "avoid"
                        )
                    )
                    / stage_total,
                    step,
                ),
                (
                    f"{stage_name}.stage_interview_confidence_avg",
                    float(
                        sum(float(result.confidence) for result in valid_stage_results)
                        / stage_total
                    ),
                    step,
                ),
            ]
        )

    valid_final_results = [
        result for result in final_results if result.status != "parse_failed"
    ]
    if valid_final_results:
        metrics.append(("final.interview_count", float(len(valid_final_results)), step))

    if metrics:
        try:
            await db_writer.log_metric(metrics)
        except Exception:
            return
