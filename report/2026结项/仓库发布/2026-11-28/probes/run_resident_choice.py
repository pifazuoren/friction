# ruff: noqa: E402
# Load the experiment modules from this checkout after locating its root.
"""Re-ask four frozen pre-hour observations and two separate post-outcome review decisions."""

import argparse
import asyncio
from collections import defaultdict
import hashlib
import json
import os
from getpass import getpass
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from uuid import UUID

OUT: Path
ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "examples/digital_friction_mvp").is_dir()
)
EXAMPLE = ROOT / "examples/digital_friction_mvp"
sys.path.insert(0, str(EXAMPLE))
from check_hourly_channel_replay import RecordedReplies, event
from check_hourly_intention_run import request_payload
from check_stratified_needs_plan import check_pre_hour
from proto.app_entry import PHONE_USE_NEEDS_V3, RESIDENT_DECISION_PLAN_VERSION
from proto.app_entry.rollout import run_app_entry_rollout_hour
from proto.llm_trace import LLMRunInterrupted, traced_agent_tick, bind_trace_context
from proto.retry_review import choose_retry_review
from run_hourly_strategy_factorial import archive_source
from run_strategy_memory_pairs import ENDPOINT, MODEL, save_json

SOURCE: Path
HOURS = [(2, 4, 3), (10, 4, 0), (1, 4, 8), (1, 4, 9)]
RETRIES = [(8, 7, 2), (3, 5, 9)]
HTTP_CAP = 18


def load():
    slots = defaultdict(list)
    for p in (SOURCE / "trace").glob("llm-requests-*.jsonl"):
        for line in p.open():
            row = json.loads(line)
            key = row["agent_id"], row["talkingdata_day"], row["hour"]
            if key in HOURS or key in RETRIES:
                slots[key].append(row)
    return slots


def scenario(rows, key, db, stem, cfg):
    agent, day, hour = key
    old_needs = event(rows, "app_needs", "request", phase="initial")
    old_plan = event(rows, "app_plan", "request", phase="initial")
    n = request_payload(old_needs)["inputs"]
    p = request_payload(old_plan)["inputs"]
    check_pre_hour(n, day, hour)
    check_pre_hour(p, day, hour)
    (raw,) = db.execute(
        f"SELECT status_json FROM {stem}_mvp_status WHERE agent_id=? AND day=3",
        (agent,),
    ).fetchone()
    snap = json.loads(raw)["proto_day4_replay_snapshot"]
    psych = n["pre_hour_psychology"]
    return dict(
        agent_id=agent,
        simulation_day=day - 1,
        tick_seconds=hour * 3600 + 1,
        environment=n["environment_cues"],
        stable_profile=n["stable_profile"],
        device_id=f"profile-{agent}",
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
        timeout=old_plan["parameters"]["timeout"],
        retries=old_plan["parameters"]["retries"],
        task_occurrence_gate_enabled=cfg["proto_task_occurrence_gate_enabled"],
        task_occurrence_prior_path=str(ROOT / cfg["proto_task_occurrence_prior_path"]),
        hourly_intention_mode="opportunity_v1",
        available_opportunities=p["available_opportunities"],
        current_intention=p["current_intention"],
        goal_review_due=p["goal_review_due"],
        max_defer_hours=p["max_defer_hours"],
    )


def review_args(rows, key, db, stem):
    agent, day, hour = key
    row = event(rows, "hourly_intention", "goal_outcome")
    (db_row,) = db.execute(
        f"SELECT payload_json FROM {stem}_proto_attempt_rows WHERE agent_id=? AND day=? AND t=?",
        (agent, day - 1, hour * 3600 + 1),
    ).fetchone()
    stored = json.loads(db_row)
    assert (
        stored["episode_id"]
        == row["episode_id"]
        == row["goal_state_after"]["last_episode_ids"][-1]
    )
    assert stored["outcome"]["outcome_type"] == row["outcome_type"]
    ep = {
        k: row[k]
        for k in (
            "episode_id",
            "strategy_type",
            "outcome_type",
            "requested_support_style",
            "support_style",
            "proxy_completion_level",
        )
        if k in row
    }
    ep["help_used"] = stored["outcome"]["help_used"]
    return dict(
        goal=row["goal_state_after"],
        episode=ep,
        resident=stored["profile_summary"],
        sim_hour=(day - 1) * 24 + hour,
        max_defer_hours=24,
        timeout=60,
    )


class Client:
    def __init__(self, client):
        self.client = client
        self.configs = [SimpleNamespace(model=MODEL)]
        self.case = None
        self.sent = []

    async def meter(self, request):
        if (
            len(self.sent) >= HTTP_CAP
            or request.method != "POST"
            or str(request.url) != ENDPOINT + "chat/completions"
        ):
            raise LLMRunInterrupted("request limit or destination mismatch")
        body = json.loads(request.content)
        assert body["model"] == MODEL
        self.sent.append(dict(case=self.case, model=MODEL))

    async def atext_request(
        self, *, dialog, temperature, max_tokens, timeout, **kwargs
    ):
        if len(self.sent) >= HTTP_CAP:
            raise LLMRunInterrupted("pilot request limit reached before dispatch")
        try:
            r = await self.client.chat.completions.create(
                model=MODEL,
                messages=dialog,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as err:
            raise LLMRunInterrupted("provider error " + type(err).__name__) from None
        assert r.model == MODEL
        self.sent[-1].update(
            response_id=r.id, tokens=r.usage.total_tokens if r.usage else None
        )
        save_json(OUT / "requests.json", self.sent)
        return r.choices[0].message.content or ""


@traced_agent_tick
async def probe(client, key, args, is_retry):
    a, d, h = key
    client.case = list(key)
    bind_trace_context(
        agent_id=a,
        simulation_day=d - 1,
        talkingdata_day=d,
        hour=h,
        tick_seconds=h * 3600 + 1,
        world="baseline_low_friction",
        purpose="frozen_week_choice_smoke",
    )
    if is_retry:
        result = await choose_retry_review(llm=client, **args)
        return dict(
            slot=key,
            kind="review",
            prior_outcome=args["episode"]["outcome_type"],
            **result,
        )
    result = await run_app_entry_rollout_hour(
        llm=client,
        phone_use_needs_version=PHONE_USE_NEEDS_V3,
        **{**args, "plan_prompt_version": RESIDENT_DECISION_PLAN_VERSION},
    )
    return dict(
        slot=key,
        kind="hour",
        phone=result.needs.phone_use_decision,
        choice=result.plan.intent["kind"],
        channel=result.bundle.primary_context,
        needs_reason=result.needs.reasoning,
        plan_reason=result.plan.intent["reason"],
    )


async def verify_saved(folder, cases):
    info = json.loads((folder / "design.json").read_text())
    if info["source"] != SOURCE.name or info["model"] != MODEL:
        raise ValueError("Incorrect source run or served model")
    events = defaultdict(list)
    for path in (folder / "trace").glob("llm-requests-*.jsonl"):
        for line in path.read_text().splitlines():
            r = json.loads(line)
            events[r["agent_id"], r["talkingdata_day"], r["hour"]].append(r)
    stored = json.loads((folder / "results.json").read_text())
    outcomes = {tuple(row["slot"]): row for row in stored}
    if (
        len(outcomes) != len(stored)
        or set(outcomes) != set(cases)
        or set(events) != set(cases)
    ):
        raise ValueError("Incomplete or duplicated six-point results")
    http = json.loads((folder / "requests.json").read_text())
    if len(http) > HTTP_CAP or any(
        item["model"] != MODEL or not item["response_id"] for item in http
    ):
        raise ValueError("Invalid archived model or HTTP response")
    at = 0
    for key, args in cases.items():
        rows = events[key]
        requests = [r for r in rows if r["kind"] == "request"]
        replies = [
            event(rows, r["module"], "response", call_id=r["call_id"])["raw"]
            for r in requests
        ]
        replay = RecordedReplies(replies)
        result = await probe(replay, key, args, key in RETRIES)
        if json.loads(json.dumps(result)) != outcomes[key]:
            raise ValueError(f"Action or reason differs for {key}")
        if [r["messages"] for r in requests] != [
            r["messages"] for r in replay.requests
        ]:
            raise ValueError(f"Prompt differs for {key}")
        if any(tuple(r["case"]) != key for r in http[at : at + len(requests)]):
            raise ValueError(f"HTTP case differs at {key}")
        at += len(requests)
    if at != len(http):
        raise ValueError("Incomplete HTTP evidence")
    print(f"Reproduced {len(cases)} results from {at} archived requests.")


async def main(online, verify):
    os.umask(0o077)
    os.environ.pop("PROTO_LLM_TRACE_DIR", None)
    cfg = json.loads((SOURCE / "resolved_config.json").read_text())["runtime"]
    (manifest,) = json.loads(
        (SOURCE / f"exp_group_manifest_{SOURCE.name}.json").read_text()
    )
    stem = "as_" + str(UUID(manifest["exp_id"])).replace("-", "_")
    slots = load()
    cases = {}
    with sqlite3.connect(
        (SOURCE / "run_evidence.sqlite").resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        for key in HOURS:
            rows = slots[key]
            kw = scenario(rows, key, db, stem, cfg)
            calls = [
                r
                for r in rows
                if r["module"] in {"app_needs", "app_plan"} and r["kind"] == "request"
            ]
            replay = RecordedReplies(
                [
                    next(
                        r["raw"]
                        for r in rows
                        if r["kind"] == "response" and r["call_id"] == c["call_id"]
                    )
                    for c in calls
                ]
            )
            old = await run_app_entry_rollout_hour(llm=replay, **kw)
            assert [c["messages"] for c in calls] == [
                c["messages"] for c in replay.requests
            ], key
            assert (
                old.plan.intent["kind"]
                == event(rows, "hourly_intention", "hourly_intention")[
                    "executed_choice"
                ]
            )
            cases[key] = kw
            print(
                key,
                "old prompt and choice verified",
                old.plan.intent["kind"],
                flush=True,
            )
        for key in RETRIES:
            cases[key] = review_args(slots[key], key, db, stem)
    if verify:
        await verify_saved(verify, cases)
    if not online:
        return
    import httpx
    from openai import AsyncOpenAI

    OUT.mkdir(parents=True, exist_ok=False)
    code_sha = archive_source(OUT)
    os.environ.update(
        PARALLEL_GROUP_NAME=OUT.name,
        PROTO_LLM_TRACE_DIR=str(OUT / "trace"),
        PROTO_RUN_SOURCE_SHA256=code_sha,
        PROTO_HOURLY_INTENTION_MODE="opportunity_v1",
        PROTO_APP_ENTRY_PLAN_PROMPT_VERSION=RESIDENT_DECISION_PLAN_VERSION,
    )
    save_json(
        OUT / "design.json",
        dict(
            source=SOURCE.name,
            hours=HOURS,
            post_outcome_retries=RETRIES,
            limit=HTTP_CAP,
            model=MODEL,
            source_sha256=code_sha,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    key = getpass("智谱 API Key（输入隐藏）：").strip()
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        async with AsyncOpenAI(
            api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
        ) as provider:
            client = Client(provider)
            http.event_hooks["request"].append(client.meter)
            results = []
            for case, kw in cases.items():
                try:
                    result = await probe(client, case, kw, case in RETRIES)
                except ValueError as exc:
                    result = dict(slot=case, error=str(exc))
                results.append(result)
                save_json(OUT / "results.json", results)
                print(
                    case,
                    result.get("choice", result.get("status", result.get("error"))),
                    flush=True,
                )
    print("requests", len(client.sent), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="First seven-day run with snapshots, SQLite and trace",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--online",
        action="store_true",
        help="Obtain new responses after verifying the old prompts",
    )
    actions.add_argument(
        "--verify-run",
        type=Path,
        help="Verify the original six results using saved responses",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="A new private directory, required only with --online",
    )
    opts = parser.parse_args()
    if bool(opts.output_dir) != opts.online:
        parser.error("Specify --output-dir only together with --online")
    SOURCE = opts.source.resolve()
    if opts.output_dir:
        OUT = opts.output_dir.resolve()
    asyncio.run(main(opts.online, opts.verify_run))
