"""Check free-hour Needs, Plan and emitted App bundles on previously unsampled frozen slots."""

import argparse
import asyncio
from collections import Counter, defaultdict
from contextlib import closing
import csv
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID

from analysis_entry_calibration_comparison import load_observations
from analysis_free_phone_probe import activity_scores
from check_hourly_channel_replay import event
from check_hourly_choice_evidence import request_payload
from check_stratified_needs_plan import check_pre_hour
from proto.app_entry import PHONE_USE_NEEDS_V3, PHONE_USE_NEEDS_V5
from proto.app_entry.rollout import run_app_entry_rollout_hour
from proto.app_entry.phone_policy import resolve_phone_use
from proto.llm_trace import LLMRunInterrupted
from run_strategy_memory_pairs import ENDPOINT, MODEL
from select_phone_habit_cases import SEED, canonical, read_candidates, select, sha

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "agentsociety_data/runs"
ARCHIVE = RUNS / "scheduled_login/scheduled_login_20261128_164754_f22f29"
OLD_PANEL = RUNS / "phone_habit_probe/selected_20261128_01"
USE, LEAVE = "use_phone", "leave_phone"
CAP = 128


def lines(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def write_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(block)
    return checksum.hexdigest()


def freeze(out):
    out.mkdir(parents=True, exist_ok=True)
    selection = out / "selection.jsonl"
    design = out / "selection_design.json"
    old = OLD_PANEL / "selection.jsonl"
    if design.exists():
        spec = json.loads(design.read_bytes())
        if digest(selection) != spec["selection_sha256"] or digest(old) != spec["excluded_panel_sha256"]:
            raise ValueError("Frozen panel changed")
        return lines(selection)
    if selection.exists():
        raise ValueError("Incomplete freeze; choose a fresh directory")
    previous = {row["case_id"] for row in lines(old)}
    candidates, cohort = read_candidates(ARCHIVE)
    chosen, inventory = select([c for c in candidates if c["case_id"] not in previous], cohort)
    ids = {r["case_id"] for r in chosen}
    if len(ids) != len(chosen) or len(ids) != 32 or ids & previous:
        raise ValueError("Incorrect or overlapping test panel")
    keep = (
        "case_id",
        "agent_id",
        "device_id",
        "talkingdata_day",
        "hour",
        "active_days",
        "split",
        "period",
        "stratum",
        "waiting",
        "old_messages_sha256",
        "old_trace_file",
        "old_query_id",
    )
    rows = [{k: r[k] for k in keep} for r in chosen]
    selection.write_bytes(b"".join(canonical(r) + b"\n" for r in rows))
    write_json(
        design,
        dict(
            source=ARCHIVE.name,
            selection_seed=SEED,
            n=len(rows),
            inventory=inventory,
            selection_sha256=digest(selection),
            excluded_panel_sha256=digest(old),
            paired_environment_seed=101,
            replay_sha256=digest(ARCHIVE / "inputs/replay.csv"),
            heldout_sha256=digest(ARCHIVE / "inputs/heldout.csv"),
            procedure="Selected on archived pre-hour requests and D1–3 history before viewing D4–7 labels or replies. Previously unsampled hours of the same archived week and residents; not an independent week or cohort. Each frozen hour is evaluated independently.",
            model=MODEL,
            endpoint="Binary activity of the simulated bundle produced by the hourly Needs and Plan stages.",
            limit=CAP,
        ),
    )
    return rows


def slot(case):
    return int(case["agent_id"]), int(case["talkingdata_day"]), int(case["hour"])


def archived_events(cases):
    wanted = {slot(c) for c in cases}
    grouped = defaultdict(list)
    for file in sorted({c["old_trace_file"] for c in cases}):
        with (ARCHIVE / "trace" / file).open() as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("module") in {"app_needs", "app_plan", "hourly_intention"} and slot(row) in wanted:
                    grouped[slot(row)].append(row)
    return grouped


def scenario(case, rows, snap, cfg):
    a, d, h = slot(case)
    first = event(rows, "app_needs", "request", phase="initial")
    if (
        first["query_id"] != case["old_query_id"]
        or sha(canonical(first["messages"])) != case["old_messages_sha256"]
    ):
        raise ValueError("Wrong Needs request in archive")
    n = request_payload(first)["inputs"]
    check_pre_hour(n, d, h)
    plans = [
        r for r in rows if (r["module"], r["kind"], r.get("phase")) == ("app_plan", "request", "initial")
    ]
    if plans:
        p = request_payload(plans[0])["inputs"]
        check_pre_hour(p, d, h)
    else:
        route = event(rows, "hourly_intention", "hourly_intention")
        if (
            route["status"] != "technical_failure"
            or route["goal_state_before"] is not None
            or route["opportunity_ids"]
        ):
            raise ValueError("Cannot reconstruct pending opportunities of an unplanned archived hour")
        p = dict(
            available_opportunities=[],
            current_intention=None,
            goal_review_due=True,
            max_defer_hours=cfg["proto_hourly_intention_max_defer_hours"],
            recent_task_episodes=n["recent_task_episodes"],
        )
    psych = n["pre_hour_psychology"]
    return dict(
        agent_id=a,
        simulation_day=d - 1,
        tick_seconds=h * 3600 + 1,
        environment=n["environment_cues"],
        stable_profile=n["stable_profile"],
        device_id=str(case["device_id"]),
        selected_rank=snap["selected_rank"],
        habit_memory=snap["app_entry_habit_memory"],
        day4_snapshot=snap,
        recent_rollout_rows=n["recent_simulated_bundles"],
        recent_task_episodes=p["recent_task_episodes"],
        latest_reflection=n["latest_reflection"],
        helplessness=psych["helplessness"],
        trust=psych["trust_in_apps"],
        avoidance=psych["avoidance_tendency"],
        needs_prompt_version=cfg["proto_app_entry_needs_prompt_version"],
        plan_prompt_version=cfg["proto_app_entry_plan_prompt_version"],
        json_attempts=cfg["proto_app_entry_rollout_json_attempts"],
        min_confidence=cfg["proto_app_entry_rollout_min_confidence"],
        top_k=cfg["proto_app_entry_rollout_top_k"],
        absolute_exposure_cap=cfg["proto_app_entry_rollout_max_exposures"],
        timeout=first["parameters"]["timeout"],
        retries=first["parameters"]["retries"],
        task_occurrence_gate_enabled=cfg["proto_task_occurrence_gate_enabled"],
        task_occurrence_prior_path=cfg["proto_task_occurrence_prior_path"],
        hourly_intention_mode="opportunity_v1",
        available_opportunities=p["available_opportunities"],
        current_intention=p["current_intention"],
        goal_review_due=p["goal_review_due"],
        max_defer_hours=p["max_defer_hours"],
    )


class ProbeProtocolError(LLMRunInterrupted):
    """Stop before another dispatch when an experiment invariant fails."""


class ExactReplay:
    def __init__(self, calls):
        self.calls = calls
        self.count = 0

    async def atext_request(self, *, dialog, **kwargs):
        if self.count >= len(self.calls):
            raise ProbeProtocolError("Unscheduled replay request")
        call = self.calls[self.count]
        if call["messages"] != dialog:
            raise ProbeProtocolError(f"Replay messages differ from archived call {self.count + 1}")
        if any(kwargs.get(k) != v for k, v in call["parameters"].items()):
            raise ProbeProtocolError("Request parameters changed")
        self.count += 1
        if "error_type" in call:
            raise LLMRunInterrupted(call["error_type"])
        return call["raw"]


async def decide(client, kwargs, version):
    try:
        result = await run_app_entry_rollout_hour(
            llm=client, **kwargs, phone_use_needs_version=version, paired_environment_seed=101
        )
    except ProbeProtocolError:
        raise
    except (ValueError, LLMRunInterrupted) as exc:
        return dict(activity="technical_failure", failure_type=type(exc).__name__, reason=str(exc))
    bundle = result.bundle
    bundle.validate()
    choice = USE if bundle.active else LEAVE
    if result.needs.phone_use_decision != choice or result.plan.intent["kind"] != (
        "habitual_app" if bundle.active else "no_app"
    ):
        raise ProbeProtocolError("Resolved phone use, accepted Plan and executed App bundle disagree")
    return dict(
        activity=choice,
        intent=result.plan.intent["kind"],
        bundle=bundle.to_dict(),
        resolution=result.needs.to_dict().get("phone_use_resolution"),
        reason=result.needs.reasoning,
    )


async def prepare(cases):
    events = archived_events(cases)
    cfg = json.loads((ARCHIVE / "resolved_config.json").read_bytes())["runtime"]
    (manifest,) = json.loads((ARCHIVE / f"exp_group_manifest_{ARCHIVE.name}.json").read_bytes())
    if (
        manifest["group_id"] != ARCHIVE.name
        or manifest["status"] != "ok"
        or cfg["proto_paired_environment_seed"] != 101
    ):
        raise ValueError("Source run, completion status or paired seed mismatch")
    stem = "as_" + str(UUID(manifest["exp_id"])).replace("-", "_")
    with closing(
        sqlite3.connect((ARCHIVE / "run_evidence.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        snaps = {
            a: json.loads(s)["proto_day4_replay_snapshot"]
            for a, s in db.execute(f"SELECT agent_id,status_json FROM {stem}_mvp_status WHERE day=3")
        }
    csv_rows = {}
    for prefix in ("app_entry_rollout_hourly", "app_entry_rollout_errors"):
        with (ARCHIVE / f"{prefix}_{ARCHIVE.name}.csv").open(encoding="utf-8-sig") as infile:
            for r in csv.DictReader(infile):
                k = slot(r)
                if k in csv_rows:
                    raise ValueError("Duplicate archived outcome")
                csv_rows[k] = r
    design = {}
    for case in cases:
        k = slot(case)
        rows = events[k]
        route = event(rows, "hourly_intention", "hourly_intention")
        kwargs = scenario(case, rows, snaps[k[0]], cfg)
        calls = []
        for r in rows:
            if r["kind"] == "request" and r["module"] in {"app_needs", "app_plan"}:
                resp = event(rows, r["module"], "response", call_id=r["call_id"])
                calls.append({**r, "raw": resp["raw"]})
        replay = ExactReplay(calls)
        previous = await decide(replay, kwargs, PHONE_USE_NEEDS_V3)
        anchor = csv_rows[k]
        if (
            anchor["device_id"] != str(case["device_id"])
            or anchor["group_id"] != ARCHIVE.name
            or int(anchor["uses_validation_data"]) != 0
        ):
            raise ValueError("Archived bundle came from a different device, run, or data split")
        archived = "technical_failure" if "active" not in anchor else USE if int(anchor["active"]) else LEAVE
        if (
            replay.count != len(calls)
            or previous["activity"] != archived
            or previous.get("intent") != route["executed_choice"]
        ):
            raise ValueError(f"Original behavior could not be reproduced at {k}")
        if archived != "technical_failure":
            b = previous["bundle"]
            if (
                b["active_event_app_exposures"] != int(anchor["active_event_app_exposures"])
                or b["app_context_counts"] != json.loads(anchor["app_context_counts_json"])
                or b["primary_context"] != anchor["primary_context"]
            ):
                raise ValueError("Original App bundle contents disagree with independent archive")
        design[case["case_id"]] = (kwargs, archived)
    return design


class CaptureFirst:
    async def atext_request(self, *, dialog, **parameters):
        self.messages = dialog
        self.parameters = parameters
        raise LLMRunInterrupted("frozen initial request")


async def freeze_initial(out, cases, design):
    expected = {}
    for c in cases:
        cid = c["case_id"]
        capture = CaptureFirst()
        await decide(capture, design[cid][0], PHONE_USE_NEEDS_V5)
        payload = request_payload({"messages": capture.messages})
        if payload["schema_version"] != PHONE_USE_NEEDS_V5 or payload["inputs"]["day1_3_habit"][
            "same_hour_active"
        ] != {"active": c["active_days"], "seen": 3}:
            raise ValueError("Wrong V5 initial request")
        check_pre_hour(payload["inputs"], c["talkingdata_day"], c["hour"])
        expected[cid] = sha(canonical({"messages": capture.messages, "parameters": capture.parameters}))
    path = out / "frozen_requests.json"
    if path.exists():
        if json.loads(path.read_bytes()) != expected:
            raise ValueError("V5 stimuli changed after freeze")
    else:
        write_json(path, expected)
    return expected


class LiveCase:
    def __init__(self, provider, case, signature, out):
        self.provider, self.case, self.signature = provider, case, signature
        self.calls = []
        self.log = out / f"{case['case_id']}.json"

    async def atext_request(self, *, dialog, **parameters):
        if len(self.calls) >= 4:
            raise ProbeProtocolError("Per-hour request cap exceeded")
        payload = request_payload({"messages": dialog})
        check_pre_hour(payload["inputs"], self.case["talkingdata_day"], self.case["hour"])
        row = dict(messages=dialog, parameters=parameters)
        if not self.calls and sha(canonical(row)) != self.signature:
            raise ProbeProtocolError("Live initial request differs from frozen stimulus")
        if "phone_use_resolution" in json.dumps(payload):
            raise ProbeProtocolError("Internal sampling details in live request")
        self.calls.append(row)
        write_json(self.log, self.calls)
        try:
            r = await self.provider.chat.completions.create(
                model=MODEL,
                messages=dialog,
                temperature=parameters["temperature"],
                timeout=parameters["timeout"],
                max_tokens=parameters["max_tokens"],
            )
        except Exception as err:
            row.update(error_type=type(err).__name__, http_status=getattr(err, "status_code", None))
            write_json(self.log, self.calls)
            if row["http_status"] in (401, 403, 429):
                raise ProbeProtocolError(f"Provider stopped experiment (HTTP {row['http_status']})") from None
            raise LLMRunInterrupted(row["error_type"]) from None
        if r.model != MODEL:
            raise ProbeProtocolError("Unexpected response model")
        row.update(
            raw=r.choices[0].message.content or "",
            model=r.model,
            response_id=r.id,
            tokens=r.usage.total_tokens if r.usage else None,
        )
        write_json(self.log, self.calls)
        return row["raw"]


async def online(out, cases, design, expected):
    import httpx
    from openai import AsyncOpenAI
    from run_hourly_strategy_factorial import archive_source

    if (out / "calls").exists():
        raise SystemExit("This directory already contains an online experiment")
    key = os.environ.get("ZHIPUAI_API_KEY") or getpass("智谱 API Key（输入隐藏）：").strip()
    if not key:
        raise SystemExit("Missing key")
    call_dir = out / "calls"
    call_dir.mkdir()
    source_hash = archive_source(out)
    write_json(
        out / "run.json",
        dict(
            source_sha256=source_hash,
            model=MODEL,
            cap=CAP,
            scheduled=len(cases),
            selection_sha256=digest(out / "selection.jsonl"),
            frozen_requests_sha256=digest(out / "frozen_requests.json"),
        ),
    )
    dispatches = []

    async def meter(request):
        body = json.loads(request.content)
        if (
            len(dispatches) >= CAP
            or request.method != "POST"
            or str(request.url) != ENDPOINT + "chat/completions"
            or body.get("model") != MODEL
        ):
            raise RuntimeError("Unscheduled request or request limit exceeded")
        dispatches.append(sha(canonical(body["messages"])))
        write_json(out / "dispatches.json", dispatches)

    gate = asyncio.Semaphore(3)
    async with httpx.AsyncClient(
        trust_env=False, follow_redirects=False, event_hooks={"request": [meter]}
    ) as http:
        async with AsyncOpenAI(
            api_key=key.strip(), base_url=ENDPOINT, max_retries=0, http_client=http
        ) as provider:

            async def one(c):
                async with gate:
                    cid = c["case_id"]
                    client = LiveCase(provider, c, expected[cid], call_dir)
                    result = await decide(client, design[cid][0], PHONE_USE_NEEDS_V5)
                    record = dict(case_id=cid, **result, requests=len(client.calls))
                    with (out / "decisions.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    print(cid, result["activity"], f"({len(client.calls)} calls)", flush=True)

            await asyncio.gather(*(one(c) for c in cases))
    print(f"完成 {len(cases)} 个时段，实际请求 {len(dispatches)} 次。", flush=True)


def matched_summary(rows, columns):
    valid = {USE, LEAVE}
    common = [r for r in rows if all(r[c] in valid for c in columns)]
    return {
        "scheduled": len(rows),
        "people": len({r["agent_id"] for r in rows}),
        "coverage": {c: dict(Counter(r[c] for r in rows)) for c in columns},
        "method_evaluable": {c: activity_scores(rows, c) for c in columns},
        "common_evaluable": {c: activity_scores(common, c) for c in columns},
    }


def compose_score(rows):
    methods = ("old_executed", "v5_executed", "history_majority", "neutral_same_draw")
    groups = {
        name: {
            str(v): matched_summary([r for r in rows if r[g] == v], methods)
            for v in sorted({r[g] for r in rows})
        }
        for name, g in (
            ("by_split", "split"),
            ("by_history", "active_days"),
            ("by_resident", "agent_id"),
            ("by_clock", "period"),
        )
    }
    resolved = [r for r in rows if r["adjusted_probability"] is not None]
    changed = [r for r in resolved if r["resolved_phone"] != r["neutral_same_draw"]]
    return {
        "design": "Previously unsampled frozen free hours of the same ten residents/week. Each starts from its old pre-hour state. Scores describe the selected strata; no continuous new trajectory.",
        "endpoint": "V5 and old systems are scored by whether the actual simulated bundle contained App activity. Missing bundles are technical failures.",
        "history_majority": "Use when at least two of the first three same-clock device hours recorded activity.",
        "neutral_same_draw": "Offline history-only decision using the same smoothed prior and same keyed draw, with all recommendations set to follow_habit. It does not call Plan.",
        "overall": matched_summary(rows, methods),
        **groups,
        "first_stated_recommendations": dict(Counter(r["first_recommendation"] for r in rows)),
        "accepted_recommendations": dict(Counter(r["accepted_recommendation"] for r in rows)),
        "resolution_changed_vs_neutral": len(changed),
        "changed_vs_neutral_with_executed_bundle": [
            r["case_id"] for r in changed if r["v5_executed"] in (USE, LEAVE)
        ],
        "mean_squared_probability_error": {
            "on_resolved_hours": len(resolved),
            **{
                k: sum((r[k] - r["observed_active"]) ** 2 for r in resolved) / len(resolved)
                if resolved
                else None
                for k in ("habit_prior", "adjusted_probability")
            },
        },
        "old_missing_cases": [r["case_id"] for r in rows if r["old_executed"] == "technical_failure"],
        "new_missing_cases": [r["case_id"] for r in rows if r["v5_executed"] == "technical_failure"],
    }


def diagnostic_old_panel(heldout):
    from analysis_free_phone_probe import check_reply

    study = json.loads((OLD_PANEL / "experiment_design.json").read_bytes())
    if (
        digest(OLD_PANEL / "selection.jsonl") != study["selection_sha256"]
        or digest(heldout) != study["heldout_sha256"]
    ):
        raise ValueError("Prior Needs panel or references changed")
    prompts = {(r["case_id"], r["arm"]): r["initial_sha256"] for r in study["schedule"]}
    previous = {}
    for r in lines(OLD_PANEL / "probe_decisions.jsonl"):
        pair = r["case_id"], r["arm"]
        if pair in previous:
            raise ValueError("Duplicate prior Needs result")
        _, previous[pair] = check_reply(r, prompts[pair], study["model"])
    obs = load_observations(heldout, (4, 5, 6, 7))
    comparisons = []
    for c in lines(OLD_PANEL / "selection.jsonl"):
        a, d, h = slot(c)
        observed = obs[(str(c["device_id"]), d, h)].count > 0
        row = dict(
            case_id=c["case_id"],
            agent_id=a,
            split=c["split"],
            observed_active=observed,
            history_majority=USE if c["active_days"] >= 2 else LEAVE,
        )
        rec = previous[c["case_id"], "new"]
        if rec in (USE, LEAVE):
            resolved = resolve_phone_use(
                same_hour_active={"active": c["active_days"], "seen": 3},
                recommendation=rec,
                agent_id=a,
                talkingdata_day=d,
                hour=h,
                paired_environment_seed=101,
            )
            replayed = resolved["final_choice"]
        else:
            replayed = "technical_failure"
        row.update(v4_accepted=rec, offline_resolved=replayed)
        comparisons.append(row)
    columns = ("v4_accepted", "offline_resolved", "history_majority")
    return dict(
        design="Diagnostic only: take historical V4 accepted Needs statements from the prior 32 hours, apply the new resolver offline. No V5 model replies, new Plan or newly executed bundles for these cases.",
        overall=matched_summary(comparisons, columns),
        by_split={
            v: matched_summary([r for r in comparisons if r["split"] == v], columns)
            for v in ("explore", "holdout")
        },
    )


async def score(out, cases, design):
    from proto.app_entry.needs import stated_phone_use_decision, sanitize_phone_needs
    from proto.app_entry.wire import parse_compact_reply

    runspec = json.loads((out / "run.json").read_bytes())
    frozen = json.loads((out / "frozen_requests.json").read_bytes())
    if (
        runspec["selection_sha256"] != digest(out / "selection.jsonl")
        or runspec["frozen_requests_sha256"] != digest(out / "frozen_requests.json")
        or runspec["source_sha256"] != digest(out / "experiment_source.zip")
        or runspec["model"] != MODEL
    ):
        raise ValueError("Online run identity or frozen inputs changed")
    records = lines(out / "decisions.jsonl")
    by_id = {r["case_id"]: r for r in records}
    if len(records) != len(cases) or set(by_id) != set(design):
        raise ValueError("Expected a recorded outcome, including technical failures, for every frozen slot")
    sent = []
    audited = []
    for case in cases:
        cid = case["case_id"]
        a, d, h = slot(case)
        calls = json.loads((out / "calls" / f"{cid}.json").read_bytes())
        if not 1 <= len(calls) <= 4 or any(
            not c.get("response_id") or c.get("model") != MODEL for c in calls if "error_type" not in c
        ):
            raise ValueError("Invalid request budget or missing provider response identity")
        if sha(canonical({k: calls[0][k] for k in ("messages", "parameters")})) != frozen[cid]:
            raise ValueError("Archived live request differs from frozen stimulus")
        replay = ExactReplay(calls)
        result = await decide(replay, design[cid][0], PHONE_USE_NEEDS_V5)
        if replay.count != len(calls) or {**result, "case_id": cid, "requests": len(calls)} != by_id[cid]:
            raise ValueError(f"V5 end-to-end replay differs at {cid}")
        sent.extend(sha(canonical(c["messages"])) for c in calls)
        staged = [(c, request_payload(c)) for c in calls]
        raw = calls[0].get("raw", "")
        first = stated_phone_use_decision(raw, allow_follow_habit=True) or "unmeasured"
        plan_calls = [(c, p) for c, p in staged if "digital_needs" in p]
        rec = "unmeasured"
        history = {"active": case["active_days"], "seen": 3}
        neutral = resolve_phone_use(
            same_hour_active=history,
            recommendation="follow_habit",
            agent_id=a,
            talkingdata_day=d,
            hour=h,
            paired_environment_seed=101,
        )
        resolution = {}
        if plan_calls or result.get("resolution"):
            needs_calls = [c for c, p in staged if p["schema_version"] == PHONE_USE_NEEDS_V5]
            parsed, _ = sanitize_phone_needs(parse_compact_reply(needs_calls[-1]["raw"]), PHONE_USE_NEEDS_V5)
            if parsed is None:
                raise ValueError("Plan started without valid Needs")
            rec = parsed["phone_use_decision"]
            resolution = resolve_phone_use(
                same_hour_active=history,
                recommendation=rec,
                agent_id=a,
                talkingdata_day=d,
                hour=h,
                paired_environment_seed=101,
            )
            if any(
                p["digital_needs"]["phone_use_decision"] != resolution["final_choice"] for c, p in plan_calls
            ):
                raise ValueError("Plan received the wrong resolved activity")
            if result["activity"] in (USE, LEAVE) and result["resolution"] != resolution:
                raise ValueError(
                    "Recorded resolver does not match the raw model recommendation and keyed draw"
                )
        row = {
            k: case[k]
            for k in ("case_id", "agent_id", "talkingdata_day", "hour", "active_days", "split", "period")
        }
        bundle = result.get("bundle", {})
        row.update(
            old_executed=design[cid][1],
            v5_executed=result["activity"],
            first_recommendation=first,
            accepted_recommendation=rec,
            resolved_phone=resolution.get("final_choice"),
            history_majority=USE if case["active_days"] >= 2 else LEAVE,
            neutral_same_draw=neutral["final_choice"],
            habit_prior=neutral["prior_use_probability"],
            sample_u=neutral["sample_u"],
            adjusted_probability=resolution.get("use_probability"),
            odds_multiplier=resolution.get("odds_multiplier"),
            opened_category=bundle.get("primary_context"),
            exposures=bundle.get("active_event_app_exposures"),
            requests=len(calls),
            failure=result.get("reason") if result["activity"] == "technical_failure" else None,
        )
        audited.append(row)
    dispatches = json.loads((out / "dispatches.json").read_bytes())
    if len(dispatches) > CAP or Counter(sent) != Counter(dispatches):
        raise ValueError("Metered HTTP dispatches disagree with per-case exchanges")
    # Only read device activity labels after every new outcome and source request has been independently reproduced.
    heldout = ARCHIVE / "inputs/heldout.csv"
    spec = json.loads((out / "selection_design.json").read_bytes())
    if digest(heldout) != spec["heldout_sha256"]:
        raise ValueError("Held-out reference changed")
    observations = load_observations(heldout, (4, 5, 6, 7))
    for c, r in zip(cases, audited):
        r["observed_active"] = observations[str(c["device_id"]), c["talkingdata_day"], c["hour"]].count > 0
    with (out / "scored_cases.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audited[0]))
        writer.writeheader()
        writer.writerows(audited)
    summary = compose_score(audited)
    summary.update(
        http_dispatches=len(dispatches),
        response_replay_verified=len(audited),
        probe_source_sha256=runspec["source_sha256"],
        scoring_script_sha256=digest(Path(__file__)),
        responses_sha256=digest(out / "decisions.jsonl"),
        heldout_sha256=digest(heldout),
    )
    write_json(out / "score.json", summary)
    write_json(out / "diagnostic_prior_32.json", diagnostic_old_panel(heldout))
    print(json.dumps(summary["overall"], ensure_ascii=False), flush=True)


async def main(args):
    os.umask(0o077)
    out = args.run_dir.resolve()
    cases = freeze(out)
    design = await prepare(cases)
    expected = await freeze_initial(out, cases, design)
    print(f"冻结 {len(cases)} 个新时段；旧版消息和执行结果、当天可见信息以及新版首条请求已核对。", flush=True)
    if args.online:
        await online(out, cases, design, expected)
    if args.score:
        await score(out, cases, design)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--score", action="store_true")
    asyncio.run(main(parser.parse_args()))
