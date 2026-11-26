"""Audit a paired seven-day scheduled-login difficulty study from trace and SQLite."""

from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from statistics import fmean
from uuid import UUID

from check_scheduled_login import FAMILY, PREFIX, SCORES, one
from check_social_memory_run import WORLD, check_replay, load_rows, request_packet
from proto.llm_psychology import (
    _extract_json_object, _normalize_strategy_score_weights, _sanitize_strategy_deliberation,
)
from proto.metrics import attempt_rows_table_name
from proto.support_protocol import classify_support_delivery


ARMS = ("standard", "elevated")
ERRORS = (KeyError, ValueError, TypeError, OSError, sqlite3.Error)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _baseline(conn, exp, agent, device):
    audit = check_replay(conn, exp, str(agent), device)
    if audit["verified_hours"] != 72 or not audit["day3_snapshot_ok"]:
        raise ValueError("incomplete day 1–3 replay or missing handoff snapshot")
    table = f"as_{exp.replace('-', '_')}_mvp_status"
    for raw, in conn.execute(f"SELECT status_json FROM {table} WHERE agent_id=? ORDER BY day,t", (agent,)):
        snapshot = json.loads(raw).get("proto_day4_replay_snapshot") or {}
        if snapshot.get("created_at_talkingdata_day") == 3:
            return {
                "baseline_hash": _digest(snapshot), "habit_hash": _digest(snapshot["app_entry_habit_memory"]),
                "helplessness": snapshot["helplessness_score"], "avoidance": snapshot["avoidance_tendency"],
                "trust": snapshot["trust_in_apps"], "rank": snapshot["selected_rank"],
            }
    raise ValueError("missing actual end-of-day-three state")


def _load_traces(folder, group):
    index = defaultdict(list)
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("module") not in {"task_schedule", "strategy", "task"}:
                    continue
                if (row.get("group_id"), row.get("world")) != (group, WORLD):
                    raise ValueError("trace run/world mismatch")
                if str(row.get("task_id", "")).startswith(PREFIX):
                    index[int(row["agent_id"]), int(row["talkingdata_day"])].append(row)
    return index


def _judgment(rows, marker, task_difficulty):
    requests = [r for r in rows if r["kind"] == "request" and r["phase"] == "initial"]
    if not requests:
        raise ValueError("missing actual initial strategy request")
    for request in requests:
        body = request_packet(request)
        if (body["task"]["task_id"] != marker["task_id"] or not math.isclose(body["task"]["difficulty"], task_difficulty, abs_tol=1e-8)
                or "rule_weights" in body or "output_schema_example" in body):
            raise ValueError("actual prompt does not match scheduled task/difficulty/hidden priors")
    parsed = [r for r in rows if r["kind"] == "parse" and r["status"] in ("ok", "ok_repaired")]
    if not parsed:
        return None
    valid = one(parsed, "accepted strategy parse")
    reply = one((r for r in rows if r["kind"] == "response" and r["call_id"] == valid["call_id"]
                 and r["query_id"] == valid["query_id"]), "original strategy response")
    record, status = _sanitize_strategy_deliberation(_extract_json_object(reply["raw"]))
    if status != "ok" or record != valid["parsed"]:
        raise ValueError("raw model reply disagrees with accepted strategy parse")
    return _normalize_strategy_score_weights(*(record[k] for k in SCORES.values()))


def _check_action(sample):
    weights, draw = sample["final_weights"], sample["draw"]
    if (set(weights) != set(SCORES) or not all(0 <= v <= 1 for v in weights.values())
            or not math.isclose(sum(weights.values()), 1) or not 0 <= draw < 1):
        raise ValueError("invalid probability vector or random draw")
    cumulative = 0.0
    selected = "avoid"
    for key in SCORES:
        cumulative += weights[key]
        if draw <= cumulative:
            selected = key
            break
    if selected != sample["action"]:
        raise ValueError("trace action disagrees with weights and actual draw")


def _attempt(rows, table, conn, expected_agent, day, marker, decision):
    tick = decision["tick_seconds"]
    strat = [r for r in rows if r["module"] == "strategy" and r["tick_id"] == decision["tick_id"]
             and r["tick_seconds"] == tick and r["task_id"] == marker["task_id"]]
    sample = one((r for r in strat if r["kind"] == "sample"), "strategy action draw")
    _check_action(sample)
    difficulty = marker["assigned_difficulty"]
    raw_weights = _judgment(strat, marker, difficulty)
    action = sample["action"]
    out = {
        "task_id": marker["task_id"], "difficulty": difficulty, "hour": decision["hour"], "tick": tick,
        "action": action, "avoid": int(action == "avoid"), "help_requested": action == "seek_help_then_attempt",
        "llm_p_avoid": raw_weights["avoid"] if raw_weights is not None else None,
        "final_p_avoid": sample["final_weights"]["avoid"], "draw": sample["draw"],
        "strategy_repair_requests": sum(r["kind"] == "request" and r["phase"] == "repair" for r in strat),
        "outcome_status": decision["status"], "outcome": None, "delivery": None, "rule_p_avoid": None,
        "strategy_source": decision.get("strategy_source"), "profile_hash": None,
    }
    if decision["status"] == "technical_failure":
        if decision.get("requested_action") != action:
            raise ValueError("failed task was attached to the wrong strategy")
        out["delivery"] = "technical_failure"
        return out
    if decision["status"] != "completed":
        raise ValueError(f"unexpected task status {decision['status']}")
    row = one(conn.execute(f"SELECT strategy_type,outcome_type,payload_json FROM {table} "
                           "WHERE agent_id=? AND day=? AND t=? AND task_id=?",
                           (expected_agent, day - 1, tick, marker["task_id"])), "matching database attempt")
    executed, outcome, raw = row
    saved = json.loads(raw)
    result = saved["strategy_deliberation"]
    if (saved["episode_id"] != decision["episode_id"] or saved["requested_strategy_type"] != action
            or decision["requested_strategy_type"] != action or saved["requested_strategy"]["strategy_type"] != action
            or decision["requested_weights"] != sample["final_weights"]
            or decision["help_used"] != saved["outcome"]["help_used"]
            or saved["requested_strategy"]["weights"] != sample["final_weights"]
            or saved["task"]["difficulty"] != difficulty or executed != decision["action"]
            or outcome != decision["outcome"] or saved["support_delivery_status"] != decision["support_delivery_status"]
            or result["source"] != decision["strategy_source"] or result["status"] != decision["strategy_status"]
            or result["llm_weights"] != raw_weights or result["rule_weights"] != decision["rule_weights"]):
        raise ValueError("decision, actual model and SQLite attempt disagree")
    if out["help_requested"]:
        req, response = saved["support_request"], saved["support_response"]
        if (not req.get("request_id") or req["request_id"] != response.get("request_id")
                or req["request_id"] != saved["support_request_id"]
                or classify_support_delivery(response) != saved["support_delivery_status"]):
            raise ValueError("help request, response and delivery do not match")
    elif saved["support_request"] or saved["support_response"] or saved["support_delivery_status"] != "not_requested":
        raise ValueError("spurious help attached to action")
    out.update(outcome=outcome, delivery=saved["support_delivery_status"], rule_p_avoid=result["rule_weights"]["avoid"],
               profile_hash=_digest(saved["profile_summary"]), strategy_status=result["status"],
               simulated_helplessness_after=saved["update"]["helplessness_after"])
    return out


def _audit_day(conn, table, agent, day, rows, run, design):
    marker = one((r for r in rows if r["kind"] == "scheduled_login" and r["module"] == "task_schedule"),
                 "scheduled opportunity")
    delta = design["difficulty_increment"] if run["arm"] == "elevated" and day in design["exposure_days"] else 0
    if (marker["task_family"] != FAMILY or marker["scheduled_hour"] != design["scheduled_hour"]
            or marker["simulation_day"] != day - 1 or marker["hour"] < marker["scheduled_hour"]
            or marker["difficulty_arm"] != run["arm"] or not math.isclose(marker["nominal_difficulty_delta"], delta)):
        raise ValueError("wrong scheduled arm, timing or nominal difficulty")
    decisions = [r for r in rows if r["module"] == "task" and r["kind"] == "decision"
                 and r["task_id"] == marker["task_id"]]
    first = one((r for r in decisions if r["tick_id"] == marker["tick_id"]
                 and r["tick_seconds"] == marker["tick_seconds"]), "first scheduled decision")
    main = _attempt(rows, table, conn, agent, day, marker, first)
    retries, problems = [], []
    for retry in sorted((r for r in decisions if r is not first), key=lambda r: r["tick_seconds"]):
        try:
            if retry["tick_seconds"] <= first["tick_seconds"]:
                raise ValueError("unexpected retry time")
            retries.append(_attempt(rows, table, conn, agent, day, marker, retry))
        except ERRORS as exc:
            problems.append(str(exc))
    return dict(main, retries=retries, retry_issues=problems)


def _read_run(study, conn, design, run, devices, days, observations, baselines, issues, exp_ids):
    seed, arm, group = run["seed"], run["arm"], run["group"]
    folder = study / run["dir"]
    manifest = one(json.loads((folder / f"exp_group_manifest_{group}.json").read_text()), "run manifest")
    exp = str(UUID(manifest["exp_id"]))
    if exp in exp_ids:
        raise ValueError("duplicate experiment ID in separate runs")
    exp_ids.add(exp)
    if (manifest["group_id"], manifest["pair_seed"], manifest["world_name"], manifest["agent_count"],
            manifest["total_days"]) != (group, seed, WORLD, len(devices), design["probe_day"]):
        raise ValueError("manifest does not represent planned run")
    if (manifest["status"], manifest["return_code"], manifest["qc_config_match"]) != ("ok", 0, 1):
        issues.append(f"{group}: experiment did not finish successfully")
    exported = load_rows(folder, "app_entry_replay_summary", group)
    trace = _load_traces(folder, group)
    for device in devices:
        rank = device["rank"]
        try:
            row = one((r for r in exported if int(r["selected_rank"]) == rank), f"rank {rank} replay export")
            if (row["group_id"], row["exp_id"], row["world_name"], row["device_id"],
                    row["uses_validation_data_any"]) != (group, exp, WORLD, str(device["device_id"]), "0"):
                raise ValueError("export identity, device or held-out use mismatch")
            agent = int(row["agent_id"])
        except ERRORS as exc:
            issues.append(f"{group}/rank {rank} identity: {exc}")
            continue
        try:
            baseline = _baseline(conn, exp, agent, str(device["device_id"]))
            if baseline["rank"] != rank:
                raise ValueError("replay rank mismatch")
            baselines[seed, arm, rank] = baseline
        except ERRORS as exc:
            # Preserve observable choices when the pre-treatment state cannot be verified.
            issues.append(f"{group}/rank {rank} replay: {exc}")
        for day in days:
            try:
                obs = _audit_day(conn, attempt_rows_table_name(exp), agent, day, trace[agent, day], run, design)
                observations[seed, arm, rank, day] = obs
                if (obs["retry_issues"] or any(a["outcome_status"] != "completed" for a in [obs, *obs["retries"]])):
                    issues.append(f"{group}/rank {rank}/day {day}: incomplete execution after strategy selection")
            except ERRORS as exc:
                issues.append(f"{group}/rank {rank}/day {day}: {exc}")


def _contrasts(design, observations, baselines, days, issues):
    pairs = []
    for seed in design["seeds"]:
        for device in design["devices"]:
            rank = device["rank"]
            b = [baselines.get((seed, a, rank)) for a in ARMS]
            baseline_match = all(b) and b[0]["baseline_hash"] == b[1]["baseline_hash"]
            if all(b) and not baseline_match:
                issues.append(f"seed {seed}/rank {rank}: actual pre-treatment snapshots differ")
            for day in days:
                arms = {a: observations.get((seed, a, rank, day)) for a in ARMS}
                lo, hi = (arms[a] for a in ARMS)
                actual_match = same_time = common_draw = same_profile = None
                if lo is not None and hi is not None:
                    delta = design["difficulty_increment"] if day in design["exposure_days"] else 0
                    actual_match = math.isclose(hi["difficulty"], min(1., lo["difficulty"] + delta), abs_tol=1e-8)
                    same_time = lo["tick"] == hi["tick"]
                    common_draw = lo["draw"] == hi["draw"]
                    same_profile = (lo["profile_hash"] == hi["profile_hash"]
                                    if lo["profile_hash"] and hi["profile_hash"] else None)
                    if not actual_match or same_profile is False or (same_time and not common_draw):
                        issues.append(f"seed {seed}/rank {rank}/day {day}: paired task, profile or random draw mismatch")
                pairs.append(dict(seed=seed, rank=rank, device_id=str(device["device_id"]), profile_id=device["profile_id"],
                                  day=day, baseline_match=baseline_match, paired_difficulty_ok=actual_match,
                                  same_tick=same_time, common_draw=common_draw, same_profile=same_profile, **arms))
    return pairs


def daily_summary(rows):
    """Only executed opportunities contribute; a missing partner never becomes 'did not avoid'."""
    paired = [p for p in rows if all(p[a] is not None for a in ARMS)]
    metrics = {}
    for name in ("avoid", "llm_p_avoid", "rule_p_avoid", "final_p_avoid"):
        valid = [p for p in paired if all(p[a][name] is not None for a in ARMS)]
        means = {a: fmean(p[a][name] for p in valid) if valid else None for a in ARMS}
        diff = fmean(p["elevated"][name] - p["standard"][name] for p in valid) if valid else None
        metrics[name] = dict(paired_n=len(valid), paired_arm_means=means, observed_elevated_minus_standard=diff,
                             planned_sample_difference=diff if len(valid) == len(rows) else None)
    arms = {}
    for arm in ARMS:
        available = [p[arm] for p in rows if p[arm] is not None]
        retries = [r for a in available for r in a["retries"]]
        arms[arm] = {
            "first_choices": dict(Counter(a["action"] for a in available)), "first_observed_n": len(available),
            "all_first_execution_outcomes": dict(Counter(a["outcome"] or "technical_failure" for a in available)),
            "first_help_delivery": dict(Counter(a["delivery"] for a in available if a["help_requested"])),
            "first_strategy_sources": dict(Counter(a["strategy_source"] or "source_unavailable" for a in available)),
            "first_strategy_status": dict(Counter(a.get("strategy_status") or "unavailable" for a in available)),
            "first_strategy_repair_requests": sum(a["strategy_repair_requests"] for a in available),
            "retry_n": len(retries), "retry_choices": dict(Counter(r["action"] for r in retries)),
            "retry_help_delivery": dict(Counter(r["delivery"] for r in retries if r["help_requested"])),
        }
    return {"planned_pairs": len(rows), "observed_pairs": len(paired), "paired_metrics": metrics, "arm_totals": arms,
            "different_execution_times": sum(p["same_tick"] is False for p in paired)}


def analyze_study(study_dir, db_path):
    study_dir = Path(study_dir)
    design = json.loads((study_dir / "design.json").read_text())
    days = [*design["exposure_days"], design["probe_day"]]
    seeds, devices = design["seeds"], design["devices"]
    ranks = [dev["rank"] for dev in devices]
    if (not seeds or len(seeds) != len(set(seeds)) or not ranks or len(ranks) != len(set(ranks))
            or len(set(str(d["device_id"]) for d in devices)) != len(devices)
            or len(set(d["profile_id"] for d in devices)) != len(devices)
            or len(devices) != design["profile_count"] or set(design["arms"]) != set(ARMS)
            or days != [4, 5, 6, 7]):
        raise ValueError("invalid paired design")
    run_keys = {(r["seed"], r["arm"]) for r in design["runs"]}
    if (len(run_keys) != len(design["runs"]) or run_keys != {(s, a) for s in seeds for a in ARMS}
            or len(set(r["group"] for r in design["runs"])) != len(run_keys)):
        raise ValueError("incomplete or duplicate design runs")
    observations, baselines, issues, exp_ids = {}, {}, [], set()
    try:
        with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            for run in design["runs"]:
                try:
                    _read_run(study_dir, conn, design, run, devices, days, observations, baselines, issues, exp_ids)
                except ERRORS as exc:
                    issues.append(f"{run['group']}: {exc}")
    except sqlite3.Error as exc:
        issues.append(f"SQLite: {exc}")
    pairs = _contrasts(design, observations, baselines, days, issues)
    trajectory = {str(day): daily_summary([p for p in pairs if p["day"] == day]) for day in days}
    probe = [p for p in pairs if p["day"] == design["probe_day"]]
    by_profile = {str(rank): daily_summary([p for p in probe if p["rank"] == rank])["paired_metrics"]["avoid"]
                  for rank in ranks}
    return {"complete": not issues, "issues": issues, "primary_endpoint": "D7 first scheduled sampled avoidance",
            "days": trajectory, "probe_by_profile": by_profile, "pairs": pairs,
            "baselines": [dict(v, seed=s, arm=a, rank=r) for (s, a, r), v in baselines.items()]}
