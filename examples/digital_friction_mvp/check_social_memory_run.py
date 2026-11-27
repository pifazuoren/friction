"""Audit one five- or seven-day social-memory run from local exports and actual requests."""

import argparse
from collections import Counter
from contextlib import closing
import csv
import json
import hashlib
from pathlib import Path
import sqlite3
from uuid import UUID

from proto.metrics import attempt_rows_table_name


WORLD = "baseline_low_friction"
MODULES = ("app_needs", "app_plan", "strategy")
SUPPORTED_DAYS = (5, 7)


def rollout_hours(expected_days):
    if expected_days not in SUPPORTED_DAYS:
        raise ValueError("expected_days must be 5 or 7")
    return {(day, hour) for day in range(4, expected_days + 1) for hour in range(24)}


def load_rows(folder, prefix, group):
    with (folder / f"{prefix}_{group}.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"group_id", "world_name", "exp_id"} <= set(reader.fieldnames or ()):
            raise ValueError(f"missing export columns in {prefix}")
        return list(reader)


def check_replay(conn, exp_id, agent, device):
    # The experiment normally exports one status per day at the next midnight.
    # Compare successive daily counts for every hour to distinguish 72 unique
    # reference hours from repeated observations in a single day.
    table = f"as_{exp_id.replace('-', '_')}_mvp_status"
    daily = {}
    snapshot = {}
    for raw, in conn.execute(f"SELECT status_json FROM {table} WHERE agent_id=? ORDER BY day,t", (agent,)):
        state = json.loads(raw)
        habit = state.get("proto_app_entry_habit_memory") or {}
        day = habit.get("last_updated_day")
        if day in (1, 2, 3) and habit.get("last_updated_hour") == 23 and str(habit.get("device_id")) == device:
            daily[day] = habit
        snapshot = state.get("proto_day4_replay_snapshot") or snapshot
    missing = []
    for day in (1, 2, 3):
        habit = daily.get(day, {})
        previous = daily.get(day - 1, {})
        for hour in range(24):
            key = str(hour)
            current_count = habit.get("active_by_hour", {}).get(key, {}).get("seen")
            last_count = previous.get("active_by_hour", {}).get(key, {}).get("seen", 0)
            if current_count != day or last_count != day - 1 or habit.get("replay_days") != list(range(1, day + 1)):
                missing.append([day, hour])
    snapshot_ok = all((
        str(snapshot.get("agent_id")) == agent, str(snapshot.get("device_id")) == device,
        snapshot.get("world") == WORLD, snapshot.get("created_at_talkingdata_day") == 3,
        snapshot.get("created_at_hour") == 23, snapshot.get("completed_replay_days") == [1, 2, 3],
        snapshot.get("app_entry_habit_memory", {}).get("total_hours_seen") == 72,
    ))
    # A continuous comparison may check this digest before attributing divergence to the mode.
    snapshot_bytes = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return {"verified_hours": 72 - len(missing), "unverified_hours": missing, "day3_snapshot_ok": snapshot_ok,
            "day3_snapshot_sha256": hashlib.sha256(snapshot_bytes).hexdigest() if snapshot_ok else None}


def read_attempts(conn, exp_id, agent):
    attempts = {3: {}, 4: {}}
    table = attempt_rows_table_name(exp_id)
    for day, tick, task, family, action, outcome, raw in conn.execute(
        f"SELECT day,t,task_id,task_family,strategy_type,outcome_type,payload_json FROM {table} "
        "WHERE agent_id=? AND day IN (3,4) ORDER BY day,t,id", (agent,),
    ):
        data = json.loads(raw)
        episode = data["episode_id"]
        if not episode or episode in attempts[day]:
            raise ValueError("missing or duplicate completed episode ID")
        attempts[day][episode] = {
            "episode_id": episode, "day": day, "tick_seconds": tick, "task_id": task,
            "task_family": family, "strategy_type": action, "outcome_type": outcome,
            "requested_strategy_type": data["requested_strategy_type"],
            "help_used": data["outcome"]["help_used"], "support_delivery_status": data["support_delivery_status"],
        }
        if data.get("support_request_id"):
            attempts[day][episode]["support_request_id"] = data["support_request_id"]
    return attempts


def request_packet(row):
    for message in row["messages"]:
        if message.get("role") == "user":
            content = message["content"]
            return json.loads(content[content.index("{"):])
    raise ValueError("request missing user message")


def audit_trace(trace, group, agent, attempts, error_hours, expected_days=7):
    expected = rollout_hours(expected_days)
    files = sorted(trace.glob("llm-requests-*.jsonl"))
    if not files:
        raise FileNotFoundError(f"missing trace in {trace}")
    checks = {name: {"requests": 0, "evidence": None} for name in MODULES}
    app_hours = {name: set() for name in MODULES[:2]}
    day4_errors = []
    traced_entry_errors = set()
    needs_errors = set()
    needs_successes = set()
    strategy_ticks = {r["tick_seconds"] for r in attempts[4].values()}
    strategy_traced_ticks = set()
    matched_ids = {name: set() for name in MODULES}
    completed_decisions = {}
    same_family = None
    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                module = row.get("module")
                if row.get("group_id") == group and str(row.get("agent_id")) == agent and row.get("world") == WORLD:
                    time_key = (row["talkingdata_day"], row["hour"])
                    if module == "app_entry" and row.get("kind") == "entry" and row.get("status") == "llm_rollout_error":
                        traced_entry_errors.add(time_key)
                    if row.get("kind") == "decision" and module == "task" and row.get("status") == "completed" and time_key[0] == 5:
                        completed_decisions[row["episode_id"]] = {
                            "episode_id": row["episode_id"], "tick_seconds": row["tick_seconds"],
                            "strategy_type": row["action"], "outcome_type": row["outcome"],
                        }
                    if module == "app_needs":
                        if row.get("kind") == "parse" and row.get("status") in {"ok", "ok_repaired"}:
                            needs_successes.add(time_key)
                        elif row.get("kind") in {"error", "parse"}:
                            needs_errors.add(time_key)
                if row.get("kind") == "decision" and module == "task" and row.get("status") == "technical_failure":
                    if row.get("group_id") == group and row.get("talkingdata_day") == 4 and str(row.get("agent_id")) == agent:
                        day4_errors.append(row.get("hour"))
                if module not in checks or row.get("kind") != "request" or row.get("phase") != "initial":
                    continue
                if row.get("group_id") != group or row.get("world") != WORLD or str(row.get("agent_id")) != agent:
                    raise ValueError("request trace belongs to another run or agent")
                day = row["talkingdata_day"]
                if row["simulation_day"] != day - 1 or not 0 <= row["hour"] <= 23:
                    raise ValueError("inconsistent request clock")
                if module in app_hours:
                    if (day, row["hour"]) not in expected:
                        raise ValueError("App request outside expected rollout hours")
                    app_hours[module].add((day, row["hour"]))
                if day != 5:
                    continue
                check = checks[module]
                check["requests"] += 1
                packet = request_packet(row)
                if module == "strategy":
                    strategy_traced_ticks.add(row["tick_seconds"])
                    records = packet["task_relevant_memory"]["recent_task_episodes"]
                else:
                    records = packet["inputs"]["recent_task_episodes"]
                for item in records:
                    prior = attempts[3].get(item.get("episode_id"))
                    if not prior or not all(item.get(k) == v for k, v in prior.items()):
                        continue
                    matched_ids[module].add(prior["episode_id"])
                    evidence = {"call_id": row["call_id"], "day5_hour": row["hour"], **prior}
                    if not check["evidence"]:
                        check["evidence"] = evidence
                    if module == "strategy" and packet["task"]["task_family"] == prior["task_family"]:
                        for later in attempts[4].values():
                            if later["task_id"] == packet["task"]["task_id"] and later["tick_seconds"] == row["tick_seconds"]:
                                same_family = {"day4": evidence, "day5": later}
    skipped_plan = (error_hours & traced_entry_errors & needs_errors) - needs_successes - app_hours["app_plan"]
    absent_requests = {"app_needs": sorted(expected - app_hours["app_needs"]),
                       "app_plan": sorted(expected - app_hours["app_plan"] - skipped_plan)}
    inconsistent = sorted(episode for episode in completed_decisions.keys() | attempts[4].keys()
                          if episode not in completed_decisions or episode not in attempts[4]
                          or any(attempts[4][episode].get(k) != v for k, v in completed_decisions[episode].items()))
    for name, check in checks.items():
        if check["evidence"]:
            check["status"] = "verified"
        elif name in app_hours and not check["requests"]:
            check["status"] = "missing_evidence"
        elif not attempts[3]:
            check["status"] = "technical_failure" if day4_errors else "no_day4_completed_task"
        elif name == "strategy" and not check["requests"] and not attempts[4]:
            check["status"] = "no_day5_strategy_opportunity"
        else:
            check["status"] = "missing_evidence"
    return {"day4_completed_tasks": len(attempts[3]), "day5_completed_tasks": len(attempts[4]),
            "modules": checks, "same_family_strategy_example": same_family,
            "shared_day4_episode_ids": sorted(set.intersection(*matched_ids.values())),
            "day4_technical_task_failure_hours": day4_errors,
            "day5_decisions": list(completed_decisions.values()),
            "day5_decision_db_disagreements": inconsistent,
            "day5_completed_task_ticks_without_strategy_request": sorted(strategy_ticks - strategy_traced_ticks),
            "entry_errors_disagree_with_trace": sorted(error_hours ^ traced_entry_errors),
            "plan_skipped_after_recorded_needs_error": sorted(skipped_plan),
            "missing_app_request_hours": absent_requests}


def check_run(folder, group, db, trace, expected_days=7):
    report = {"group_id": group, "run_complete": False, "acceptance_ok": False,
              "cross_day_status": "missing_evidence", "issues": []}
    issues = report["issues"]
    try:
        expected_hours = rollout_hours(expected_days)
        manifest, = json.loads((folder / f"exp_group_manifest_{group}.json").read_text(encoding="utf-8"))
        exp = str(UUID(manifest["exp_id"]))
        expected = dict(group_id=group, world_name=WORLD, status="ok", agent_count=1, return_code=0,
                        qc_config_match=1, stage_mode="single", stage_count=1, stage_days=expected_days,
                        total_days=expected_days,
                        decision_interval_minutes=60, proto_app_entry_replay_days="1,2,3",
                        proto_task_entry_mode="app_context_replay_then_llm_rollout", uses_forced_replay=1)
        mismatch = [k for k, v in expected.items() if manifest.get(k) != v]
        snapshot_path = folder / "resolved_config.json"
        if snapshot_path.exists():
            archived_mode = json.loads(snapshot_path.read_text())["runtime"].get("proto_hourly_intention_mode", "legacy")
            if archived_mode != manifest.get("proto_hourly_intention_mode", "legacy"):
                mismatch.append("proto_hourly_intention_mode")
        if mismatch:
            issues.append("manifest mismatch: " + ", ".join(mismatch))
        replay, = load_rows(folder, "app_entry_replay_summary", group)
        rollout = load_rows(folder, "app_entry_rollout_hourly", group)
        errors = load_rows(folder, "app_entry_rollout_errors", group)
        agent, device = replay["agent_id"], replay["device_id"]
        for row in [replay, *rollout, *errors]:
            if (row["group_id"], row["world_name"], row["exp_id"], row["agent_id"], row["device_id"]) != (
                group, WORLD, exp, agent, device,
            ):
                raise ValueError("exports disagree on run, world, agent or device")
        if (not device or replay["replay_hours_seen"] != "72" or replay["uses_validation_data_any"] != "0"
                or replay["day4_snapshot_created"] != "1"):
            issues.append("replay summary incomplete or used held-out data")
        successes = Counter((int(r["talkingdata_day"]), int(r["hour"])) for r in rollout)
        failures = Counter((int(r["talkingdata_day"]), int(r["hour"])) for r in errors)
        counts = successes + failures
        missing = sorted(expected_hours - counts.keys())
        invalid = sorted(k for k, n in counts.items() if n != 1 or k not in expected_hours)
        report["rollout"] = {"accounted_hours": len(expected_hours & counts.keys()), "missing": missing,
                             "valid_hours": len(expected_hours & successes.keys()), "expected_hours": len(expected_hours),
                             "duplicate_or_unexpected": invalid, "error_hours": sorted(failures)}
        if missing or invalid:
            issues.append("hourly rollout records missing, duplicated or out of range")
        if any(r["source"] != "llm_memory_rollout" or r["uses_validation_data"] != "0"
               or int(r["simulation_day"]) != int(r["talkingdata_day"]) - 1
               or min(int(r["needs_actual_requests"]), int(r["plan_actual_requests"])) < 1
               or not manifest.get("config_fingerprint") or r["config_fingerprint"] != manifest["config_fingerprint"]
               for r in rollout):
            issues.append("invalid rollout provenance or request counts")
        if any(r["entry_status"] != "llm_rollout_error" or r["uses_validation_data"] != "0"
               or int(r["simulation_day"]) != int(r["talkingdata_day"]) - 1
               or r["config_fingerprint"] != manifest.get("config_fingerprint") or r["bundle_generated"] != "0"
               for r in errors):
            issues.append("invalid rollout error provenance")
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            replay_check = report["replay"] = check_replay(conn, exp, agent, device)
            if replay_check["unverified_hours"] or not replay_check["day3_snapshot_ok"]:
                issues.append("incomplete replay or incorrect handoff snapshot")
            attempts = read_attempts(conn, exp, agent)
            report["exports_complete"] = not issues
            if manifest.get("proto_hourly_intention_mode") == "opportunity_v1":
                from check_hourly_intention_run import audit_intention_run
                report["hourly_intention"] = audit_intention_run(
                    folder, trace, conn, exp, agent, group, WORLD, expected_hours, set(failures))
        trace_check = report["cross_day"] = audit_trace(trace, group, agent, attempts, set(failures), expected_days)
        if trace_check["entry_errors_disagree_with_trace"]:
            issues.append("error export disagrees with actual hourly entry trace")
        if any(trace_check["missing_app_request_hours"].values()):
            issues.append(f"incomplete actual App request trace for days 4–{expected_days}")
        report["run_complete"] = not issues
        statuses = {v["status"] for v in trace_check["modules"].values()}
        if "hourly_intention" in report:
            issues.extend(report["hourly_intention"]["issues"])
            report["cross_day_status"] = report["hourly_intention"]["cross_day_status"]
            if trace_check["day5_completed_task_ticks_without_strategy_request"] or trace_check["day5_decision_db_disagreements"]:
                issues.append("missing low-level execution evidence")
        elif not successes and set(failures) == expected_hours:
            report["cross_day_status"] = "technical_failure"
        elif ("missing_evidence" in statuses or "technical_failure" in statuses
                or trace_check["day5_completed_task_ticks_without_strategy_request"]
                or trace_check["day5_decision_db_disagreements"]):
            issues.append("missing cross-day request evidence")
        elif statuses == {"verified"}:
            report["cross_day_status"] = "verified"
        else:
            report["cross_day_status"] = "no_natural_opportunity"
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, StopIteration) as exc:
        issues.append(f"{type(exc).__name__}: {exc}")
    if report["cross_day_status"] == "technical_failure" and not any("no valid" in x for x in issues):
        issues.append("no valid hourly decision to test the mechanism")
    report["acceptance_ok"] = report["run_complete"] and not issues
    monitor = report.get("rollout", {})
    expected_count = monitor.get("expected_hours", 0)
    valid_count = report.get("hourly_intention", {}).get("valid_intention_decisions", monitor.get("valid_hours", 0))
    rate = valid_count / expected_count if expected_count else None
    blockers = []
    if not report["acceptance_ok"]:
        blockers.append("run evidence failed acceptance")
    if rate is None or rate < 0.95:
        blockers.append("valid decision rate below the 95% project threshold")
    if report.get("hourly_intention", {}).get("low_level_technical_failure_hours"):
        blockers.append("technical failure during task execution")
    report["stability_gate"] = {
        "valid_decision_rate": rate, "valid_decisions": valid_count, "expected_hours": expected_count,
        "minimum_valid_rate": 0.95, "eligible_by_technical_stability": not blockers,
        "blockers": blockers, "remaining_expansion_checks": ["paired behavioral effect vs repeat noise", "cost and latency budget"],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("run-dir", "db", "trace", "output"):
        parser.add_argument(f"--{flag}", required=True, type=Path)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--expected-days", type=int, choices=SUPPORTED_DAYS, default=7)
    args = parser.parse_args()
    report = check_run(args.run_dir, args.group_id, args.db, args.trace, args.expected_days)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"run_complete={report['run_complete']} acceptance_ok={report['acceptance_ok']} "
          f"cross_day_status={report['cross_day_status']} "
          f"eligible_by_technical_stability={report['stability_gate']['eligible_by_technical_stability']} {args.output}")
    return int(not report["acceptance_ok"])


if __name__ == "__main__":
    raise SystemExit(main())
