#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MVP_DIR = REPO_ROOT / "examples" / "digital_friction_mvp"
sys.path.insert(0, str(MVP_DIR))

from clean_talkingdata_event_app_context import (  # noqa: E402
    APP_CONTEXTS,
    TASK_ELIGIBLE_CONTEXTS,
    classify_categories,
)


DEFAULT_RAW_DIR = Path(
    os.environ.get("TALKINGDATA_RAW_DIR") or REPO_ROOT.parent / "talkingdata-mobile-user-demographics"
)
DEFAULT_SELECTION_CSV = (
    REPO_ROOT
    / "outputs"
    / "talkingdata_59_phone_prices"
    / "talkingdata_59_device_summary.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "agentsociety_data" / "elderly"
REFERENCE_START = "2016-05-01"
VALIDATION_START = "2016-05-04"
END_EXCLUSIVE = "2016-05-08"


@dataclass(frozen=True, slots=True)
class EventInfo:
    event_id: str
    device_id: str
    timestamp: str
    date: str
    hour: int
    hour_key: str
    day_index: int
    phase: str
    longitude: str
    latitude: str


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _load_selected_people(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        people = {
            str(row["device_id"]).strip(): {key: str(value or "").strip() for key, value in row.items()}
            for row in reader
            if str(row.get("device_id", "")).strip()
        }
    if not people:
        raise ValueError(f"No selected device_id rows found in {path}")
    return people


def _load_app_labels(raw_dir: Path) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    label_to_category: dict[str, str] = {}
    with (raw_dir / "label_categories.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            label_id = str(row.get("label_id", "") or "").strip()
            if label_id:
                label_to_category[label_id] = str(row.get("category", "") or "").strip()

    labels_by_app: defaultdict[str, set[str]] = defaultdict(set)
    categories_by_app: defaultdict[str, set[str]] = defaultdict(set)
    with (raw_dir / "app_labels.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            app_id = str(row.get("app_id", "") or "").strip()
            label_id = str(row.get("label_id", "") or "").strip()
            if not app_id or not label_id:
                continue
            labels_by_app[app_id].add(label_id)
            category = label_to_category.get(label_id, "")
            if category:
                categories_by_app[app_id].add(category)

    return (
        {app_id: tuple(sorted(values, key=lambda item: _safe_int(item, 10**9))) for app_id, values in labels_by_app.items()},
        {app_id: tuple(sorted(values)) for app_id, values in categories_by_app.items()},
    )


def _phase_for_date(date: str) -> str:
    if REFERENCE_START <= date < VALIDATION_START:
        return "replay_day_1_3"
    if VALIDATION_START <= date < END_EXCLUSIVE:
        return "heldout_day_4_7"
    return "outside_window"


def _day_index(date: str) -> int:
    return _safe_int(date[-2:], 0)


def _load_selected_events(raw_dir: Path, selected_ids: set[str]) -> dict[str, EventInfo]:
    events: dict[str, EventInfo] = {}
    with (raw_dir / "events.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            device_id = str(row.get("device_id", "") or "").strip()
            if device_id not in selected_ids:
                continue
            timestamp = str(row.get("timestamp", "") or "").strip()
            date = timestamp[:10]
            if not (REFERENCE_START <= date < END_EXCLUSIVE):
                continue
            event_id = str(row.get("event_id", "") or "").strip()
            if not event_id:
                continue
            hour = _safe_int(timestamp[11:13], 0) if len(timestamp) >= 13 else 0
            events[event_id] = EventInfo(
                event_id=event_id,
                device_id=device_id,
                timestamp=timestamp,
                date=date,
                hour=hour,
                hour_key=f"{date} {hour:02d}:00:00",
                day_index=_day_index(date),
                phase=_phase_for_date(date),
                longitude=str(row.get("longitude", "") or "").strip(),
                latitude=str(row.get("latitude", "") or "").strip(),
            )
    return events


def _empty_hour_stats() -> dict[str, Any]:
    return {
        "exposures": 0,
        "active_events": set(),
        "active_apps": set(),
        "task_eligible_exposures": 0,
        "contexts": Counter(),
    }


def _empty_device_stats() -> dict[str, Any]:
    return {
        "day1_3_hours": set(),
        "day4_7_hours": set(),
        "day1_3_events": set(),
        "day4_7_events": set(),
        "day1_3_apps": set(),
        "day4_7_apps": set(),
        "day1_3_exposures": 0,
        "day4_7_exposures": 0,
        "day1_3_task_eligible_exposures": 0,
        "day4_7_task_eligible_exposures": 0,
        "contexts": Counter(),
        "reference_contexts": Counter(),
        "validation_contexts": Counter(),
    }


def _write_context_distribution(
    path: Path,
    context_by_phase: Counter[tuple[str, str]],
    phase_totals: Counter[str],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["phase", "app_context", "active_event_app_exposures", "share"],
        )
        writer.writeheader()
        for phase in ("replay_day_1_3", "heldout_day_4_7", "all"):
            for context in APP_CONTEXTS:
                count = int(context_by_phase.get((phase, context), 0))
                total = int(phase_totals.get(phase, 0))
                writer.writerow(
                    {
                        "phase": phase,
                        "app_context": context,
                        "active_event_app_exposures": count,
                        "share": f"{(count / total) if total else 0:.6f}",
                    }
                )


def _write_hourly_summary(path: Path, hourly_stats: dict[tuple[str, str], dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "device_id",
                "hour_key",
                "date",
                "hour",
                "day_index",
                "phase",
                "active_event_app_exposures",
                "unique_active_events",
                "unique_active_apps",
                "task_eligible_exposures",
                "app_context_counts_json",
                "top_app_context",
            ],
        )
        writer.writeheader()
        for (device_id, hour_key), stats in sorted(hourly_stats.items()):
            date = hour_key[:10]
            hour = _safe_int(hour_key[11:13], 0)
            contexts: Counter[str] = stats["contexts"]
            top_context = contexts.most_common(1)[0][0] if contexts else ""
            writer.writerow(
                {
                    "device_id": device_id,
                    "hour_key": hour_key,
                    "date": date,
                    "hour": hour,
                    "day_index": _day_index(date),
                    "phase": _phase_for_date(date),
                    "active_event_app_exposures": int(stats["exposures"]),
                    "unique_active_events": len(stats["active_events"]),
                    "unique_active_apps": len(stats["active_apps"]),
                    "task_eligible_exposures": int(stats["task_eligible_exposures"]),
                    "app_context_counts_json": _json_dumps(dict(sorted(contexts.items()))),
                    "top_app_context": top_context,
                }
            )


def _write_device_summary(
    path: Path,
    people: dict[str, dict[str, str]],
    device_stats: dict[str, dict[str, Any]],
) -> None:
    fieldnames = [
        "device_id",
        "gender",
        "age",
        "talkingdata_group",
        "phone_brand",
        "device_model",
        "normalized_phone_model",
        "launch_price_or_reference_cny",
        "price_basis",
        "price_confidence",
        "day1_3_active_hours_cleaned",
        "day4_7_active_hours_cleaned",
        "total_active_hours_cleaned",
        "day1_3_active_event_app_exposures",
        "day4_7_active_event_app_exposures",
        "total_active_event_app_exposures",
        "day1_3_unique_active_events",
        "day4_7_unique_active_events",
        "day1_3_unique_active_apps",
        "day4_7_unique_active_apps",
        "day1_3_task_eligible_exposures",
        "day4_7_task_eligible_exposures",
        "top_app_contexts_json",
        "reference_top_app_contexts_json",
        "validation_top_app_contexts_json",
        "old_day1_3_active_hours",
        "old_day4_7_active_hours",
        "old_day1_3_active_rows",
        "old_day4_7_active_rows",
        "selection_basis",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for device_id in sorted(people):
            person = people[device_id]
            stats = device_stats.get(device_id, _empty_device_stats())
            top = dict(stats["contexts"].most_common(8))
            top_ref = dict(stats["reference_contexts"].most_common(8))
            top_val = dict(stats["validation_contexts"].most_common(8))
            day1_hours = len(stats["day1_3_hours"])
            day4_hours = len(stats["day4_7_hours"])
            row = {
                "device_id": device_id,
                "gender": person.get("gender", ""),
                "age": person.get("age", ""),
                "talkingdata_group": person.get("talkingdata_group", ""),
                "phone_brand": person.get("phone_brand", ""),
                "device_model": person.get("device_model", ""),
                "normalized_phone_model": person.get("normalized_phone_model", ""),
                "launch_price_or_reference_cny": person.get("launch_price_or_reference_cny", ""),
                "price_basis": person.get("price_basis", ""),
                "price_confidence": person.get("price_confidence", ""),
                "day1_3_active_hours_cleaned": day1_hours,
                "day4_7_active_hours_cleaned": day4_hours,
                "total_active_hours_cleaned": day1_hours + day4_hours,
                "day1_3_active_event_app_exposures": int(stats["day1_3_exposures"]),
                "day4_7_active_event_app_exposures": int(stats["day4_7_exposures"]),
                "total_active_event_app_exposures": int(stats["day1_3_exposures"])
                + int(stats["day4_7_exposures"]),
                "day1_3_unique_active_events": len(stats["day1_3_events"]),
                "day4_7_unique_active_events": len(stats["day4_7_events"]),
                "day1_3_unique_active_apps": len(stats["day1_3_apps"]),
                "day4_7_unique_active_apps": len(stats["day4_7_apps"]),
                "day1_3_task_eligible_exposures": int(stats["day1_3_task_eligible_exposures"]),
                "day4_7_task_eligible_exposures": int(stats["day4_7_task_eligible_exposures"]),
                "top_app_contexts_json": _json_dumps(top),
                "reference_top_app_contexts_json": _json_dumps(top_ref),
                "validation_top_app_contexts_json": _json_dumps(top_val),
                "old_day1_3_active_hours": person.get("day1_3_active_hours", ""),
                "old_day4_7_active_hours": person.get("day4_7_active_hours", ""),
                "old_day1_3_active_rows": person.get("day1_3_active_rows_old_cleaned", ""),
                "old_day4_7_active_rows": person.get("day4_7_active_rows_old_cleaned", ""),
                "selection_basis": person.get("selection_basis", ""),
            }
            writer.writerow(row)


def run_cleaning(raw_dir: Path, selection_csv: Path, output_dir: Path) -> dict[str, Any]:
    missing = [
        name for name in ("events.csv", "app_events.csv", "app_labels.csv", "label_categories.csv")
        if not (raw_dir / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Set --raw-dir or TALKINGDATA_RAW_DIR to the local TalkingData dataset; "
            f"missing files: {', '.join(missing)}"
        )
    if not selection_csv.is_file():
        raise FileNotFoundError("Provide the local 59-device cohort metadata using --selection-csv")
    output_dir.mkdir(parents=True, exist_ok=True)
    people = _load_selected_people(selection_csv)
    selected_ids = set(people)
    label_ids_by_app, categories_by_app = _load_app_labels(raw_dir)
    events = _load_selected_events(raw_dir, selected_ids)
    app_cache: dict[str, dict[str, Any]] = {}

    all_path = output_dir / "talkingdata_elderly_59_event_app_context.csv"
    ref_path = output_dir / "talkingdata_elderly_59_reference_day1_3.csv"
    val_path = output_dir / "talkingdata_elderly_59_validation_day4_7.csv"

    fieldnames = [
        "event_id",
        "device_id",
        "gender",
        "age",
        "talkingdata_group",
        "phone_brand",
        "device_model",
        "normalized_phone_model",
        "timestamp",
        "date",
        "hour",
        "hour_key",
        "day_index",
        "phase",
        "longitude",
        "latitude",
        "app_id",
        "is_installed",
        "is_active",
        "label_ids_json",
        "categories_json",
        "app_context",
        "task_eligible",
        "matched_contexts_json",
        "context_mapping_basis",
        "context_review_status",
        "launch_price_or_reference_cny",
        "price_basis",
        "price_confidence",
    ]

    hourly_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(_empty_hour_stats)
    device_stats: dict[str, dict[str, Any]] = defaultdict(_empty_device_stats)
    context_by_phase: Counter[tuple[str, str]] = Counter()
    phase_totals: Counter[str] = Counter()
    event_app_pairs: set[tuple[str, str]] = set()
    event_ids_with_active_apps: set[str] = set()

    handles = [
        all_path.open("w", encoding="utf-8-sig", newline=""),
        ref_path.open("w", encoding="utf-8-sig", newline=""),
        val_path.open("w", encoding="utf-8-sig", newline=""),
    ]
    try:
        writers = [csv.DictWriter(handle, fieldnames=fieldnames) for handle in handles]
        for writer in writers:
            writer.writeheader()
        all_writer, ref_writer, val_writer = writers

        with (raw_dir / "app_events.csv").open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if str(row.get("is_active", "")).strip() != "1":
                    continue
                event_id = str(row.get("event_id", "") or "").strip()
                event = events.get(event_id)
                if event is None:
                    continue
                app_id = str(row.get("app_id", "") or "").strip()
                if not app_id:
                    continue
                event_app_pairs.add((event_id, app_id))
                event_ids_with_active_apps.add(event_id)

                app_info = app_cache.get(app_id)
                if app_info is None:
                    label_ids = label_ids_by_app.get(app_id, ())
                    categories = categories_by_app.get(app_id, ())
                    result = classify_categories(categories)
                    app_info = {
                        "label_ids": label_ids,
                        "categories": categories,
                        "app_context": result.app_context,
                        "task_eligible": result.task_eligible,
                        "matched_contexts": result.matched_contexts,
                        "mapping_basis": result.mapping_basis,
                        "review_status": result.review_status,
                    }
                    app_cache[app_id] = app_info

                person = people[event.device_id]
                out = {
                    "event_id": event.event_id,
                    "device_id": event.device_id,
                    "gender": person.get("gender", ""),
                    "age": person.get("age", ""),
                    "talkingdata_group": person.get("talkingdata_group", ""),
                    "phone_brand": person.get("phone_brand", ""),
                    "device_model": person.get("device_model", ""),
                    "normalized_phone_model": person.get("normalized_phone_model", ""),
                    "timestamp": event.timestamp,
                    "date": event.date,
                    "hour": event.hour,
                    "hour_key": event.hour_key,
                    "day_index": event.day_index,
                    "phase": event.phase,
                    "longitude": event.longitude,
                    "latitude": event.latitude,
                    "app_id": app_id,
                    "is_installed": str(row.get("is_installed", "") or "").strip(),
                    "is_active": "1",
                    "label_ids_json": _json_dumps(list(app_info["label_ids"])),
                    "categories_json": _json_dumps(list(app_info["categories"])),
                    "app_context": app_info["app_context"],
                    "task_eligible": str(bool(app_info["task_eligible"])).lower(),
                    "matched_contexts_json": _json_dumps(list(app_info["matched_contexts"])),
                    "context_mapping_basis": app_info["mapping_basis"],
                    "context_review_status": app_info["review_status"],
                    "launch_price_or_reference_cny": person.get("launch_price_or_reference_cny", ""),
                    "price_basis": person.get("price_basis", ""),
                    "price_confidence": person.get("price_confidence", ""),
                }

                all_writer.writerow(out)
                if event.phase == "replay_day_1_3":
                    ref_writer.writerow(out)
                elif event.phase == "heldout_day_4_7":
                    val_writer.writerow(out)

                context = str(app_info["app_context"])
                is_task = bool(app_info["task_eligible"])
                hourly = hourly_stats[(event.device_id, event.hour_key)]
                hourly["exposures"] += 1
                hourly["active_events"].add(event.event_id)
                hourly["active_apps"].add(app_id)
                hourly["contexts"][context] += 1
                if is_task:
                    hourly["task_eligible_exposures"] += 1

                device = device_stats[event.device_id]
                target_prefix = "day1_3" if event.phase == "replay_day_1_3" else "day4_7"
                device[f"{target_prefix}_hours"].add(event.hour_key)
                device[f"{target_prefix}_events"].add(event.event_id)
                device[f"{target_prefix}_apps"].add(app_id)
                device[f"{target_prefix}_exposures"] += 1
                if is_task:
                    device[f"{target_prefix}_task_eligible_exposures"] += 1
                device["contexts"][context] += 1
                if event.phase == "replay_day_1_3":
                    device["reference_contexts"][context] += 1
                elif event.phase == "heldout_day_4_7":
                    device["validation_contexts"][context] += 1

                context_by_phase[(event.phase, context)] += 1
                context_by_phase[("all", context)] += 1
                phase_totals[event.phase] += 1
                phase_totals["all"] += 1
    finally:
        for handle in handles:
            handle.close()

    _write_hourly_summary(output_dir / "talkingdata_elderly_59_hourly_summary.csv", hourly_stats)
    _write_device_summary(output_dir / "talkingdata_elderly_59_device_summary.csv", people, device_stats)
    _write_context_distribution(
        output_dir / "talkingdata_elderly_59_app_context_distribution.csv",
        context_by_phase,
        phase_totals,
    )

    raw_hashes = {
        name: _hash_file(raw_dir / name)
        for name in [
            "events.csv",
            "app_events.csv",
            "app_labels.csv",
            "label_categories.csv",
            "gender_age_train.csv",
            "phone_brand_device_model.csv",
        ]
        if (raw_dir / name).exists()
    }
    manifest = {
        "schema_version": "talkingdata_elderly_59_event_app_context_v3",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_dir": str(raw_dir),
        "selection_csv": str(selection_csv),
        "output_dir": str(output_dir),
        "raw_hashes": raw_hashes,
        "selected_device_count": len(people),
        "selected_event_count_in_window": len(events),
        "active_event_count": len(event_ids_with_active_apps),
        "active_event_app_rows": int(phase_totals["all"]),
        "unique_active_event_app_pairs": len(event_app_pairs),
        "reference_active_event_app_rows": int(phase_totals["replay_day_1_3"]),
        "validation_active_event_app_rows": int(phase_totals["heldout_day_4_7"]),
        "reference_start": REFERENCE_START,
        "validation_start": VALIDATION_START,
        "end_exclusive": END_EXCLUSIVE,
        "unit_of_analysis": "event_id + app_id active app exposure where app_events.is_active == 1",
        "phase_definition": {
            "replay_day_1_3": "2016-05-01 <= timestamp < 2016-05-04",
            "heldout_day_4_7": "2016-05-04 <= timestamp < 2016-05-08",
        },
        "outputs": {
            "all_event_app_context": str(all_path),
            "reference_day1_3": str(ref_path),
            "validation_day4_7": str(val_path),
            "hourly_summary": str(output_dir / "talkingdata_elderly_59_hourly_summary.csv"),
            "device_summary": str(output_dir / "talkingdata_elderly_59_device_summary.csv"),
            "app_context_distribution": str(output_dir / "talkingdata_elderly_59_app_context_distribution.csv"),
        },
        "notes": [
            "The 59 selected device_id values are preserved from the existing phone-price device summary.",
            "Rows are regenerated from raw TalkingData CSV files at active event-app granularity.",
            "Category labels are aggregated into JSON arrays and are not counted as separate app entries.",
            "v3 strict app-context cleaning does not promote broad taxonomy/profile/content labels to task-eligible contexts.",
            "Day 1-3 is intended for replay calibration; Day 4-7 is held out for baseline app-entry validation.",
        ],
    }
    (output_dir / "cleaning_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--selection-csv", type=Path, default=DEFAULT_SELECTION_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = run_cleaning(args.raw_dir, args.selection_csv, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
