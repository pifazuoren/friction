"""Verify the two scheduled login decisions against the database and actual GLM traces."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import UUID

from check_social_memory_run import WORLD, load_rows, read_attempts, request_packet
from proto.llm_psychology import _extract_json_object, _sanitize_strategy_deliberation
from proto.metrics import attempt_rows_table_name
from proto.support_protocol import classify_support_delivery


FAMILY = "account_login_verification"
PREFIX = "scheduled_login_account_login_verification_"
SCORES = {"attempt_self": "attempt_self_score", "seek_help_then_attempt": "seek_help_score", "avoid": "avoid_score"}


def one(items, label):
    rows = list(items)
    if len(rows) != 1:
        raise ValueError(f"expected one {label}, found {len(rows)}")
    return rows[0]


def recalled_login_attempts(first, episodes, memory):
    """Link all visible attempts on this scheduled login, including its deferred retry."""
    scheduled = {key: ep for key, ep in episodes.items() if ep["task_id"] == first["task_id"]
                 and ep["task_family"] == FAMILY and ep["tick_seconds"] >= first["tick_seconds"]}
    recalled = {}
    for row in memory:
        key = row.get("episode_id")
        if key not in scheduled and row.get("task_id") != first["task_id"]:
            continue
        if key in recalled or key not in scheduled or any(row.get(k) != v for k, v in scheduled[key].items()):
            raise ValueError("recalled login identity, strategy, outcome, timing or help disagrees with day four")
        recalled[key] = row
    if not recalled:
        raise ValueError("no matching day-four login episode in the actual day-five strategy request")
    return sorted(recalled.values(), key=lambda row: row["tick_seconds"])


def verify_day(day, conn, table, agent, episodes, trace):
    marker = one((r for r in trace if r.get("kind") == "scheduled_login" and r.get("module") == "task_schedule"
                  and r["talkingdata_day"] == day and r["simulation_day"] == day - 1),
                 f"Day {day} login opportunity")
    if marker["task_family"] != FAMILY or not marker["task_id"].startswith(PREFIX) or marker["scheduled_hour"] != 9:
        raise ValueError(f"Day {day} scheduling marker does not identify the planned 09:00 login")
    episode = one((ep for ep in episodes.values() if ep["task_family"] == FAMILY
                   and ep["task_id"] == marker["task_id"] and ep["tick_seconds"] == marker["tick_seconds"]),
                  f"Day {day} scheduled login completion")
    raw, = one(conn.execute(f"SELECT payload_json FROM {table} WHERE agent_id=? AND day=? AND t=? AND task_id=?",
                            (agent, day - 1, episode["tick_seconds"], episode["task_id"])), "attempt payload")
    payload = json.loads(raw)
    rows = [r for r in trace if r.get("task_id") == episode["task_id"] and r["talkingdata_day"] == day
            and r["simulation_day"] == day - 1 and r["tick_seconds"] == episode["tick_seconds"]]
    decision = one((r for r in rows if r["module"] == "task" and r["kind"] == "decision"
                    and r["status"] == "completed"), f"Day {day} task decision")
    strategy = [r for r in rows if r["module"] == "strategy" and r["tick_id"] == decision["tick_id"]]
    sample = one((r for r in strategy if r["kind"] == "sample"), "sampled action")
    parsed = one((r for r in strategy if r["kind"] == "parse" and r["status"] in {"ok", "ok_repaired"}),
                 "accepted strategy judgment")
    query = [r for r in strategy if r.get("query_id") == parsed["query_id"]]
    # Invalid initial answers may trigger a repair or another initial attempt.
    initial = [r for r in query if r["kind"] == "request" and r["phase"] == "initial"]
    if not initial or any(r["messages"] != initial[0]["messages"] for r in initial):
        raise ValueError("missing or inconsistent initial strategy prompts")
    reply = one((r for r in query if r["kind"] == "response" and r["call_id"] == parsed["call_id"]),
                "accepted strategy response")
    model_reply = _extract_json_object(reply["raw"])
    result = payload["strategy_deliberation"]
    sanitized, status = _sanitize_strategy_deliberation(model_reply)
    if status != "ok" or sanitized != parsed["parsed"] or any(sanitized[k] != result[k] for k in SCORES.values()):
        raise ValueError("database strategy scores disagree with the accepted model judgment")
    if (decision["episode_id"] != episode["episode_id"] or decision["action"] != episode["strategy_type"]
            or decision["outcome"] != episode["outcome_type"] or decision["help_used"] != episode["help_used"]
            or decision["support_delivery_status"] != episode["support_delivery_status"]
            or decision["requested_strategy_type"] != sample["action"] or sample["action"] != episode["requested_strategy_type"]
            or sample["final_weights"] != payload["requested_strategy"]["weights"]
            or result["source"] != "hybrid_blended" or decision["strategy_source"] != result["source"]):
        raise ValueError("decision, persisted model participation, sampled strategy or weights disagree")
    request, response = payload["support_request"], payload["support_response"]
    if sample["action"] == "seek_help_then_attempt":
        if not request or not response or not (request["request_id"] == episode.get("support_request_id") == response["request_id"]):
            raise ValueError("no matching dispatched help request and helper response record")
        if classify_support_delivery(response) != episode["support_delivery_status"]:
            raise ValueError("helper response disagrees with the recorded delivery status")
    elif request or response or episode["support_delivery_status"] != "not_requested":
        raise ValueError("unexpected help attached to a strategy that did not request it")
    packet = request_packet(initial[0])
    if packet["task"]["task_id"] != episode["task_id"] or packet["task"]["task_family"] != FAMILY:
        raise ValueError("actual model prompt names a different task")
    return {
        **episode, "clock_day": day, "scheduled_hour": marker["scheduled_hour"], "executed_hour": marker["hour"],
        "model": initial[0].get("model"), "initial_call_id": initial[0]["call_id"],
        "accepted_call_id": parsed["call_id"], "model_scores": {s: model_reply[k] for s, k in SCORES.items()},
        "output_example_visible": "output_schema_example" in packet, "rule_weights_visible": "rule_weights" in packet,
        "strategy_source": result["source"], "sampled_weights": sample["final_weights"], "draw": sample["draw"],
        "sampled_action": sample["action"], "helper_responded": response.get("responded"),
        "support_style": response.get("support_style"),
    }, packet["task_relevant_memory"]["recent_task_episodes"]


def check(folder, db):
    group = folder.name
    report = {"group_id": group, "verified": False}
    try:
        manifest = one(json.loads((folder / f"exp_group_manifest_{group}.json").read_text()), "manifest")
        replay = one(load_rows(folder, "app_entry_replay_summary", group), "replay summary")
        if any(manifest[k] != replay[k] for k in ("exp_id", "world_name", "group_id")) or (
                replay["group_id"], replay["world_name"]) != (group, WORLD):
            raise ValueError("manifest and replay do not identify the same experiment and world")
        agent, exp = replay["agent_id"], str(UUID(manifest["exp_id"]))
        trace = []
        for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    if (row.get("group_id"), row.get("world"), str(row.get("agent_id"))) == (group, WORLD, agent):
                        if row.get("talkingdata_day") in (4, 5) and row.get("module") in {"task_schedule", "task", "strategy"}:
                            trace.append(row)
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            attempts = read_attempts(conn, exp, agent)
            table = attempt_rows_table_name(exp)
            prior, _ = verify_day(4, conn, table, agent, attempts[3], trace)
            report["day4"] = prior
            later, memory = verify_day(5, conn, table, agent, attempts[4], trace)
            report["day5"] = later
        recalled = recalled_login_attempts(prior, attempts[3], memory)
        first_recalled = recalled[0]["episode_id"] == prior["episode_id"]
        report.update(verified=True, day4_scheduled_episodes_in_day5_prompt=recalled,
                      day4_first_decision_in_day5_prompt=first_recalled,
                      day4_episode_in_day5_prompt=recalled[0] if first_recalled else recalled[-1])
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
        report["issue"] = str(error)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args()
    evidence = check(args.run_dir, args.db)
    output = args.run_dir / "scheduled_login_evidence.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"verified={evidence['verified']} {output}")
    raise SystemExit(int(not evidence["verified"]))
