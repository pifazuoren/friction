from __future__ import annotations

import csv
import json

import pytest

from analysis_app_entry_validation import write_validation_report


def _write_generated(path, rows) -> None:
    fieldnames = [
        "device_id",
        "talkingdata_day",
        "hour",
        "active",
        "active_event_app_exposures",
        "app_context_counts_json",
        "primary_context",
        "task_generated",
        "needs_prompt_version",
        "needs_prompt_hash",
        "plan_prompt_version",
        "plan_prompt_hash",
        "uses_validation_data",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_observed(path, rows) -> None:
    fieldnames = [
        "device_id",
        "day_index",
        "hour",
        "active",
        "active_event_app_exposures",
        "app_context_counts_json",
        "primary_context",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _generated_row(hour: int, *, active=True, counts=None, task_generated=False):
    counts = counts if counts is not None else {"finance_context": 2}
    return {
        "device_id": "device-a",
        "talkingdata_day": 4,
        "hour": hour,
        "active": str(active).lower(),
        "active_event_app_exposures": sum(counts.values()),
        "app_context_counts_json": json.dumps(counts),
        "primary_context": "deliberately_ignored",
        "task_generated": str(task_generated).lower(),
        "needs_prompt_version": "needs-v1",
        "needs_prompt_hash": "needs-hash",
        "plan_prompt_version": "plan-v1",
        "plan_prompt_hash": "plan-hash",
        "uses_validation_data": "false",
    }


def _observed_row(hour: int, *, active=True, counts=None):
    counts = counts if counts is not None else {"finance_context": 2}
    return {
        "device_id": "device-a",
        "day_index": 4,
        "hour": hour,
        "active": str(active).lower(),
        "active_event_app_exposures": sum(counts.values()),
        "app_context_counts_json": json.dumps(counts),
        "primary_context": "also_ignored",
    }


def test_validation_reports_exact_match_and_hashes(tmp_path) -> None:
    generated = tmp_path / "generated.csv"
    observed = tmp_path / "observed.csv"
    output_json = tmp_path / "report.json"
    output_csv = tmp_path / "report.csv"
    _write_generated(generated, [_generated_row(9, task_generated=True)])
    _write_observed(observed, [_observed_row(9)])

    report = write_validation_report(
        generated_csv=generated,
        observed_csv=observed,
        output_json=output_json,
        output_csv=output_csv,
        expected_rows=1,
    )

    metrics = report["metrics"]
    assert metrics["active_precision"] == 1.0
    assert metrics["active_recall"] == 1.0
    assert metrics["active_f1"] == 1.0
    assert metrics["all_hour_exposure_intensity_mae"] == 0.0
    assert metrics["global_app_context_distribution_tvd"] == 0.0
    assert metrics["primary_context_agreement"] == 1.0
    assert metrics["task_generated_rate"] == 1.0
    assert len(report["generated_csv_sha256"]) == 64
    assert report["prompt_versions_and_hashes"]["plan_prompt_version"] == [
        "plan-v1"
    ]
    assert output_json.exists()
    assert output_csv.exists()
    report_csv_text = output_csv.read_text(encoding="utf-8")
    assert "metadata.generated_csv_sha256" in report_csv_text
    assert report["generated_csv_sha256"] in report_csv_text
    assert "metadata.plan_prompt_version" in report_csv_text


def test_validation_computes_activity_bundle_and_tie_metrics(tmp_path) -> None:
    generated = tmp_path / "generated.csv"
    observed = tmp_path / "observed.csv"
    _write_generated(
        generated,
        [
            _generated_row(
                9,
                counts={"finance_context": 1, "media_entertainment_context": 1},
            ),
            _generated_row(10, active=False, counts={}),
        ],
    )
    _write_observed(
        observed,
        [
            _observed_row(9, counts={"finance_context": 2}),
            _observed_row(10, counts={"communication_social_context": 1}),
        ],
    )

    report = write_validation_report(
        generated_csv=generated,
        observed_csv=observed,
        output_json=tmp_path / "report.json",
        output_csv=tmp_path / "report.csv",
        expected_rows=2,
    )
    metrics = report["metrics"]

    assert metrics["active_precision"] == 1.0
    assert metrics["active_recall"] == 0.5
    assert metrics["active_f1"] == pytest.approx(2.0 / 3.0)
    assert metrics["all_hour_exposure_intensity_mae"] == 0.5
    assert metrics["observed_active_hour_exposure_intensity_mae"] == 0.5
    assert metrics["generated_top_count_tie_rate"] == 0.5
    assert metrics["observed_top_count_tie_rate"] == 0.0
    assert metrics["primary_context_agreement"] == 0.0
    assert metrics["mean_hourly_bundle_context_share_l1"] == 1.0


def test_validation_rejects_missing_duplicate_and_leaking_rows(tmp_path) -> None:
    generated = tmp_path / "generated.csv"
    observed = tmp_path / "observed.csv"
    _write_generated(generated, [_generated_row(9)])
    _write_observed(observed, [_observed_row(10)])
    with pytest.raises(ValueError, match="do not match exactly"):
        write_validation_report(
            generated_csv=generated,
            observed_csv=observed,
            output_json=tmp_path / "report.json",
            output_csv=tmp_path / "report.csv",
            expected_rows=1,
        )

    leaking = _generated_row(9)
    leaking["uses_validation_data"] = "true"
    _write_generated(generated, [leaking])
    _write_observed(observed, [_observed_row(9)])
    with pytest.raises(ValueError, match="uses_validation_data=true"):
        write_validation_report(
            generated_csv=generated,
            observed_csv=observed,
            output_json=tmp_path / "report.json",
            output_csv=tmp_path / "report.csv",
            expected_rows=1,
        )

    _write_generated(generated, [_generated_row(9), _generated_row(9)])
    with pytest.raises(ValueError, match="duplicate"):
        write_validation_report(
            generated_csv=generated,
            observed_csv=observed,
            output_json=tmp_path / "report.json",
            output_csv=tmp_path / "report.csv",
            expected_rows=1,
        )


def test_validation_rejects_non_heldout_day(tmp_path) -> None:
    generated = tmp_path / "generated.csv"
    observed = tmp_path / "observed.csv"
    generated_row = _generated_row(9)
    generated_row["talkingdata_day"] = 3
    observed_row = _observed_row(9)
    observed_row["day_index"] = 3
    _write_generated(generated, [generated_row])
    _write_observed(observed, [observed_row])

    with pytest.raises(ValueError, match="only accepts days 4..7"):
        write_validation_report(
            generated_csv=generated,
            observed_csv=observed,
            output_json=tmp_path / "report.json",
            output_csv=tmp_path / "report.csv",
            expected_rows=1,
        )
