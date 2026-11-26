"""Build a matched 60+ rehearsal cohort from the existing 59-device v3 sample."""
from __future__ import annotations

import csv
from itertools import permutations
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pandas as pd

from proto.app_entry.bundle_loader import HourlyBundleReplaySource


EXAMPLE = Path(__file__).resolve().parent
ROOT = EXAMPLE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_talkingdata_elderly_10_artifact import REFERENCE_DATES, _build_full_hourly_bundle

SOURCE = ROOT / "agentsociety_data" / "elderly_v3"
PROFILE_FILE = EXAMPLE / "profiles.json"
GENDERS = {"F": "女", "M": "男"}


def prepare_cohort(output_dir: Path, count: int, *, source: Path = SOURCE,
                   profile_file: Path = PROFILE_FILE) -> list[dict]:
    """Write the run's device map, 72-hour input bundles and simulation profiles.

    The upstream 59-device pool was preselected for activity in both observation
    windows. Within it, select by demographics alone. Only D1–3 app signals
    enter the simulation. Profile assignment is computed for all eligible devices
    before truncating, keeping an existing pilot pair stable during expansion.
    """
    if type(count) is not int or not 1 <= count <= 6:
        raise ValueError("count must be an integer from 1 to 6")
    summary_file = source / "talkingdata_elderly_59_device_summary.csv"
    with summary_file.open(encoding="utf-8-sig", newline="") as handle:
        eligible = sorted(
            [(row["gender"], int(row["device_id"]), int(row["age"]),
              int(row["day1_3_active_hours_cleaned"]), int(row["day1_3_active_event_app_exposures"]))
             for row in csv.DictReader(handle) if int(row["age"]) >= 60],
        )
    if len(eligible) < count or len({r[1] for r in eligible}) != len(eligible):
        raise ValueError("insufficient or duplicate age-eligible devices in the source")
    profiles = sorted(json.loads(profile_file.read_text()), key=lambda profile: profile["id"])
    if len({p["id"] for p in profiles}) != len(profiles):
        raise ValueError("duplicate source profile IDs")
    matched = {}
    for gender in sorted({r[0] for r in eligible}):
        devices = [r for r in eligible if r[0] == gender]
        candidates = [p for p in profiles if p["gender"] == GENDERS[gender] and p["age"] >= 60]
        if len(candidates) < len(devices):
            raise ValueError(f"too few distinct age-eligible synthetic profiles of gender {gender}")
        best = min(permutations(candidates, len(devices)),
                   key=lambda assignment: sum(abs(p["age"] - device[2]) for p, device in zip(assignment, devices)))
        matched.update({device[1]: p for device, p in zip(devices, best)})

    records, run_profiles = [], []
    for rank, (gender, device, age, active_hours, exposures) in enumerate(eligible[:count], 1):
        profile = matched[device]
        records.append({"rank": rank, "device_id": str(device), "device_age": age,
                        "profile_id": profile["id"], "profile_age": profile["age"], "gender": gender,
                        "reference_active_hours": active_hours, "reference_exposures": exposures})
        run_profiles.append(dict(profile, id=rank))
    device_ids = [r["device_id"] for r in records]
    with (source / "talkingdata_elderly_59_hourly_summary.csv").open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        observations = pd.DataFrame([row for row in reader if row["date"] in REFERENCE_DATES
                                     and row["device_id"] in device_ids], columns=reader.fieldnames)
    if observations.duplicated(["device_id", "hour_key"]).any():
        raise ValueError("duplicate source device-hour in the reference period")
    for obs in observations.itertuples(index=False):
        day = REFERENCE_DATES.index(obs.date) + 1
        if (obs.phase != "replay_day_1_3" or int(obs.day_index) != day or not 0 <= int(obs.hour) < 24
                or obs.hour_key != f"{obs.date} {int(obs.hour):02d}:00:00"):
            raise ValueError("inconsistent source date, phase, day index or replay hour")
    # The existing bundle builder fills unobserved hours with inactive bundles.
    # It does not see held-out observations; keep only the three reference days.
    bundles = _build_full_hourly_bundle(observations, device_ids)
    replay = bundles.loc[bundles["day_index"] <= len(REFERENCE_DATES)]
    for record in records:
        device_rows = replay.loc[replay["device_id"] == record["device_id"]]
        if (len(device_rows) != 72 or (device_rows["active"] == "true").sum() != record["reference_active_hours"]
                or device_rows["active_event_app_exposures"].sum() != record["reference_exposures"]):
            raise ValueError(f"72-hour replay coverage disagrees with the source summary at rank {record['rank']}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir) as staging:
        staged = Path(staging)
        mapping = pd.DataFrame(records).rename(columns={"rank": "selected_rank"})
        mapping.to_csv(staged / "devices.csv", encoding="utf-8-sig", index=False)
        replay.to_csv(staged / "replay.csv", encoding="utf-8-sig", index=False)
        (staged / "profiles.json").write_text(json.dumps(run_profiles, ensure_ascii=False, indent=2) + "\n")
        HourlyBundleReplaySource(bundle_path=str(staged / "replay.csv"),
                                device_mapping_path=str(staged / "devices.csv"), replay_days=(1, 2, 3))
        for name in ("devices.csv", "replay.csv", "profiles.json"):
            (staged / name).replace(output_dir / name)
    return records
