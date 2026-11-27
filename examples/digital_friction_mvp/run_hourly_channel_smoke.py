"""Re-ask two failed Plan hours from a completed five-day run. Default is offline."""

import argparse
import asyncio
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import os
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from check_hourly_channel_replay import load_archive_hours, rebuild_plan_kwargs
from check_hourly_intention_run import request_payload
from proto.app_entry.intention_contract import COMPACT_PLAN_VERSION
from proto.app_entry.planner import DigitalAppEntryPlanBlock, HourlyIntentionPlanError
from proto.llm_trace import bind_trace_context, traced_agent_tick
from run_hourly_intention_pairs import CapturePlan, SmokeRequestBudget, SMOKE_HTTP_LIMIT
from run_strategy_memory_pairs import (
    ENDPOINT,
    EXAMPLE,
    MODEL,
    ROOT,
    ZhipuStrategyClient,
    save_json,
)


CASES = {
    9: "selected goal must use its required_channel during an active hour",
    20: "unknown app channel",
}


async def prepare_cases(folder):
    hours = load_archive_hours(folder)
    cases = []
    for hour, reason in CASES.items():
        events = hours[4, hour]
        (request,) = [
            r
            for r in events
            if r["module"] == "app_plan"
            and r["kind"] == "request"
            and r["phase"] == "initial"
        ]
        (audit,) = [r for r in events if r["kind"] == "intent_validation"]
        if (
            not audit["technical_failure"]
            or audit["rejection_reason"] != reason
            or request["model"] != MODEL
        ):
            raise ValueError(f"Day 4 hour {hour} is not the expected failed GLM case")
        kwargs = rebuild_plan_kwargs(events)
        recorder = CapturePlan("opportunity_v1")
        await DigitalAppEntryPlanBlock().forward(llm=recorder, **kwargs)
        (stimulus,) = recorder.requests
        old, new = request_payload(request), request_payload(stimulus)
        # Only the decision interface changes. Replay the state recorded at this hour,
        # even if the new model answers the earlier hour differently.
        for field in (
            "inputs",
            "digital_needs",
            "channels",
            "exposure_cap",
            "minimum_confidence",
            "targets",
            "defer_options",
        ):
            if old[field] != new[field]:
                raise ValueError(f"Day 4 hour {hour} differs in {field}")
        if (
            new["schema_version"] != COMPACT_PLAN_VERSION
            or request["parameters"] != stimulus["parameters"]
        ):
            raise ValueError("Unexpected Plan version or changed sampling parameters")
        evidence = dict(
            hour=hour,
            source_call_id=request["call_id"],
            source_rejection=reason,
            stimulus=stimulus,
        )
        cases.append((kwargs, evidence))
    return cases


@traced_agent_tick
async def measure_case(client, kwargs, evidence):
    bind_trace_context(
        purpose="archived_channel_smoke",
        talkingdata_day=4,
        hour=evidence["hour"],
        source_call_id=evidence["source_call_id"],
    )
    transport = ZhipuStrategyClient(client, evidence["stimulus"]["messages"])
    try:
        plan = await DigitalAppEntryPlanBlock().forward(llm=transport, **kwargs)
    except HourlyIntentionPlanError as exc:
        plan, audit = None, exc.audit
    else:
        audit = plan.audit
    return {
        "hour": evidence["hour"],
        "source_call_id": evidence["source_call_id"],
        "parse_status": audit["parse_status"],
        "plan_valid": plan is not None,
        "accepted_choice": plan.intent if plan else None,
        "app_context_counts": plan.app_context_counts if plan else None,
        "rejection_reason": audit.get("rejection_reason"),
        "requests": transport.requests,
        "returned_models": transport.returned_models,
        "transport_errors": transport.transport_errors,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archive",
        type=Path,
        help="Original five-day v3 run with the two failed channel decisions",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="Contact GLM for two cases, at most four HTTP requests",
    )
    parser.add_argument("--output-dir", type=Path, help="New output directory")
    args = parser.parse_args()
    os.umask(0o077)
    os.environ.pop("PROTO_LLM_TRACE_DIR", None)
    cases = await prepare_cases(args.archive)
    name = (
        "channel_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
    )
    folder = (
        args.output_dir or ROOT / "agentsociety_data/runs/hourly_channel_smoke" / name
    )
    folder.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__).resolve(), *(EXAMPLE / "proto").rglob("*.py")]
    sources.extend(
        EXAMPLE / f
        for f in (
            "check_hourly_channel_replay.py",
            "check_hourly_intention_run.py",
            "run_hourly_intention_pairs.py",
            "run_strategy_memory_pairs.py",
            "probe_hourly_intention.py",
            "probe_strategy_memory_pair.py",
            "config_runtime.py",
            "analysis_strategy_memory_pairs.py",
            "compare_strategy_prompt_runs.py",
            "analysis_entry_calibration_comparison.py",
            "analysis_app_entry_validation.py",
        )
    )
    archive = folder / "experiment_source.zip"
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as z:
        for source in sorted(sources):
            z.write(source, str(source.relative_to(EXAMPLE)))
    code_hash = sha256(archive.read_bytes()).hexdigest()
    save_json(
        folder / "design.json",
        {
            "model": MODEL,
            "schema_version": COMPACT_PLAN_VERSION,
            "source_archive": args.archive.name,
            "source_trace_sha256": {
                f.name: sha256(f.read_bytes()).hexdigest()
                for f in sorted((args.archive / "trace").glob("*.jsonl"))
            },
            "experiment_source_sha256": code_hash,
            "online": args.online,
            "http_request_limit": SMOKE_HTTP_LIMIT,
            "observations": "Two independent archived Day 4 Plan inputs; no continuous simulation or task execution.",
        },
    )
    save_json(folder / "stimuli.json", [e for _, e in cases])
    print(f"已核对第 4 天 09:00 和 20:00 的真实观测，结果目录 {folder}", flush=True)
    if not args.online:
        print("离线准备完成，在线请求 0 次。")
        return 0

    import httpx
    from openai import AsyncOpenAI

    key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
    if not key or key == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（输入隐藏）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        parser.exit(2, "未提供密钥，实验未启动。\n")
    os.environ.update(
        LLM_API_KEY=key,
        PROTO_LLM_TRACE_DIR=str((folder / "trace").resolve()),
        PARALLEL_GROUP_NAME=folder.name,
        PROTO_RUN_SOURCE_SHA256=code_hash,
    )
    rows = []
    budget = SmokeRequestBudget()
    http = httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [budget.before_send]},
    )
    async with AsyncOpenAI(
        api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
    ) as client:
        for kwargs, evidence in cases:
            budget.case_dispatched = 0
            row = await measure_case(client, kwargs, evidence)
            rows.append(row)
            report = {
                "complete": len(rows) == len(cases),
                "first_valid": sum(r["parse_status"] == "ok" for r in rows),
                "final_valid": sum(r["plan_valid"] for r in rows),
                "http_requests": budget.dispatched,
                "decisions": rows,
            }
            save_json(folder / "summary.json", report)
            print(f"第 4 天 {row['hour']:02d}:00，{row['parse_status']}。", flush=True)
            if any(
                e["http_status"] in {401, 403, 429} for e in row["transport_errors"]
            ):
                break
    return int(not report["complete"] or report["final_valid"] != len(cases))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
