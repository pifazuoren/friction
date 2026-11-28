"""Audit one five- or seven-day social-memory run from local exports and actual requests."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
import json
import hashlib
from pathlib import Path
import sqlite3
from uuid import UUID

from proto.app_entry.bundle_loader import get_replay_source
from proto.app_entry.intention_contract import DAILY_OPENING_VERSIONS, parse_compact_reply, stated_open_channel
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


def daily_opening_evidence(rows, parsed):
    """Re-read the reply accepted by the model-call audit, including a repaired reply."""
    initial = next((r for r in rows if (r["module"], r["kind"], r.get("phase")) == ("app_plan", "request", "initial")), None)
    if initial is None:
        raise ValueError("accepted daily action missing its initial Plan request")
    packet = request_packet(initial)
    if packet.get("schema_version") not in DAILY_OPENING_VERSIONS:
        return False, None  # Earlier daily actions specified a bag of App counts without an opening.
    replies = [r for r in rows if (r["module"], r["kind"]) == ("app_plan", "response")
               and r.get("call_id") and r["call_id"] == parsed.get("call_id")]
    raw = parse_compact_reply(replies[0].get("raw", "")) if len(replies) == 1 else None
    return True, stated_open_channel((raw or {}).get("action"), packet)


def count_stage_calls(rows, module, name, counts):
    calls = [r for r in rows if (r["module"], r["kind"]) == (module, "request")]
    counts[name + "_requests"] += len(calls)
    counts[name + "_repair_requests"] += sum(r.get("phase") == "repair" for r in calls)
    # Multiple JSON attempts may produce more than one request tagged initial.
    initial = next((r for r in calls if r.get("phase") == "initial"), None)
    if initial is None:
        return
    counts[name + "_hours_called"] += 1
    linked = [r for r in rows if r.get("module") == module and r.get("call_id")
              and r["call_id"] == initial.get("call_id")]
    if any(r["kind"] == "parse" and r["status"] == "ok" for r in linked):
        counts[name + "_first_pass_valid"] += 1
    elif not any(r["kind"] in {"parse", "error"} for r in linked):
        counts[name + "_first_result_unverified"] += 1
    elif module == "app_needs":
        # Detect the transmitted observation even when the response stops mid-JSON.
        obs = request_packet(initial).get("inputs", {})
        if obs:
            prefix = '"inputs":' + json.dumps(obs, ensure_ascii=False, separators=(",", ":"))
            prefix = "".join(prefix.split())[:100]
            if any(r["kind"] == "response" and prefix in "".join(str(r.get("raw", "")).split())
                   for r in linked):
                counts["needs_first_reply_echoed_observation"] += 1


def total_app_activity(metrics):
    """Keep zero counts in the JSON so callers can distinguish zero from a missing audit."""
    totals = Counter(dict.fromkeys((
        "needs_first_pass_valid", "needs_first_result_unverified", "needs_hours_called",
        "needs_requests", "needs_repair_requests", "needs_first_reply_echoed_observation",
        "plan_first_pass_valid", "plan_first_result_unverified", "plan_hours_called",
        "plan_requests", "plan_repair_requests", "accepted_daily_choices",
        "daily_exports_verified", "daily_opening_exports_verified", "daily_legacy_counts_only",
        "daily_at_run_end", "next_needs_verified", "next_plan_verified", "technical_failure_hours",
        "failed_after_initial_daily_choice_without_channel", "route_missing_or_duplicate",
    ), 0))
    for row in metrics:
        totals.update(row)
    return dict(totals)


def app_activity_flow(records, rollout, expected):
    """Follow accepted habitual choices into their export and the next real model inputs."""
    slots, exports = defaultdict(list), defaultdict(list)
    for row in rollout:
        exports[int(row["talkingdata_day"]), int(row["hour"])].append(row)
    for row in records:
        if row.get("module") in {"app_needs", "app_plan", "hourly_intention"}:
            slots[row["talkingdata_day"], row["hour"]].append(row)
    days = defaultdict(Counter)
    issues = []
    for day, hour in sorted(expected):
        counts, rows = days[day], slots[day, hour]
        counts["expected_hours"] += 1
        for module, name in [("app_needs", "needs"), ("app_plan", "plan")]:
            count_stage_calls(rows, module, name, counts)
        routes = [r for r in rows if (r["module"], r["kind"]) == ("hourly_intention", "hourly_intention")]
        if len(routes) != 1:
            counts["route_missing_or_duplicate"] += 1
            continue
        route = routes[0]
        if route["status"] == "technical_failure":
            counts["technical_failure_hours"] += 1
            checks = [r for r in rows if r["kind"] == "intent_validation" and r["module"] == "app_plan"]
            if (len(checks) == 1 and (checks[0].get("raw_choice") or {}).get("kind") == "habitual_app"
                    and checks[0].get("raw_activity") == {}):
                counts["failed_after_initial_daily_choice_without_channel"] += 1
            continue
        if route.get("status") != "accepted" or route.get("executed_choice") != "habitual_app":
            continue
        counts["accepted_daily_choices"] += 1
        parsed = [r for r in rows if (r["module"], r["kind"]) == ("app_plan", "parse")
                  and r.get("status") in {"ok", "ok_repaired"} and isinstance(r.get("parsed"), dict)]
        channels = parsed[0]["parsed"].get("app_context_counts") if len(parsed) == 1 else None
        exported = exports[day, hour]
        if (not isinstance(channels, dict) or not channels
                or not all(type(n) is int and n > 0 for n in channels.values())
                or len(exported) != 1 or exported[0].get("entry_status") != "intention_habitual_app"
                or exported[0].get("active") != "1"
                or exported[0].get("active_event_app_exposures") != str(sum(channels.values()))
                or json.loads(exported[0].get("app_context_counts_json") or "null") != channels):
            issues.append(f"day {day} hour {hour}: accepted daily App counts lack matching hourly export")
            continue
        counts["daily_exports_verified"] += 1
        requires_opening, opening = daily_opening_evidence(rows, parsed[0])
        if requires_opening:
            counts["daily_with_explicit_opening"] += 1
            if not opening or exported[0].get("opened_channel") != opening:
                issues.append(f"day {day} hour {hour}: first opened App differs between reply and hourly export")
                continue
            counts["daily_opening_exports_verified"] += 1
        else:
            counts["daily_legacy_counts_only"] += 1
        next_slot = (day + (hour + 1) // 24, (hour + 1) % 24)
        if next_slot not in expected:
            counts["daily_at_run_end"] += 1
            continue
        for module, name in [("app_needs", "needs"), ("app_plan", "plan")]:
            calls = [r for r in slots[next_slot] if (r["module"], r["kind"], r.get("phase"))
                     == (module, "request", "initial")]
            if not calls:
                counts["next_" + name + "_not_observed"] += 1
                continue
            # Check every sent initial prompt if this module repeated its JSON attempt.
            matches = []
            for call in calls:
                bundles = request_packet(call).get("inputs", {}).get("recent_simulated_bundles") or []
                prior = [b for b in bundles if (b.get("talkingdata_day"), b.get("hour")) == (day, hour)]
                matches.append(len(prior) == 1 and prior[0].get("app_context_counts") == channels
                               and prior[0].get("active") is True
                               and prior[0].get("active_event_app_exposures") == sum(channels.values())
                               and (not requires_opening or prior[0].get("opened_channel") == opening))
            if all(matches):
                counts["next_" + name + "_verified"] += 1
            else:
                issues.append(f"day {day} hour {hour}: daily App counts differ in next {name} observation")
    return {"by_day": {str(d): total_app_activity([values]) for d, values in days.items()},
            "totals": total_app_activity(days.values()), "issues": issues}


def load_agent_traces(trace, group, agents):
    files = sorted(trace.glob("llm-requests-*.jsonl"))
    if not files:
        raise FileNotFoundError(f"missing trace in {trace}")
    records = defaultdict(list)
    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                agent = str(row.get("agent_id"))
                if row.get("group_id") != group or row.get("world") != WORLD or agent not in agents:
                    raise ValueError("request trace belongs to another run or agent")
                records[agent].append(row)
    return records


def audit_trace(records, attempts, error_hours, expected_days=7):
    expected = rollout_hours(expected_days)
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
    for row in records:
        module = row.get("module")
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
            if row.get("talkingdata_day") == 4:
                day4_errors.append(row.get("hour"))
        if module not in checks or row.get("kind") != "request" or row.get("phase") != "initial":
            continue
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
            episodes = packet["task_relevant_memory"]["recent_task_episodes"]
        else:
            episodes = packet["inputs"]["recent_task_episodes"]
        for item in episodes:
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


AUDIT_ERRORS = (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, StopIteration)


def empty_report(group):
    return {"group_id": group, "run_complete": False, "acceptance_ok": False,
            "cross_day_status": "missing_evidence", "issues": []}


def check_resident(folder, manifest, replay, rollout, errors, records, conn, expected_days):
    group = manifest["group_id"]
    exp = str(UUID(manifest["exp_id"]))
    agent, device = replay["agent_id"], replay["device_id"]
    expected_hours = rollout_hours(expected_days)
    report = empty_report(group)
    issues = report["issues"]
    try:
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
        replay_check = report["replay"] = check_replay(conn, exp, agent, device)
        if replay_check["unverified_hours"] or not replay_check["day3_snapshot_ok"]:
            issues.append("incomplete replay or incorrect handoff snapshot")
        attempts = read_attempts(conn, exp, agent)
        report["exports_complete"] = not issues
        if manifest.get("proto_hourly_intention_mode") == "opportunity_v1":
            from check_hourly_intention_run import audit_intention_run
            report["hourly_intention"] = audit_intention_run(
                folder, None, conn, exp, agent, group, WORLD, expected_hours, set(failures), records=records)
            report["app_activity_flow"] = app_activity_flow(records, rollout, expected_hours)
        trace_check = report["cross_day"] = audit_trace(records, attempts, set(failures), expected_days)
        if trace_check["entry_errors_disagree_with_trace"]:
            issues.append("error export disagrees with actual hourly entry trace")
        if any(trace_check["missing_app_request_hours"].values()):
            issues.append(f"incomplete actual App request trace for days 4–{expected_days}")
        report["run_complete"] = not issues
        statuses = {v["status"] for v in trace_check["modules"].values()}
        if "hourly_intention" in report:
            issues.extend(report["hourly_intention"]["issues"])
            issues.extend(report["app_activity_flow"]["issues"])
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
    except AUDIT_ERRORS as exc:
        issues.append(f"{type(exc).__name__}: {exc}")
    if report["cross_day_status"] == "technical_failure" and not any("no valid" in x for x in issues):
        issues.append("no valid hourly decision to test the mechanism")
    return finish_report(report)


def finish_report(report):
    report["acceptance_ok"] = report["run_complete"] and not report["issues"]
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
    if any(not resident["stability_gate"]["eligible_by_technical_stability"]
           for resident in report.get("agents", {}).values()):
        blockers.append("at least one resident failed the individual technical stability checks")
    report["stability_gate"] = {
        "valid_decision_rate": rate, "valid_decisions": valid_count, "expected_hours": expected_count,
        "minimum_valid_rate": 0.95, "eligible_by_technical_stability": not blockers,
        "blockers": blockers, "remaining_expansion_checks": ["paired behavioral effect vs repeat noise", "cost and latency budget"],
    }
    return report


def check_cohort_mapping(folder, snapshot, replays, count):
    settings = snapshot["settings"]
    if int(settings["AGENT_COUNT"]) != count:
        raise ValueError("archived resident count differs from the requested count")
    # Resolve against the archived input directory so copied runs remain auditable.
    def archived_input(key):
        configured = Path(settings[key])
        local = folder / "inputs" / configured.name
        return local if local.is_file() else configured

    profiles_path = archived_input("DIGITAL_FRICTION_PROFILES_PATH")
    if hashlib.sha256(profiles_path.read_bytes()).hexdigest() != snapshot["profiles_sha256"]:
        raise ValueError("archived profile hash mismatch")
    profiles = json.loads(profiles_path.read_text())[:count]
    source = get_replay_source(bundle_path=str(archived_input("PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH")),
                               device_mapping_path=str(archived_input("PROTO_APP_ENTRY_REPLAY_DEVICE_PATH")),
                               replay_days=(1, 2, 3))
    if (source.bundle_hash, source.device_mapping_hash) != (snapshot["reference_hash"], snapshot["device_mapping_hash"]):
        raise ValueError("archived replay input hashes disagree")
    assigned = source.assignments_for_agent_ids([profile["id"] for profile in profiles])
    expected_cohort = {key: (item.selected_rank, item.device_id, key) for key, item in assigned.items()}
    archived_cohort = {int(row["agent_id"]): (int(row["selected_rank"]), str(row["device_id"]), int(row["profile_id"]))
                       for row in snapshot["cohort"]}
    if (len(assigned) != count or len(snapshot["cohort"]) != count or archived_cohort != expected_cohort
            or set(replays) != {str(agent) for agent in assigned}):
        raise ValueError("exported residents or archived cohort disagree with the input profiles and device ranks")
    for agent, row in replays.items():
        rank, device, _ = expected_cohort[int(agent)]
        if (int(row["selected_rank"]), row["device_id"], row["replay_bundle_hash"], row["device_mapping_hash"]) != (
                rank, device, source.bundle_hash, source.device_mapping_hash):
            raise ValueError(f"resident {agent} replay export disagrees with the archived device mapping")


def summarize_residents(report, agents, expected_hours):
    report["agents"] = agents
    statuses = Counter(r["cross_day_status"] for r in agents.values())
    report["cross_day_status_counts"] = dict(statuses)
    report["cross_day_status"] = next(iter(statuses)) if len(statuses) == 1 else "mixed"
    report["replay"] = {
        "expected_hours": len(agents) * 72,
        "verified_hours": sum(r.get("replay", {}).get("verified_hours", 0) for r in agents.values()),
    }
    report["rollout"] = {
        "expected_hours": len(agents) * expected_hours,
        **{key: sum(r.get("rollout", {}).get(key, 0) for r in agents.values())
           for key in ("accounted_hours", "valid_hours")},
        "error_hours_count": sum(len(r.get("rollout", {}).get("error_hours", [])) for r in agents.values()),
    }
    intentions = [r.get("hourly_intention", {}) for r in agents.values()]
    flows = [r["app_activity_flow"] for r in agents.values() if "app_activity_flow" in r]
    report["app_activity_flow"] = {"residents_with_audit": len(flows),
                                  "totals": total_app_activity(f["totals"] for f in flows)}
    report["hourly_intention"] = {
        key: sum(row.get(key, 0) for row in intentions)
        for key in ("valid_intention_decisions", "scheduled_login_opportunities", "published_opportunities",
                    "visible_opportunities", "distinct_tasks_entered", "low_level_decisions",
                    "operations_started", "help_requests")
    }
    report["hourly_intention"]["expected_scheduled_login_opportunities"] = 2 * len(agents)
    report["run_complete"] = not report["issues"] and all(r["run_complete"] for r in agents.values())
    report["exports_complete"] = not report["issues"] and all(r.get("exports_complete") for r in agents.values())
    for agent, resident in agents.items():
        report["issues"].extend(f"resident {agent}: {issue}" for issue in resident["issues"])


def check_run(folder, group, db, trace, expected_days=7, expected_agents=1):
    report = empty_report(group)
    try:
        expected_hours = rollout_hours(expected_days)
        manifest, = json.loads((folder / f"exp_group_manifest_{group}.json").read_text(encoding="utf-8"))
        exp = str(UUID(manifest["exp_id"]))
        expected = dict(group_id=group, world_name=WORLD, status="ok", agent_count=expected_agents, return_code=0,
                        qc_config_match=1, stage_mode="single", stage_count=1, stage_days=expected_days,
                        total_days=expected_days, decision_interval_minutes=60, proto_app_entry_replay_days="1,2,3",
                        proto_task_entry_mode="app_context_replay_then_llm_rollout", uses_forced_replay=1)
        mismatch = [k for k, v in expected.items() if manifest.get(k) != v]
        snapshot_path = folder / "resolved_config.json"
        snapshot = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else {}
        if snapshot and snapshot["runtime"].get("proto_hourly_intention_mode", "legacy") != manifest.get(
                "proto_hourly_intention_mode", "legacy"):
            mismatch.append("proto_hourly_intention_mode")
        if mismatch:
            report["issues"].append("manifest mismatch: " + ", ".join(mismatch))
        replay_rows = load_rows(folder, "app_entry_replay_summary", group)
        replays = {row["agent_id"]: row for row in replay_rows}
        if (expected_agents < 1 or len(replay_rows) != expected_agents or len(replays) != expected_agents
                or len({row["device_id"] for row in replay_rows}) != expected_agents):
            raise ValueError("expected one replay summary and one distinct device per resident")
        if expected_agents > 1:
            if (expected_days != 5 or manifest.get("proto_hourly_intention_mode") != "opportunity_v1"
                    or snapshot["runtime"]["proto_scheduled_login_hour"] != 9):
                raise ValueError("cohort audit requires the five-day scheduled opportunity-mode design")
            check_cohort_mapping(folder, snapshot, replays, expected_agents)
        rollout = defaultdict(list)
        errors = defaultdict(list)
        for rows, grouped in ((replay_rows, None), (load_rows(folder, "app_entry_rollout_hourly", group), rollout),
                              (load_rows(folder, "app_entry_rollout_errors", group), errors)):
            for row in rows:
                agent = row["agent_id"]
                if (agent not in replays or row["device_id"] != replays[agent]["device_id"]
                        or (row["group_id"], row["world_name"], row["exp_id"]) != (group, WORLD, exp)):
                    raise ValueError("exports disagree on run, world, agent or device")
                if grouped is not None:
                    grouped[agent].append(row)
        records = load_agent_traces(trace, group, replays)
        agents = {}
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            for agent, replay in replays.items():
                resident = check_resident(folder, manifest, replay, rollout[agent], errors[agent],
                                          records[agent], conn, expected_days)
                if expected_agents == 1:
                    if report["issues"]:
                        resident["issues"][:0] = report["issues"]
                        resident["run_complete"] = resident["exports_complete"] = False
                    return finish_report(resident)
                resident.update(agent_id=int(agent), selected_rank=int(replay["selected_rank"]),
                                device_id=replay["device_id"])
                agents[agent] = resident
        summarize_residents(report, agents, len(expected_hours))
    except AUDIT_ERRORS as exc:
        report["issues"].append(f"{type(exc).__name__}: {exc}")
    return finish_report(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("run-dir", "db", "trace", "output"):
        parser.add_argument(f"--{flag}", required=True, type=Path)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--expected-days", type=int, choices=SUPPORTED_DAYS, default=7)
    parser.add_argument("--expected-agents", type=int, default=1)
    args = parser.parse_args()
    report = check_run(args.run_dir, args.group_id, args.db, args.trace, args.expected_days, args.expected_agents)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"run_complete={report['run_complete']} acceptance_ok={report['acceptance_ok']} "
          f"cross_day_status={report['cross_day_status']} "
          f"eligible_by_technical_stability={report['stability_gate']['eligible_by_technical_stability']} {args.output}")
    return int(not report["acceptance_ok"])


if __name__ == "__main__":
    raise SystemExit(main())
