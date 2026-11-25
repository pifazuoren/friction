from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from proto.app_entry.bundle import (
    PRIMARY_CONTEXT_RULE_VERSION,
    HourlyAppEntryBundle,
    derive_primary_context,
)
from proto.app_entry.types import APP_CONTEXT_SET


VALIDATION_SCHEMA_VERSION = "app_entry_heldout_validation_v1"
DEFAULT_EXPECTED_ROWS = 10 * 4 * 24


@dataclass(frozen=True, slots=True)
class ValidationRow:
    device_id: str
    day: int
    hour: int
    active: bool
    exposures: int
    context_counts: dict[str, int]
    primary_context: str
    top_count_tied: bool
    task_generated: bool = False

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.device_id, self.day, self.hour)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n", ""}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _parse_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    return parsed


def _parse_context_counts(value: Any) -> dict[str, int]:
    if isinstance(value, dict):
        payload = value
    else:
        try:
            payload = json.loads(str(value or "{}").strip() or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("app_context_counts_json must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("app_context_counts_json must contain a JSON object")
    counts: dict[str, int] = {}
    for raw_context, raw_count in payload.items():
        context = str(raw_context).strip()
        if context not in APP_CONTEXT_SET:
            raise ValueError(f"unknown app context: {context}")
        count = _parse_int(raw_count, f"app_context_counts[{context}]")
        if count < 0:
            raise ValueError(f"app_context_counts[{context}] must be >= 0")
        if count:
            counts[context] = count
    return counts


def _top_count_tied(counts: dict[str, int]) -> bool:
    if not counts:
        return False
    maximum = max(counts.values())
    return sum(1 for count in counts.values() if count == maximum) > 1


def _normalize_row(raw: dict[str, Any], *, generated: bool) -> ValidationRow:
    day_field = "talkingdata_day" if generated else "day_index"
    if not str(raw.get(day_field, "")).strip():
        day_field = "day"
    device_id = str(raw.get("device_id", "")).strip()
    day = _parse_int(raw.get(day_field), day_field)
    hour = _parse_int(raw.get("hour"), "hour")
    if day < 4 or day > 7:
        raise ValueError("held-out app-entry validation only accepts days 4..7")
    active = _parse_bool(raw.get("active"))
    exposures = _parse_int(
        raw.get("active_event_app_exposures", 0),
        "active_event_app_exposures",
    )
    counts = _parse_context_counts(
        raw.get("app_context_counts_json", raw.get("app_context_counts", "{}"))
    )
    primary_context = derive_primary_context(counts)
    bundle = HourlyAppEntryBundle.from_dict(
        {
            "device_id": device_id,
            "day": day,
            "hour": hour,
            "active": active,
            "active_event_app_exposures": exposures,
            "app_context_counts": counts,
            "primary_context": primary_context,
            "source": "generated_validation_input" if generated else "heldout_observed",
        }
    )
    return ValidationRow(
        device_id=bundle.device_id,
        day=bundle.day,
        hour=bundle.hour,
        active=bundle.active,
        exposures=bundle.active_event_app_exposures,
        context_counts=bundle.app_context_counts,
        primary_context=bundle.primary_context,
        top_count_tied=_top_count_tied(bundle.app_context_counts),
        task_generated=(
            _parse_bool(raw.get("task_generated")) if generated else False
        ),
    )


def _load_rows(
    path: Path,
    *,
    generated: bool,
    world_name: str | None = None,
) -> tuple[dict[tuple[str, int, int], ValidationRow], dict[str, set[str]]]:
    rows: dict[tuple[str, int, int], ValidationRow] = {}
    versions: dict[str, set[str]] = defaultdict(set)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        for line_number, raw in enumerate(reader, start=2):
            raw_world_name = str(raw.get("world_name", "")).strip()
            if generated and world_name and raw_world_name != world_name:
                continue
            row = _normalize_row(raw, generated=generated)
            if row.key in rows:
                raise ValueError(
                    f"duplicate (device_id, day, hour) at {path}:{line_number}: "
                    f"{row.key}; select one baseline world when the CSV contains "
                    "multiple worlds"
                )
            rows[row.key] = row
            if generated:
                for field in (
                    "needs_prompt_version",
                    "needs_prompt_hash",
                    "plan_prompt_version",
                    "plan_prompt_hash",
                ):
                    value = str(raw.get(field, "")).strip()
                    if value:
                        versions[field].add(value)
                for field in (
                    "group_id",
                    "world_name",
                    "exp_id",
                    "config_fingerprint",
                ):
                    value = str(raw.get(field, "")).strip()
                    if value:
                        versions[field].add(value)
                if _parse_bool(raw.get("uses_validation_data", False)):
                    raise ValueError(
                        "generated rollout row is marked uses_validation_data=true"
                    )
    if generated and not world_name and len(versions.get("world_name", set())) > 1:
        raise ValueError(
            "generated CSV contains multiple worlds; select one baseline world"
        )
    return rows, versions


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _distribution(counts: Counter[str]) -> dict[str, float]:
    total = sum(counts.values())
    return {
        context: _safe_ratio(counts.get(context, 0), total)
        for context in APP_CONTEXT_SET
    }


def _tvd(left: dict[str, float], right: dict[str, float]) -> float:
    return 0.5 * sum(
        abs(float(left.get(context, 0.0)) - float(right.get(context, 0.0)))
        for context in APP_CONTEXT_SET
    )


def _context_share_l1(left: ValidationRow, right: ValidationRow) -> float:
    left_total = sum(left.context_counts.values())
    right_total = sum(right.context_counts.values())
    return sum(
        abs(
            _safe_ratio(left.context_counts.get(context, 0), left_total)
            - _safe_ratio(right.context_counts.get(context, 0), right_total)
        )
        for context in APP_CONTEXT_SET
    )


def compute_validation_metrics(
    generated_rows: dict[tuple[str, int, int], ValidationRow],
    observed_rows: dict[tuple[str, int, int], ValidationRow],
    *,
    expected_rows: int | None = DEFAULT_EXPECTED_ROWS,
) -> dict[str, Any]:
    generated_keys = set(generated_rows)
    observed_keys = set(observed_rows)
    if generated_keys != observed_keys:
        missing_generated = sorted(observed_keys - generated_keys)[:10]
        missing_observed = sorted(generated_keys - observed_keys)[:10]
        raise ValueError(
            "generated and observed rows do not match exactly; "
            f"missing_generated={missing_generated}, missing_observed={missing_observed}"
        )
    if expected_rows is not None and len(generated_keys) != expected_rows:
        raise ValueError(
            f"expected {expected_rows} matched rows, got {len(generated_keys)}"
        )
    if not generated_keys:
        raise ValueError("validation input contains no matched rows")

    tp = fp = fn = tn = 0
    all_hour_errors: list[float] = []
    observed_active_errors: list[float] = []
    primary_matches = 0
    hourly_l1: list[float] = []
    generated_ties = 0
    observed_ties = 0
    task_generated = 0
    generated_contexts: Counter[str] = Counter()
    observed_contexts: Counter[str] = Counter()
    generated_by_device: dict[str, Counter[str]] = defaultdict(Counter)
    observed_by_device: dict[str, Counter[str]] = defaultdict(Counter)

    for key in sorted(generated_keys):
        generated = generated_rows[key]
        observed = observed_rows[key]
        if generated.active and observed.active:
            tp += 1
        elif generated.active:
            fp += 1
        elif observed.active:
            fn += 1
        else:
            tn += 1
        error = abs(generated.exposures - observed.exposures)
        all_hour_errors.append(float(error))
        if observed.active:
            observed_active_errors.append(float(error))
        primary_matches += int(generated.primary_context == observed.primary_context)
        generated_ties += int(generated.top_count_tied)
        observed_ties += int(observed.top_count_tied)
        task_generated += int(generated.task_generated)
        hourly_l1.append(_context_share_l1(generated, observed))
        generated_contexts.update(generated.context_counts)
        observed_contexts.update(observed.context_counts)
        generated_by_device[generated.device_id].update(generated.context_counts)
        observed_by_device[observed.device_id].update(observed.context_counts)

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _safe_ratio(2.0 * precision * recall, precision + recall)
    devices = sorted(generated_by_device)
    per_agent_tvd = [
        _tvd(
            _distribution(generated_by_device[device_id]),
            _distribution(observed_by_device[device_id]),
        )
        for device_id in devices
    ]
    row_count = len(generated_keys)
    return {
        "matched_rows": row_count,
        "device_count": len({key[0] for key in generated_keys}),
        "active_confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "active_precision": precision,
        "active_recall": recall,
        "active_f1": f1,
        "all_hour_exposure_intensity_mae": sum(all_hour_errors) / row_count,
        "observed_active_hour_exposure_intensity_mae": (
            sum(observed_active_errors) / len(observed_active_errors)
            if observed_active_errors
            else 0.0
        ),
        "global_app_context_distribution_tvd": _tvd(
            _distribution(generated_contexts),
            _distribution(observed_contexts),
        ),
        "mean_per_agent_app_context_distribution_tvd": (
            sum(per_agent_tvd) / len(per_agent_tvd) if per_agent_tvd else 0.0
        ),
        "primary_context_agreement": _safe_ratio(primary_matches, row_count),
        "observed_top_count_tie_rate": _safe_ratio(observed_ties, row_count),
        "generated_top_count_tie_rate": _safe_ratio(generated_ties, row_count),
        "mean_hourly_bundle_context_share_l1": sum(hourly_l1) / row_count,
        "task_generated_rate": _safe_ratio(task_generated, row_count),
        "task_generated_count": task_generated,
        "primary_context_rule_version": PRIMARY_CONTEXT_RULE_VERSION,
    }


def _flatten_metrics(metrics: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    for key, value in metrics.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                yield f"{key}.{nested_key}", nested_value
        else:
            yield key, value


def write_validation_report(
    *,
    generated_csv: Path,
    observed_csv: Path,
    output_json: Path,
    output_csv: Path,
    expected_rows: int | None = DEFAULT_EXPECTED_ROWS,
    world_name: str | None = None,
) -> dict[str, Any]:
    generated_rows, prompt_versions = _load_rows(
        generated_csv,
        generated=True,
        world_name=world_name,
    )
    observed_rows, _ = _load_rows(observed_csv, generated=False)
    metrics = compute_validation_metrics(
        generated_rows,
        observed_rows,
        expected_rows=expected_rows,
    )
    report = {
        "validation_schema_version": VALIDATION_SCHEMA_VERSION,
        "generated_csv": str(generated_csv.resolve()),
        "generated_csv_sha256": _file_hash(generated_csv),
        "observed_csv": str(observed_csv.resolve()),
        "observed_csv_sha256": _file_hash(observed_csv),
        "expected_rows": expected_rows,
        "selected_world_name": world_name or "",
        "prompt_versions_and_hashes": {
            key: sorted(values) for key, values in sorted(prompt_versions.items())
        },
        "metrics": metrics,
        "notes": {
            "validation_timing": "post_run_only",
            "active_hour_mae_denominator": "observed_active_hours",
            "task_generated_rate": "model_sanity_metric_not_talkingdata_accuracy",
            "uses_validation_data_at_runtime": False,
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerow(
            {
                "metric": "metadata.validation_schema_version",
                "value": report["validation_schema_version"],
            }
        )
        writer.writerow(
            {
                "metric": "metadata.generated_csv_sha256",
                "value": report["generated_csv_sha256"],
            }
        )
        writer.writerow(
            {
                "metric": "metadata.observed_csv_sha256",
                "value": report["observed_csv_sha256"],
            }
        )
        writer.writerow(
            {
                "metric": "metadata.selected_world_name",
                "value": report["selected_world_name"],
            }
        )
        for key, values in report["prompt_versions_and_hashes"].items():
            writer.writerow(
                {
                    "metric": f"metadata.{key}",
                    "value": json.dumps(values, ensure_ascii=False),
                }
            )
        for metric, value in _flatten_metrics(metrics):
            writer.writerow({"metric": f"metrics.{metric}", "value": value})
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate post-run Day 4-7 app-entry bundles against held-out TalkingData."
    )
    parser.add_argument("--generated-csv", required=True, type=Path)
    parser.add_argument("--observed-csv", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument(
        "--world-name",
        default="",
        help="Select one baseline world when the generated CSV contains multiple worlds.",
    )
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=DEFAULT_EXPECTED_ROWS,
        help="Strict matched-row count; use 0 to disable for a partial smoke run.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    report = write_validation_report(
        generated_csv=args.generated_csv,
        observed_csv=args.observed_csv,
        output_json=args.output_json,
        output_csv=args.output_csv,
        expected_rows=(None if args.expected_rows == 0 else args.expected_rows),
        world_name=(str(args.world_name).strip() or None),
    )
    print(args.output_json)
    print(args.output_csv)
    print(json.dumps(report["metrics"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
