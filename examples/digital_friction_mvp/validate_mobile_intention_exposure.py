#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


MOBILE_INTENTIONS = (
    "check_information",
    "use_payment_or_finance",
    "login_or_verify_account",
    "submit_service_application",
    "upload_or_manage_profile",
    "find_location_or_service",
    "communicate_or_seek_help",
    "browse_entertainment",
    "no_mobile_action",
    "unknown_or_unmapped",
)
TASK_FAMILIES = (
    "information_search_judgment",
    "payment_risk_confirmation",
    "account_login_verification",
    "service_application_submission",
    "profile_form_upload",
    "navigation_service_location",
)


def _load_json(raw_value: Any) -> Any:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if raw_value in (None, ""):
        return {}
    try:
        return json.loads(str(raw_value))
    except json.JSONDecodeError:
        return {}


def _normalize(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, float]:
    total = sum(max(0, counter.get(key, 0)) for key in keys)
    if total <= 0:
        return {key: 0.0 for key in keys}
    return {key: float(max(0, counter.get(key, 0))) / float(total) for key in keys}


def _tvd(left: dict[str, float], right: dict[str, float], keys: tuple[str, ...]) -> float:
    return 0.5 * sum(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) for key in keys)


def _js(left: dict[str, float], right: dict[str, float], keys: tuple[str, ...]) -> float:
    def _kl(p: dict[str, float], q: dict[str, float]) -> float:
        value = 0.0
        for key in keys:
            p_value = float(p.get(key, 0.0))
            q_value = float(q.get(key, 0.0))
            if p_value > 0.0 and q_value > 0.0:
                value += p_value * math.log(p_value / q_value, 2)
        return value

    midpoint = {
        key: 0.5 * (float(left.get(key, 0.0)) + float(right.get(key, 0.0)))
        for key in keys
    }
    return 0.5 * _kl(left, midpoint) + 0.5 * _kl(right, midpoint)


def _target_intention_distribution(targets: dict[str, Any]) -> dict[str, float]:
    global_prior = targets.get("global_prior", {})
    if isinstance(global_prior, dict):
        values = global_prior.get("p_mobile_intention", global_prior)
        if isinstance(values, dict):
            return {key: float(values.get(key, 0.0)) for key in MOBILE_INTENTIONS}
    return {key: 0.0 for key in MOBILE_INTENTIONS}


def _target_task_distribution(targets: dict[str, Any]) -> dict[str, float]:
    values = targets.get("p_task_family", {})
    if not isinstance(values, dict):
        return {key: 0.0 for key in TASK_FAMILIES}
    return {key: float(values.get(key, 0.0)) for key in TASK_FAMILIES}


def _load_task_targets(validation_dir: Path) -> dict[str, Any]:
    path = validation_dir / "task_family_opportunity_prior.json"
    if not path.exists():
        return {}
    payload = _load_json(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_intention_targets(validation_dir: Path) -> dict[str, Any]:
    path = validation_dir / "mobile_intention_prior_by_bucket_hour.json"
    if not path.exists():
        raise FileNotFoundError(f"validation target not found: {path}")
    payload = _load_json(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"validation target must be a JSON object: {path}")
    if not bool(payload.get("uses_validation_data", False)):
        raise ValueError("held-out validation target must be marked uses_validation_data=true")
    return payload


def _load_simulated_distributions(
    status_csv: Path,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    int,
    int,
]:
    intention_counts: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    hour_counts: Counter[str] = Counter()
    entry_hour_counts: Counter[str] = Counter()
    evaluated_count = 0
    task_generated_count = 0
    with status_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status_json = _load_json(row.get("status_json"))
            if not isinstance(status_json, dict):
                continue
            decision = status_json.get("proto_mobile_entry_decision", {})
            if not isinstance(decision, dict) or not decision.get("entry_evaluated"):
                continue
            evaluated_count += 1
            audit = decision.get("audit", {})
            if not isinstance(audit, dict):
                audit = {}
            hour = str(int(float(row.get("t") or 0.0)) // 3600 % 24)
            hour_counts[hour] += 1
            if bool(decision.get("task_generated", False)):
                task_generated_count += 1
                entry_hour_counts[hour] += 1
            intention = str(decision.get("selected_mobile_intention", "")).strip()
            if intention in MOBILE_INTENTIONS:
                intention_counts[intention] += 1
            family = str(decision.get("mapped_task_family", "") or "").strip()
            if bool(decision.get("task_generated", False)) and family in TASK_FAMILIES:
                task_counts[family] += 1
            elif bool(audit.get("task_generated", False)):
                family = str(audit.get("mapped_task_family", "") or "").strip()
                if family in TASK_FAMILIES:
                    task_counts[family] += 1
    hours = tuple(str(hour) for hour in range(24))
    return (
        _normalize(intention_counts, MOBILE_INTENTIONS),
        _normalize(task_counts, TASK_FAMILIES),
        _normalize(hour_counts, hours),
        _normalize(entry_hour_counts, hours),
        evaluated_count,
        task_generated_count,
    )


def write_validation_report(status_csv: Path, validation_dir: Path, out_csv: Path) -> None:
    intention_targets = _load_intention_targets(validation_dir)
    task_targets = _load_task_targets(validation_dir)
    (
        sim_intentions,
        sim_tasks,
        _sim_hours,
        sim_entry_hours,
        evaluated_count,
        task_generated_count,
    ) = _load_simulated_distributions(status_csv)
    target_intentions = _target_intention_distribution(intention_targets)
    target_tasks = _target_task_distribution(task_targets)
    target_hours = {
        str(hour): float(
            intention_targets.get("global_hourly_prior", {})
            .get(str(hour), {})
            .get("p_mobile_intention", {})
            .get("no_mobile_action", 0.0)
        )
        for hour in range(24)
    }
    target_mobile_hours = {
        key: max(0.0, 1.0 - float(value)) for key, value in target_hours.items()
    }
    target_mobile_hours = _normalize(Counter(target_mobile_hours), tuple(str(hour) for hour in range(24)))
    hours = tuple(str(hour) for hour in range(24))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerow(
            {
                "metric": "mobile_intention_tvd",
                "value": f"{_tvd(sim_intentions, target_intentions, MOBILE_INTENTIONS):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "mobile_intention_js",
                "value": f"{_js(sim_intentions, target_intentions, MOBILE_INTENTIONS):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "task_family_opportunity_tvd",
                "value": f"{_tvd(sim_tasks, target_tasks, TASK_FAMILIES):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "task_family_opportunity_js",
                "value": f"{_js(sim_tasks, target_tasks, TASK_FAMILIES):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "hourly_mobile_activity_tvd",
                "value": f"{_tvd(sim_entry_hours, target_mobile_hours, hours):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "sim_unknown_or_unmapped_mass",
                "value": f"{sim_intentions.get('unknown_or_unmapped', 0.0):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "target_unknown_or_unmapped_mass",
                "value": f"{target_intentions.get('unknown_or_unmapped', 0.0):.6f}",
            }
        )
        writer.writerow(
            {
                "metric": "sim_task_generated_per_evaluated_entry",
                "value": (
                    f"{(task_generated_count / evaluated_count):.6f}"
                    if evaluated_count
                    else "0.000000"
                ),
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare simulated mobile-intention exposure to held-out targets."
    )
    parser.add_argument("--status-csv", required=True, type=Path)
    parser.add_argument("--validation-dir", required=True, type=Path)
    parser.add_argument(
        "--out-csv",
        default=Path("examples/digital_friction_mvp/analysis/mobile_intention_exposure_validation.csv"),
        type=Path,
    )
    args = parser.parse_args()
    write_validation_report(args.status_csv, args.validation_dir, args.out_csv)


if __name__ == "__main__":
    main()
