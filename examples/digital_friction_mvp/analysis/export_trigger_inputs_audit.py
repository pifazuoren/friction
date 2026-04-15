#!/usr/bin/env python3
import argparse
import bisect
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any


def table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _parse_decision_json(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _parse_status_summary(raw: Any) -> str:
    if raw is None:
        return ""
    value = raw
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    for _ in range(2):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                break
    return value if isinstance(value, str) else str(value)


def _to_abs_t(day: Any, t: Any) -> float:
    return (_as_float(day, 0.0) * 86400.0) + _as_float(t, 0.0)


def _status_same_t_key(day: Any, t: Any) -> tuple[int, int]:
    return (_as_int(day, 0), int(round(_as_float(t, 0.0) * 1_000_000)))


def _build_status_index(
    status_rows: list[sqlite3.Row],
) -> dict[int, dict[str, Any]]:
    by_agent: dict[int, list[dict[str, Any]]] = {}
    for row in status_rows:
        agent_id = _as_int(row["agent_id"], 0)
        entry = {
            "agent_id": agent_id,
            "day": _as_int(row["day"], 0),
            "t": _as_float(row["t"], 0.0),
            "action": _as_text(row["action"]),
            "status": row["status"],
        }
        by_agent.setdefault(agent_id, []).append(entry)

    index: dict[int, dict[str, Any]] = {}
    for agent_id, rows in by_agent.items():
        rows_sorted = sorted(rows, key=lambda item: _to_abs_t(item["day"], item["t"]))
        abs_times = [_to_abs_t(item["day"], item["t"]) for item in rows_sorted]
        same_t_map: dict[tuple[int, int], dict[str, Any]] = {}
        for item in rows_sorted:
            same_t_map[_status_same_t_key(item["day"], item["t"])] = item
        index[agent_id] = {
            "rows": rows_sorted,
            "abs_times": abs_times,
            "same_t": same_t_map,
        }
    return index


def _resolve_status_match(
    status_index: dict[int, dict[str, Any]],
    *,
    agent_id: Any,
    day: Any,
    t: Any,
    join_mode: str,
) -> tuple[str, str, Any, Any, Any]:
    aid = _as_int(agent_id, 0)
    info = status_index.get(aid)
    if not info:
        return "", "", "", "", ""

    attempt_day = _as_int(day, 0)
    attempt_t = _as_float(t, 0.0)
    attempt_abs_t = _to_abs_t(attempt_day, attempt_t)

    matched: dict[str, Any] | None = None
    if join_mode == "same_t":
        matched = info["same_t"].get(_status_same_t_key(attempt_day, attempt_t))
    elif join_mode == "prev_snapshot":
        pos = bisect.bisect_left(info["abs_times"], attempt_abs_t) - 1
        if pos >= 0:
            matched = info["rows"][pos]
    else:
        raise ValueError(f"Unsupported join mode: {join_mode}")

    if not matched:
        return "", "", "", "", ""

    lag = attempt_abs_t - _to_abs_t(matched["day"], matched["t"])
    return (
        _as_text(matched["action"]),
        _parse_status_summary(matched["status"]),
        matched["day"],
        matched["t"],
        lag,
    )


def _pick_text(obj: dict[str, Any], key: str) -> str:
    return _as_text(obj.get(key, ""))


def _pick_float(obj: dict[str, Any], key: str, default: float = 0.0) -> float:
    return _as_float(obj.get(key), default=default)


def _pick_int(obj: dict[str, Any], key: str, default: int = 0) -> int:
    return _as_int(obj.get(key), default=default)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "导出 trigger_event_shocks 使用的审计输入（基于 mvp_decision_attempt + decision_json）"
        )
    )
    parser.add_argument("exp_id", help="实验编号，例如 dd589b8c-e4d3-45d8-a7f7-2901ebb6be4b")
    parser.add_argument("--db-path", default="agentsociety_data/sqlite.db", help="sqlite 路径")
    parser.add_argument(
        "--join-mode",
        choices=["same_t", "prev_snapshot"],
        default="prev_snapshot",
        help="附带 action/status 对齐方式：same_t=同时刻，prev_snapshot=最近过去快照（默认）",
    )
    parser.add_argument(
        "--out-csv",
        default=None,
        help="输出 CSV 路径（默认自动命名到 examples/digital_friction_mvp/analysis）",
    )
    parser.add_argument(
        "--include-decision-json",
        type=int,
        choices=[0, 1],
        default=1,
        help="是否附带原始 decision_json 列（默认=1）",
    )
    args = parser.parse_args()

    exp_id = args.exp_id.strip()
    prefix = exp_id.replace("-", "_")
    attempt_table = f"as_{prefix}_mvp_decision_attempt"
    status_table = f"as_{prefix}_agent_status"

    if args.out_csv:
        out_csv = Path(args.out_csv)
    else:
        out_csv = Path(
            f"examples/digital_friction_mvp/analysis/attempt_trigger_inputs_{exp_id[:8]}.csv"
        )

    conn = sqlite3.connect(str(args.db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if not table_exists(cur, attempt_table):
        raise SystemExit(f"找不到表: {attempt_table}")

    rows = cur.execute(
        f"""
        SELECT
          attempt_uid, agent_id, day, t, step, stage_name, stage_index,
          intention, need, step_type, step_intention, status_text, step_eval_text, step_outcome,
          digital_exposure, digital_from_action, digital_from_status, digital_from_intention, digital_from_signal,
          scenario, scenario_entry_reason, scenario_match_source, llm_match_status, llm_match_confidence, llm_match_reason,
          emitted, outcome, roll, p_negative_interval, p_positive_interval, total_event_prob, hazard_p_total, llm_status,
          decision_json
        FROM {attempt_table}
        ORDER BY day, t, agent_id
        """
    ).fetchall()
    status_rows: list[sqlite3.Row] = []
    if table_exists(cur, status_table):
        status_rows = cur.execute(
            f"""
            SELECT id AS agent_id, day, t, action, status
            FROM {status_table}
            ORDER BY id, day, t
            """
        ).fetchall()
    conn.close()
    status_index = _build_status_index(status_rows)

    header = [
        "attempt_uid",
        "agent_id",
        "day",
        "t",
        "step",
        "stage_name",
        "stage_index",
        "intention",
        "need",
        "step_type",
        "step_intention",
        "status_text",
        "step_eval_text",
        "step_outcome",
        "aligned_action",
        "aligned_agent_status_status",
        "aligned_action_snapshot_day",
        "aligned_action_snapshot_t",
        "aligned_join_mode",
        "aligned_join_lag_seconds",
        "digital_exposure",
        "digital_from_action",
        "digital_from_status",
        "digital_from_intention",
        "digital_from_signal",
        "digital_task_hint",
        "digital_task_hint_need",
        "digital_task_hint_pending",
        "digital_task_adopted",
        "scenario",
        "scenario_entry_reason",
        "scenario_match_source",
        "llm_match_status",
        "llm_match_confidence",
        "llm_match_reason",
        "emitted",
        "outcome",
        "roll",
        "p_negative_interval",
        "p_positive_interval",
        "total_event_prob",
        "hazard_p_total",
        "llm_status",
        "match_pipeline_mode",
        "digital_gate_source",
        "digital_gate_status",
        "digital_gate_confidence",
        "digital_gate_reason",
        "scenario_aligned",
        "input_source",
        "status_summary_text",
        "plan_index",
        "step_failure_pressure",
        "step_success_support",
        "step_consumed_time",
        "step_effort_bucket",
        "decision_mode",
        "prob_model",
        "llm_calls_this_step",
        "llm_scenario_calls_this_step",
        "llm_calls_for_agent",
        "fallback_reason",
    ]
    include_decision_json = bool(args.include_decision_json)
    if include_decision_json:
        header.append("decision_json")

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        for row in rows:
            attempt_uid = row["attempt_uid"]
            agent_id = row["agent_id"]
            day = row["day"]
            t = row["t"]
            step = row["step"]
            stage_name = row["stage_name"]
            stage_index = row["stage_index"]
            intention = row["intention"]
            need = row["need"]
            step_type = row["step_type"]
            step_intention = row["step_intention"]
            status_text = row["status_text"]
            step_eval_text = row["step_eval_text"]
            step_outcome = row["step_outcome"]
            digital_exposure = row["digital_exposure"]
            digital_from_action = row["digital_from_action"]
            digital_from_status = row["digital_from_status"]
            digital_from_intention = row["digital_from_intention"]
            digital_from_signal = row["digital_from_signal"]
            scenario = row["scenario"]
            scenario_entry_reason = row["scenario_entry_reason"]
            scenario_match_source = row["scenario_match_source"]
            llm_match_status = row["llm_match_status"]
            llm_match_confidence = row["llm_match_confidence"]
            llm_match_reason = row["llm_match_reason"]
            emitted = row["emitted"]
            outcome = row["outcome"]
            roll = row["roll"]
            p_negative_interval = row["p_negative_interval"]
            p_positive_interval = row["p_positive_interval"]
            total_event_prob = row["total_event_prob"]
            hazard_p_total = row["hazard_p_total"]
            llm_status = row["llm_status"]
            decision_json_raw = row["decision_json"]
            decision_obj = _parse_decision_json(decision_json_raw)
            (
                aligned_action,
                aligned_agent_status_status,
                aligned_action_snapshot_day,
                aligned_action_snapshot_t,
                aligned_join_lag_seconds,
            ) = _resolve_status_match(
                status_index,
                agent_id=agent_id,
                day=day,
                t=t,
                join_mode=args.join_mode,
            )
            out_row = [
                _as_text(attempt_uid),
                _as_int(agent_id),
                _as_int(day),
                _as_float(t),
                _as_int(step),
                _as_text(stage_name),
                _as_int(stage_index),
                _as_text(intention),
                _as_text(need),
                _as_text(step_type),
                _as_text(step_intention),
                _as_text(status_text),
                _as_text(step_eval_text),
                _as_text(step_outcome),
                aligned_action,
                aligned_agent_status_status,
                aligned_action_snapshot_day,
                aligned_action_snapshot_t,
                args.join_mode,
                aligned_join_lag_seconds,
                _as_int(digital_exposure),
                _as_int(digital_from_action),
                _as_int(digital_from_status),
                _as_int(digital_from_intention),
                _as_int(digital_from_signal),
                _pick_text(decision_obj, "digital_task_hint"),
                _pick_text(decision_obj, "digital_task_hint_need"),
                _pick_int(decision_obj, "digital_task_hint_pending", default=0),
                _pick_int(decision_obj, "digital_task_adopted", default=0),
                _as_text(scenario),
                _as_text(scenario_entry_reason),
                _as_text(scenario_match_source),
                _as_text(llm_match_status),
                _as_float(llm_match_confidence),
                _as_text(llm_match_reason),
                _as_int(emitted),
                _as_text(outcome),
                _as_float(roll),
                _as_float(p_negative_interval),
                _as_float(p_positive_interval),
                _as_float(total_event_prob),
                _as_float(hazard_p_total),
                _as_text(llm_status),
                _pick_text(decision_obj, "match_pipeline_mode"),
                _pick_text(decision_obj, "digital_gate_source"),
                _pick_text(decision_obj, "digital_gate_status"),
                _pick_float(decision_obj, "digital_gate_confidence", default=0.0),
                _pick_text(decision_obj, "digital_gate_reason"),
                _pick_int(decision_obj, "scenario_aligned", default=0),
                _pick_text(decision_obj, "input_source"),
                _pick_text(decision_obj, "status_summary_text"),
                _pick_int(decision_obj, "plan_index", default=0),
                _pick_float(decision_obj, "step_failure_pressure", default=0.0),
                _pick_float(decision_obj, "step_success_support", default=0.0),
                _pick_float(decision_obj, "step_consumed_time", default=0.0),
                _pick_text(decision_obj, "step_effort_bucket"),
                _pick_text(decision_obj, "decision_mode"),
                _pick_text(decision_obj, "prob_model"),
                _pick_int(decision_obj, "llm_calls_this_step", default=0),
                _pick_int(decision_obj, "llm_scenario_calls_this_step", default=0),
                _pick_int(decision_obj, "llm_calls_for_agent", default=0),
                _pick_text(decision_obj, "fallback_reason"),
            ]
            if include_decision_json:
                out_row.append(_as_text(decision_json_raw))
            writer.writerow(out_row)

    print(out_csv)


if __name__ == "__main__":
    main()
