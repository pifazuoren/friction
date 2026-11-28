# ruff: noqa: E402
# Load the experiment modules from this checkout after locating its root.
"""Offline D4–7 device-hour idle scoring for one or two frozen seven-day runs."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "examples/digital_friction_mvp").is_dir()
)
sys.path.insert(0, str(ROOT / "examples/digital_friction_mvp"))
from analysis_entry_calibration_comparison import (
    build_history,
    load_csv,
    load_observations,
    parse_bundle,
)


from check_hourly_choice_evidence import exchanges, request_payload
from proto.app_entry import PHONE_USE_NEEDS_V3
from proto.app_entry.needs import stated_phone_use_decision


def read_run(folder, ranks, expected):
    group = folder.name
    (manifest,) = json.loads((folder / f"exp_group_manifest_{group}.json").read_text())
    if (
        manifest["group_id"] != group
        or manifest["world_name"] != "baseline_low_friction"
        or manifest["status"] != "ok"
        or manifest["total_days"] != 7
        or manifest["agent_count"] != len(ranks)
    ):
        raise ValueError(f"Expected one completed seven-day baseline world in {folder}")
    identity = group, manifest["world_name"], manifest["exp_id"]

    def belongs(row):
        return (row["group_id"], row["world_name"], row["exp_id"]) == identity

    mapping = {}
    for row in load_csv(folder / f"app_entry_replay_summary_{group}.csv"):
        device, agent = row["device_id"], row["agent_id"]
        if (
            not belongs(row)
            or agent in mapping
            or ranks.get(device) != int(row["selected_rank"])
            or row["uses_validation_data_any"] != "0"
        ):
            raise ValueError(f"Invalid replay mapping in {folder}")
        mapping[agent] = device
    if len(mapping) != len(ranks) or set(mapping.values()) != ranks.keys():
        raise ValueError(f"Incomplete device mapping in {folder}")
    valid, failed = {}, set()
    for prefix, is_error in (
        ("app_entry_rollout_hourly", False),
        ("app_entry_rollout_errors", True),
    ):
        for row in load_csv(folder / f"{prefix}_{group}.csv"):
            key = row["device_id"], int(row["talkingdata_day"]), int(row["hour"])
            if (
                not belongs(row)
                or key not in expected
                or key in valid
                or key in failed
                or mapping.get(row["agent_id"]) != key[0]
                or row["uses_validation_data"] != "0"
                or (row["entry_status"] == "llm_rollout_error") != is_error
            ):
                raise ValueError(f"Invalid or duplicate export {key} in {folder}")
            if is_error:
                failed.add(key)
            else:
                valid[key] = parse_bundle(row, key[1])
    return valid, failed


def score(keys, observed, model):
    actual_idle = sum(observed[k].count == 0 for k in keys)
    predicted_idle = sum(model[k].count == 0 for k in keys)
    hit = sum(observed[k].count == model[k].count == 0 for k in keys)
    actual_active, false_idle = len(keys) - actual_idle, predicted_idle - hit
    return dict(
        scored=len(keys),
        observed_idle=actual_idle,
        observed_active=actual_active,
        predicted_idle=predicted_idle,
        idle_hit=hit,
        active_misread_idle=false_idle,
        idle_recall=hit / actual_idle if actual_idle else None,
        idle_precision=hit / predicted_idle if predicted_idle else None,
        false_idle_rate=false_idle / actual_active if actual_active else None,
    )


def compare(old, new):
    folders = {"old": old}
    if new is not None:
        folders["new"] = new
    hashes = {
        name: {
            f: hashlib.sha256((p / "inputs" / f).read_bytes()).hexdigest()
            for f in ("devices.csv", "replay.csv", "heldout.csv")
        }
        for name, p in folders.items()
    }
    if any(value != hashes["old"] for value in hashes.values()):
        raise ValueError("Frozen cohort, replay or held-out inputs differ across runs")
    devices = load_csv(old / "inputs/devices.csv")
    ranks = {r["device_id"]: int(r["selected_rank"]) for r in devices}
    if (
        not ranks
        or len(ranks) != len(devices)
        or set(ranks.values()) != set(range(1, len(devices) + 1))
    ):
        raise ValueError("Invalid frozen device roster")
    observed = load_observations(old / "inputs/heldout.csv", (4, 5, 6, 7))
    reference = load_observations(old / "inputs/replay.csv", (1, 2, 3))
    for records, days in ((reference, (1, 2, 3)), (observed, (4, 5, 6, 7))):
        if records.keys() != {
            (dev, d, h) for dev in ranks for d in days for h in range(24)
        }:
            raise ValueError("Incomplete or foreign hours in frozen inputs")
    expected = set(observed)
    history = build_history(reference, expected)
    models, failures = {}, {}
    for name, folder in folders.items():
        models[name], failures[name] = read_run(folder, ranks, expected)
    common = expected.intersection(*(model.keys() for model in models.values()))

    def section(selected):
        shared = selected & common
        coverage, own, paired = {}, {}, {}
        for name, model in models.items():
            valid, failed = selected.intersection(model), selected & failures[name]
            coverage[name] = dict(
                valid=len(valid),
                failed=len(failed),
                missing=len(selected - valid - failed),
            )
            own[name] = score(valid, observed, model)
            paired[name] = score(shared, observed, model)
        paired["personal_history"] = score(shared, observed, history)
        return dict(
            expected=len(selected),
            coverage=coverage,
            common_valid=paired,
            method_valid=own,
        )

    night = {k for k in expected if k[2] <= 5}
    usual_idle = {k for k in expected if history[k].count == 0}
    return dict(
        runs={name: p.name for name, p in folders.items()},
        frozen_sha256=hashes["old"],
        all_hours=section(expected),
        hours_00_to_05=section(night),
        hours_06_to_23=section(expected - night),
        historically_idle_hours=section(usual_idle),
        historically_active_hours=section(expected - usual_idle),
        historically_idle_hours_06_to_23=section(usual_idle - night),
        by_day={d: section({k for k in expected if k[1] == d}) for d in range(4, 8)},
        by_clock_hour={
            h: section({k for k in expected if k[2] == h}) for h in range(24)
        },
    )


def empty_summary():
    return {
        "free_hours": 0,
        "raw_initial": Counter(),
        "raw_repair": Counter(),
        "execution": Counter(),
        "history_3_of_3_and_heldout_active_execution": Counter(),
    }


def audit(folder, through_day):
    days = range(4, through_day + 1)
    cohort = json.loads((folder / "resolved_config.json").read_text())["cohort"]
    devices = {r["agent_id"]: r["device_id"] for r in cohort}
    if (
        not devices
        or len(devices) != len(cohort)
        or len(set(devices.values())) != len(cohort)
    ):
        raise ValueError("Missing or duplicate resident/device mappings")
    replay = load_observations(folder / "inputs/replay.csv", (1, 2, 3))
    heldout = load_observations(folder / "inputs/heldout.csv", days)
    expected = {(agent, d, h) for agent in devices for d in days for h in range(24)}
    traces = defaultdict(list)
    routes = {}
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.endswith("\n") and through_day < 7:
                    continue  # The active run may be appending next day's last trace record.
                row = json.loads(line)
                if row["talkingdata_day"] not in days:
                    continue
                key = row["agent_id"], row["talkingdata_day"], row["hour"]
                if (
                    row["group_id"] != folder.name
                    or row["world"] != "baseline_low_friction"
                    or key not in expected
                ):
                    raise ValueError(f"Foreign trace record {key}")
                if (row["module"], row["kind"]) == (
                    "hourly_intention",
                    "hourly_intention",
                ):
                    if key in routes:
                        raise ValueError(f"Duplicate route {key}")
                    routes[key] = row
                if row["module"] == "app_needs":
                    traces[key].append(row)
    if routes.keys() != expected:
        raise ValueError(
            f"Expected {len(expected)} completed resident-hours, found {len(routes)}"
        )
    by_day = {d: empty_summary() for d in days}
    for (agent, day, hour), route in routes.items():
        key = agent, day, hour
        calls = exchanges(traces[key], "app_needs", route)
        if not calls:
            raise ValueError(f"Missing Needs evidence {key}")
        first = request_payload(calls[0][0])
        if first.get("schema_version") != PHONE_USE_NEEDS_V3:
            continue
        inputs = first["inputs"]
        device = devices[agent]
        past_active = sum(replay[device, d, hour].count > 0 for d in (1, 2, 3))
        if (
            inputs["phone_use_context"]["task_opportunity"] != "none_actionable"
            or (inputs["talkingdata_day"], inputs["hour"]) != (day, hour)
            or inputs["day1_3_habit"]["same_hour_active"]
            != {"seen": 3, "active": past_active}
            or [c["phase"] for c, _, _ in calls]
            not in (["initial"], ["initial", "repair"])
        ):
            raise ValueError(f"Invalid free-hour evidence {key}")
        summary = by_day[day]
        summary["free_hours"] += 1
        for call, reply, _ in calls:
            choice = (
                "transport_error"
                if reply["kind"] == "error"
                else stated_phone_use_decision(reply["raw"])
            )
            summary["raw_" + call["phase"]][choice or "unstated"] += 1
        action = route["executed_choice"]
        if route["status"] == "technical_failure" and action is None:
            action = "technical_failure"
        elif route["status"] != "accepted" or action not in {"no_app", "habitual_app"}:
            raise ValueError(f"Unknown free-hour execution {key}")
        summary["execution"][action] += 1
        if past_active == 3 and heldout[device, day, hour].count > 0:
            summary["history_3_of_3_and_heldout_active_execution"][action] += 1
    total = empty_summary()
    for summary in by_day.values():
        total["free_hours"] += summary["free_hours"]
        for field in total.keys() - {"free_hours"}:
            total[field].update(summary[field])
    return {"run": folder.name, "by_day": by_day, "total": total}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(
        description="Recompute the two archived seven-day device comparisons and the V3 free-hour decisions."
    )
    cli.add_argument(
        "old",
        type=Path,
        help="First completed seven-day run with inputs and hourly exports",
    )
    cli.add_argument(
        "new",
        type=Path,
        help="Second completed seven-day run with inputs, hourly exports and trace",
    )
    args = cli.parse_args()
    idle = compare(args.old, args.new)
    phone = audit(args.new, 7)
    if not phone["total"]["free_hours"]:
        cli.error("Second run contains no V3 free-hour Needs requests")
    print(
        json.dumps(
            {"idle_comparison": idle, "free_phone_hour_audit": phone},
            indent=2,
            ensure_ascii=False,
        )
    )
