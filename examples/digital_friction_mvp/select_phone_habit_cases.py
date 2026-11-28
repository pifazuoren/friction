"""Freeze a stratified, participant-disjoint retrospective panel from archived initial requests."""

import argparse
from collections import Counter
from contextlib import closing
import hashlib
from itertools import combinations, product
import json
from pathlib import Path
import random
import sqlite3
from uuid import UUID

from check_hourly_choice_evidence import request_payload
from proto.app_entry.bundle_loader import HourlyBundleReplaySource
from proto.app_entry.habit_memory import update_habit_memory_from_bundle


SEED = 20261128
STRATA = list(product(range(4), ("night00_05", "day06_23")))
PER_CELL = 2
# The proposed prompt was illustrated with this resident's D4 13:00 record.
SHOWN = (2, 4, 13)
V3 = "digital_needs_phone_use_v3"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def stratum(case):
    return case["active_days"], case["period"]


def name(cell):
    return f"{cell[0]}of3_{cell[1]}"


def read_baseline(folder, cohort):
    inputs = folder / "inputs"
    replay = HourlyBundleReplaySource(
        bundle_path=str(inputs / "replay.csv"),
        device_mapping_path=str(inputs / "devices.csv"),
        replay_days=(1, 2, 3),
    )
    (manifest,) = json.loads(
        (folder / f"exp_group_manifest_{folder.name}.json").read_text()
    )
    if manifest["group_id"] != folder.name or manifest["status"] != "ok":
        raise ValueError("Incomplete archive")
    table = "as_" + str(UUID(manifest["exp_id"])).replace("-", "_") + "_mvp_status"
    db = (folder / "run_evidence.sqlite").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(db, uri=True)) as con:
        snapshots = {
            a: json.loads(s)["proto_day4_replay_snapshot"]
            for a, s in con.execute(
                f"SELECT agent_id,status_json FROM {table} WHERE day=3"
            )
        }
    if set(snapshots) != set(cohort):
        raise ValueError("Missing day-3 handoff")
    habits = {}
    for agent, device in cohort.items():
        memory = {}
        for d in (1, 2, 3):
            for h in range(24):
                bundle = replay.bundle_for_device(
                    device_id=device, talkingdata_day=d, hour=h
                )
                memory = update_habit_memory_from_bundle(memory, bundle)
        if (
            memory != snapshots[agent]["app_entry_habit_memory"]
            or memory["total_hours_seen"] != 72
        ):
            raise ValueError(
                f"Replay and archived day-3 memory differ for resident {agent}"
            )
        habits[agent] = memory
    return habits


def read_candidates(folder):
    config = json.loads((folder / "resolved_config.json").read_bytes())
    cohort = {r["agent_id"]: r["device_id"] for r in config["cohort"]}
    habits = read_baseline(folder, cohort)
    seen, candidates = set(), []
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        for line_no, line in enumerate(path.open(encoding="utf-8"), 1):
            row = json.loads(line)
            if (row.get("module"), row.get("kind"), row.get("phase")) != (
                "app_needs",
                "request",
                "initial",
            ):
                continue
            agent, day, hour = row["agent_id"], row["talkingdata_day"], row["hour"]
            if day < 4:
                continue
            key = (agent, day, hour)
            if (
                key in seen
                or row["group_id"] != folder.name
                or row["code_hash"] != config["source_sha256"]
            ):
                raise ValueError(f"Unverified request {key}")
            seen.add(key)
            body = request_payload(row)
            if body.get("schema_version") != V3:
                continue
            inputs = body["inputs"]
            context = inputs["phone_use_context"]
            hh = str(hour)
            habit = habits[agent]
            if (
                context["task_opportunity"] != "none_actionable"
                or (inputs["talkingdata_day"], inputs["hour"]) != (day, hour)
                or inputs["day1_3_habit"]
                != {
                    "replay_days": [1, 2, 3],
                    "same_hour_active": habit["active_by_hour"][hh],
                }
            ):
                raise ValueError(
                    f"Archive and reconstructed exposure disagree at {key}"
                )
            period = "night00_05" if hour < 6 else "day06_23"
            active = habit["active_by_hour"][hh]["active"]
            candidates.append(
                dict(
                    case_id=f"p{agent:02d}_d{day}_h{hour:02d}",
                    agent_id=agent,
                    talkingdata_day=day,
                    hour=hour,
                    period=period,
                    active_days=active,
                    stratum=name((active, period)),
                    waiting="hours_until_review" in context,
                    device_id=cohort[agent],
                    same_hour_context_counts=habit["context_by_hour"][hh],
                    same_hour_primary_counts=habit["primary_context_by_hour"][hh],
                    old_messages=row["messages"],
                    old_messages_sha256=sha(canonical(row["messages"])),
                    old_request_sha256=sha(line.encode()),
                    old_trace_file=path.name,
                    old_line_number=line_no,
                    old_query_id=row["query_id"],
                    old_call_id=row["call_id"],
                    old_parameters=row["parameters"],
                    old_schema_version=V3,
                )
            )
    if seen != set(product(cohort, range(4, 8), range(24))):
        raise ValueError("Incomplete initial Needs coverage")
    return candidates, cohort


def select(candidates, cohort):
    rng = random.Random(SEED)
    pool = [
        c
        for c in candidates
        if (c["agent_id"], c["talkingdata_day"], c["hour"]) != SHOWN
    ]
    agents = sorted(cohort)
    # Pick a seeded five/five partition maximizing available sampling cells on both sides.
    partitions = list(
        combinations([a for a in agents if a != SHOWN[0]], len(agents) // 2)
    )
    rng.shuffle(partitions)

    def coverage(held):
        counts = Counter((c["agent_id"] in held, stratum(c)) for c in pool)
        return sum(min(PER_CELL, n) for n in counts.values())

    holdout = set(max(partitions, key=coverage))
    chosen, inventory = [], {}
    for split, wanted in (("holdout", holdout), ("explore", set(agents) - holdout)):
        grouped = {
            k: [c for c in pool if c["agent_id"] in wanted and stratum(c) == k]
            for k in STRATA
        }
        quota = {k: min(PER_CELL, len(v)) for k, v in grouped.items()}
        for source in STRATA:
            for _ in range(PER_CELL - quota[source]):
                # If a cell cannot be filled, preserve the history frequency before matching clock period.
                eligible = [k for k in STRATA if quota[k] < len(grouped[k])]
                target = min(
                    eligible,
                    key=lambda k: (abs(k[0] - source[0]), quota[k], k[1] != source[1]),
                )
                quota[target] += 1
        counts = Counter()
        records = []
        for cell in sorted(STRATA, key=lambda k: len(grouped[k])):
            avail = list(grouped[cell])
            rng.shuffle(avail)
            for _ in range(quota[cell]):

                def priority(c):
                    a, h = c["agent_id"], c["hour"]
                    return (
                        counts["person", a] > 0,
                        counts["clock", a, h],
                        counts["person", a],
                        counts["day", c["talkingdata_day"]],
                        counts["waiting", c["waiting"], c["period"]],
                    )

                selected = min(avail, key=priority)
                avail.remove(selected)
                counts.update(
                    [
                        ("person", selected["agent_id"]),
                        ("clock", selected["agent_id"], selected["hour"]),
                        ("day", selected["talkingdata_day"]),
                        ("waiting", selected["waiting"], selected["period"]),
                    ]
                )
                records.append(dict(selected, split=split))
        if {c["agent_id"] for c in records} != wanted:
            raise ValueError("Participant coverage incomplete")
        inventory[split] = {
            "people": sorted(wanted),
            "available": {name(k): len(v) for k, v in grouped.items()},
            "selected": {name(k): n for k, n in quota.items()},
        }
        chosen.extend(records)
    return sorted(chosen, key=lambda c: c["case_id"]), inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    candidates, cohort = read_candidates(args.archive)
    rows, inventory = select(candidates, cohort)
    payload = b"".join(canonical(r) + b"\n" for r in rows)
    meta = dict(
        source=args.archive.name,
        seed=SEED,
        all_eligible=len(candidates),
        split_details=inventory,
        excluded_previously_shown=[list(SHOWN)],
        sample_size=len(rows),
        availability_before_example_exclusion=dict(
            Counter(c["stratum"] for c in candidates)
        ),
        selection_sha256=sha(payload),
        replay_sha256=sha((args.archive / "inputs/replay.csv").read_bytes()),
        procedure="Two per active-days × time-bin stratum in each participant-disjoint split wherever available; deficits reallocated within same active-day count first. Sample prioritizes people, distinct same-person clock hours, days and waiting status. D4–7 labels, historical model replies, and actions excluded from selection.",
    )
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "selection.jsonl").write_bytes(payload)
    (args.out / "selection_design.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
