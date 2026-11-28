"""Score paired free-hour Needs replies against held-out device-hour activity."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from analysis_entry_calibration_comparison import load_observations
from check_hourly_choice_evidence import request_payload
from proto.app_entry.needs import sanitize_phone_needs, stated_phone_use_decision
from proto.app_entry.wire import parse_compact_reply


USE = "use_phone"
LEAVE = "leave_phone"
CHOICES = (USE, LEAVE)
ARMS = ("old", "new")


def rate(n, denominator):
    return n / denominator if denominator else None


def activity_scores(rows, column):
    """Missing/invalid responses are accounted for separately from phone non-use."""
    scored = [r for r in rows if r[column] in CHOICES]
    active = sum(r["observed_active"] for r in scored)
    idle = len(scored) - active
    use_hit = sum(r["observed_active"] and r[column] == USE for r in scored)
    false_use = sum(not r["observed_active"] and r[column] == USE for r in scored)
    use_recall = rate(use_hit, active)
    idle_recall = rate(idle - false_use, idle)
    return {
        "evaluable": len(scored), "observed_active": active, "observed_idle": idle,
        "use_on_active": use_hit, "leave_on_active": active - use_hit,
        "use_on_idle": false_use, "leave_on_idle": idle - false_use,
        "use_recall": use_recall, "idle_recall": idle_recall, "false_use_rate": rate(false_use, idle),
        "use_rate": rate(use_hit + false_use, len(scored)), "accuracy": rate(use_hit + idle - false_use, len(scored)),
        "balanced_accuracy": (use_recall + idle_recall) / 2 if active and idle else None,
    }


def stage_summary(rows, stage):
    columns = {arm: f"{arm}_{stage}" for arm in ARMS}
    paired = [r for r in rows if all(r[col] in CHOICES for col in columns.values())]
    transitions = Counter((r[columns["old"]], r[columns["new"]], r["observed_active"]) for r in paired)
    switched = {
        f"{a}_to_{b}": {label: transitions[a, b, active] for label, active in (("active", True), ("idle", False))}
        for a in CHOICES for b in CHOICES
    }
    return {
        "coverage": {arm: dict(Counter(r[col] for r in rows)) for arm, col in columns.items()},
        "method_evaluable": {arm: activity_scores(rows, col) for arm, col in columns.items()},
        "common_evaluable": {method: activity_scores(paired, col)
                             for method, col in {**columns, "history": "history_choice"}.items()},
        "paired_transitions": switched,
    }


def section(rows):
    return {
        "scheduled": len(rows), "people": len({r["agent_id"] for r in rows}),
        "baseline_all_scheduled": activity_scores(rows, "history_choice"),
        "initial": stage_summary(rows, "initial"), "final": stage_summary(rows, "final"),
    }


def make_report(rows):
    def groups(key):
        return {str(value): section([r for r in rows if r[key] == value]) for value in sorted({r[key] for r in rows})}

    return {
        "endpoint": "Initial stated choice and production-accepted Needs intention in one frozen free hour per case.",
        "reference": "Presence of any recorded App activity on the held-out device in that hour.",
        "baseline": "Same device, same hour of days 1–3; use if at least two of three hours recorded App activity.",
        "sampling": "Stratified matched probe. Its unweighted results describe the selected hours.",
        "overall": section(rows), "by_split": groups("split"), "by_history_active_days": groups("active_days"),
        "by_clock": groups("clock"), "by_resident": groups("agent_id"),
        "by_device_activity": groups("observed_active"),
        "requests": {
            arm: {"total": sum(r[f"{arm}_requests"] for r in rows),
                  "repairs": sum(r[f"{arm}_requests"] == 2 for r in rows)}
            for arm in ARMS
        },
    }


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def messages_digest(messages):
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def json_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def check_reply(row, design_hash, model):
    if row["model"] != model or row["initial_sha256"] != design_hash:
        raise ValueError("Model or frozen message hash mismatch")
    calls = row["exchanges"]
    if len(calls) not in (1, 2) or len(calls) != row["requests"] or messages_digest(calls[0]["messages"]) != design_hash:
        raise ValueError("Recorded requests disagree with the frozen schedule")
    initial = request_payload(calls[0])
    first_raw = calls[0].get("raw")
    stated = stated_phone_use_decision(first_raw) if isinstance(first_raw, str) else None
    if row["raw_initial_choice"] != (stated if stated in CHOICES else None):
        raise ValueError("First-choice flag disagrees with raw reply")
    accepted = None
    expected_status = None
    for index, call in enumerate(calls):
        if call.get("model") is not None and call["model"] != model:
            raise ValueError("Unexpected response model")
        if request_payload(call) != initial:
            raise ValueError("Repair changed the observation or output schema")
        raw = call.get("raw")
        if not isinstance(raw, str):
            if index != len(calls) - 1:
                raise ValueError("Unexpected repair after transport failure")
            continue
        parsed, _ = sanitize_phone_needs(parse_compact_reply(raw), initial["schema_version"])
        if parsed and stated in (None, parsed["phone_use_decision"]):
            if index != len(calls) - 1:
                raise ValueError("Extra request after valid reply")
            accepted = parsed["phone_use_decision"]
            expected_status = "ok_repaired" if index else "ok"
    if (row["accepted_choice"] != accepted or (accepted and row["parse_status"] != expected_status)
            or (not accepted and row["parse_status"] in {"ok", "ok_repaired"})):
        raise ValueError("Final intention or status disagrees with archived replies")
    raw_label = stated if stated in CHOICES else ("unmeasured" if isinstance(first_raw, str) else "transport_error")
    return raw_label, accepted or "technical_failure"


def analyze(folder, heldout):
    design = json.loads((folder / "experiment_design.json").read_text(encoding="utf-8"))
    selection = folder / "selection.jsonl"
    if file_digest(selection) != design["selection_sha256"] or file_digest(heldout) != design["heldout_sha256"]:
        raise ValueError("Frozen selection or held-out data modified")
    cases = json_lines(selection)
    schedule = design["schedule"]
    expected = {(r["case_id"], arm) for r in cases for arm in ARMS}
    slots = {(r["case_id"], r["arm"]): r["initial_sha256"] for r in schedule}
    if (len(cases) != design["n_cases"] or len(expected) != len(cases) * 2
            or set(slots) != expected or len(slots) != len(schedule)):
        raise ValueError("Incomplete or duplicate case schedule")
    decisions_path = folder / "probe_decisions.jsonl"
    decisions = json_lines(decisions_path) if decisions_path.is_file() else []
    predictions = {}
    for decision in decisions:
        key = (decision["case_id"], decision["arm"])
        if key not in slots or key in predictions:
            raise ValueError("Unknown or duplicate decision")
        predictions[key] = (*check_reply(decision, slots[key], design["model"]), decision["requests"])
    observed = load_observations(heldout, (4, 5, 6, 7))
    rows, resident_splits, device_hours = [], {}, set()
    for case in cases:
        cid, resident, split = case["case_id"], case["agent_id"], case["split"]
        day, hour = case["talkingdata_day"], case["hour"]
        device_key = (str(case["device_id"]), day, hour)
        if (split not in ("explore", "holdout") or resident_splits.setdefault(resident, split) != split
                or device_key in device_hours or device_key not in observed):
            raise ValueError("Duplicate or unrelated case or person leaked between partitions")
        device_hours.add(device_key)
        previous = request_payload({"messages": case["old_messages"]})["inputs"]
        history = previous["day1_3_habit"]["same_hour_active"]
        active = case["active_days"]
        if (slots[cid, "old"] != messages_digest(case["old_messages"]) or slots[cid, "old"] != case["old_messages_sha256"]
                or type(active) is not int or not 0 <= active <= 3 or history != {"seen": 3, "active": active}
                or previous["talkingdata_day"] != day or previous["hour"] != hour):
            raise ValueError("Archived original request or history inconsistent with the selected case")
        row = dict(case_id=cid, split=split, agent_id=resident, talkingdata_day=day, hour=hour,
                   clock="00_to_05" if hour < 6 else "06_to_23", active_days=active,
                   history_choice=USE if active >= 2 else LEAVE,
                   observed_active=observed[device_key].count > 0)
        for arm in ARMS:
            first, final, requests = predictions.get((cid, arm), ("missing", "missing", 0))
            row.update({f"{arm}_initial": first, f"{arm}_final": final, f"{arm}_requests": requests})
        rows.append(row)
    report = make_report(rows)
    report.update(model=design["model"], selection_sha256=design["selection_sha256"],
                  heldout_sha256=design["heldout_sha256"], design_sha256=file_digest(folder / "experiment_design.json"),
                  responses_sha256=file_digest(decisions_path) if decisions_path.is_file() else None)
    with (folder / "device_activity_cases.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (folder / "device_activity_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                           encoding="utf-8")
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run-dir", required=True, type=Path)
    cli.add_argument("--heldout", required=True, type=Path)
    args = cli.parse_args()
    report = analyze(args.run_dir, args.heldout)
    print(json.dumps({name: section["final"]["common_evaluable"] for name, section in report["by_split"].items()}))
