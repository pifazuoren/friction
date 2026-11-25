#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO_ROOT / "agentsociety_data" / "elderly"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "agentsociety_data" / "elderly" / "10person"

REFERENCE_DATES = ("2016-05-01", "2016-05-02", "2016-05-03")
VALIDATION_DATES = ("2016-05-04", "2016-05-05", "2016-05-06", "2016-05-07")
TASK_ELIGIBLE_CONTEXTS = {
    "finance_context",
    "public_service_context",
    "health_service_context",
    "shopping_lifestyle_context",
    "navigation_transport_context",
    "education_work_context",
}

SELECTION_NAME = "talkingdata_elderly_10_selected_devices.csv"


def _load_selection(input_dir: Path, output_dir: Path, selection_csv: Path | None) -> pd.DataFrame:
    if selection_csv is None:
        candidates = (
            output_dir / SELECTION_NAME,
            input_dir / "10person" / SELECTION_NAME,
            DEFAULT_OUTPUT_DIR / SELECTION_NAME,
            DEFAULT_INPUT_DIR / "10person_v3" / SELECTION_NAME,
        )
        selection_csv = next((path for path in candidates if path.is_file()), None)
    if selection_csv is None or not selection_csv.is_file():
        raise FileNotFoundError(
            "Supply the local 10-device cohort with --selection-csv. Required columns: "
            "device_id, selection_role, selection_reason. Optional: selected_rank (1..10)."
        )
    columns = ["device_id", "selection_role", "selection_reason"]
    selected = pd.read_csv(selection_csv, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if not set(columns).issubset(selected):
        raise ValueError(f"--selection-csv requires columns: {', '.join(columns)}")
    if len(selected) != 10 or selected["device_id"].nunique() != 10 or (selected["device_id"] == "").any():
        raise ValueError("--selection-csv must contain 10 distinct nonempty device_id values")
    if "selected_rank" in selected:
        selected["selected_rank"] = selected["selected_rank"].map(int)
        if sorted(selected["selected_rank"]) != list(range(1, 11)):
            raise ValueError("--selection-csv ranks must contain each integer from 1 to 10 once")
        selected = selected.sort_values("selected_rank")
    else:
        selected["selected_rank"] = range(1, 11)
    return selected[["selected_rank", *columns]]


def _read_csv(path: Path) -> pd.DataFrame:
    dtype = {
        "device_id": "string",
        "event_id": "string",
        "app_id": "string",
        "hour_key": "string",
        "date": "string",
        "phase": "string",
    }
    return pd.read_csv(path, encoding="utf-8-sig", dtype=dtype)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _top_context(value: Any) -> str:
    counts = _json_loads(value, {})
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: (int(item[1]), item[0]))[0]


def _count_for_context(value: Any, context: str) -> int:
    counts = _json_loads(value, {})
    return int(counts.get(context, 0))


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _subset_by_device(df: pd.DataFrame, selected_ids: set[str]) -> pd.DataFrame:
    return df[df["device_id"].astype("string").isin(selected_ids)].copy()


def _build_full_hourly_bundle(hourly_observed: pd.DataFrame, selected_order: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    observed_by_key = {
        (str(row.device_id), str(row.hour_key)): row
        for row in hourly_observed.itertuples(index=False)
    }
    all_dates = (*REFERENCE_DATES, *VALIDATION_DATES)

    for device_id in selected_order:
        for day_index, date in enumerate(all_dates, start=1):
            phase = "replay_day_1_3" if day_index <= 3 else "heldout_day_4_7"
            split_role = "calibration_replay" if day_index <= 3 else "heldout_validation"
            for hour in range(24):
                hour_key = f"{date} {hour:02d}:00:00"
                observed = observed_by_key.get((device_id, hour_key))
                if observed is None:
                    counts_json = "{}"
                    active_event_app_exposures = 0
                    unique_active_events = 0
                    unique_active_apps = 0
                    task_eligible_exposures = 0
                    primary_context = "no_app_context"
                    primary_context_count = 0
                    source = "talkingdata_inactive_hour"
                    active = False
                else:
                    counts_json = str(observed.app_context_counts_json)
                    active_event_app_exposures = int(observed.active_event_app_exposures)
                    unique_active_events = int(observed.unique_active_events)
                    unique_active_apps = int(observed.unique_active_apps)
                    task_eligible_exposures = int(observed.task_eligible_exposures)
                    primary_context = str(observed.top_app_context or "") or _top_context(counts_json)
                    primary_context_count = _count_for_context(counts_json, primary_context)
                    source = "talkingdata_observed_active_hour"
                    active = active_event_app_exposures > 0

                primary_context_share = (
                    primary_context_count / active_event_app_exposures
                    if active_event_app_exposures
                    else 0.0
                )
                bundle = {
                    "active": active,
                    "active_event_app_exposures": active_event_app_exposures,
                    "unique_active_events": unique_active_events,
                    "unique_active_apps": unique_active_apps,
                    "task_eligible_exposures": task_eligible_exposures,
                    "app_context_counts": _json_loads(counts_json, {}),
                    "primary_context": primary_context,
                    "primary_context_count": primary_context_count,
                    "primary_context_share": round(primary_context_share, 6),
                    "source": source,
                }
                rows.append(
                    {
                        "device_id": device_id,
                        "hour_key": hour_key,
                        "date": date,
                        "hour": hour,
                        "day_index": day_index,
                        "hour_index": (day_index - 1) * 24 + hour,
                        "phase": phase,
                        "split_role": split_role,
                        "active": str(active).lower(),
                        "active_event_app_exposures": active_event_app_exposures,
                        "unique_active_events": unique_active_events,
                        "unique_active_apps": unique_active_apps,
                        "task_eligible_exposures": task_eligible_exposures,
                        "app_context_counts_json": counts_json,
                        "primary_context": primary_context,
                        "primary_context_count": primary_context_count,
                        "primary_context_share": f"{primary_context_share:.6f}",
                        "primary_context_task_eligible": str(primary_context in TASK_ELIGIBLE_CONTEXTS).lower(),
                        "source": source,
                        "app_entry_bundle_json": _json_dumps(bundle),
                    }
                )

    return pd.DataFrame(rows)


def _write_jsonl(df: pd.DataFrame, path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in df.to_dict(orient="records"):
            parsed = dict(row)
            parsed["active"] = str(parsed["active"]).lower() == "true"
            parsed["primary_context_task_eligible"] = (
                str(parsed["primary_context_task_eligible"]).lower() == "true"
            )
            parsed["app_context_counts"] = _json_loads(parsed.pop("app_context_counts_json"), {})
            parsed["app_entry_bundle"] = _json_loads(parsed.pop("app_entry_bundle_json"), {})
            handle.write(json.dumps(parsed, ensure_ascii=False, sort_keys=True) + "\n")


def _load_source_manifest(input_dir: Path) -> dict[str, Any]:
    manifest_path = input_dir / "cleaning_manifest.json"
    if not manifest_path.exists():
        return {}
    return _json_loads(manifest_path.read_text(encoding="utf-8"), {})


def build_artifacts(
    input_dir: Path, output_dir: Path, selection_csv: Path | None = None
) -> dict[str, Any]:
    selected_meta = _load_selection(input_dir, output_dir, selection_csv)
    selected_order = selected_meta["device_id"].tolist()
    selected_ids = set(selected_order)
    source_manifest = _load_source_manifest(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device_summary_59 = _read_csv(input_dir / "talkingdata_elderly_59_device_summary.csv")
    missing = sorted(selected_ids - set(device_summary_59["device_id"].astype("string")))
    if missing:
        raise ValueError(f"Selected device_id values not found in 59-person summary: {missing}")

    device_summary_10 = (
        device_summary_59[device_summary_59["device_id"].astype("string").isin(selected_ids)]
        .copy()
        .merge(selected_meta, on="device_id", how="left")
        .sort_values("selected_rank")
    )
    device_summary_10["reference_primary_context"] = device_summary_10[
        "reference_top_app_contexts_json"
    ].map(_top_context)
    device_summary_10["validation_primary_context"] = device_summary_10[
        "validation_top_app_contexts_json"
    ].map(_top_context)

    event_all_59 = _read_csv(input_dir / "talkingdata_elderly_59_event_app_context.csv")
    reference_59 = _read_csv(input_dir / "talkingdata_elderly_59_reference_day1_3.csv")
    validation_59 = _read_csv(input_dir / "talkingdata_elderly_59_validation_day4_7.csv")
    hourly_59 = _read_csv(input_dir / "talkingdata_elderly_59_hourly_summary.csv")

    event_all_10 = _subset_by_device(event_all_59, selected_ids)
    reference_10 = _subset_by_device(reference_59, selected_ids)
    validation_10 = _subset_by_device(validation_59, selected_ids)
    hourly_observed_10 = _subset_by_device(hourly_59, selected_ids).sort_values(
        ["device_id", "hour_key"]
    )
    hourly_observed_10["active"] = "true"
    hourly_observed_10["primary_context"] = hourly_observed_10["top_app_context"]
    hourly_observed_10["source"] = "talkingdata_observed_active_hour"

    hourly_bundle_10 = _build_full_hourly_bundle(hourly_observed_10, selected_order)
    reference_hourly_bundle_10 = hourly_bundle_10[hourly_bundle_10["day_index"] <= 3].copy()
    validation_hourly_bundle_10 = hourly_bundle_10[hourly_bundle_10["day_index"] >= 4].copy()

    context_distribution_10 = (
        event_all_10.groupby(["phase", "app_context"], dropna=False)
        .size()
        .reset_index(name="active_event_app_exposures")
    )
    phase_totals = context_distribution_10.groupby("phase")["active_event_app_exposures"].transform(
        "sum"
    )
    context_distribution_10["share"] = (
        context_distribution_10["active_event_app_exposures"] / phase_totals
    ).round(6)

    paths = {
        "selected_devices": output_dir / "talkingdata_elderly_10_selected_devices.csv",
        "device_summary": output_dir / "talkingdata_elderly_10_device_summary.csv",
        "event_app_context": output_dir / "talkingdata_elderly_10_event_app_context.csv",
        "reference_day1_3": output_dir / "talkingdata_elderly_10_reference_day1_3.csv",
        "validation_day4_7": output_dir / "talkingdata_elderly_10_validation_day4_7.csv",
        "hourly_observed": output_dir / "talkingdata_elderly_10_hourly_observed.csv",
        "hourly_app_entry_bundle": output_dir
        / "talkingdata_elderly_10_hourly_app_entry_bundle.csv",
        "hourly_app_entry_bundle_jsonl": output_dir
        / "talkingdata_elderly_10_hourly_app_entry_bundle.jsonl",
        "reference_hourly_bundle_day1_3": output_dir
        / "talkingdata_elderly_10_reference_hourly_bundle_day1_3.csv",
        "validation_hourly_bundle_day4_7": output_dir
        / "talkingdata_elderly_10_validation_hourly_bundle_day4_7.csv",
        "app_context_distribution": output_dir
        / "talkingdata_elderly_10_app_context_distribution.csv",
        "manifest": output_dir / "talkingdata_elderly_10_manifest.json",
        "readme": output_dir / "talkingdata_elderly_10_README.md",
    }

    selected_devices = device_summary_10[
        [
            "selected_rank",
            "device_id",
            "selection_role",
            "selection_reason",
            "gender",
            "age",
            "talkingdata_group",
            "phone_brand",
            "device_model",
            "launch_price_or_reference_cny",
            "day1_3_active_hours_cleaned",
            "day4_7_active_hours_cleaned",
            "day1_3_active_event_app_exposures",
            "day4_7_active_event_app_exposures",
            "reference_primary_context",
            "validation_primary_context",
        ]
    ]

    _write_csv(selected_devices, paths["selected_devices"])
    _write_csv(device_summary_10, paths["device_summary"])
    _write_csv(event_all_10, paths["event_app_context"])
    _write_csv(reference_10, paths["reference_day1_3"])
    _write_csv(validation_10, paths["validation_day4_7"])
    _write_csv(hourly_observed_10, paths["hourly_observed"])
    _write_csv(hourly_bundle_10, paths["hourly_app_entry_bundle"])
    _write_jsonl(hourly_bundle_10, paths["hourly_app_entry_bundle_jsonl"])
    _write_csv(reference_hourly_bundle_10, paths["reference_hourly_bundle_day1_3"])
    _write_csv(validation_hourly_bundle_10, paths["validation_hourly_bundle_day4_7"])
    _write_csv(context_distribution_10, paths["app_context_distribution"])

    manifest = {
        "schema_version": "talkingdata_elderly_10_app_entry_bundle_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "source_population": "talkingdata_elderly_59_* artifacts generated from cleaned TalkingData active event-app exposures",
        "source_cleaning_manifest": str(input_dir / "cleaning_manifest.json")
        if (input_dir / "cleaning_manifest.json").exists()
        else "",
        "source_schema_version": str(source_manifest.get("schema_version", "")),
        "selected_device_count": len(selected_order),
        "selected_devices": selected_meta.to_dict(orient="records"),
        "selection_criteria": [
            "All selected devices come from the cleaned 59-person elderly TalkingData subset.",
            "Prefer devices with sufficient Day 1-3 and Day 4-7 active-hour coverage.",
            "Cover multiple behavioral types: social, finance, navigation/transport, multi-context/taxonomy-heavy, and one low-mapping-confidence control.",
            "Avoid selecting only the cleanest or most finance-heavy cases, so validation remains more honest.",
        ],
        "phase_definition": {
            "replay_day_1_3": "2016-05-01 through 2016-05-03; intended for replay/calibration.",
            "heldout_day_4_7": "2016-05-04 through 2016-05-07; intended for held-out baseline validation.",
        },
        "hourly_bundle_schema": {
            "unit": "one row per device_id per hour for a complete 10 devices x 7 days x 24 hours grid",
            "active": "true when TalkingData records at least one active event-app exposure in this hour",
            "active_event_app_exposures": "count of event_id + app_id rows with is_active == 1",
            "app_context_counts_json": "all observed app-context exposure counts within the hour",
            "primary_context": "the top observed app context for active hours; no_app_context for inactive hours",
            "primary_context_task_eligible": "whether primary_context can enter the existing task occurrence gate",
            "app_entry_bundle_json": "runtime-friendly nested representation of the same hourly app-entry bundle",
        },
        "no_leakage_note": "Day 4-7 rows are included only as held-out validation labels. A baseline simulation should not read these rows while generating app entries.",
        "row_counts": {
            "selected_devices": int(len(selected_devices)),
            "event_app_context": int(len(event_all_10)),
            "reference_day1_3_event_rows": int(len(reference_10)),
            "validation_day4_7_event_rows": int(len(validation_10)),
            "hourly_observed_active_rows": int(len(hourly_observed_10)),
            "hourly_app_entry_bundle_rows": int(len(hourly_bundle_10)),
            "reference_hourly_bundle_rows": int(len(reference_hourly_bundle_10)),
            "validation_hourly_bundle_rows": int(len(validation_hourly_bundle_10)),
        },
        "outputs": {key: str(path) for key, path in paths.items() if key not in {"manifest", "readme"}},
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if not paths["readme"].exists():
        paths["readme"].write_text(
            "\n".join(
                [
                    "# TalkingData Elderly 10-Person App Entry Artifact",
                    "",
                    "This folder contains a frozen 10-person subset derived from the cleaned 59-person TalkingData elderly artifacts.",
                    "",
                    "Use Day 1-3 files for replay/calibration and Day 4-7 files only for held-out app-entry validation.",
                    "",
                    "Key runtime file:",
                    "",
                    "- `talkingdata_elderly_10_hourly_app_entry_bundle.csv`: complete 10 x 7 x 24 hourly grid.",
                    "- `talkingdata_elderly_10_hourly_app_entry_bundle.jsonl`: JSONL version of the same bundle.",
                    "",
                    "No-leakage rule: Day 4-7 rows are validation labels, not generation inputs.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--selection-csv", type=Path,
        help="Local cohort metadata; defaults to the existing 10-device selection CSV.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_artifacts(args.input_dir, args.output_dir, args.selection_csv)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
