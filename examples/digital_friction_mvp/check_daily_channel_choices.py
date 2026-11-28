"""Replay all 480 archived v4 Plan decisions and optionally re-ask six fixed states with v5."""

import argparse
import asyncio
from collections import Counter, defaultdict
import csv
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from check_hourly_channel_replay import (
    RecordedReplies,
    event,
    rebuild_plan_kwargs,
    require,
)
from check_hourly_intention_run import check_plan_calls, request_payload
from proto.app_entry.intention_contract import (
    COMPACT_PLAN_V4,
    COMPACT_PLAN_V5,
    parse_compact_reply,
)
from proto.app_entry.planner import (
    DigitalAppEntryPlanBlock,
    HourlyIntentionPlanError,
    decode_compact_plan,
)
from proto.llm_trace import LLMRunInterrupted, bind_trace_context, traced_agent_tick
from run_hourly_intention_pairs import SmokeRequestBudget
from run_hourly_strategy_factorial import FactorialClient, experiment_environment
from run_strategy_memory_pairs import ENDPOINT, EXAMPLE, MODEL, ROOT, save_json


FAILURE_TYPES = ("changed_intent_on_repair", "invalid_intent")
CASES = tuple(f"day{day}_{status}" for day in (4, 5) for status in FAILURE_TYPES) + (
    "control_no_app",
    "control_habitual_app",
)
HTTP_LIMIT = 2 * len(CASES)


def file_digest(path):
    return sha256(path.read_bytes()).hexdigest()


def load_archive(folder):
    (manifest_path,) = folder.glob("exp_group_manifest_*.json")
    (manifest,) = json.loads(manifest_path.read_text())
    config = json.loads((folder / "resolved_config.json").read_text())
    digest = file_digest(folder / "experiment_source.zip")
    group, world = manifest["group_id"], manifest["world_name"]
    require(
        config["source_sha256"] == digest and manifest["status"] == "ok",
        "Invalid source or manifest",
    )
    require(
        (manifest["agent_count"], manifest["total_days"]) == (10, 5),
        "Expected the five-day ten-person run",
    )
    rank_path = folder / f"app_entry_replay_summary_{group}.csv"
    with rank_path.open() as stream:
        people = list(csv.DictReader(stream))
    require(
        all(
            (r["group_id"], r["world_name"], r["exp_id"])
            == (group, world, manifest["exp_id"])
            for r in people
        ),
        "Mixed cohort mapping",
    )
    ranks = {int(r["agent_id"]): int(r["selected_rank"]) for r in people}
    require(
        len(people) == len(ranks) == 10 and set(ranks.values()) == set(range(1, 11)),
        "Invalid cohort mapping",
    )
    slots = defaultdict(list)
    trace_files = sorted((folder / "trace").glob("llm-requests-*.jsonl"))
    for path in trace_files:
        with path.open() as stream:
            for line in stream:
                r = json.loads(line)
                if r.get("module") not in {
                    "app_plan",
                    "app_needs",
                    "hourly_intention",
                } or r.get("talkingdata_day") not in (4, 5):
                    continue
                require(
                    (r["group_id"], r["world"], r["code_hash"])
                    == (group, world, digest),
                    "Foreign trace record",
                )
                slots[r["talkingdata_day"], r["hour"], ranks[r["agent_id"]]].append(r)
    require(
        set(slots)
        == {(d, h, rank) for d in (4, 5) for h in range(24) for rank in ranks.values()},
        "Missing or extra cohort hours",
    )
    ticks = set()
    for slot, events in slots.items():
        (tick,) = {r["tick_id"] for r in events}
        require(tick and tick not in ticks, f"Missing or reused tick at {slot}")
        ticks.add(tick)
    return slots, {
        "group": group,
        "world": world,
        "experiment_source_sha256": digest,
        "trace_sha256": {f.name: file_digest(f) for f in trace_files},
        "cohort_mapping_sha256": file_digest(rank_path),
    }


def reexpress_valid(raw, old):
    """Move one recorded opening into the action only after the original decoder accepts the choice."""
    decode_compact_plan(raw, old)
    if raw["action"] != "habitual_app":
        return dict(raw)
    first, *other = raw["additional_apps"]
    return {**raw, "action": f"habitual_app@open:{first}", "additional_apps": other}


def verify_stimulus(request, stimulus):
    old, new = request_payload(request), request_payload(stimulus)
    require(
        old["schema_version"] == COMPACT_PLAN_V4
        and new["schema_version"] == COMPACT_PLAN_V5,
        "Expected v4 archive and production v5 count-mode contracts",
    )

    def scene(body):
        return {k: v for k, v in body.items() if k not in ("schema_version", "actions")}

    require(
        scene(old) == scene(new),
        "Observation, needs, targets, channels or constraints changed",
    )
    daily_actions = {f"habitual_app@open:{c}" for c in old["channels"]}
    require(
        set(new["actions"]) == (set(old["actions"]) - {"habitual_app"}) | daily_actions
        and len(new["actions"]) == len(set(new["actions"])),
        "Unexpected change to action menu",
    )
    require(
        request["model"] == MODEL and request["parameters"] == stimulus["parameters"],
        "Model or sampling settings changed",
    )


async def replay_hour(slot, events):
    day, hour, rank = slot
    route = event(events, "hourly_intention", "hourly_intention")
    check_plan_calls(events, route)
    request = event(events, "app_plan", "request", phase="initial")
    old = request_payload(request)
    kwargs = rebuild_plan_kwargs(events, expected_version=COMPACT_PLAN_V4)
    kwargs["compact_schema_version"] = COMPACT_PLAN_V5
    first = event(events, "app_plan", "response", phase="initial")["raw"]
    replies = [first]
    if route["repair_count"]:
        replies.append(event(events, "app_plan", "response", phase="repair")["raw"])
    first_wire = parse_compact_reply(first) or {}
    failed = route["status"] == "technical_failure"
    old_kind = None if failed else route["accepted_choice"]["kind"]
    bare_empty = (
        first_wire.get("action") == "habitual_app"
        and first_wire.get("additional_apps") == []
    )
    if failed:
        # Keep both original texts. A repair that looks valid alone cannot replace the first choice.
        replay = RecordedReplies(replies)
    else:
        encoded = reexpress_valid(parse_compact_reply(replies[-1]), old)
        replay = RecordedReplies([json.dumps(encoded, ensure_ascii=False)])
    try:
        result = await DigitalAppEntryPlanBlock().forward(llm=replay, **kwargs)
    except HourlyIntentionPlanError as exc:
        require(
            failed
            and exc.audit["technical_failure"]
            and exc.audit["accepted_choice"] is None
            and len(replay.requests) == len(replies),
            f"Unexpected v5 rejection at {slot}",
        )
    else:
        require(
            not failed and len(replay.requests) == 1,
            f"Rejected archive pair gained an action at {slot}",
        )
        phase = "repair" if route["repair_count"] else "initial"
        archived = event(events, "app_plan", "parse", phase=phase)["parsed"]
        current = result.to_dict(include_audit=False)
        require(
            all(current[k] == v for k, v in archived.items()),
            f"Archived Plan semantics changed at {slot}",
        )
    verify_stimulus(request, replay.requests[0])
    case = None
    if failed and bare_empty and route["parse_status"] in FAILURE_TYPES:
        case = f"day{day}_{route['parse_status']}"
    elif old_kind in ("no_app", "habitual_app"):
        case = "control_" + old_kind
    evidence = {
        "stratum": case,
        "day": day,
        "hour": hour,
        "rank": rank,
        "agent_id": request["agent_id"],
        "source_call_id": request["call_id"],
        "source_parse_status": route["parse_status"],
        "source_accepted_kind": old_kind,
        "source_rejection": route.get("rejection_reason"),
    }
    return evidence, kwargs, replay.requests[0], len(replies), bare_empty


def choose_cases(candidates):
    """Take the earliest day/hour per stratum, preferring an unused profile then lowest rank on ties."""
    selected = []
    used = set()
    for label in CASES:
        available = [c for c in candidates if c[0]["stratum"] == label]
        require(available, f"Missing archived smoke stratum: {label}")
        choice = min(
            available,
            key=lambda c: (
                c[0]["day"],
                c[0]["hour"],
                c[0]["rank"] in used,
                c[0]["rank"],
            ),
        )
        selected.append(choice)
        used.add(choice[0]["rank"])
    return selected


async def replay_archive(folder):
    slots, provenance = load_archive(folder)
    counts, rejected = Counter(), Counter()
    candidates = []
    requests = bare_empty_failures = first_valid = 0
    # Retain candidate identifiers only. Capture the six selected prompts from their original hours.
    for slot, events in sorted(slots.items()):
        evidence, _, _, n, bare_empty = await replay_hour(slot, events)
        requests += n
        if evidence["source_accepted_kind"] is None:
            rejected[evidence["source_parse_status"]] += 1
            bare_empty_failures += bare_empty
        else:
            counts[evidence["source_accepted_kind"]] += 1
            first_valid += n == 1
        if evidence["stratum"]:
            candidates.append((evidence, slot))
    cases = []
    for evidence, slot in choose_cases(candidates):
        _, kwargs, stimulus, _, _ = await replay_hour(slot, slots[slot])
        cases.append((evidence, kwargs, stimulus))
    return {
        "source": provenance,
        "source_schema": COMPACT_PLAN_V4,
        "current_schema": COMPACT_PLAN_V5,
        "hours": len(slots),
        "archived_plan_requests": requests,
        "equivalent_accepted": sum(counts.values()),
        "equivalent_actions": dict(counts),
        "archived_first_valid": first_valid,
        "archived_repaired_valid": sum(counts.values()) - first_valid,
        "rejected_original_pairs": sum(rejected.values()),
        "original_failed_by_status": dict(rejected),
        "failed_bare_habitual_empty_first_reply": bare_empty_failures,
        "new_model_choices": 0,
        "online_requests": 0,
    }, cases


@traced_agent_tick
async def reask(client, evidence, kwargs, stimulus):
    bind_trace_context(
        purpose="daily_channel_choices",
        talkingdata_day=evidence["day"],
        hour=evidence["hour"],
        profile_rank=evidence["rank"],
        agent_id=evidence["agent_id"],
        source_call_id=evidence["source_call_id"],
        stratum=evidence["stratum"],
    )
    transport = FactorialClient(client, stimulus)
    try:
        plan = await DigitalAppEntryPlanBlock().forward(llm=transport, **kwargs)
        audit = plan.audit
    except HourlyIntentionPlanError as exc:
        plan, audit = None, exc.audit
    except LLMRunInterrupted:
        if not transport.stop_http:
            raise
        plan, audit = None, {}
    initial_daily = (audit.get("raw_choice") or {}).get(
        "kind"
    ) == "habitual_app" and bool(audit.get("raw_opened_channel"))
    return {
        **evidence,
        "parse_status": audit.get("parse_status", "request_error"),
        "plan_valid": plan is not None,
        "initial_explicit_daily_channel": audit.get("raw_opened_channel")
        if initial_daily
        else None,
        "accepted_daily_channel": (
            audit.get("repaired_opened_channel")
            if audit.get("parse_status") == "ok_repaired"
            else audit.get("raw_opened_channel")
        )
        if plan and plan.intent["kind"] == "habitual_app"
        else None,
        "accepted_plan": plan.to_dict(include_audit=False) if plan else None,
        "rejection_reason": audit.get("rejection_reason"),
        "model_requests": transport.requests,
        "returned_models": transport.returned_models,
        "transport_errors": transport.transport_errors,
        "provider_stopped": transport.stop_http,
    }


def summarize_online(rows):
    groups = {}
    for group in ("failed", "controls"):
        members = [
            r
            for r in rows
            if r["stratum"].startswith("control_") == (group == "controls")
        ]
        groups[group] = {
            "states": len(members),
            "first_valid": sum(r["parse_status"] == "ok" for r in members),
            "final_valid": sum(r["plan_valid"] for r in members),
            "initial_explicit_daily_token": sum(
                r["initial_explicit_daily_channel"] is not None for r in members
            ),
            "accepted_explicit_daily_token": sum(
                r["accepted_daily_channel"] is not None for r in members
            ),
        }
    return {
        "complete": len(rows) == len(CASES)
        and all(not r["transport_errors"] for r in rows),
        "http_request_limit": HTTP_LIMIT,
        "http_requests": sum(r["http_requests"] for r in rows),
        "by_source_group": groups,
        "decisions": rows,
    }


async def run_online(folder, cases):
    import httpx
    from openai import AsyncOpenAI

    key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
    if not key or key == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（输入隐藏）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        raise SystemExit("未提供密钥，在线复问未启动。")
    budget = SmokeRequestBudget(limit=HTTP_LIMIT)
    http = httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [budget.before_send]},
    )
    rows = []
    async with AsyncOpenAI(
        api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
    ) as client:
        for evidence, kwargs, stimulus in cases:
            budget.case_dispatched = 0
            row = await reask(client, evidence, kwargs, stimulus)
            row["http_requests"] = budget.case_dispatched
            rows.append(row)
            summary = summarize_online(rows)
            save_json(folder / "summary.json", summary)
            print(
                f"{row['stratum']}  D{row['day']} {row['hour']:02d}:00  #{row['rank']}  {row['parse_status']}",
                flush=True,
            )
            if row["provider_stopped"]:
                break
    return 0 if summary["complete"] and all(r["plan_valid"] for r in rows) else 1


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archive", type=Path, help="Completed ten-resident, five-day v4 archive"
    )
    parser.add_argument("--output-dir", type=Path, help="New result directory")
    parser.add_argument(
        "--online",
        action="store_true",
        help="Re-ask six archived states, at most 12 HTTP requests",
    )
    args = parser.parse_args()
    os.umask(0o077)
    with experiment_environment({"PROTO_LLM_TRACE_DIR": None}):
        report, cases = await replay_archive(args.archive)
    folder = (
        args.output_dir
        or ROOT
        / "agentsociety_data/runs/daily_channel_choices"
        / (
            "daily_channels_"
            + datetime.now().strftime("%Y%m%d_%H%M%S_")
            + uuid4().hex[:6]
        )
    )
    folder.mkdir(parents=True, exist_ok=False)
    source = folder / "experiment_source.zip"
    with ZipFile(source, "x", compression=ZIP_DEFLATED) as bundle:
        for path in sorted([*EXAMPLE.glob("*.py"), *(EXAMPLE / "proto").rglob("*.py")]):
            bundle.write(path, str(path.relative_to(EXAMPLE)))
    digest = file_digest(source)
    save_json(folder / "replay.json", report)
    save_json(folder / "stimuli.json", [{**e, "stimulus": s} for e, _, s in cases])
    selected_hours = Counter(f"{e['hour']:02d}:00" for e, _, _ in cases)
    save_json(
        folder / "design.json",
        {
            "model": MODEL,
            "source": report["source"],
            "source_schema": COMPACT_PLAN_V4,
            "schema": COMPACT_PLAN_V5,
            "experiment_source_sha256": digest,
            "online_requested": args.online,
            "http_request_limit": HTTP_LIMIT,
            "sdk_retries": 0,
            "max_http_per_case": 2,
            "selected_case_counts_by_clock_hour": dict(selected_hours),
            "time_coverage": (
                "All six selected cases are at 00:00."
                if selected_hours == {"00:00": 6}
                else "See the selected case counts by clock hour."
            ),
            "case_order": CASES,
            "selection": "Earliest day/hour within each stratum; unused rank first, then lowest rank at a tied hour.",
            "observations": "Six independent archived hourly Plan states with original needs, history and sampling settings. Each model decision is free.",
        },
    )
    print(
        f"{report['hours']} 个归档小时；{report['equivalent_accepted']} 个有效选择等价，"
        f"{report['rejected_original_pairs']} 组原始失败仍被拒绝。结果目录 {folder}",
        flush=True,
    )
    if not args.online:
        return 0
    with experiment_environment(
        {
            "PROTO_LLM_TRACE_DIR": str((folder / "trace").resolve()),
            "PARALLEL_GROUP_NAME": folder.name,
            "PROTO_RUN_SOURCE_SHA256": digest,
            "PROTO_HOURLY_INTENTION_MODE": "opportunity_v1",
            "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION": cases[0][1]["prompt_version"],
        }
    ):
        return await run_online(folder, cases)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
