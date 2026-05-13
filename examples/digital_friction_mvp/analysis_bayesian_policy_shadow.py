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
DEFAULT_UTILITY_PROFILE = "shadow_v1"


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


def _default_utility_profile(config_payload: dict[str, Any]) -> str:
    value = str(
        config_payload.get(
            "PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE",
            DEFAULT_UTILITY_PROFILE,
        )
        or DEFAULT_UTILITY_PROFILE
    ).strip()
    return value or DEFAULT_UTILITY_PROFILE


def _top_action(pi: dict[str, Any]) -> str:
    values = {
        action: _safe_float(pi.get(action), None)
        for action in POLICY_ACTIONS
    }
    valid = {action: value for action, value in values.items() if value is not None}
    if not valid:
        return ""
    return max(valid, key=lambda action: float(valid[action]))


def _top_probability(pi: dict[str, Any]) -> float | None:
    values = [_safe_float(pi.get(action), None) for action in POLICY_ACTIONS]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _action_suffix(action: str) -> str:
    return "help" if action == "seek_help_then_attempt" else action.replace(
        "attempt_self",
        "attempt",
    )


def _mean(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return sum(valid) / len(valid) if valid else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else numerator / denominator


def _pearson(xs: list[float | None], ys: list[float | None]) -> float | None:
    pairs = [
        (float(x), float(y))
        for x, y in zip(xs, ys)
        if x is not None and y is not None
    ]
    if len(pairs) < 2:
        return None
    x_values = [x for x, _ in pairs]
    y_values = [y for _, y in pairs]
    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(y_values) / len(y_values)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_values))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_values))
    denominator = denom_x * denom_y
    return None if denominator <= 0.0 else numerator / denominator


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return round(value, 10)
    return value


def _unique_join(records: list[dict[str, Any]], key: str) -> str:
    values = sorted({str(record.get(key, "")).strip() for record in records if record.get(key) not in (None, "")})
    return "|".join(values)


def _extract_attempt_records(
    *,
    cur: sqlite3.Cursor,
    manifest_rows: list[dict[str, Any]],
    config_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    qc_rows: list[dict[str, Any]] = []
    default_profile = _default_utility_profile(config_payload)

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
            auxiliary = payload.get("auxiliary_audit")
            auxiliary = auxiliary if isinstance(auxiliary, dict) else {}
            policy = auxiliary.get("bayesian_policy_lite")
            policy = policy if isinstance(policy, dict) else {}
            control = auxiliary.get("bayesian_control")
            control = control if isinstance(control, dict) else {}
            pi = policy.get("pi_bayes_shadow")
            pi = _as_dict(pi)
            pi_prior = _as_dict(policy.get("pi_prior"))
            pi_llm = _as_dict(policy.get("pi_llm"))
            pi_semantic = _as_dict(policy.get("pi_semantic"))
            pi_ref = _as_dict(policy.get("pi_ref"))
            pi_bayes = _as_dict(policy.get("pi_bayes"))
            pi_final = _as_dict(policy.get("pi_final"))
            semantic_delta = _as_dict(policy.get("semantic_delta_from_prior"))
            delta_applied = _as_dict(policy.get("delta_applied"))
            bayesian_shift_before_floor = _as_dict(
                policy.get("bayesian_shift_before_floor")
            )
            final_delta_after_floor = _as_dict(policy.get("final_delta_after_floor"))
            confidence = policy.get("confidence_by_action")
            confidence = _as_dict(confidence)
            entropy = policy.get("posterior_entropy_by_action")
            entropy = _as_dict(entropy)
            top_action = _top_action(pi)
            utility_profile = str(
                policy.get("utility_profile")
                or default_profile
            ).strip() or DEFAULT_UTILITY_PROFILE
            record = {
                "group_id": str(manifest_row.get("group_id", "")).strip(),
                "config_fingerprint": str(
                    manifest_row.get("config_fingerprint", "")
                ).strip(),
                "utility_profile": utility_profile,
                "reference_mode": str(policy.get("reference_mode", "")).strip(),
                "lambda_llm": _safe_float(policy.get("lambda_llm"), None),
                "min_llm_confidence": _safe_float(
                    policy.get("min_llm_confidence"),
                    None,
                ),
                "semantic_fallback_used": policy.get("semantic_fallback_used"),
                "semantic_fallback_reason": str(
                    policy.get("semantic_fallback_reason", "")
                ),
                "rule_fallback_used": policy.get("rule_fallback_used"),
                "rule_fallback_reason": str(policy.get("rule_fallback_reason", "")),
                "safety_guard_status": str(policy.get("safety_guard_status", "")),
                "intervention_applied": policy.get("intervention_applied"),
                "total_variation_distance": _safe_float(
                    policy.get("total_variation_distance"),
                    None,
                ),
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
                "has_policy_payload": bool(policy),
                "has_control_payload": bool(control),
                "policy_status": str(policy.get("status", "")),
                "policy_mode": str(policy.get("mode", "")),
                "pi_attempt": _safe_float(pi.get("attempt_self"), None),
                "pi_help": _safe_float(pi.get("seek_help_then_attempt"), None),
                "pi_avoid": _safe_float(pi.get("avoid"), None),
                "shadow_top_action": top_action,
                "shadow_top_prob": _top_probability(pi),
                "actual_matches_shadow_top": int(
                    bool(top_action) and top_action == str(strategy_type or "")
                ),
                "uses_post_outcome_information_for_policy": policy.get(
                    "uses_post_outcome_information_for_policy"
                ),
                "strategy_unchanged": policy.get("strategy_unchanged"),
                "post_outcome_fields_ignored_for_policy": "|".join(
                    str(item)
                    for item in policy.get(
                        "post_outcome_fields_ignored_for_policy",
                        [],
                    )
                    if item
                )
                if isinstance(
                    policy.get("post_outcome_fields_ignored_for_policy"),
                    list,
                )
                else "",
                "c_hat_before": _safe_float(control.get("belief_before"), None),
                "c_hat_after": _safe_float(control.get("belief_after"), None),
            }
            for action in POLICY_ACTIONS:
                suffix = _action_suffix(action)
                record[f"pi_prior_{suffix}"] = _safe_float(
                    pi_prior.get(action),
                    None,
                )
                record[f"pi_llm_{suffix}"] = _safe_float(pi_llm.get(action), None)
                record[f"pi_semantic_{suffix}"] = _safe_float(
                    pi_semantic.get(action),
                    None,
                )
                record[f"pi_ref_{suffix}"] = _safe_float(pi_ref.get(action), None)
                record[f"pi_bayes_{suffix}"] = _safe_float(pi_bayes.get(action), None)
                record[f"pi_final_{suffix}"] = _safe_float(pi_final.get(action), None)
                record[f"semantic_delta_{suffix}"] = _safe_float(
                    semantic_delta.get(action),
                    None,
                )
                record[f"delta_applied_{suffix}"] = _safe_float(
                    delta_applied.get(action),
                    None,
                )
                record[f"bayesian_shift_before_floor_{suffix}"] = _safe_float(
                    bayesian_shift_before_floor.get(action),
                    None,
                )
                record[f"final_delta_after_floor_{suffix}"] = _safe_float(
                    final_delta_after_floor.get(action),
                    None,
                )
                record[f"confidence_{suffix}"] = _safe_float(
                    confidence.get(action),
                    None,
                )
                record[f"entropy_{suffix}"] = _safe_float(entropy.get(action), None)
            records.append(record)
            run_records.append(record)

        qc_rows.append(
            _aggregate_records(
                run_records,
                extra_fields={
                    "group_id": str(manifest_row.get("group_id", "")).strip(),
                    "pair_index": _safe_int(manifest_row.get("pair_index"), 0),
                    "pair_seed": _safe_int(
                        manifest_row.get("pair_seed"),
                        _safe_int(manifest_row.get("seed"), 0),
                    ),
                    "world_order": _safe_int(manifest_row.get("world_order"), 0),
                    "world_name": world_name,
                    "exp_id": exp_id,
                    "status": str(manifest_row.get("status", "")).strip(),
                    "table_name": table_name,
                    "table_found": int(table_found),
                    "config_fingerprint": str(
                        manifest_row.get("config_fingerprint", "")
                    ).strip(),
                    "utility_profile": (
                        _unique_join(run_records, "utility_profile")
                        if run_records
                        else default_profile
                    ),
                },
            )
        )
    return records, qc_rows


def _aggregate_records(
    records: list[dict[str, Any]],
    *,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(records)
    policy_count = sum(1 for record in records if record.get("has_policy_payload"))
    control_count = sum(1 for record in records if record.get("has_control_payload"))
    leak_count = sum(
        1
        for record in records
        if record.get("has_policy_payload")
        and record.get("uses_post_outcome_information_for_policy") is not False
    )
    strategy_changed_count = sum(
        1
        for record in records
        if record.get("has_policy_payload") and record.get("strategy_unchanged") is not True
    )
    semantic_fallback_count = sum(
        1
        for record in records
        if record.get("has_policy_payload")
        and record.get("semantic_fallback_used") is True
    )
    rule_fallback_count = sum(
        1
        for record in records
        if record.get("has_policy_payload") and record.get("rule_fallback_used") is True
    )
    safety_guard_fallback_count = sum(
        1
        for record in records
        if record.get("has_policy_payload")
        and str(record.get("safety_guard_status", "")).startswith("fallback")
    )
    intervention_count = sum(
        1
        for record in records
        if record.get("has_policy_payload")
        and record.get("intervention_applied") is True
    )
    aggregate = {
        "row_count": total,
        "policy_payload_count": policy_count,
        "control_payload_count": control_count,
        "policy_payload_coverage": _ratio(policy_count, total),
        "control_payload_coverage": _ratio(control_count, total),
        "uses_post_outcome_information_true_count": leak_count,
        "all_uses_post_outcome_information_false": int(
            policy_count > 0 and leak_count == 0
        ),
        "strategy_changed_count": strategy_changed_count,
        "all_strategy_unchanged": int(policy_count > 0 and strategy_changed_count == 0),
        "semantic_fallback_count": semantic_fallback_count,
        "semantic_fallback_rate": _ratio(semantic_fallback_count, policy_count),
        "rule_fallback_count": rule_fallback_count,
        "rule_fallback_rate": _ratio(rule_fallback_count, policy_count),
        "safety_guard_fallback_count": safety_guard_fallback_count,
        "safety_guard_fallback_rate": _ratio(
            safety_guard_fallback_count,
            policy_count,
        ),
        "intervention_applied_count": intervention_count,
        "intervention_applied_rate": _ratio(intervention_count, policy_count),
        "mean_total_variation_distance": _mean(
            [record.get("total_variation_distance") for record in records]
        ),
        "max_total_variation_distance": max(
            [
                float(record.get("total_variation_distance"))
                for record in records
                if record.get("total_variation_distance") is not None
            ],
            default=None,
        ),
        "ignored_post_outcome_fields_seen_count": sum(
            1 for record in records if record.get("post_outcome_fields_ignored_for_policy")
        ),
        "mean_pi_attempt": _mean([record.get("pi_attempt") for record in records]),
        "mean_pi_help": _mean([record.get("pi_help") for record in records]),
        "mean_pi_avoid": _mean([record.get("pi_avoid") for record in records]),
        "mean_shadow_top_prob": _mean(
            [record.get("shadow_top_prob") for record in records]
        ),
        "actual_shadow_top_match_rate": _mean(
            [
                float(record.get("actual_matches_shadow_top", 0))
                for record in records
                if record.get("shadow_top_action")
            ]
        ),
        "c_hat_before_mean": _mean(
            [record.get("c_hat_before") for record in records]
        ),
        "c_hat_after_mean": _mean([record.get("c_hat_after") for record in records]),
        "c_hat_before_pi_avoid_corr": _pearson(
            [record.get("c_hat_before") for record in records],
            [record.get("pi_avoid") for record in records],
        ),
        "c_hat_after_pi_avoid_corr_post_update_audit": _pearson(
            [record.get("c_hat_after") for record in records],
            [record.get("pi_avoid") for record in records],
        ),
    }
    for action in POLICY_ACTIONS:
        label = _action_suffix(action)
        aggregate[f"actual_{label}_share"] = _ratio(
            sum(1 for record in records if record.get("actual_strategy") == action),
            total,
        )
        aggregate[f"shadow_top_{label}_share"] = _ratio(
            sum(1 for record in records if record.get("shadow_top_action") == action),
            total,
        )
        aggregate[f"mean_confidence_{label}"] = _mean(
            [record.get(f"confidence_{label}") for record in records]
        )
        aggregate[f"mean_entropy_{label}"] = _mean(
            [record.get(f"entropy_{label}") for record in records]
        )
        for prefix in (
            "pi_prior",
            "pi_llm",
            "pi_semantic",
            "pi_ref",
            "pi_bayes",
            "pi_final",
            "semantic_delta",
            "delta_applied",
            "bayesian_shift_before_floor",
            "final_delta_after_floor",
        ):
            aggregate[f"mean_{prefix}_{label}"] = _mean(
                [record.get(f"{prefix}_{label}") for record in records]
            )
    if extra_fields:
        return {**extra_fields, **aggregate}
    return aggregate


def _group_records(
    records: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        group_key = tuple(record.get(key, "") for key in keys)
        buckets.setdefault(group_key, []).append(record)
    rows: list[dict[str, Any]] = []
    for group_key, bucket in sorted(buckets.items()):
        extra = {key: group_key[index] for index, key in enumerate(keys)}
        extra["group_id"] = _unique_join(bucket, "group_id")
        extra["config_fingerprint"] = _unique_join(bucket, "config_fingerprint")
        extra["utility_profile"] = _unique_join(bucket, "utility_profile")
        rows.append(_aggregate_records(bucket, extra_fields=extra))
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def run_analysis(
    *,
    manifest_json: Path,
    db_path: Path,
    out_dir: Path,
) -> list[Path]:
    manifest_rows = _load_manifest(manifest_json)
    group_id = _group_id_from_manifest(manifest_json, manifest_rows)
    config_payload = _load_config_payload(manifest_json, group_id)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        records, qc_rows = _extract_attempt_records(
            cur=cur,
            manifest_rows=manifest_rows,
            config_payload=config_payload,
        )
    finally:
        conn.close()

    summary_row = _aggregate_records(
        records,
        extra_fields={
            "group_id": group_id,
            "config_fingerprint": _unique_join(records, "config_fingerprint"),
            "utility_profile": _unique_join(records, "utility_profile")
            or _default_utility_profile(config_payload),
        },
    )
    outputs = {
        f"bayesian_policy_shadow_summary_{group_id}.csv": [summary_row],
        f"bayesian_policy_shadow_by_world_{group_id}.csv": _group_records(
            records,
            ("world_name",),
        ),
        f"bayesian_policy_shadow_by_world_day_{group_id}.csv": _group_records(
            records,
            ("world_name", "day"),
        ),
        f"bayesian_policy_shadow_by_task_family_{group_id}.csv": _group_records(
            records,
            ("task_family",),
        ),
        f"bayesian_policy_shadow_qc_{group_id}.csv": qc_rows,
    }
    output_paths: list[Path] = []
    for filename, rows in outputs.items():
        path = out_dir / filename
        _write_csv(path, rows)
        output_paths.append(path)
    return output_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Bayesian policy-lite shadow payloads."
    )
    parser.add_argument("--manifest-json", required=True, type=Path)
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("examples/digital_friction_mvp/analysis"),
    )
    args = parser.parse_args()
    output_paths = run_analysis(
        manifest_json=args.manifest_json,
        db_path=args.db_path,
        out_dir=args.out_dir,
    )
    for path in output_paths:
        print(path)


if __name__ == "__main__":
    main()
