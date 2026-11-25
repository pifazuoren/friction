"""Replay the archived v3 device's valid Day 4 decisions with the v4 count rule.

Generates an offline counterfactual before opening labels for retrospective scoring.
The original error audit supplies failures for both methods.
"""

import argparse
import hashlib
import json
from pathlib import Path

from analysis_entry_calibration_comparison import compare, load_csv, write_csv
from proto.app_entry.bundle import HourlyAppEntryBundle, derive_primary_context
from proto.app_entry.habit_memory import (
    build_calibrated_intensity_profile,
    update_habit_memory_from_bundle,
)
from proto.app_entry.planner import CALIBRATED_PLAN_VERSION, _calibrated_counts


EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
DATA = ROOT / "agentsociety_data/elderly/10person_v3"
REFERENCE = DATA / "talkingdata_elderly_10_reference_hourly_bundle_day1_3.csv"
LABELS = DATA / "talkingdata_elderly_10_validation_hourly_bundle_day4_7.csv"
GROUP = "smoke_phase3a_plan_v3_1agent_day4_seed101"
ARCHIVE = EXAMPLE / "analysis" / f"app_entry_rollout_hourly_{GROUP}.csv"
ERRORS = EXAMPLE / "analysis" / f"app_entry_rollout_errors_{GROUP}.csv"
DEFAULT_OUTPUT = ROOT / "report/2026结项/20261125入口校准/固定历史决策校准"


def build_reference_memory(path, device):
    bundles = {}
    for row in load_csv(path):
        if int(row["day_index"]) not in (1, 2, 3) or row["split_role"] != "calibration_replay":
            raise ValueError("Expected only Day 1–3 reference rows")
        if row["device_id"] == device:
            bundle = HourlyAppEntryBundle.from_row(row)
            key = (bundle.day, bundle.hour)
            if key in bundles:
                raise ValueError(f"Duplicate reference hour {key}")
            bundles[key] = bundle
    if set(bundles) != {(day, hour) for day in (1, 2, 3) for hour in range(24)}:
        raise ValueError("Expected all 72 reference hours")
    memory = {}
    for key in sorted(bundles):
        memory = update_habit_memory_from_bundle(memory, bundles[key])
    return memory


def recalculate(reference, archive):
    rows = load_csv(archive)
    devices = {r["device_id"] for r in rows}
    hours = {int(r["hour"]) for r in rows}
    if len(devices) != 1 or len(rows) != 23 or hours != set(range(24)) - {19}:
        raise ValueError("Expected the archived single device and its 23 valid hours")
    memory = build_reference_memory(reference, devices.pop())
    predictions = []
    for row in sorted(rows, key=lambda r: int(r["hour"])):
        source = (
            row["group_id"], row["plan_prompt_version"], row["talkingdata_day"],
            row["world_name"], row["uses_validation_data"],
        )
        if source != (GROUP, "app_entry_plan_v3", "4", "baseline_low_friction", "0"):
            raise ValueError("Unexpected source, prompt, phase, world or evidence flag")
        old = HourlyAppEntryBundle.from_dict({
            "device_id": row["device_id"], "day": 4, "hour": row["hour"],
            "active": row["active"], "app_context_counts": json.loads(row["app_context_counts_json"]),
            "primary_context": row["primary_context"],
            "active_event_app_exposures": row["active_event_app_exposures"],
        })
        profile = build_calibrated_intensity_profile(memory, hour=old.hour)
        counts = _calibrated_counts(old.app_context_counts, profile["exposures_if_active"]) if old.active else {}
        predictions.append({
            "device_id": old.device_id, "talkingdata_day": old.day, "hour": old.hour,
            "active": int(old.active), "active_event_app_exposures": sum(counts.values()),
            "app_context_counts_json": json.dumps(counts, sort_keys=True),
            "primary_context": derive_primary_context(counts), "world_name": row["world_name"],
            "exp_id": row["exp_id"], "source": "offline_fixed_v3_decisions_v4_count_rule",
            "archived_exposures": old.active_event_app_exposures,
            "archived_weights_json": row["app_context_counts_json"],
            "reference_mean_exposures": profile["same_hour_mean_exposures"],
            "uses_validation_data": 0, "new_api_requests": 0,
        })
    return predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    output = parser.parse_args().output_dir
    predictions = recalculate(REFERENCE, ARCHIVE)
    failures = load_csv(ERRORS)
    archived_error_keys = [
        (row["group_id"], row["exp_id"], row["device_id"], row["talkingdata_day"],
         row["hour"], row["entry_status"]) for row in failures
    ]
    expected_error = (GROUP, predictions[0]["exp_id"], predictions[0]["device_id"],
                      "4", "19", "llm_rollout_error")
    if archived_error_keys != [expected_error]:
        raise ValueError("The archive must retain the original device's failed hour 19")
    output.mkdir(parents=True, exist_ok=True)
    derived = output / "recounted_predictions.csv"
    write_csv(derived, predictions)
    methods = [("recorded_v3", ARCHIVE, ERRORS), ("fixed_v3_v4_intensity", derived, ERRORS)]
    summary, hourly = compare(REFERENCE, LABELS, methods)
    write_csv(output / "summary.csv", summary)
    write_csv(output / "hourly.csv", hourly)
    sources = [REFERENCE, ARCHIVE, ERRORS, LABELS, Path(__file__).resolve(),
               EXAMPLE / "proto/app_entry/habit_memory.py", EXAMPLE / "proto/app_entry/planner.py",
               EXAMPLE / "analysis_entry_calibration_comparison.py"]
    manifest = {
        "method": "固定历史v3的逐小时活跃决策，将原场景计数作为相对权重，仅替换数量计算。",
        "count_rule": CALIBRATED_PLAN_VERSION,
        "historical_group": GROUP, "new_api_requests": 0, "reference_device_hours": 72,
        "expected_day4_hours": 24, "scored_model_hours": len(predictions), "failed_hours": [19],
        "evaluation": "先生成并保存预测，再读取已检查过的第4天标签做回顾性对照。没有重新运行LLM或更新仿真后续轨迹。",
        "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    (output / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
