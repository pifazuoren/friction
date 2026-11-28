"""Replay 48 archived V3 count-mode decisions against the V4 Plan interface offline."""

import argparse
import asyncio
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path

from check_hourly_intention_run import check_plan_calls, request_payload
from proto.app_entry.intention_contract import (
    COMPACT_PLAN_V3,
    COMPACT_PLAN_V4,
    compact_menu,
    compact_needs,
    compact_observation,
    parse_compact_reply,
)
from proto.app_entry.needs import DigitalNeedsResult
from proto.app_entry.planner import DigitalAppEntryPlanBlock, HourlyIntentionPlanError, decode_compact_plan


def require(condition, message):
    if not condition:
        raise ValueError(message)


def event(events, module, kind, **fields):
    selected = [
        r
        for r in events
        if (r.get("module"), r.get("kind")) == (module, kind)
        and all(r.get(k) == v for k, v in fields.items())
    ]
    require(len(selected) == 1, f"Expected one {module}/{kind} matching {fields}, found {len(selected)}")
    return selected[0]


def load_archive_hours(folder):
    """Load the one resident's D4–5 records, matching source archive, world, run, tick, and hour."""
    folder = Path(folder)
    (manifest_path,) = folder.glob("exp_group_manifest_*.json")
    (manifest,) = json.loads(manifest_path.read_text())
    digest = sha256((folder / "experiment_source.zip").read_bytes()).hexdigest()
    config = json.loads((folder / "resolved_config.json").read_text())
    require(
        config["source_sha256"] == digest and manifest["status"] == "ok",
        "Invalid archived source or manifest",
    )
    slots = defaultdict(list)
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("module") not in {"hourly_intention", "app_plan", "app_needs"}:
                    continue
                if row.get("talkingdata_day") not in {4, 5}:
                    continue
                require(
                    (row["group_id"], row["world"], row["code_hash"])
                    == (manifest["group_id"], manifest["world_name"], digest),
                    "Foreign archive trace",
                )
                slots[row["talkingdata_day"], row["hour"]].append(row)
    require(set(slots) == {(d, h) for d in (4, 5) for h in range(24)}, "Expected all 48 archived hours")
    agents = set()
    seen_ticks = set()
    for hour, rows in slots.items():
        identities = {(r["agent_id"], r["tick_id"]) for r in rows}
        require(len(identities) == 1, f"Mixed agent/tick at {hour}")
        agent, tick = identities.pop()
        require(tick and tick not in seen_ticks, f"Reused tick at {hour}")
        agents.add(agent)
        seen_ticks.add(tick)
        route = event(rows, "hourly_intention", "hourly_intention")
        check_plan_calls(rows, route)
    require(len(agents) == 1, "Archived input combines multiple residents")
    return dict(slots)


def rebuild_plan_kwargs(events, expected_version=COMPACT_PLAN_V3):
    """Restore the inputs to the production Plan from its actual call and that hour's accepted Needs."""
    request = event(events, "app_plan", "request", phase="initial")
    body = request_payload(request)
    require(
        body["schema_version"] == expected_version and "exposure_cap" in body,
        f"Expected an archived {expected_version} count-based Plan",
    )
    accepted = [
        r
        for r in events
        if (r["module"], r["kind"]) == ("app_needs", "parse") and r["status"] in {"ok", "ok_repaired"}
    ]
    require(len(accepted) == 1, "Expected one accepted Needs parse")
    needs_request = event(
        events,
        "app_needs",
        "request",
        phase="initial",
        query_id=accepted[0]["query_id"],
        attempt=accepted[0]["attempt"],
    )
    needs_input = request_payload(needs_request)["inputs"]
    needs = DigitalNeedsResult.from_sanitized(accepted[0]["parsed"])
    require(
        compact_needs(needs.to_dict(include_audit=False), body["schema_version"]) == body["digital_needs"],
        "Needs disagree with Plan",
    )
    packet = {**body["inputs"], "day1_3_habit": needs_input["day1_3_habit"]}
    require(compact_observation(packet) == body["inputs"], "Could not reconstruct the Plan observation")
    audit = event(events, "app_plan", "intent_validation")
    candidates = audit["candidate_app_contexts"]
    require(sorted(candidates) == body["channels"], "Candidate evidence disagrees with the Plan menu")
    parameters = request["parameters"]
    return dict(
        needs=needs,
        candidate_contexts={k: v for k, v in candidates.items() if v > 0},
        input_payload=packet,
        intensity_profile={"active_exposure_cap": body["exposure_cap"]},
        prompt_version=request["plan_prompt_version"],
        min_confidence=body["minimum_confidence"],
        timeout=parameters["timeout"],
        retries=parameters["retries"],
        json_attempts=audit["json_attempts_configured"],
    )


class RecordedReplies:
    def __init__(self, replies):
        self.replies = replies
        self.requests = []

    async def atext_request(self, *, dialog, **parameters):
        index = len(self.requests)
        require(index < len(self.replies), "Unexpected extra replay request")
        self.requests.append({"messages": dialog, "parameters": parameters})
        return self.replies[index]


def encode_valid_choice(raw, old_body):
    """Re-express only a valid archived choice; never add an opening absent in the original reply."""
    old_plan = decode_compact_plan(raw, old_body)
    action = raw["action"]
    additional = list(raw["apps"])
    if old_plan["intent"]["kind"] in {"engage_goal", "continue_goal"}:
        prefix = action + "@open:"
        (target,) = [
            token for token in compact_menu(old_body["inputs"], COMPACT_PLAN_V4)["actions"] if token.startswith(prefix)
        ]
        additional.remove(target[len(prefix) :])  # One already observed opening is encoded in the v4 token.
        action = target
    return {**{k: v for k, v in raw.items() if k != "apps"}, "action": action, "additional_apps": additional}


async def replay_archive(folder):
    hours = load_archive_hours(folder)
    failures = Counter()
    accepted = Counter()
    first_valid = repaired_valid = 0
    for slot, events in sorted(hours.items()):
        initial = event(events, "app_plan", "request", phase="initial")
        old_body = request_payload(initial)
        route = event(events, "hourly_intention", "hourly_intention")
        phases = ["initial"] + (["repair"] if route["repair_count"] else [])
        archived = [event(events, "app_plan", "response", phase=phase)["raw"] for phase in phases]
        failed = route["status"] == "technical_failure"
        if failed:
            require(len(archived) == 2, f"Missing rejected first or corrected reply at {slot}")
            reasons = []
            for raw_text in archived:
                try:
                    encode_valid_choice(parse_compact_reply(raw_text), old_body)
                except ValueError as exc:
                    category = str(exc)
                else:
                    raise ValueError(f"Rejected archived decision was representable at {slot}")
                require(
                    category
                    in {
                        "unknown app channel",
                        "selected goal must use its required_channel during an active hour",
                    },
                    f"Unexpected reason for archived channel failure at {slot}: {category}",
                )
                reasons.append(category)
            require(reasons[0] == reasons[1], f"Archived repair changed the channel error at {slot}")
            failures[reasons[0]] += 1
            replay = RecordedReplies(archived)
        else:
            raw = parse_compact_reply(archived[-1])
            encoded = encode_valid_choice(raw, old_body)
            replay = RecordedReplies([json.dumps(encoded, ensure_ascii=False)])
        try:
            result = await DigitalAppEntryPlanBlock().forward(
                llm=replay, compact_schema_version=COMPACT_PLAN_V4, **rebuild_plan_kwargs(events)
            )
        except HourlyIntentionPlanError as exc:
            require(
                failed
                and exc.audit["technical_failure"]
                and exc.audit["accepted_choice"] is None
                and len(replay.requests) == 2,
                f"Unexpected current rejection at {slot}",
            )
        else:
            require(
                not failed and len(replay.requests) == 1,
                f"Current contract accepted an invalid reply at {slot}",
            )
            old_plan = event(events, "app_plan", "parse", phase=phases[-1])["parsed"]
            current_plan = result.to_dict(include_audit=False)
            require(
                all(current_plan[k] == value for k, value in old_plan.items()),
                f"The v4 encoding changed accepted behavior, volume, scores or reason at {slot}",
            )
            accepted[result.intent["kind"]] += 1
            first_valid += route["repair_count"] == 0
            repaired_valid += route["repair_count"] == 1
        current = request_payload(replay.requests[0])
        require(
            current["schema_version"] == COMPACT_PLAN_V4
            and all(
                current[k] == old_body[k]
                for k in ("inputs", "digital_needs", "channels", "exposure_cap", "minimum_confidence")
            ),
            f"Current Plan did not see the archived scene and constraints at {slot}",
        )
    return {
        "hours": len(hours),
        "archived_failed_pairs_rejected_by_v4": sum(failures.values()),
        "archived_channel_failure_counts": dict(failures),
        "archived_valid_reexpressed_in_v4": sum(accepted.values()),
        "equivalent_actions": dict(accepted),
        "archived_first_valid": first_valid,
        "archived_repaired_valid": repaired_valid,
        "new_model_choices": 0,
        "online_requests": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Completed five-day v3 count-mode experiment directory")
    parser.add_argument("--output", type=Path, help="Optional new JSON result file")
    args = parser.parse_args()
    os.environ.pop("PROTO_LLM_TRACE_DIR", None)
    report = asyncio.run(replay_archive(args.run))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        with args.output.open("x", encoding="utf-8") as target:
            target.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
