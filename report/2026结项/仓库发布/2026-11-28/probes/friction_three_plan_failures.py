"""Post-test three archived Plan failures, independently, with at most one HTTP dispatch per case."""

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

example = Path(
    os.getenv("FRICTION_PROBE_EXAMPLE", Path.cwd() / "examples/digital_friction_mvp")
)
sys.path.insert(0, str(example))
from check_hourly_channel_replay import (
    event,
    rebuild_plan_kwargs,
    RecordedReplies,
    require,
)
from check_hourly_intention_run import request_payload, check_plan_calls
from proto.app_entry.intention_contract import parse_compact_reply, COMPACT_PLAN_VERSION
from proto.app_entry.planner import DigitalAppEntryPlanBlock, HourlyIntentionPlanError
from proto.llm_trace import LLMQueryTrace, bind_trace_context, traced_agent_tick
from run_stratified_needs_plan import StageClient, Meter
from run_hourly_strategy_factorial import archive_source, experiment_environment
from run_strategy_memory_pairs import ENDPOINT, MODEL, ROOT, save_json

LABELS = ("missing_open", "unavailable_hour", "before_scheduled_review")


def classify(raw, body):
    action = raw.get("action")
    if not isinstance(action, str):
        return None
    parts = action.split("@")
    if len(parts) == 2 and parts[0] in ("engage_goal", "continue_goal"):
        matches = [s for s in body["actions"] if s.startswith(action + "@open:")]
        if len(matches) == 1:
            return LABELS[0], matches[0]
    # Count-path pilot has explicit (not grouped) review options.
    if len(parts) == 3 and parts[0] == "defer_goal" and parts[2].isdigit():
        allowed = body["defer_options"].get(parts[1])
        if isinstance(allowed, list) and allowed and action not in allowed:
            return LABELS[1], allowed[0]
    goal = body["inputs"]["current_intention"]
    if (
        goal
        and goal["status"] == "deferred"
        and not body["inputs"]["goal_review_due"]
        and goal["next_review_at_sim_hour"] > body["inputs"]["monotonic_sim_hour"]
        and not body["defer_options"]
        and parts[0] == "defer_goal"
    ):
        return LABELS[2], "no_app"
    return None


def select(folder):
    source_hash = sha256((folder / "experiment_source.zip").read_bytes()).hexdigest()
    require(
        source_hash
        == json.loads((folder / "resolved_config.json").read_text())["source_sha256"],
        "Source hash disagrees with config",
    )
    slots = defaultdict(list)
    for p in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        with p.open("rb") as f:
            for line in f:
                if not line.endswith(b"\n"):
                    break  # ignore an unfinished write in the still-running experiment
                r = json.loads(line)
                if r.get("module") not in (
                    "app_plan",
                    "app_needs",
                    "hourly_intention",
                ) or r.get("talkingdata_day") not in (4, 5):
                    continue
                require(
                    r["group_id"] == folder.name
                    and r["code_hash"] == source_hash
                    and r["world"] == "baseline_low_friction",
                    "Foreign trace row",
                )
                slots[r["talkingdata_day"], r["hour"], r["agent_id"]].append(r)
    selected = {}
    completed = Counter()
    for slot, rows in sorted(slots.items()):
        routes = [r for r in rows if r["module"] == r["kind"] == "hourly_intention"]
        if not routes:
            continue
        require(
            len(routes) == 1 and len({r["tick_id"] for r in rows}) == 1,
            "Mixed archived tick",
        )
        completed[slot[:2]] += 1
        if routes[0]["status"] != "technical_failure":
            continue
        plans = [
            r
            for r in rows
            if r["module"] == "app_plan"
            and r["kind"] == "request"
            and r["phase"] == "initial"
        ]
        if not plans:
            continue
        (req,) = plans
        first = event(
            rows, "app_plan", "response", call_id=req["call_id"], phase="initial"
        )["raw"]
        body = request_payload(req)
        match = classify(parse_compact_reply(first) or {}, body)
        if not match or match[0] in selected:
            continue
        check_plan_calls(rows, routes[0])
        repair = event(
            rows, "app_plan", "request", phase="repair", query_id=req["query_id"]
        )
        last = event(
            rows, "app_plan", "response", call_id=repair["call_id"], phase="repair"
        )["raw"]
        require(
            req["model"] == repair["model"] == MODEL, "Unexpected archived Plan model"
        )
        selected[match[0]] = (
            rows,
            {
                "case": match[0],
                "day": slot[0],
                "hour": slot[1],
                "agent_id": slot[2],
                "archived_initial": {
                    k: req[k] for k in ("call_id", "query_id", "messages", "parameters")
                },
                "archived_repair": {
                    k: repair[k]
                    for k in ("call_id", "query_id", "messages", "parameters")
                },
                "archived_initial_raw": first,
                "archived_repair_raw": last,
                "archived_status": routes[0]["parse_status"],
                "fixture_action": match[1],
                "new_dispatch_phase": "initial" if match[0] == LABELS[2] else "repair",
            },
        )
    require(
        set(selected) == set(LABELS),
        "Archive does not yet contain all three failure types",
    )
    latest = max((c["day"] - 4) * 24 + c["hour"] for _, c in selected.values())
    require(
        all(completed[4 + t // 24, t % 24] == 10 for t in range(latest + 1)),
        "Earlier hours still have unfinished residents",
    )
    return source_hash, [selected[label] for label in LABELS]


async def replay(kwargs, replies):
    transport = RecordedReplies(replies)
    # Replays never generate online evidence.
    with experiment_environment({"PROTO_LLM_TRACE_DIR": None}):
        try:
            result = await DigitalAppEntryPlanBlock().forward(llm=transport, **kwargs)
            audit = result.audit
        except HourlyIntentionPlanError as exc:
            result, audit = None, exc.audit
    return result, audit, transport.requests


async def prepare(folder, enforce_changes):
    source_hash, selected = select(folder)
    cases = []
    routing = []
    for rows, case in selected:
        old = request_payload(case["archived_initial"])
        kwargs = rebuild_plan_kwargs(rows, expected_version=old["schema_version"])
        first = case["archived_initial_raw"]
        wire = parse_compact_reply(first)
        valid = json.dumps(
            {**wire, "action": case["fixture_action"]}, ensure_ascii=False
        )
        repair = case["new_dispatch_phase"] == "repair"
        result, _, requests = await replay(
            kwargs, [first, valid] if repair else [valid]
        )
        body = request_payload(requests[0])
        require(
            requests[0]["parameters"] == case["archived_initial"]["parameters"],
            "Sampling parameters changed",
        )
        require(
            {
                k: v
                for k, v in body.items()
                if k not in ("schema_version", "pending_review_notice")
            }
            == {k: v for k, v in old.items() if k != "schema_version"},
            "Scene, menu, scores or memory changed",
        )
        require(
            requests[0]["messages"][0] == case["archived_initial"]["messages"][0],
            "System wording drift",
        )
        case["new_initial"] = requests[0]
        case["new_stimulus"] = requests[1] if repair else requests[0]
        case["local_positive_control_valid"] = result is not None
        if enforce_changes:
            require(
                result is not None,
                "New decoder still rejects legal fixture " + case["case"],
            )
            if repair:
                require(
                    len(requests) == 2
                    and case["new_stimulus"]["messages"]
                    != case["archived_repair"]["messages"],
                    "Updated repair prompt is missing",
                )
                require(
                    case["new_stimulus"]["parameters"]
                    == case["archived_repair"]["parameters"],
                    "Repair sampling changed",
                )
                invalid, _, _ = await replay(
                    kwargs, [first, json.dumps({**wire, "action": "no_app"})]
                )
                require(invalid is None, "An unrelated alternative passed as a repair")
            else:
                require(
                    body.get("pending_review_notice")
                    and "pending_review_notice" not in old,
                    "Missing new review notice",
                )
        cases.append(case)
        routing.append(kwargs)
    return source_hash, cases, routing


@traced_agent_tick
async def measure(client, meter, case, kwargs):
    phase = case["new_dispatch_phase"]
    bind_trace_context(
        purpose="plan_failure_posttest",
        case=case["case"],
        phase_source=phase,
        source_call_id=case["archived_initial"]["call_id"],
        day=case["day"],
        hour=case["hour"],
        agent_id=case["agent_id"],
    )
    stimulus = case["new_stimulus"]
    transport = StageClient(client, stimulus)
    trace = LLMQueryTrace("app_plan", transport)
    meter.case_dispatched = 0
    usage_start = len(meter.usage)
    result = None
    status = "request_error"
    reason = None
    raw = None
    try:
        raw = await trace.request(
            phase, 1, dialog=stimulus["messages"], **stimulus["parameters"]
        )
    except Exception:
        if not transport.transport_errors:
            raise
    if raw is not None:
        # A rejected new initial remains rejected; no live retry or invented behavior.
        replies = (
            [case["archived_initial_raw"], raw] if phase == "repair" else [raw, raw]
        )
        result, audit, requests = await replay(kwargs, replies)
        require(
            requests[1 if phase == "repair" else 0] == stimulus,
            "Response was validated against a different source",
        )
        if phase == "initial" and len(requests) > 1:
            result = None
            status = "invalid_first_response"
        else:
            status = audit["parse_status"]
        reason = audit.get("rejection_reason")
        trace.parsed(status, result.to_dict(include_audit=False) if result else None)
    require(
        transport.requests == meter.case_dispatched == 1
        and all(m == MODEL for m in transport.returned_models),
        "Actual model or dispatch count mismatch",
    )
    return {
        "case": case["case"],
        "day": case["day"],
        "hour": case["hour"],
        "agent_id": case["agent_id"],
        "source_call_id": case["archived_initial"]["call_id"],
        "phase": phase,
        "old_action": parse_compact_reply(case["archived_initial_raw"])["action"],
        "new_action": (parse_compact_reply(raw) or {}).get("action") if raw else None,
        "new_raw": raw,
        "status": status,
        "accepted": result.to_dict(include_audit=False) if result else None,
        "rejection": reason,
        "new_http_requests": meter.case_dispatched,
        "returned_models": transport.returned_models,
        "usage": meter.usage[usage_start:],
        "transport_errors": transport.transport_errors,
        "stop": transport.stop_http,
    }


async def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("--source-only", action="store_true")
    cli.add_argument("--online", action="store_true")
    cli.add_argument("--output-dir", type=Path)
    args = cli.parse_args()
    require(not (args.source_only and args.online), "Source-only mode cannot dispatch")
    os.umask(0o077)
    sh, cases, routing = await prepare(args.source, not args.source_only)
    for c in cases:
        print(
            c["case"],
            f"D{c['day']} {c['hour']:02d}:00 #{c['agent_id']}",
            c["new_dispatch_phase"],
            "local positive control",
            c["local_positive_control_valid"],
            flush=True,
        )
    if args.source_only:
        return 0
    out = args.output_dir or ROOT / "agentsociety_data/runs/plan_failure_probes" / (
        "three_plan_failures_"
        + datetime.now().strftime("%Y%m%d_%H%M%S_")
        + uuid4().hex[:6]
    )
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, out / "posttest.py")
    current_hash = archive_source(out)
    save_json(out / "stimuli.json", cases)
    save_json(
        out / "design.json",
        {
            "source": args.source.name,
            "source_sha256": sh,
            "current_sha256": current_hash,
            "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "schema": COMPACT_PLAN_VERSION,
            "scope": "Three independent, retrospective single-hour probes. Source trajectory and its 480-hour denominator stay fixed.",
            "selection": "Earliest completed failure of each specified type by day, hour, resident ID. Selected without new replies.",
            "model": MODEL,
            "sdk_retries": 0,
            "max_http": 3,
            "max_per_point": 1,
        },
    )
    print(out, flush=True)
    if not args.online:
        return 0
    import httpx
    from openai import AsyncOpenAI

    key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
    if not key or key == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（隐藏输入）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        return 2
    meter = Meter(3)
    http = httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [meter.before_send], "response": [meter.response]},
    )
    rows = []
    with experiment_environment(
        {
            "LLM_API_KEY": key,
            "PROTO_LLM_TRACE_DIR": str((out / "trace").resolve()),
            "PARALLEL_GROUP_NAME": out.name,
            "PROTO_RUN_SOURCE_SHA256": current_hash,
        }
    ):
        async with AsyncOpenAI(
            api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
        ) as client:
            try:
                for case, kwargs in zip(cases, routing, strict=True):
                    row = await measure(client, meter, case, kwargs)
                    rows.append(row)
                    print(case["case"], row["status"], flush=True)
                    save_json(out / "results.json", rows)
                    if row["stop"]:
                        break
            finally:
                save_json(
                    out / "summary.json",
                    {
                        "expected": 3,
                        "measured": len(rows),
                        "http_requests": meter.dispatched,
                        "repairs_valid": sum(
                            r["phase"] == "repair" and r["accepted"] is not None
                            for r in rows
                        ),
                        "fresh_initial_valid": sum(
                            r["phase"] == "initial" and r["accepted"] is not None
                            for r in rows
                        ),
                    },
                )
    return 0 if len(rows) == 3 and all(r["accepted"] is not None for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
