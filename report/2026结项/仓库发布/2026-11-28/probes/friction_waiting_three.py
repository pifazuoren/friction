"""Three fresh first answers from the first/middle/last archived waiting hours, one wire call apiece."""

import argparse
import asyncio
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4
import friction_three_plan_failures as probe
from check_daily_channel_choices import load_archive


async def prepare(source, prior):
    slots, provenance = load_archive(source)
    eligible = []
    for slot, rows in sorted(slots.items()):
        requests = [
            r
            for r in rows
            if r["module"] == "app_plan"
            and r["kind"] == "request"
            and r["phase"] == "initial"
        ]
        if not requests:
            continue
        (request,) = requests
        body = probe.request_payload(request)
        obs = body["inputs"]
        goal = obs["current_intention"]
        if (
            goal
            and goal["status"] == "deferred"
            and not obs["goal_review_due"]
            and goal["next_review_at_sim_hour"] > obs["monotonic_sim_hour"]
            and not body["targets"]
            and not body["defer_options"]
        ):
            eligible.append((slot, rows, request, goal))
    calls = [r["call_id"] for _, _, r, _ in eligible]
    probe.require(
        len(eligible) == len(set(calls)) == 17
        and len({g["goal_id"] for _, _, _, g in eligible}) == 1,
        "Expected seventeen waiting hours on a single appointment",
    )
    results = json.loads((prior / "results.json").read_text())
    prior_design = json.loads((prior / "design.json").read_text())
    probe.require(
        prior_design["source"] == source.name
        and prior_design["source_sha256"] == provenance["experiment_source_sha256"],
        "Previous probe referenced a different continuous run",
    )
    (prior_case,) = [
        c
        for c in json.loads((prior / "stimuli.json").read_text())
        if c["case"] == "before_scheduled_review"
    ]
    (prior_row,) = [r for r in results if r["source_call_id"] in calls]
    probe.require(
        prior_row["source_call_id"]
        == calls[0]
        == prior_case["archived_initial"]["call_id"]
        and prior_row["phase"] == "initial"
        and prior_row["accepted"] is None,
        "Prior seen/unseen accounting differs",
    )
    cases = []
    routing = []
    for ix in [0, len(eligible) // 2, len(eligible) - 1]:
        (day, hour, _), rows, request, goal = eligible[ix]
        old = probe.request_payload(request)
        route = probe.event(rows, "hourly_intention", "hourly_intention")
        probe.check_plan_calls(rows, route)
        raw = probe.event(
            rows, "app_plan", "response", phase="initial", call_id=request["call_id"]
        )["raw"]
        wire = probe.parse_compact_reply(raw)
        kwargs = probe.rebuild_plan_kwargs(rows, expected_version=old["schema_version"])
        answer = json.dumps(
            {**wire, "action": "no_app", "additional_apps": []}, ensure_ascii=False
        )
        result, _, original = await probe.replay(
            {**kwargs, "pending_review_notice_version": "pending_review_v1"}, [answer]
        )
        probe.require(
            result is not None and len(original) == 1,
            "Failed to generate previous waiting prompt",
        )
        if ix == 0:
            probe.require(
                original[0] == prior_case["new_stimulus"],
                "Prior 07:00 transmitted prompt changed",
            )
        result, _, new = await probe.replay(kwargs, [answer])
        probe.require(result is not None and len(new) == 1, "No-phone choice was lost")
        v1 = probe.request_payload(original[0])
        v2 = probe.request_payload(new[0])
        notice = v2["pending_review_notice"]
        expected = {
            **v1,
            "pending_review_notice": {
                **v1["pending_review_notice"],
                "version": "pending_review_v2",
            },
        }
        system = new[0]["messages"][0]["content"]
        probe.require(
            v2 == expected
            and new[0]["parameters"]
            == original[0]["parameters"]
            == request["parameters"]
            and system != original[0]["messages"][0]["content"]
            and "从 actions 中原样选一个" in system
            and not any(
                t in system
                for t in (
                    "engage_goal",
                    "continue_goal",
                    "drop_goal",
                    "defer_goal",
                    "defer_options",
                )
            )
            and notice["next_review_at_sim_hour"] == goal["next_review_at_sim_hour"],
            "Unexpected change outside waiting guidance",
        )
        probe.require(
            all(
                k == "no_app" or k.startswith("habitual_app@open:")
                for k in v2["actions"]
            ),
            "Unexpected target/action in waiting-hour menu",
        )
        for token in v2["actions"]:
            if token == "no_app":
                continue
            p, _, _ = await probe.replay(
                kwargs, [json.dumps({**wire, "action": token, "additional_apps": []})]
            )
            probe.require(
                p and p.app_context_counts == {token.split(":", 1)[1]: 1},
                "Daily channel lost in new menu",
            )
        bad, _, _ = await probe.replay(kwargs, [raw, raw])
        probe.require(bad is None, "The archived out-of-menu deferral was adopted")
        seen = ix == 0
        cases.append(
            {
                "case": ("early", "middle", "late")[
                    (0, len(eligible) // 2, len(eligible) - 1).index(ix)
                ],
                "day": day,
                "hour": hour,
                "agent_id": request["agent_id"],
                "seen_in_previous_probe": seen,
                "new_dispatch_phase": "initial",
                "archived_status": route["parse_status"],
                "archived_initial": {
                    k: request[k]
                    for k in ("call_id", "query_id", "messages", "parameters")
                },
                "archived_initial_raw": raw,
                "notice_v1_stimulus": original[0],
                "new_stimulus": new[0],
                "notice_v1_response": prior_row["new_raw"] if seen else None,
            }
        )
        routing.append(kwargs)
    probe.require(
        [c["hour"] for c in cases] == [7, 15, 23]
        and len({(c["day"], c["agent_id"]) for c in cases}) == 1,
        "Old waiting-hour schedule changed",
    )
    return provenance, calls, cases, routing


async def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("prior", type=Path)
    cli.add_argument("--output-dir", type=Path)
    cli.add_argument("--online", action="store_true")
    args = cli.parse_args()
    os.umask(0o077)
    provenance, eligible, cases, routes = await prepare(args.source, args.prior)
    out = (
        args.output_dir
        or probe.ROOT
        / "agentsociety_data/runs/plan_failure_probes"
        / (
            "waiting_first_"
            + datetime.now().strftime("%Y%m%d_%H%M%S_")
            + uuid4().hex[:6]
        )
    )
    out.mkdir(parents=True, exist_ok=False)
    for p in (Path(__file__), Path(probe.__file__)):
        shutil.copy2(p, out / p.name)
    source_hash = probe.archive_source(out)
    probe.save_json(
        out / "design.json",
        {
            "continuous_run": provenance,
            "prior_probe": args.prior.name,
            "eligible_call_ids_by_hour": eligible,
            "selection": "First, median, last of 17 waiting hours for one goal",
            "previous_source": "Only the first time point was asked during the prior V1 pilot",
            "model": probe.MODEL,
            "source_sha256": source_hash,
            "http_limit": 3,
            "per_case_limit": 1,
            "repairs": 0,
            "sdk_retries": 0,
            "purpose": "Independent first answers to three archived observations. No continuation or source writeback.",
        },
    )
    probe.save_json(out / "stimuli.json", cases)
    print("已选 07:00、15:00、23:00，均为第 5 天 3 号人物；", out, flush=True)
    if not args.online:
        return 0
    import httpx
    from openai import AsyncOpenAI

    key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
    if not key or key == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（隐藏输入）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        return 2
    meter = probe.Meter(3)
    rows = []
    http = httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [meter.before_send], "response": [meter.response]},
    )
    with probe.experiment_environment(
        {
            "LLM_API_KEY": key,
            "PROTO_LLM_TRACE_DIR": str((out / "trace").resolve()),
            "PARALLEL_GROUP_NAME": out.name,
            "PROTO_RUN_SOURCE_SHA256": source_hash,
        }
    ):
        async with AsyncOpenAI(
            api_key=key, base_url=probe.ENDPOINT, max_retries=0, http_client=http
        ) as client:
            try:
                for case, kwargs in zip(cases, routes, strict=True):
                    r = await probe.measure(client, meter, case, kwargs)
                    r["seen_in_previous_probe"] = case["seen_in_previous_probe"]
                    r["recorded_behavior"] = (
                        r["accepted"]["intent"]["kind"] if r["accepted"] else None
                    )
                    rows.append(r)
                    probe.save_json(out / "results.json", rows)
                    print(case["hour"], r["status"], r["recorded_behavior"], flush=True)
                    if r["stop"]:
                        break
            finally:
                probe.save_json(
                    out / "summary.json",
                    {
                        "attempted": len(rows),
                        "scheduled": 3,
                        "http_requests": meter.dispatched,
                        "first_valid": sum(r["accepted"] is not None for r in rows),
                        "daily_app": sum(
                            r["recorded_behavior"] == "habitual_app" for r in rows
                        ),
                        "no_phone": sum(
                            r["recorded_behavior"] == "no_app" for r in rows
                        ),
                        "failed": sum(r["accepted"] is None for r in rows),
                        "not_reached": 3 - len(rows),
                    },
                )
    return 0 if len(rows) == 3 and all(r["accepted"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
