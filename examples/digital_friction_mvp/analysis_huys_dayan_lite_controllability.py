#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from pathlib import Path
from typing import Any


POLICY_ACTIONS = (
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
)


def _safe_float(value: Any, default: float | None = None) -> float | None:
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


def _table_name(exp_id: str, suffix: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_{suffix}"


def _table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _load_json_object(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        payload = json.loads(str(raw_value))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"manifest format invalid: {manifest_path}")


def _group_id_from_manifest(manifest_path: Path, rows: list[dict[str, Any]]) -> str:
    for row in rows:
        group_id = str(row.get("group_id", "")).strip()
        if group_id:
            return group_id
    stem = manifest_path.stem
    prefix = "exp_group_manifest_"
    return stem[len(prefix) :] if stem.startswith(prefix) else stem


def _load_config_payload(manifest_path: Path, group_id: str) -> dict[str, Any]:
    snapshot_path = manifest_path.parent / f"config_snapshot_{group_id}.json"
    if not snapshot_path.exists():
        return {}
    payload = _load_json_object(snapshot_path.read_text(encoding="utf-8"))
    config_payload = payload.get("config_payload")
    return config_payload if isinstance(config_payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _mean(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return sum(valid) / len(valid) if valid else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else numerator / denominator


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return round(value, 10)
    return value


def _unique_join(records: list[dict[str, Any]], key: str) -> str:
    values = sorted(
        {
            str(record.get(key, "")).strip()
            for record in records
            if record.get(key) not in (None, "")
        }
    )
    return "|".join(values)


def _extract_records(
    *,
    cur: sqlite3.Cursor,
    manifest_rows: list[dict[str, Any]],
    config_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    qc_rows: list[dict[str, Any]] = []
    for manifest_row in manifest_rows:
        exp_id = str(manifest_row.get("exp_id", "")).strip()
        world_name = str(manifest_row.get("world_name", "")).strip()
        table_name = _table_name(exp_id, "proto_attempt_rows") if exp_id else ""
        table_found = bool(table_name and _table_exists(cur, table_name))
        run_records: list[dict[str, Any]] = []
        if table_found:
            rows = cur.execute(
                f"""
                SELECT day, task_family, strategy_type, payload_json
                FROM {table_name}
                ORDER BY day, t, agent_id, id
                """
            ).fetchall()
        else:
            rows = []
        for day, task_family, strategy_type, payload_json in rows:
            payload = _load_json_object(payload_json)
            auxiliary = _as_dict(payload.get("auxiliary_audit"))
            huys = _as_dict(auxiliary.get("huys_dayan_lite_controllability"))
            policy = _as_dict(auxiliary.get("bayesian_policy_lite"))
            before = _as_dict(huys.get("before_event"))
            after = _as_dict(huys.get("after_event"))
            record = {
                "group_id": str(manifest_row.get("group_id", "")).strip(),
                "config_fingerprint": str(
                    manifest_row.get("config_fingerprint", "")
                ).strip(),
                "pair_index": _safe_int(manifest_row.get("pair_index"), 0),
                "pair_seed": _safe_int(
                    manifest_row.get("pair_seed"),
                    _safe_int(manifest_row.get("seed"), 0),
                ),
                "world_order": _safe_int(manifest_row.get("world_order"), 0),
                "world_name": world_name,
                "exp_id": exp_id,
                "day": _safe_int(day, 0),
                "task_family": str(task_family or ""),
                "actual_strategy": str(strategy_type or ""),
                "has_huys_payload": bool(huys),
                "mode": str(huys.get("mode", "")).strip(),
                "status": str(huys.get("status", "")).strip(),
                "reference_mode": str(policy.get("reference_mode", "")).strip(),
                "lambda_llm": _safe_float(policy.get("lambda_llm"), None),
                "max_delta": _safe_float(
                    config_payload.get("PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA"),
                    None,
                ),
                "utility_profile": str(policy.get("utility_profile", "")).strip(),
                "intervention_applied": huys.get("intervention_applied"),
                "modulation_family": str(huys.get("modulation_family", "")).strip(),
                "modulation_status": str(huys.get("modulation_status", "")).strip(),
                "controllability_gate_open": huys.get("controllability_gate_open"),
                "best_nonavoid_action": str(
                    huys.get("best_nonavoid_action", "")
                ).strip(),
                "best_nonavoid_source": str(
                    huys.get("best_nonavoid_source", "")
                ).strip(),
                "uniform_mix_gamma": _safe_float(
                    huys.get("uniform_mix_gamma"),
                    None,
                ),
                "reference_mix_gamma": _safe_float(
                    huys.get("reference_mix_gamma"),
                    None,
                ),
                "control_centered_low_c_target": str(
                    huys.get("control_centered_low_c_target", "")
                ).strip(),
                "removed_avoid_mass": _safe_float(
                    huys.get("removed_avoid_mass"),
                    None,
                ),
                "total_variation_distance_from_phase4_pi_final": _safe_float(
                    huys.get("total_variation_distance_from_phase4_pi_final"),
                    None,
                ),
                "max_abs_controllability_delta": _safe_float(
                    huys.get("max_abs_controllability_delta"),
                    None,
                ),
                "uses_post_outcome_information_for_controllability_policy": (
                    huys.get("uses_post_outcome_information_for_controllability_policy")
                ),
                "low_c_directional_help_shift_enabled": huys.get(
                    "low_c_directional_help_shift_enabled"
                ),
                "extreme_low_c_avoid_shift_enabled": huys.get(
                    "extreme_low_c_avoid_shift_enabled"
                ),
                "C_family_before_event": _safe_float(
                    before.get("shrunk_c_family"),
                    None,
                ),
                "raw_c_family_before_event": _safe_float(
                    before.get("raw_c_family"),
                    None,
                ),
                "family_confidence_before_event": _safe_float(
                    before.get("family_confidence"),
                    None,
                ),
                "entropy_control_before_event": _safe_float(
                    before.get("entropy_control"),
                    None,
                ),
                "action_contrast_control_before_event": _safe_float(
                    before.get("action_contrast_control"),
                    None,
                ),
                "reward_control_chi_lite_before_event": _safe_float(
                    before.get("reward_control_chi_lite"),
                    None,
                ),
                "global_controllability_trace_before": _safe_float(
                    before.get("global_controllability_trace"),
                    None,
                ),
                "C_family_after_event": _safe_float(
                    after.get("shrunk_c_family"),
                    None,
                ),
                "raw_c_family_after_event": _safe_float(
                    after.get("raw_c_family"),
                    None,
                ),
                "global_controllability_trace_after": _safe_float(
                    after.get("global_controllability_trace_after"),
                    None,
                ),
                "would_update_global": after.get("would_update_global"),
            }
            for action in POLICY_ACTIONS:
                suffix = "help" if action == "seek_help_then_attempt" else action.replace(
                    "attempt_self",
                    "attempt",
                )
                pi_base = _as_dict(huys.get("pi_base_before_controllability"))
                pi_reference = _as_dict(huys.get("pi_reference_for_control_centered"))
                pi_final = _as_dict(huys.get("pi_final_controllability"))
                final_delta = _as_dict(
                    huys.get("final_delta_after_controllability_floor")
                )
                record[f"pi_base_{suffix}"] = _safe_float(pi_base.get(action), None)
                record[f"pi_reference_for_control_centered_{suffix}"] = _safe_float(
                    pi_reference.get(action),
                    None,
                )
                record[f"pi_final_controllability_{suffix}"] = _safe_float(
                    pi_final.get(action),
                    None,
                )
                record[f"final_delta_controllability_{suffix}"] = _safe_float(
                    final_delta.get(action),
                    None,
                )
            records.append(record)
            run_records.append(record)
        qc_rows.append(
            {
                "exp_id": exp_id,
                "world_name": world_name,
                "table_name": table_name,
                "table_found": int(table_found),
                "row_count": len(rows),
                "huys_payload_count": sum(1 for record in run_records if record["has_huys_payload"]),
            }
        )
    return records, qc_rows


def _summary(records: list[dict[str, Any]], group_id: str) -> dict[str, Any]:
    total = len(records)
    payload_count = sum(1 for record in records if record.get("has_huys_payload"))
    leak_count = sum(
        1
        for record in records
        if record.get("has_huys_payload")
        and record.get("uses_post_outcome_information_for_controllability_policy")
        is True
    )
    intervention_count = sum(
        1
        for record in records
        if record.get("has_huys_payload") and record.get("intervention_applied") is True
    )
    return {
        "group_id": group_id,
        "row_count": total,
        "huys_payload_count": payload_count,
        "huys_payload_coverage": _ratio(payload_count, total),
        "uses_post_outcome_information_true_count": leak_count,
        "intervention_applied_count": intervention_count,
        "intervention_applied_rate": _ratio(intervention_count, payload_count),
        "mean_c_family_before_event": _mean(
            [record.get("C_family_before_event") for record in records]
        ),
        "mean_c_family_after_event": _mean(
            [record.get("C_family_after_event") for record in records]
        ),
        "mean_family_confidence_before_event": _mean(
            [record.get("family_confidence_before_event") for record in records]
        ),
        "mean_entropy_control_before_event": _mean(
            [record.get("entropy_control_before_event") for record in records]
        ),
        "mean_action_contrast_control_before_event": _mean(
            [record.get("action_contrast_control_before_event") for record in records]
        ),
        "mean_reward_control_chi_lite_before_event": _mean(
            [record.get("reward_control_chi_lite_before_event") for record in records]
        ),
        "mean_total_variation_distance_from_phase4_pi_final": _mean(
            [
                record.get("total_variation_distance_from_phase4_pi_final")
                for record in records
            ]
        ),
        "mean_reference_mix_gamma": _mean(
            [record.get("reference_mix_gamma") for record in records]
        ),
        "mean_pi_reference_for_control_centered_attempt": _mean(
            [
                record.get("pi_reference_for_control_centered_attempt")
                for record in records
            ]
        ),
        "mean_pi_reference_for_control_centered_help": _mean(
            [
                record.get("pi_reference_for_control_centered_help")
                for record in records
            ]
        ),
        "mean_pi_reference_for_control_centered_avoid": _mean(
            [
                record.get("pi_reference_for_control_centered_avoid")
                for record in records
            ]
        ),
        "max_total_variation_distance_from_phase4_pi_final": max(
            [
                float(record.get("total_variation_distance_from_phase4_pi_final"))
                for record in records
                if record.get("total_variation_distance_from_phase4_pi_final") is not None
            ]
            or [0.0]
        ),
        "reference_modes": _unique_join(records, "reference_mode"),
        "utility_profiles": _unique_join(records, "utility_profile"),
        "modulation_families": _unique_join(records, "modulation_family"),
        "modulation_statuses": _unique_join(records, "modulation_status"),
        "control_centered_low_c_targets": _unique_join(
            records,
            "control_centered_low_c_target",
        ),
    }


def _group_records(records: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(tuple(record.get(key) for key in keys), []).append(record)
    rows: list[dict[str, Any]] = []
    for key_values, group in sorted(grouped.items(), key=lambda item: item[0]):
        row = {key: value for key, value in zip(keys, key_values)}
        row.update(_summary(group, str(group[0].get("group_id", ""))))
        rows.append(row)
    return rows


def _lagged_prediction(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(
            (
                str(record.get("world_name", "")),
                str(record.get("task_family", "")),
                _safe_int(record.get("day"), 0),
            ),
            [],
        ).append(record)
    day_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for key, group in grouped.items():
        strategies = [str(record.get("actual_strategy", "")) for record in group]
        total = len(strategies)
        day_rows[key] = {
            "world_name": key[0],
            "task_family": key[1],
            "day": key[2],
            "c_family_after_event": _mean(
                [record.get("C_family_after_event") for record in group]
            ),
            "avoid_rate": _ratio(strategies.count("avoid"), total),
            "attempt_rate": _ratio(strategies.count("attempt_self"), total),
            "help_seek_rate": _ratio(strategies.count("seek_help_then_attempt"), total),
        }
    rows: list[dict[str, Any]] = []
    for (world_name, task_family, day), current in sorted(day_rows.items()):
        prev = day_rows.get((world_name, task_family, day - 1))
        if not prev:
            continue
        rows.append(
            {
                "world_name": world_name,
                "task_family": task_family,
                "day": day,
                "c_family_after_event_day_t_minus_1": prev.get(
                    "c_family_after_event"
                ),
                "avoid_rate_day_t": current.get("avoid_rate"),
                "attempt_rate_day_t": current.get("attempt_rate"),
                "help_seek_rate_day_t": current.get("help_seek_rate"),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def run_analysis(
    *,
    manifest_json: Path,
    db_path: Path,
    out_dir: Path,
) -> dict[str, Path]:
    manifest_rows = _load_manifest(manifest_json)
    group_id = _group_id_from_manifest(manifest_json, manifest_rows)
    config_payload = _load_config_payload(manifest_json, group_id)
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        records, qc_rows = _extract_records(
            cur=cur,
            manifest_rows=manifest_rows,
            config_payload=config_payload,
        )
    outputs = {
        f"huys_dayan_lite_summary_{group_id}.csv": [_summary(records, group_id)],
        f"huys_dayan_lite_by_world_{group_id}.csv": _group_records(
            records,
            ("world_name",),
        ),
        f"huys_dayan_lite_by_world_day_{group_id}.csv": _group_records(
            records,
            ("world_name", "day"),
        ),
        f"huys_dayan_lite_by_task_family_{group_id}.csv": _group_records(
            records,
            ("task_family",),
        ),
        f"huys_dayan_lite_lagged_prediction_{group_id}.csv": _lagged_prediction(
            records
        ),
        f"huys_dayan_lite_qc_{group_id}.csv": qc_rows,
    }
    written: dict[str, Path] = {}
    for filename, rows in outputs.items():
        path = out_dir / filename
        _write_csv(path, rows)
        written[filename] = path
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-json", required=True, type=Path)
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    outputs = run_analysis(
        manifest_json=args.manifest_json,
        db_path=args.db_path,
        out_dir=args.out_dir,
    )
    for path in outputs.values():
        print(path)


if __name__ == "__main__":
    main()
