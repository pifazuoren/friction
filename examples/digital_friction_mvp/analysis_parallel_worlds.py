#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


WORLD_METRIC_FIELDS = (
    "attempt_rate",
    "success_rate",
    "help_seek_rate",
    "abandon_rate",
    "negative_feedback_rate",
    "helplessness_delta",
    "mobile_entry_task_generated_rate",
)


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


def _table_name(exp_id: str, suffix: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_{suffix}"


def _table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(cur: sqlite3.Cursor, table_name: str) -> set[str]:
    try:
        rows = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return set()
    return {str(row[1]) for row in rows}


def _clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _load_profiles(
    profiles_path: Path,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    if not profiles_path.exists():
        return {}, []
    try:
        payload = json.loads(profiles_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, []
    if not isinstance(payload, list):
        return {}, []
    profiles = [item for item in payload if isinstance(item, dict)]
    index: dict[int, dict[str, Any]] = {}
    for profile in profiles:
        raw_id = profile.get("id")
        try:
            profile_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        index[profile_id] = profile
    return index, profiles


def _resolve_profile_for_agent(
    agent_id: int,
    ordered_agent_ids: list[int],
    profile_index: dict[int, dict[str, Any]],
    profile_list: list[dict[str, Any]],
) -> dict[str, Any]:
    if agent_id in profile_index:
        return profile_index[agent_id]
    if ordered_agent_ids and profile_list:
        try:
            position = ordered_agent_ids.index(agent_id)
        except ValueError:
            position = -1
        if 0 <= position < len(profile_list):
            return profile_list[position]
    return {}


def _compute_init_status_from_profile(profile: dict[str, Any]) -> tuple[float, float, float]:
    digital_experience = _safe_float(profile.get("digital_experience"), 0.5)
    vision_limit = _safe_float(profile.get("vision_limit"), 0.3)
    past_fraud = _safe_float(profile.get("past_fraud_experience"), 0.2)
    helplessness = _clamp(20 + (1 - digital_experience) * 25 + past_fraud * 15)
    trust = _clamp(70 + digital_experience * 10 - past_fraud * 25)
    avoidance = _clamp(20 + (1 - digital_experience) * 20 + vision_limit * 15)
    return helplessness, trust, avoidance


def _compute_status_delta(
    cur: sqlite3.Cursor,
    table_name: str,
    profile_index: dict[int, dict[str, Any]],
    profile_list: list[dict[str, Any]],
) -> tuple[float, float, float]:
    rows = cur.execute(
        f"""
        SELECT agent_id, day, t, helplessness_score, trust_in_apps, avoidance_tendency
        FROM {table_name}
        ORDER BY day, t, agent_id
        """
    ).fetchall()
    if not rows:
        return 0.0, 0.0, 0.0

    def _avg(records: list[tuple[Any, ...]], index: int) -> float:
        values = [_safe_float(item[index], 0.0) for item in records]
        return sum(values) / len(values) if values else 0.0

    grouped_by_time: dict[tuple[int, float], list[tuple[Any, ...]]] = {}
    for row in rows:
        key = (_safe_int(row[1], 0), _safe_float(row[2], 0.0))
        grouped_by_time.setdefault(key, []).append(row)
    time_keys = list(grouped_by_time.keys())
    if not time_keys:
        return 0.0, 0.0, 0.0

    if len(time_keys) >= 2:
        first_rows = grouped_by_time[time_keys[0]]
        last_rows = grouped_by_time[time_keys[-1]]
        helplessness_delta = _avg(last_rows, 3) - _avg(first_rows, 3)
        trust_delta = _avg(last_rows, 4) - _avg(first_rows, 4)
        avoidance_delta = _avg(last_rows, 5) - _avg(first_rows, 5)
        return helplessness_delta, trust_delta, avoidance_delta

    snapshot_rows = grouped_by_time[time_keys[0]]
    ordered_agent_ids = [_safe_int(item[0], 0) for item in snapshot_rows]
    delta_helplessness: list[float] = []
    delta_trust: list[float] = []
    delta_avoidance: list[float] = []
    for item in snapshot_rows:
        agent_id = _safe_int(item[0], 0)
        final_helplessness = _safe_float(item[3], 0.0)
        final_trust = _safe_float(item[4], 0.0)
        final_avoidance = _safe_float(item[5], 0.0)
        profile = _resolve_profile_for_agent(
            agent_id=agent_id,
            ordered_agent_ids=ordered_agent_ids,
            profile_index=profile_index,
            profile_list=profile_list,
        )
        init_helplessness, init_trust, init_avoidance = _compute_init_status_from_profile(
            profile
        )
        delta_helplessness.append(final_helplessness - init_helplessness)
        delta_trust.append(final_trust - init_trust)
        delta_avoidance.append(final_avoidance - init_avoidance)
    if not delta_helplessness:
        return 0.0, 0.0, 0.0
    return (
        sum(delta_helplessness) / len(delta_helplessness),
        sum(delta_trust) / len(delta_trust),
        sum(delta_avoidance) / len(delta_avoidance),
    )


def _load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"manifest format invalid: {manifest_path}")


def _compute_world_proto_metrics(
    cur: sqlite3.Cursor,
    attempt_table: str,
) -> dict[str, Any]:
    rows = cur.execute(
        f"""
        SELECT day, strategy_type, outcome_type, payload_json
        FROM {attempt_table}
        """
    ).fetchall()
    total_rows = len(rows)
    if total_rows == 0:
        return {
            "task_count": 0,
            "attempts": 0,
            "successes": 0,
            "help_seek_count": 0,
            "abandon_count": 0,
            "negative_feedback_count": 0,
            "attempt_rate": 0.0,
            "success_rate": 0.0,
            "help_seek_rate": 0.0,
            "abandon_rate": 0.0,
            "negative_feedback_rate": 0.0,
            "neg_share": 0.0,
            "emit_given_attempt": 0.0,
            "positives": 0,
            "negatives": 0,
            "emitted": 0,
            "trajectory_call_count": 0,
            "trajectory_invalid_count": 0,
            "trajectory_low_confidence_count": 0,
            "trajectory_retry_success_count": 0,
            "trajectory_json_attempts_used_max": 0,
            "trajectory_mean_tvd_from_rule": 0.0,
            "outcome_model_modes_json": "{}",
            "outcome_types_json": "{}",
            "daily_negative_episode_count_json": "{}",
            "h_update_mean_raw_delta_before_damping": 0.0,
            "h_update_mean_damping_factor": 0.0,
            "h_update_mean_delta_before_daily_cap": 0.0,
            "h_update_mean_final_delta": 0.0,
            "h_update_daily_cap_applied_count": 0,
            "h_update_mean_daily_harm_used_after": 0.0,
    }

    attempt_count = sum(
        1 for _, _, outcome, _ in rows if outcome != "avoid_without_attempt"
    )
    success_count = sum(
        1
        for _, _, outcome, _ in rows
        if outcome in {"success_self", "success_with_help"}
    )
    help_seek_count = sum(
        1 for _, strategy, _, _ in rows if strategy == "seek_help_then_attempt"
    )
    abandon_count = sum(
        1 for _, _, outcome, _ in rows if outcome == "abandon_midway"
    )
    negative_feedback_count = sum(
        1
        for _, _, outcome, _ in rows
        if outcome in {"failure_after_attempt", "failure_even_with_help", "abandon_midway"}
    )
    trajectory_call_count = 0
    trajectory_invalid_count = 0
    trajectory_low_confidence_count = 0
    trajectory_retry_success_count = 0
    trajectory_json_attempts_used_max = 0
    trajectory_tvd_values: list[float] = []
    outcome_model_modes: Counter[str] = Counter()
    outcome_types: Counter[str] = Counter(str(outcome) for _, _, outcome, _ in rows)
    daily_negative_counts: Counter[str] = Counter()
    raw_delta_values: list[float] = []
    damping_values: list[float] = []
    delta_before_cap_values: list[float] = []
    final_delta_values: list[float] = []
    daily_harm_used_after_values: list[float] = []
    daily_cap_applied_count = 0
    for day_value_raw, _, outcome, raw_payload in rows:
        try:
            payload = json.loads(raw_payload or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        if outcome in {
            "failure_after_attempt",
            "failure_even_with_help",
            "abandon_midway",
        }:
            day_value = str(day_value_raw).strip()
            daily_negative_counts[day_value or "unknown"] += 1
        outcome_payload = payload.get("outcome", {})
        if not isinstance(outcome_payload, dict):
            continue
        mode = str(outcome_payload.get("outcome_model_mode", "")).strip()
        if mode:
            outcome_model_modes[mode] += 1
        trajectory_status = str(outcome_payload.get("trajectory_status", "")).strip()
        if trajectory_status and not trajectory_status.startswith("not_called"):
            trajectory_call_count += 1
        if trajectory_status in {
            "parse_failed",
            "request_error",
            "invalid_schema",
            "taxonomy_outside",
            "invalid_probability_sum",
            "invalid_outcome_keys",
            "banned_phrase",
        }:
            trajectory_invalid_count += 1
        if trajectory_status == "low_confidence":
            trajectory_low_confidence_count += 1
        attempts_used = _safe_int(
            outcome_payload.get("trajectory_json_attempts_used"),
            1,
        )
        trajectory_json_attempts_used_max = max(
            trajectory_json_attempts_used_max,
            attempts_used,
        )
        if attempts_used > 1 and trajectory_status in {"ok", "ok_repaired"}:
            trajectory_retry_success_count += 1
        trajectory_tvd = _safe_float(
            outcome_payload.get("trajectory_tvd_from_rule"),
            0.0,
        )
        if trajectory_tvd > 0:
            trajectory_tvd_values.append(trajectory_tvd)
        update_payload = payload.get("update", {})
        if isinstance(update_payload, dict):
            raw_delta_values.append(
                _safe_float(update_payload.get("raw_delta_before_damping"), 0.0)
            )
            damping_values.append(
                _safe_float(update_payload.get("damping_factor"), 0.0)
            )
            delta_before_cap_values.append(
                _safe_float(update_payload.get("delta_before_daily_cap"), 0.0)
            )
            final_delta_values.append(_safe_float(update_payload.get("delta"), 0.0))
            daily_harm_used_after_values.append(
                _safe_float(update_payload.get("daily_harm_used_after"), 0.0)
            )
            if bool(update_payload.get("daily_cap_applied", False)):
                daily_cap_applied_count += 1
    denominator = float(total_rows)
    neg_share = (
        float(negative_feedback_count) / float(attempt_count) if attempt_count > 0 else 0.0
    )
    return {
        "task_count": total_rows,
        "attempts": attempt_count,
        "successes": success_count,
        "help_seek_count": help_seek_count,
        "abandon_count": abandon_count,
        "negative_feedback_count": negative_feedback_count,
        "attempt_rate": float(attempt_count / denominator),
        "success_rate": float(success_count / denominator),
        "help_seek_rate": float(help_seek_count / denominator),
        "abandon_rate": float(abandon_count / denominator),
        "negative_feedback_rate": float(negative_feedback_count / denominator),
        "neg_share": neg_share,
        "emit_given_attempt": 1.0 if attempt_count > 0 else 0.0,
        "positives": success_count,
        "negatives": negative_feedback_count,
        "emitted": attempt_count,
        "trajectory_call_count": int(trajectory_call_count),
        "trajectory_invalid_count": int(trajectory_invalid_count),
        "trajectory_low_confidence_count": int(trajectory_low_confidence_count),
        "trajectory_retry_success_count": int(trajectory_retry_success_count),
        "trajectory_json_attempts_used_max": int(trajectory_json_attempts_used_max),
        "trajectory_mean_tvd_from_rule": (
            sum(trajectory_tvd_values) / len(trajectory_tvd_values)
            if trajectory_tvd_values
            else 0.0
        ),
        "outcome_model_modes_json": json.dumps(
            dict(sorted(outcome_model_modes.items())),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "outcome_types_json": json.dumps(
            dict(sorted(outcome_types.items())),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "daily_negative_episode_count_json": json.dumps(
            dict(sorted(daily_negative_counts.items())),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "h_update_mean_raw_delta_before_damping": (
            sum(raw_delta_values) / len(raw_delta_values)
            if raw_delta_values
            else 0.0
        ),
        "h_update_mean_damping_factor": (
            sum(damping_values) / len(damping_values)
            if damping_values
            else 0.0
        ),
        "h_update_mean_delta_before_daily_cap": (
            sum(delta_before_cap_values) / len(delta_before_cap_values)
            if delta_before_cap_values
            else 0.0
        ),
        "h_update_mean_final_delta": (
            sum(final_delta_values) / len(final_delta_values)
            if final_delta_values
            else 0.0
        ),
        "h_update_daily_cap_applied_count": int(daily_cap_applied_count),
        "h_update_mean_daily_harm_used_after": (
            sum(daily_harm_used_after_values) / len(daily_harm_used_after_values)
            if daily_harm_used_after_values
            else 0.0
        ),
    }


def _compute_mobile_entry_metrics(
    cur: sqlite3.Cursor,
    status_table: str,
) -> dict[str, Any]:
    if (
        not _table_exists(cur, status_table)
        or "status_json" not in _table_columns(cur, status_table)
    ):
        return {
            "mobile_entry_eval_count": 0,
            "mobile_entry_task_generated_count": 0,
            "mobile_entry_noop_count": 0,
            "mobile_entry_context_count": 0,
            "mobile_entry_task_generated_rate": 0.0,
            "mobile_entry_top_intentions_json": "{}",
            "mobile_entry_mapped_task_families_json": "{}",
        }
    rows = cur.execute(
        f"""
        SELECT agent_id, day, t, status_json
        FROM {status_table}
        ORDER BY day, t, agent_id
        """
    ).fetchall()
    seen: set[tuple[int, int, int]] = set()
    intention_counts: Counter[str] = Counter()
    task_family_counts: Counter[str] = Counter()
    eval_count = 0
    task_generated_count = 0
    noop_count = 0
    context_count = 0
    for agent_id, row_day, row_t, raw_status in rows:
        try:
            status = json.loads(raw_status or "{}")
        except Exception:
            continue
        if not isinstance(status, dict):
            continue
        decision = status.get("proto_mobile_entry_decision", {})
        if not isinstance(decision, dict):
            continue
        if not bool(decision.get("entry_evaluated", False)):
            continue
        audit = decision.get("audit", {})
        if not isinstance(audit, dict):
            audit = {}
        key = (
            _safe_int(audit.get("agent_id", agent_id), _safe_int(agent_id, 0)),
            _safe_int(audit.get("day", row_day), _safe_int(row_day, 0)),
            int(round(_safe_float(audit.get("tick_seconds", row_t), _safe_float(row_t, 0.0)))),
        )
        if key in seen:
            continue
        seen.add(key)
        eval_count += 1
        selected = str(decision.get("selected_mobile_intention", "")).strip()
        if selected:
            intention_counts[selected] += 1
        mapped_family = str(decision.get("mapped_task_family", "") or "").strip()
        if mapped_family:
            task_family_counts[mapped_family] += 1
        if bool(decision.get("task_generated", False)):
            task_generated_count += 1
        else:
            noop_count += 1
        entry_status = str(decision.get("entry_status", "")).strip()
        if entry_status.endswith("_context_only"):
            context_count += 1
    denominator = max(1, eval_count)
    return {
        "mobile_entry_eval_count": int(eval_count),
        "mobile_entry_task_generated_count": int(task_generated_count),
        "mobile_entry_noop_count": int(noop_count),
        "mobile_entry_context_count": int(context_count),
        "mobile_entry_task_generated_rate": float(task_generated_count / denominator),
        "mobile_entry_top_intentions_json": json.dumps(
            dict(sorted(intention_counts.items())),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "mobile_entry_mapped_task_families_json": json.dumps(
            dict(sorted(task_family_counts.items())),
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def _load_stage_summary_rows(
    cur: sqlite3.Cursor,
    stage_table: str,
    *,
    manifest_row: dict[str, Any],
) -> list[dict[str, Any]]:
    if not _table_exists(cur, stage_table):
        return []
    rows = cur.execute(
        f"""
        SELECT day, t, step, stage_name, stage_index, agent_count, task_count,
               attempt_rate, success_rate, help_seek_rate, abandon_rate,
               negative_feedback_rate, helplessness_delta
        FROM {stage_table}
        ORDER BY stage_index, day, t
        """
    ).fetchall()
    stage_rows: list[dict[str, Any]] = []
    for row in rows:
        stage_rows.append(
            {
                "group_id": str(manifest_row.get("group_id", "")).strip(),
                "pair_index": _safe_int(manifest_row.get("pair_index"), -1),
                "pair_seed": _safe_int(
                    manifest_row.get("pair_seed"),
                    _safe_int(manifest_row.get("seed"), 0),
                ),
                "world_order": _safe_int(manifest_row.get("world_order"), -1),
                "world_name": str(manifest_row.get("world_name", "")).strip(),
                "exp_id": str(manifest_row.get("exp_id", "")).strip(),
                "status": str(manifest_row.get("status", "")).strip(),
                "day": _safe_int(row[0], 0),
                "t": _safe_float(row[1], 0.0),
                "step": _safe_int(row[2], 0),
                "stage_name": str(row[3] or "").strip(),
                "stage_index": _safe_int(row[4], 0),
                "agent_count": _safe_int(row[5], 0),
                "task_count": _safe_int(row[6], 0),
                "attempt_rate": round(_safe_float(row[7], 0.0), 6),
                "success_rate": round(_safe_float(row[8], 0.0), 6),
                "help_seek_rate": round(_safe_float(row[9], 0.0), 6),
                "abandon_rate": round(_safe_float(row[10], 0.0), 6),
                "negative_feedback_rate": round(_safe_float(row[11], 0.0), 6),
                "helplessness_delta": round(_safe_float(row[12], 0.0), 6),
            }
        )
    return stage_rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _plot_world_metrics(
    rows: list[dict[str, Any]],
    *,
    world_order: list[str],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    aggregated: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        if str(row.get("status", "")).strip().lower() != "ok":
            continue
        world_name = str(row.get("world_name", "")).strip()
        if not world_name:
            continue
        world_bucket = aggregated.setdefault(
            world_name,
            {metric: [] for metric in WORLD_METRIC_FIELDS},
        )
        for metric in WORLD_METRIC_FIELDS:
            world_bucket[metric].append(_safe_float(row.get(metric), 0.0))

    ordered_worlds = [
        world_name for world_name in world_order if world_name in aggregated
    ]
    for metric in WORLD_METRIC_FIELDS:
        values = []
        labels = []
        for world_name in ordered_worlds:
            metric_values = aggregated.get(world_name, {}).get(metric, [])
            if not metric_values:
                continue
            labels.append(world_name)
            values.append(sum(metric_values) / len(metric_values))
        if not labels:
            continue
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(labels, values, color="#4C78A8")
        ax.set_title(metric)
        ax.set_xlabel("world_name")
        ax.set_ylabel(metric)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", rotation=15)
        fig.tight_layout()
        fig.savefig(output_dir / f"{metric}.png", dpi=150)
        plt.close(fig)


def main() -> None:
    default_profiles = os.getenv("DIGITAL_FRICTION_PROFILES_PATH", "").strip()
    if not default_profiles:
        default_profiles = str(Path(__file__).resolve().parent / "profiles.json")
    parser = argparse.ArgumentParser(
        description="Summarize proto-native metrics across parallel world experiments."
    )
    parser.add_argument("--manifest", required=True, help="Path to exp_group_manifest_*.json")
    parser.add_argument("--db-path", default="agentsociety_data/sqlite.db", help="Path to sqlite db")
    parser.add_argument(
        "--profiles-path",
        default=default_profiles,
        help="Path to profiles.json used to rebuild init-status baseline",
    )
    parser.add_argument(
        "--out-csv",
        default="examples/digital_friction_mvp/analysis/parallel_world_summary.csv",
        help="Output CSV path for world-level summary",
    )
    parser.add_argument(
        "--out-stage-csv",
        default="",
        help="Output CSV path for stage-level summary",
    )
    parser.add_argument(
        "--plot-dir",
        default="",
        help="Output directory for world-level metric plots",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"sqlite db not found: {db_path}")
    profiles_path = Path(args.profiles_path).expanduser()
    if not profiles_path.is_absolute():
        profiles_path = (Path.cwd() / profiles_path).resolve()
    profile_index, profile_list = _load_profiles(profiles_path)

    out_csv = Path(args.out_csv)
    out_stage_csv = Path(args.out_stage_csv) if args.out_stage_csv else out_csv.with_name(
        out_csv.name.replace("parallel_world_summary", "parallel_stage_summary")
    )
    plot_dir = Path(args.plot_dir) if args.plot_dir else out_csv.parent / (
        out_csv.stem.replace("parallel_world_summary", "parallel_world_plots")
    )

    manifest_rows = _load_manifest(manifest_path)
    world_order: list[str] = []
    for row in manifest_rows:
        world_name = str(row.get("world_name", "")).strip()
        if world_name and world_name not in world_order:
            world_order.append(world_name)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    world_summary_rows: list[dict[str, Any]] = []
    stage_summary_rows: list[dict[str, Any]] = []
    for row in manifest_rows:
        exp_id = str(row.get("exp_id", "")).strip()
        world_name = str(row.get("world_name", "")).strip()
        status = str(row.get("status", "")).strip().lower()
        attempt_table = _table_name(exp_id, "proto_attempt_rows") if exp_id else ""
        stage_table = _table_name(exp_id, "proto_stage_summary") if exp_id else ""
        status_table = _table_name(exp_id, "mvp_status") if exp_id else ""

        world_metrics = {
            "task_count": 0,
            "attempts": 0,
            "successes": 0,
            "help_seek_count": 0,
            "abandon_count": 0,
            "negative_feedback_count": 0,
            "attempt_rate": 0.0,
            "success_rate": 0.0,
            "help_seek_rate": 0.0,
            "abandon_rate": 0.0,
            "negative_feedback_rate": 0.0,
            "neg_share": 0.0,
            "emit_given_attempt": 0.0,
            "positives": 0,
            "negatives": 0,
            "emitted": 0,
            "trajectory_call_count": 0,
            "trajectory_invalid_count": 0,
            "trajectory_low_confidence_count": 0,
            "trajectory_retry_success_count": 0,
            "trajectory_json_attempts_used_max": 0,
            "trajectory_mean_tvd_from_rule": 0.0,
            "outcome_model_modes_json": "{}",
            "outcome_types_json": "{}",
            "daily_negative_episode_count_json": "{}",
            "h_update_mean_raw_delta_before_damping": 0.0,
            "h_update_mean_damping_factor": 0.0,
            "h_update_mean_delta_before_daily_cap": 0.0,
            "h_update_mean_final_delta": 0.0,
            "h_update_daily_cap_applied_count": 0,
            "h_update_mean_daily_harm_used_after": 0.0,
        }
        if exp_id and attempt_table and _table_exists(cur, attempt_table):
            world_metrics = _compute_world_proto_metrics(cur, attempt_table)

        helplessness_delta = 0.0
        trust_delta = 0.0
        avoidance_delta = 0.0
        if exp_id and status_table and _table_exists(cur, status_table):
            helplessness_delta, trust_delta, avoidance_delta = _compute_status_delta(
                cur,
                status_table,
                profile_index=profile_index,
                profile_list=profile_list,
            )
        mobile_entry_metrics = _compute_mobile_entry_metrics(cur, status_table)

        world_summary_rows.append(
            {
                "group_id": str(row.get("group_id", "")).strip(),
                "pair_index": _safe_int(row.get("pair_index"), -1),
                "pair_seed": _safe_int(row.get("pair_seed"), _safe_int(row.get("seed"), 0)),
                "world_order": _safe_int(row.get("world_order"), -1),
                "world_name": world_name,
                "exp_id": exp_id,
                "status": status,
                "qc_config_match": _safe_int(row.get("qc_config_match"), 0),
                "config_fingerprint": str(row.get("config_fingerprint", "")).strip(),
                "agent_count": _safe_int(row.get("agent_count"), 0),
                "total_days": _safe_int(row.get("total_days"), 0),
                "task_count": _safe_int(world_metrics["task_count"], 0),
                "attempts": _safe_int(world_metrics["attempts"], 0),
                "successes": _safe_int(world_metrics["successes"], 0),
                "help_seek_count": _safe_int(world_metrics["help_seek_count"], 0),
                "abandon_count": _safe_int(world_metrics["abandon_count"], 0),
                "negative_feedback_count": _safe_int(world_metrics["negative_feedback_count"], 0),
                "attempt_rate": round(_safe_float(world_metrics["attempt_rate"]), 6),
                "success_rate": round(_safe_float(world_metrics["success_rate"]), 6),
                "help_seek_rate": round(_safe_float(world_metrics["help_seek_rate"]), 6),
                "abandon_rate": round(_safe_float(world_metrics["abandon_rate"]), 6),
                "negative_feedback_rate": round(
                    _safe_float(world_metrics["negative_feedback_rate"]), 6
                ),
                "helplessness_delta": round(helplessness_delta, 6),
                "trust_delta": round(trust_delta, 6),
                "avoidance_delta": round(avoidance_delta, 6),
                "emitted": _safe_int(world_metrics["emitted"], 0),
                "positives": _safe_int(world_metrics["positives"], 0),
                "negatives": _safe_int(world_metrics["negatives"], 0),
                "neg_share": round(_safe_float(world_metrics["neg_share"]), 6),
                "emit_given_attempt": round(
                    _safe_float(world_metrics["emit_given_attempt"]), 6
                ),
                "mobile_entry_eval_count": _safe_int(
                    mobile_entry_metrics["mobile_entry_eval_count"], 0
                ),
                "mobile_entry_task_generated_count": _safe_int(
                    mobile_entry_metrics["mobile_entry_task_generated_count"], 0
                ),
                "mobile_entry_noop_count": _safe_int(
                    mobile_entry_metrics["mobile_entry_noop_count"], 0
                ),
                "mobile_entry_context_count": _safe_int(
                    mobile_entry_metrics["mobile_entry_context_count"], 0
                ),
                "mobile_entry_task_generated_rate": round(
                    _safe_float(
                        mobile_entry_metrics["mobile_entry_task_generated_rate"]
                    ),
                    6,
                ),
                "mobile_entry_top_intentions_json": str(
                    mobile_entry_metrics["mobile_entry_top_intentions_json"]
                ),
                "mobile_entry_mapped_task_families_json": str(
                    mobile_entry_metrics["mobile_entry_mapped_task_families_json"]
                ),
                "trajectory_call_count": _safe_int(
                    world_metrics["trajectory_call_count"], 0
                ),
                "trajectory_invalid_count": _safe_int(
                    world_metrics["trajectory_invalid_count"], 0
                ),
                "trajectory_low_confidence_count": _safe_int(
                    world_metrics["trajectory_low_confidence_count"], 0
                ),
                "trajectory_retry_success_count": _safe_int(
                    world_metrics["trajectory_retry_success_count"], 0
                ),
                "trajectory_json_attempts_used_max": _safe_int(
                    world_metrics["trajectory_json_attempts_used_max"], 0
                ),
                "trajectory_mean_tvd_from_rule": round(
                    _safe_float(world_metrics["trajectory_mean_tvd_from_rule"]), 6
                ),
                "outcome_model_modes_json": str(
                    world_metrics["outcome_model_modes_json"]
                ),
                "outcome_types_json": str(world_metrics["outcome_types_json"]),
                "daily_negative_episode_count_json": str(
                    world_metrics["daily_negative_episode_count_json"]
                ),
                "h_update_mean_raw_delta_before_damping": round(
                    _safe_float(
                        world_metrics["h_update_mean_raw_delta_before_damping"]
                    ),
                    6,
                ),
                "h_update_mean_damping_factor": round(
                    _safe_float(world_metrics["h_update_mean_damping_factor"]),
                    6,
                ),
                "h_update_mean_delta_before_daily_cap": round(
                    _safe_float(
                        world_metrics["h_update_mean_delta_before_daily_cap"]
                    ),
                    6,
                ),
                "h_update_mean_final_delta": round(
                    _safe_float(world_metrics["h_update_mean_final_delta"]),
                    6,
                ),
                "h_update_daily_cap_applied_count": _safe_int(
                    world_metrics["h_update_daily_cap_applied_count"], 0
                ),
                "h_update_mean_daily_harm_used_after": round(
                    _safe_float(world_metrics["h_update_mean_daily_harm_used_after"]),
                    6,
                ),
            }
        )

        if exp_id and stage_table:
            stage_summary_rows.extend(
                _load_stage_summary_rows(cur, stage_table, manifest_row=row)
            )

    conn.close()

    world_fieldnames = [
        "group_id",
        "pair_index",
        "pair_seed",
        "world_order",
        "world_name",
        "exp_id",
        "status",
        "qc_config_match",
        "config_fingerprint",
        "agent_count",
        "total_days",
        "attempt_rate",
        "success_rate",
        "help_seek_rate",
        "abandon_rate",
        "negative_feedback_rate",
        "helplessness_delta",
        "task_count",
        "attempts",
        "successes",
        "help_seek_count",
        "abandon_count",
        "negative_feedback_count",
        "trust_delta",
        "avoidance_delta",
        "emitted",
        "positives",
        "negatives",
        "neg_share",
        "emit_given_attempt",
        "mobile_entry_eval_count",
        "mobile_entry_task_generated_count",
        "mobile_entry_noop_count",
        "mobile_entry_context_count",
        "mobile_entry_task_generated_rate",
        "mobile_entry_top_intentions_json",
        "mobile_entry_mapped_task_families_json",
        "trajectory_call_count",
        "trajectory_invalid_count",
        "trajectory_low_confidence_count",
        "trajectory_retry_success_count",
        "trajectory_json_attempts_used_max",
        "trajectory_mean_tvd_from_rule",
        "outcome_model_modes_json",
        "outcome_types_json",
        "daily_negative_episode_count_json",
        "h_update_mean_raw_delta_before_damping",
        "h_update_mean_damping_factor",
        "h_update_mean_delta_before_daily_cap",
        "h_update_mean_final_delta",
        "h_update_daily_cap_applied_count",
        "h_update_mean_daily_harm_used_after",
    ]
    stage_fieldnames = [
        "group_id",
        "pair_index",
        "pair_seed",
        "world_order",
        "world_name",
        "exp_id",
        "status",
        "stage_index",
        "stage_name",
        "agent_count",
        "task_count",
        "attempt_rate",
        "success_rate",
        "help_seek_rate",
        "abandon_rate",
        "negative_feedback_rate",
        "helplessness_delta",
        "day",
        "t",
        "step",
    ]

    _write_csv(out_csv, world_summary_rows, world_fieldnames)
    _write_csv(out_stage_csv, stage_summary_rows, stage_fieldnames)
    _plot_world_metrics(world_summary_rows, world_order=world_order, output_dir=plot_dir)

    print(out_csv)
    print(out_stage_csv)
    print(plot_dir)


if __name__ == "__main__":
    main()
