import csv
import json

import pytest

from prepare_login_cohort import prepare_cohort
from proto.app_entry.bundle_loader import HourlyBundleReplaySource


def write_rows(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_cohort_is_age_eligible_and_uses_only_reference_signals(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    summary = [dict(device_id=str(device), gender=gender, age=age,
                    day1_3_active_hours_cleaned=1, day1_3_active_event_app_exposures=3,
                    day4_7_active_hours_cleaned=0)
               for device, gender, age in [(984, "M", 65), (123, "F", 61), (980, "M", 46)]]
    hourly = [dict(device_id=r["device_id"], date="2016-05-01", hour_key="2016-05-01 09:00:00",
                   day_index=1, hour=9, phase="replay_day_1_3", active_event_app_exposures=3,
                   unique_active_events=2, unique_active_apps=2, task_eligible_exposures=2,
                   app_context_counts_json='{"finance_context":2,"communication_social_context":1}',
                   top_app_context="finance_context") for r in summary]
    heldout = dict(hourly[0], date="2016-05-04", day_index=4, phase="heldout_day_4_7",
                   hour_key="2016-05-04 09:00:00", active_event_app_exposures="not read")
    summary_file = source / "talkingdata_elderly_59_device_summary.csv"
    hourly_file = source / "talkingdata_elderly_59_hourly_summary.csv"
    profile_file = source / "profiles.json"
    profiles = [{"id": 25, "gender": "男", "age": 69}, {"id": 35, "gender": "男", "age": 66},
                {"id": 15, "gender": "女", "age": 62}]
    write_rows(summary_file, summary)
    write_rows(hourly_file, [*hourly, heldout])
    profile_file.write_text(json.dumps(profiles))
    dest = tmp_path / "cohort"
    records = prepare_cohort(dest, 2, source=source, profile_file=profile_file)
    assert [(r["device_id"], r["profile_id"]) for r in records] == [("123", 15), ("984", 35)]
    assert [p["id"] for p in json.loads((dest / "profiles.json").read_text())] == [1, 2]
    loader = HourlyBundleReplaySource(bundle_path=str(dest / "replay.csv"),
                                      device_mapping_path=str(dest / "devices.csv"), replay_days=(1, 2, 3))
    assert loader.selected_devices == [(1, "123"), (2, "984")]
    with (dest / "replay.csv").open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 144 and all(int(r["day_index"]) <= 3 for r in rows)
    for row in rows:
        observed = (row["day_index"], row["hour"]) == ("1", "9")
        assert int(row["active_event_app_exposures"]) == (3 if observed else 0)
        assert row["primary_context"] == ("finance_context" if observed else "no_app_context")
    profile_file.write_text(json.dumps(profiles[::-1]))
    write_rows(summary_file, [dict(r, day4_7_active_hours_cleaned=95) for r in reversed(summary)])
    write_rows(hourly_file, list(reversed(hourly)))
    assert prepare_cohort(tmp_path / "pilot", 1, source=source, profile_file=profile_file) == records[:1]
    assert prepare_cohort(tmp_path / "round2", 2, source=source, profile_file=profile_file) == records
    write_rows(hourly_file, hourly[:1])
    with pytest.raises(ValueError, match="coverage disagrees"):
        prepare_cohort(tmp_path / "incomplete", 2, source=source, profile_file=profile_file)
