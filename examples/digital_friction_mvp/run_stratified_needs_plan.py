"""Exercise the live Needs → Plan path once per frozen stratum. Default is offline."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from check_hourly_channel_replay import RecordedReplies, event, require
from check_hourly_intention_run import request_payload
from check_stratified_needs_plan import (
    check_archive,
    check_pre_hour,
    plan_candidates,
    stratum,
)
from proto.app_entry.intention_contract import (
    COMPACT_PLAN_VERSION,
    compact_menu,
    compact_needs,
    compact_observation,
    include_required_channels,
)
from proto.app_entry.needs import (
    COMPACT_NEEDS_REPAIR_V1,
    COMPACT_NEEDS_REPAIR_VERSION,
    DigitalNeedsBlock,
)
from proto.app_entry.planner import DigitalAppEntryPlanBlock, HourlyIntentionPlanError
from proto.llm_psychology import _extract_json_object
from proto.llm_trace import (
    LLMQueryTrace,
    LLMRunInterrupted,
    bind_trace_context,
    traced_agent_tick,
)
from run_hourly_intention_pairs import SmokeRequestBudget
from run_hourly_strategy_factorial import (
    FactorialClient,
    archive_source,
    experiment_environment,
)
from run_strategy_memory_pairs import ENDPOINT, MODEL, ROOT, save_json

POINTS = 12
HTTP_LIMIT = POINTS * 2 * 2


class Meter(SmokeRequestBudget):
    """Two HTTP dispatches per block. Retain provider-reported usage without storing headers."""

    def __init__(self, limit=HTTP_LIMIT):
        super().__init__(limit=limit)
        self.usage = []

    async def response(self, response):
        if response.is_success:
            await response.aread()
            try:
                usage = response.json().get("usage")
            except (ValueError, AttributeError):
                usage = None
            self.usage.append(usage if isinstance(usage, dict) else None)


class FirstResponseOnly(LLMRunInterrupted):
    """A failed Plan first answer ends the two-call repair pilot before another send."""


class StageClient(FactorialClient):
    first_raw = None
    initial_only = False

    async def atext_request(self, **kwargs):
        if self.initial_only and self.requests:
            raise FirstResponseOnly("Plan repair omitted by the two-request design")
        raw = await super().atext_request(**kwargs)
        if self.requests == 1:
            self.first_raw = raw
        return raw


def fresh_plan(case, needs, top_k, *, plan_schema=COMPACT_PLAN_VERSION):
    reference = case["plan_given_archived_needs"]
    old = request_payload(reference)
    base = request_payload(case["needs"])["inputs"]
    packet = {**old["inputs"], "day1_3_habit": base["day1_3_habit"]}
    check_pre_hour(packet, case["day"], case["hour"])
    require(
        compact_observation(packet) == old["inputs"]
        and list(stratum(packet)) == case["stratum"]
        and old["schema_version"] == plan_schema,
        "Plan template or stratum drift",
    )
    candidates = plan_candidates(base, needs, top_k)
    channels = sorted(include_required_channels(candidates, packet))
    expected = deepcopy(reference)
    body = {
        **old,
        "digital_needs": compact_needs(needs.to_dict(include_audit=False), plan_schema),
        **compact_menu(old["inputs"], old["schema_version"], channels),
        "channels": channels,
    }
    prefix, _ = expected["messages"][1]["content"].split("\n", 1)
    expected["messages"][1]["content"] = (
        prefix + "\n" + json.dumps(body, ensure_ascii=False)
    )
    kwargs = dict(
        input_payload=packet,
        candidate_contexts=candidates,
        needs=needs,
        intensity_profile={"active_exposure_cap": old["exposure_cap"]},
        min_confidence=old["minimum_confidence"],
        compact_schema_version=old["schema_version"],
    )
    return kwargs, expected


async def run_stage(client, meter, stimulus, block, kwargs, *, initial_only=False):
    transport = StageClient(client, stimulus)
    transport.initial_only = initial_only
    meter.case_dispatched = 0
    usage_start = len(meter.usage)
    params = stimulus["parameters"]
    output = None
    error = None
    try:
        output = await block.forward(
            llm=transport,
            **kwargs,
            timeout=params["timeout"],
            retries=params["retries"],
            json_attempts=1,
        )
        status = output.audit["parse_status"]
    except FirstResponseOnly:
        status = "invalid_first_response"
        error = "plan_repair_not_dispatched"
    except LLMRunInterrupted:
        if not transport.stop_http:
            raise
        status = "provider_stopped"
    except HourlyIntentionPlanError as exc:
        status = exc.audit["parse_status"]
        error = exc.audit.get("rejection_reason")
    except ValueError as exc:
        if not str(exc).startswith(
            "DigitalNeedsBlock JSON output failed after bounded attempts: "
        ):
            raise
        status = str(exc).rsplit(": ", 1)[-1]
        error = "invalid_needs" if not transport.transport_errors else "request_error"
    require(
        meter.case_dispatched == transport.requests
        and 1 <= transport.requests <= 2
        and all(m == MODEL for m in transport.returned_models),
        "Dispatched request count/model mismatch",
    )
    first = _extract_json_object(transport.first_raw) if transport.first_raw else None
    return output, {
        "status": status,
        "valid": output is not None,
        "error": error,
        "requests": transport.requests,
        "returned_models": transport.returned_models,
        "transport_errors": transport.transport_errors,
        "provider_stopped": transport.stop_http,
        "usage": meter.usage[usage_start:],
        "first_echoed_inputs": isinstance(first, dict)
        and first.get("inputs") == request_payload(stimulus)["inputs"],
        "first_action": first.get("action") if isinstance(first, dict) else None,
    }


@traced_agent_tick
async def measure(client, meter, case, top_k, needs_version):
    row = {
        k: v for k, v in case.items() if k not in ("needs", "plan_given_archived_needs")
    }
    bind_trace_context(purpose="stratified_needs_plan", **row)
    base = request_payload(case["needs"])["inputs"]
    needs, row["needs"] = await run_stage(
        client,
        meter,
        case["needs"],
        DigitalNeedsBlock(),
        dict(input_payload=base, prompt_version=needs_version),
    )
    row.update(plan=None, accepted_needs=None, intent=None, bundle=None)
    if needs is None:
        return row
    row["accepted_needs"] = needs.to_dict(include_audit=False)
    kwargs, stimulus = fresh_plan(case, needs, top_k)
    prompt_bytes = json.dumps(stimulus, sort_keys=True, ensure_ascii=False).encode()
    row["plan_stimulus_sha256"] = sha256(prompt_bytes).hexdigest()
    plan, row["plan"] = await run_stage(
        client, meter, stimulus, DigitalAppEntryPlanBlock(), kwargs
    )
    if plan is not None:
        row["intent"] = plan.intent
        bundle = plan.to_bundle(device_id="probe", day=case["day"], hour=case["hour"])
        row["bundle"] = {
            "active": bundle.active,
            "primary_context": bundle.primary_context,
            "app_context_counts": bundle.app_context_counts,
            "exposures": bundle.active_event_app_exposures,
        }
    return row


def summarize(rows, meter):
    stages = {}
    for module in ("needs", "plan"):
        measured = [row[module] for row in rows if row[module] is not None]
        stages[module] = {
            "scheduled": POINTS,
            "attempted": len(measured),
            "first_valid": sum(s["status"] == "ok" for s in measured),
            "final_valid": sum(s["valid"] for s in measured),
            "failed": sum(not s["valid"] for s in measured),
            "repair_requests": sum(s["requests"] - 1 for s in measured),
            "first_echoed_inputs": sum(s["first_echoed_inputs"] for s in measured),
            "http_requests": sum(s["requests"] for s in measured),
            "returned_models": dict(
                Counter(m for s in measured for m in s["returned_models"])
            ),
            "statuses": dict(Counter(s["status"] for s in measured)),
        }
    reported = [u for u in meter.usage if u is not None]
    return {
        "expected": POINTS,
        "recorded": len(rows),
        "complete": len(rows) == POINTS,
        "http_request_limit": HTTP_LIMIT,
        "http_requests": meter.dispatched,
        "stages": stages,
        "chain_valid": sum(row["bundle"] is not None for row in rows),
        "recorded_origins": dict(Counter(row["origin"] for row in rows)),
        "accepted_actions": dict(
            Counter(r["intent"]["kind"] for r in rows if r["intent"])
        ),
        "usage_reports": len(reported),
        "reported_tokens": {
            k: sum(u.get(k) or 0 for u in reported)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        if reported
        else None,
        "billed_amount": None,
        "billing_note": "Provider billing is not part of the completion response.",
    }


async def collect(client, meter, folder, cases, top_k, needs_version):
    rows = []
    with (folder / "decisions.jsonl").open("x", encoding="utf-8") as log:
        for case in cases:
            try:
                row = await measure(client, meter, case, top_k, needs_version)
            except BaseException as exc:
                save_json(
                    folder / "summary.json",
                    {
                        **summarize(rows, meter),
                        "interrupted_at": case["stratum"],
                        "interruption": type(exc).__name__,
                    },
                )
                raise
            log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            log.flush()
            rows.append(row)
            report = summarize(rows, meter)
            save_json(folder / "summary.json", report)
            status = row["plan"]["status"] if row["plan"] else "not_reached"
            print(
                f"[{len(rows)}/{len(cases)}] {case['stratum']} Needs={row['needs']['status']} Plan={status}",
                flush=True,
            )
            if any(row[k] and row[k]["provider_stopped"] for k in ("needs", "plan")):
                break
    return summarize(rows, meter)


async def replay_failed_initial(case, raw, second, needs_version, repair_version):
    """Reconstruct both production dialogs and validate replies locally, without tracing mock sends."""
    transport = RecordedReplies([raw, second])
    params = case["needs"]["parameters"]
    with experiment_environment({"PROTO_LLM_TRACE_DIR": None}):
        try:
            needs = await DigitalNeedsBlock().forward(
                llm=transport,
                input_payload=request_payload(case["needs"])["inputs"],
                prompt_version=needs_version,
                compact_repair_version=repair_version,
                timeout=params["timeout"],
                retries=params["retries"],
            )
        except ValueError as exc:
            if not str(exc).startswith(
                "DigitalNeedsBlock JSON output failed after bounded attempts: "
            ):
                raise
            needs = None
    require(
        len(transport.requests) == 2 and transport.requests[0] == case["needs"],
        "Archived first answer no longer triggers the same Needs decision",
    )
    return needs, transport.requests[1]


async def load_failed_initial(folder, cases, source, needs_version):
    design = json.loads((folder / "design.json").read_text())
    data = (folder / "stimuli.json").read_bytes()
    replay = json.loads((folder / "replay.json").read_text())
    require(
        sha256(data).hexdigest() == design["stimuli_sha256"]
        and json.loads(data) == cases
        and design["model"] == MODEL
        and design["needs_prompt"] == needs_version
        and replay["source"] == source
        and replay["plan_schema"] == design["plan_schema"]
        and all(request_payload(c["plan_given_archived_needs"])["schema_version"] == design["plan_schema"] for c in cases)
        and sha256((folder / "experiment_source.zip").read_bytes()).hexdigest()
        == design["source_sha256"],
        "Prior prompts, experiment version, or source archive mismatch",
    )
    rows = [
        json.loads(line) for line in (folder / "decisions.jsonl").read_text().splitlines()
    ]
    require(
        len(rows) == len(cases)
        and [r["stratum"] for r in rows] == [c["stratum"] for c in cases],
        "Prior run did not measure the full frozen stratum schedule",
    )
    failed = [i for i, row in enumerate(rows) if not row["needs"]["valid"]]
    require(
        len(failed) == 1,
        "Expected exactly one exhausted Needs response in the prior pilot",
    )
    idx = failed[0]
    row, case = rows[idx], cases[idx]
    require(
        row["plan"] is None
        and row["needs"]["requests"] == 2
        and row["needs"]["returned_models"] == [MODEL, MODEL]
        and all(
            row[k] == v
            for k, v in case.items()
            if k not in ("needs", "plan_given_archived_needs")
        ),
        "Prior failure must match the source hour and two returned Needs responses",
    )
    traces = []
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if (
                record.get("stratum") == case["stratum"]
                and record["module"] == "app_needs"
            ):
                require(
                    record["group_id"] == folder.name
                    and record["code_hash"] == design["source_sha256"]
                    and record["source_needs_call_id"] == case["source_needs_call_id"]
                    and all(
                        record[k] == case[k] for k in ("origin", "rank", "day", "hour")
                    ),
                    "Unrelated source trace in failed Needs probe",
                )
                traces.append(record)
    first, repair = [
        event(traces, "app_needs", "request", phase=p) for p in ("initial", "repair")
    ]
    require(
        first["query_id"] == repair["query_id"]
        and first["tick_id"] == repair["tick_id"]
        and first["call_id"] != repair["call_id"]
        and all(r["model"] == MODEL for r in (first, repair)),
        "Prior Needs request linkage mismatch",
    )

    def rejected_raw(req):
        fields = {k: req[k] for k in ("phase", "query_id", "tick_id", "call_id")}
        require(
            event(traces, "app_needs", "parse", **fields)["status"] == "invalid_schema",
            "Expected an invalid source reply",
        )
        return event(traces, "app_needs", "response", **fields)["raw"]

    initial_raw, old_repair_raw = rejected_raw(first), rejected_raw(repair)
    require(
        {k: first[k] for k in ("messages", "parameters")} == case["needs"],
        "Recorded first reply came from a different prompt",
    )
    old_result, old_stimulus = await replay_failed_initial(
        case, initial_raw, old_repair_raw, needs_version, COMPACT_NEEDS_REPAIR_V1
    )
    new_result, new_stimulus = await replay_failed_initial(
        case, initial_raw, old_repair_raw, needs_version, COMPACT_NEEDS_REPAIR_VERSION
    )
    require(
        old_result is None
        and new_result is None
        and old_stimulus == {k: repair[k] for k in ("messages", "parameters")}
        and new_stimulus["messages"] != old_stimulus["messages"]
        and new_stimulus["parameters"] == old_stimulus["parameters"]
        and request_payload(new_stimulus) == request_payload(case["needs"]),
        "Repair contrast was not isolated",
    )
    return case, {
        "source_run": folder.name,
        "source_sha256": design["source_sha256"],
        "source_plan_schema": design["plan_schema"],
        "source_first_call_id": first["call_id"],
        "source_repair_call_id": repair["call_id"],
        "source_initial_sha256": sha256(initial_raw.encode()).hexdigest(),
        "source_initial_raw": initial_raw,
        "source_repair_sha256": sha256(old_repair_raw.encode()).hexdigest(),
        "repair_version": COMPACT_NEEDS_REPAIR_VERSION,
        "new_repair_stimulus": new_stimulus,
    }


@traced_agent_tick
async def retry_failed(client, meter, case, fixture, folder, top_k, needs_version):
    bind_trace_context(
        purpose="retry_failed_needs",
        stratum=case["stratum"],
        origin=case["origin"],
        rank=case["rank"],
        hour=case["hour"],
        day=case["day"],
        source_first_call_id=fixture["source_first_call_id"],
        repair_version=fixture["repair_version"],
    )
    stimulus = fixture["new_repair_stimulus"]
    stage = StageClient(client, stimulus)
    trace = LLMQueryTrace("app_needs", stage)
    result = {
        "source_first_call_id": fixture["source_first_call_id"],
        "stratum": case["stratum"],
        "origin": case["origin"],
        "archived_initial_responses": 1,
        "new_needs_initial_requests": 0,
        "http_request_limit": meter.limit,
        "accepted_needs": None,
        "plan": None,
        "bundle": None,
        "intent": None,
        "chain_valid": 0,
    }
    try:
        try:
            raw = await trace.request(
                "repair", 1, dialog=stimulus["messages"], **stimulus["parameters"]
            )
        except LLMRunInterrupted:
            if not stage.stop_http:
                raise
            raw = None
        except Exception:
            if not stage.transport_errors:
                raise
            raw = None
        require(
            stage.requests == meter.dispatched == 1
            and all(m == MODEL for m in stage.returned_models),
            "New Needs repair dispatch count or model mismatch",
        )
        needs = None
        if raw is not None:
            needs, check = await replay_failed_initial(
                case,
                fixture["source_initial_raw"],
                raw,
                needs_version,
                fixture["repair_version"],
            )
            require(
                check == stimulus,
                "New raw reply does not match its frozen correction prompt",
            )
            trace.parsed(
                "ok_repaired" if needs else "invalid_repair",
                needs.to_dict(include_audit=False) if needs else None,
            )
        result["needs_repair"] = {
            "valid": needs is not None,
            "requests": stage.requests,
            "returned_models": stage.returned_models,
            "transport_errors": stage.transport_errors,
            "usage": list(meter.usage),
        }
        if needs is not None:
            result["accepted_needs"] = needs.to_dict(include_audit=False)
            kwargs, expected = fresh_plan(case, needs, top_k, plan_schema=fixture["source_plan_schema"])
            save_json(folder / "plan_after_new_needs.json", expected)
            plan, result["plan"] = await run_stage(
                client,
                meter,
                expected,
                DigitalAppEntryPlanBlock(),
                kwargs,
                initial_only=True,
            )
            if plan is not None:
                result["chain_valid"] = 1
                result["intent"] = plan.intent
                bundle = plan.to_bundle(
                    device_id="probe", day=case["day"], hour=case["hour"]
                )
                result["bundle"] = {
                    "active": bundle.active,
                    "app_context_counts": bundle.app_context_counts,
                    "exposures": bundle.active_event_app_exposures,
                }
    except BaseException as exc:
        result["interruption"] = type(exc).__name__
        raise
    finally:
        result["http_requests"] = meter.dispatched
        save_json(folder / "summary.json", result)
    return result


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--online", action="store_true")
    parser.add_argument(
        "--retry-failed-needs",
        type=Path,
        help="Pilot run with one exhausted Needs clip; replay its archived first answer",
    )
    args = parser.parse_args(argv)
    os.umask(0o077)
    plan_schema = COMPACT_PLAN_VERSION
    if args.retry_failed_needs:
        design = json.loads((args.retry_failed_needs / "design.json").read_text())
        plan_schema = design["plan_schema"]
    with experiment_environment({"PROTO_LLM_TRACE_DIR": None}):
        report, cases = await check_archive(args.archive, plan_schema=plan_schema)
    require(
        len(cases) == POINTS == len({tuple(c["stratum"]) for c in cases}),
        "Expected all 12 strata",
    )
    top_k = json.loads((args.archive / "resolved_config.json").read_text())["runtime"][
        "proto_app_entry_rollout_top_k"
    ]
    retry = None
    if args.retry_failed_needs:
        selected, retry = await load_failed_initial(
            args.retry_failed_needs, cases, report["source"], report["needs_prompt"]
        )
        cases = [selected]
    limit = 2 if retry else HTTP_LIMIT
    folder = (
        args.output_dir
        or ROOT
        / "agentsociety_data/runs/stratified_needs_plan"
        / ("strata_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6])
    )
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    source_hash = archive_source(folder)
    if retry:
        save_json(folder / "repair_fixture.json", retry)
    save_json(folder / "replay.json", report)
    save_json(folder / "stimuli.json", cases)
    save_json(
        folder / "design.json",
        {
            "model": MODEL,
            "expected": len(cases),
            "study": "retry_failed_needs" if retry else "stratified_needs_plan",
            "sdk_retries": 0,
            "top_k": top_k,
            "needs_prompt": report["needs_prompt"],
            "plan_schema": report["plan_schema"],
            "http_limit": limit,
            "per_stage_limit": 2,
            "source_sha256": source_hash,
            "stimuli_sha256": sha256(
                (folder / "stimuli.json").read_bytes()
            ).hexdigest(),
            "scope": "Independent single-hour probes. No writeback to the source trajectory.",
        },
    )
    print(f"{len(cases)} 个场景已冻结，结果目录 {folder}", flush=True)
    if not args.online:
        return 0
    import httpx
    from openai import AsyncOpenAI

    key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
    if not key or key == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（隐藏输入）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        return 2
    meter = Meter(limit=limit)
    http = httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [meter.before_send], "response": [meter.response]},
    )
    with experiment_environment(
        {
            "LLM_API_KEY": key,
            "PROTO_LLM_TRACE_DIR": str((folder / "trace").resolve()),
            "PARALLEL_GROUP_NAME": folder.name,
            "PROTO_RUN_SOURCE_SHA256": source_hash,
            "PROTO_HOURLY_INTENTION_MODE": "opportunity_v1",
            "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION": "app_entry_plan_v3",
        }
    ):
        async with AsyncOpenAI(
            api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
        ) as client:
            if retry:
                result = await retry_failed(
                    client,
                    meter,
                    cases[0],
                    retry,
                    folder,
                    top_k,
                    report["needs_prompt"],
                )
            else:
                result = await collect(
                    client, meter, folder, cases, top_k, report["needs_prompt"]
                )
    return 0 if result["chain_valid"] == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
