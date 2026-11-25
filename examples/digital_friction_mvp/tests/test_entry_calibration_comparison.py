import csv
import json

import pytest

from analysis_entry_calibration_comparison import compare, load_csv, write_csv


@pytest.fixture
def observations(tmp_path):
    reference = tmp_path / "reference.csv"
    heldout = tmp_path / "heldout.csv"
    rows = []
    for day in range(1, 5):
        for hour in range(24):
            count = day if hour >= 8 else 0
            rows.append({
                "device_id": "synthetic-device",
                "day_index": day,
                "hour": hour,
                "active": bool(count),
                "active_event_app_exposures": count,
                "app_context_counts_json": json.dumps({"finance_context": count} if count else {}),
            })
    write_csv(reference, rows[:72])
    write_csv(heldout, rows[72:])
    return reference, heldout


def test_valid_intersection_and_error_audit_leave_missing_hours_unscored(tmp_path, observations):
    reference, heldout = observations
    observed = load_csv(heldout)
    device = observed[0]["device_id"]
    day4 = [r for r in observed if r["device_id"] == device and r["day_index"] == "4"]
    rollout = [dict(r, talkingdata_day="4", exp_id="trial") for r in day4]
    old, new, errors = (tmp_path / name for name in ("old.csv", "new.csv", "errors.csv"))
    write_csv(old, rollout[1:])
    write_csv(new, rollout[:-2])
    write_csv(errors, [{"exp_id": "trial", "device_id": device, "talkingdata_day": 4, "hour": 0}])
    summary, hourly = compare(reference, heldout, [("old", old, errors), ("new", new, None)])
    results = {(r["method"], r["hour_scope"]): r for r in summary if r["level"] == "all"}
    assert results["old", "method_valid"]["error_hours"] == 1
    assert results["old", "method_valid"]["valid_hours"] == 23
    assert results["new", "method_valid"]["valid_hours"] == 22
    assert results["new", "method_valid"]["missing_hours"] == 2
    for method in ("old", "new", "personal_history"):
        assert results[method, "common_valid"]["scored_hours"] == 21
    assert results["old", "common_valid"]["exposure_mae"] == 0
    assert results["new", "common_valid"]["primary_correct"] == 21
    assert results["personal_history", "method_valid"]["scored_hours"] == 24
    assert results["personal_history", "method_valid"]["exposure_mae"] == pytest.approx(16 * 2 / 24)
    absent = [r for r in hourly if r["status"] != "valid"]
    assert {r["status"] for r in absent} == {"failed", "missing"}
    assert all(r["absolute_error"] is None and r["predicted_count"] is None for r in absent)


def test_empty_rollout_explicit_cohort_and_no_truth_leakage(tmp_path, observations):
    reference, heldout = observations
    observed = load_csv(heldout)[0]
    device = observed["device_id"]
    rollout = tmp_path / "empty.csv"
    with rollout.open("w", newline="") as handle:
        csv.writer(handle).writerow(["device_id", "talkingdata_day", "hour"])
    rows, _ = compare(reference, heldout, [("new", rollout, None)], [device])
    assert rows[0]["scored_hours"] == 0
    assert rows[0]["exposure_mae"] is None
    assert rows[0]["missing_hours"] == 24
    write_csv(rollout, [dict(observed, talkingdata_day=4, uses_validation_data="true")])
    with pytest.raises(ValueError, match="used held-out data"):
        compare(reference, heldout, [("new", rollout, None)], [device])
