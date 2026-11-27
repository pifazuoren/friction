"""Score Day 4 baseline-world app-entry predictions and their common valid hours.

Inputs are the project's hourly bundle, rollout and optional error-audit CSVs.
History uses days 1–3 only: exposure count is the personal same-hour median.
For a positive median, predict the modal primary context among active reference
days, breaking ties by greatest lexical order, as in the rollout evaluator.
Both observed and generated contexts are derived from their exposure counts
using the same project rule. Missing/failed model hours have no predicted value.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
from statistics import mean, median

from analysis_app_entry_validation import _parse_bool, _parse_context_counts
from proto.app_entry.bundle import NO_APP_CONTEXT, HourlyAppEntryBundle, derive_primary_context


DATA_DIR = Path(__file__).resolve().parents[2] / "agentsociety_data/elderly/10person_v3"
HISTORY = "personal_history"
COMMUNICATION = "communication_social_context"
OVERALL = "personal_overall"
CONSTANT = "constant_communication"
SHUFFLED = "personal_history_shuffled"


@dataclass(frozen=True)
class Prediction:
    count: int
    context: str


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No CSV header in {path}")
        return list(reader)


def parse_bundle(row, day):
    count = int(row["active_event_app_exposures"])
    contexts = _parse_context_counts(row["app_context_counts_json"])
    primary = derive_primary_context(contexts)
    bundle = HourlyAppEntryBundle.from_dict({
        "device_id": row["device_id"], "day": day, "hour": row["hour"],
        "active": _parse_bool(row["active"]), "active_event_app_exposures": count,
        "app_context_counts": contexts, "primary_context": primary,
    })
    return Prediction(bundle.active_event_app_exposures, bundle.primary_context)


def load_observations(path, days):
    result = {}
    for row in load_csv(path):
        day = int(row["day_index"])
        if day not in days:
            continue
        key = (row["device_id"], day, int(row["hour"]))
        if key in result:
            raise ValueError(f"Duplicate observation {key} in {path}")
        result[key] = parse_bundle(row, day)
    return result


def load_model(rollout, errors, target_day):
    valid, failed = {}, set()
    run_ids = set()
    for path, is_error_log in [(rollout, False), (errors, True)]:
        if path is None:
            continue
        for row in load_csv(path):
            if row.get("world_name", "baseline_low_friction") != "baseline_low_friction":
                raise ValueError(f"Expected only baseline-world rows in {path}")
            if _parse_bool(row.get("uses_validation_data", False)):
                raise ValueError(f"Rollout used held-out data in {path}")
            day = int(row["talkingdata_day"])
            if day != target_day:
                continue
            key = (row["device_id"], day, int(row["hour"]))
            if key in valid or key in failed:
                raise ValueError(f"Overlapping or duplicate rollout and error key {key} in {path}")
            if row.get("exp_id"):
                run_ids.add(row["exp_id"])
            if is_error_log or row.get("entry_status") == "llm_rollout_error":
                if not key[0] or not 0 <= key[2] < 24:
                    raise ValueError(f"Invalid failed-hour key {key}")
                failed.add(key)
            else:
                valid[key] = parse_bundle(row, day)
    if len(run_ids) > 1:
        raise ValueError("Expected each rollout/error pair to describe one run")
    return valid, failed


def build_history(reference, keys):
    history = {}
    for device, day, hour in keys:
        records = [reference[device, d, hour] for d in (1, 2, 3)]
        count = int(median(r.count for r in records))
        active_contexts = Counter(r.context for r in records if r.count > 0)
        context = derive_primary_context(active_contexts) if count else NO_APP_CONTEXT
        history[device, day, hour] = Prediction(count, context)
    return history


def shuffled_hours(device, day, seed):
    """Map each destination hour to a source hour within the same replay day."""
    order = list(range(24))
    digest = hashlib.sha256(f"{seed}|{device}|{day}".encode()).digest()
    random.Random(digest).shuffle(order)
    return order


def write_shuffled_reference(reference_path, output, seed):
    """Permute complete activity records, retaining the destination date/hour keys."""
    groups = defaultdict(dict)
    for row in load_csv(reference_path):
        day, hour = int(row["day_index"]), int(row["hour"])
        group = groups[row["device_id"], day]
        if day not in (1, 2, 3) or hour in group:
            raise ValueError("expected unique reference hours from days 1–3")
        group[hour] = row
    result = []
    time_columns = ("device_id", "day_index", "hour", "date", "hour_index", "hour_key")
    for (device, day), group in sorted(groups.items()):
        if set(group) != set(range(24)):
            raise ValueError("cannot shuffle an incomplete device-day")
        for hour, source in enumerate(shuffled_hours(device, day, seed)):
            row = group[source].copy()
            row.update({key: group[hour][key] for key in time_columns if key in row})
            result.append(row)
    write_csv(output, result)


def summarize(observed, predictions, failures, selected, common):
    rows = []
    for method, model in predictions.items():
        matched = selected.intersection(model)
        failed = selected.intersection(failures[method])
        for scope, evaluated in (("method_valid", matched), ("common_valid", selected & common)):
            errors = [abs(model[k].count - observed[k].count) for k in evaluated]
            matches = sum(model[k].context == observed[k].context for k in evaluated)
            active = [k for k in evaluated if observed[k].count > 0]
            idle = [k for k in evaluated if not observed[k].count]
            predicted_idle = sum(model[k].count == 0 for k in evaluated)
            idle_hits = sum(model[k].count == 0 for k in idle)
            totals = Counter(observed[k].context for k in evaluated)
            correct = Counter(observed[k].context for k in evaluated if observed[k].context == model[k].context)
            recalls = {name: correct[name] / n for name, n in sorted(totals.items())}
            non_comm = len(evaluated) - totals[COMMUNICATION]
            rows.append({
                "method": method, "hour_scope": scope, "expected_hours": len(selected),
                "valid_hours": len(matched), "error_hours": len(failed),
                "missing_hours": len(selected) - len(matched) - len(failed),
                "coverage": len(matched) / len(selected), "scored_hours": len(evaluated),
                "exposure_mae": mean(errors) if errors else None,
                "failure_rate": len(failed) / len(selected),
                "idle_precision": idle_hits / predicted_idle if predicted_idle else None,
                "idle_recall": idle_hits / len(idle) if idle else None,
                "observed_idle_scored": len(idle), "predicted_idle_scored": predicted_idle,
                "idle_correct": idle_hits, "non_communication_scored": non_comm,
                "non_communication_recall": (matches - correct[COMMUNICATION]) / non_comm if non_comm else None,
                "macro_recall": mean(recalls.values()) if recalls else None,
                "class_recall_json": json.dumps(recalls, sort_keys=True),
                "exposure_mae_observed_active": mean(abs(model[k].count - observed[k].count) for k in active) if active else None,
                "exposure_mae_observed_idle": mean(model[k].count for k in idle) if idle else None,
                "primary_correct": matches,
                "primary_accuracy": matches / len(evaluated) if evaluated else None,
                "observed_active_scored": len(active),
                "primary_accuracy_on_observed_active": (
                    mean(model[k].context == observed[k].context for k in active) if active else None
                ),
            })
    return rows


def compare(reference_path, heldout_path, inputs, devices=(), day=4, shuffle_seed=101):
    if day not in (4, 5, 6, 7):
        raise ValueError("Held-out day must be one of 4, 5, 6, 7")
    reference = load_observations(reference_path, {1, 2, 3})
    observed = load_observations(heldout_path, {day})
    predictions, failures = {}, {}
    model_devices = set()
    for method, rollout, errors in inputs:
        if method in predictions or method in {HISTORY, CONSTANT, OVERALL, SHUFFLED}:
            raise ValueError(f"Duplicate or reserved method name: {method}")
        valid, failed = load_model(rollout, errors, day)
        if (valid.keys() | failed) - observed.keys():
            raise ValueError(f"Some {method} device-hour keys lack a held-out observation")
        model_devices.update(k[0] for k in valid.keys() | failed)
        predictions[method], failures[method] = valid, failed
    if devices:
        devices = set(devices)
    elif inputs:
        devices = model_devices
    else:
        devices = {k[0] for k in observed}
    if not devices:
        raise ValueError("No evaluation devices; specify --device if the rollout is empty")
    keys = {(device, day, hour) for device in devices for hour in range(24)}
    if not keys <= observed.keys():
        raise ValueError("Each selected device must have 24 observed target hours")
    ref_keys = {(device, d, hour) for device in devices for d in (1, 2, 3) for hour in range(24)}
    if not ref_keys <= reference.keys():
        raise ValueError("Each selected device must have 72 observed reference hours")
    predictions[HISTORY] = build_history(reference, keys)
    overall, constant, shuffled = {}, {}, {}
    for device in devices:
        records = [reference[device, d, h] for d in (1, 2, 3) for h in range(24)]
        counts = Counter(r.context for r in records)
        modal_context = max(counts, key=lambda ctx: (counts[ctx], ctx))
        modal_count = int(median(r.count for r in records if r.context == modal_context))
        typical_active = [r.count for r in records if r.count > 0]
        active_count = int(median(typical_active)) if typical_active else 1
        for h in range(24):
            overall[device, day, h] = Prediction(modal_count, modal_context)
            constant[device, day, h] = Prediction(active_count, COMMUNICATION)
        for d in (1, 2, 3):
            for h, src in enumerate(shuffled_hours(device, d, shuffle_seed)):
                shuffled[device, d, h] = reference[device, d, src]
    predictions.update({OVERALL: overall, CONSTANT: constant, SHUFFLED: build_history(shuffled, keys)})
    failures.update({name: set() for name in (HISTORY, OVERALL, CONSTANT, SHUFFLED)})
    common = keys.copy()
    for model in predictions.values():
        common.intersection_update(model)
    summary = []
    for level, device, selected in [("all", "", keys)] + [
        ("device", device, {k for k in keys if k[0] == device}) for device in sorted(devices)
    ]:
        for metrics in summarize(observed, predictions, failures, selected, common):
            summary.append({"level": level, "device_id": device, "day": day, **metrics})
    hourly = []
    for key in sorted(keys):
        obs = observed[key]
        for method, model in predictions.items():
            pred = model.get(key)
            status = "valid" if pred else ("failed" if key in failures[method] else "missing")
            hourly.append({
                "device_id": key[0], "day": day, "hour": key[2], "method": method,
                "status": status, "common_valid": int(key in common),
                "observed_count": obs.count, "predicted_count": pred.count if pred else None,
                "absolute_error": abs(pred.count - obs.count) if pred else None,
                "observed_primary": obs.context, "predicted_primary": pred.context if pred else None,
            })
    return summary, hourly


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DATA_DIR / "talkingdata_elderly_10_reference_hourly_bundle_day1_3.csv")
    parser.add_argument("--heldout", type=Path, default=DATA_DIR / "talkingdata_elderly_10_validation_hourly_bundle_day4_7.csv")
    for label in ("old", "new"):
        parser.add_argument(f"--{label}-rollout", type=Path)
        parser.add_argument(f"--{label}-errors", type=Path)
    parser.add_argument("--device", action="append", default=[], help="Repeat to select devices. Without models the default is all devices.")
    parser.add_argument("--day", type=int, default=4, choices=(4, 5, 6, 7))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inputs = []
    for label in ("old", "new"):
        rollout = getattr(args, f"{label}_rollout")
        errors = getattr(args, f"{label}_errors")
        if errors and not rollout:
            parser.error(f"--{label}-errors requires --{label}-rollout")
        if rollout:
            inputs.append((label, rollout, errors))
    summary, hourly = compare(args.reference, args.heldout, inputs, args.device, args.day)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "summary.csv", summary)
    write_csv(args.output_dir / "hourly.csv", hourly)


if __name__ == "__main__":
    main()
