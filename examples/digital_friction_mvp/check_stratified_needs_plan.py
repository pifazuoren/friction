"""Offline check of current Needs and Plan contracts on all ten residents' archived hours."""

import argparse
import asyncio
from collections import Counter, defaultdict
from itertools import product
import json
from pathlib import Path

from check_daily_channel_choices import load_archive, reexpress_valid
from check_hourly_channel_replay import (
    RecordedReplies,
    event,
    rebuild_plan_kwargs,
    require,
)
from check_hourly_intention_run import check_plan_calls, request_payload
from proto.app_entry.candidate import build_rollout_app_context_candidates
from proto.app_entry.intention_contract import (
    COMPACT_PLAN_V4,
    COMPACT_PLAN_V7,
    COMPACT_PLAN_V8,
    COMPACT_PLAN_VERSION,
    compact_needs,
    parse_compact_reply,
)
from proto.app_entry.needs import (
    COMPACT_NEEDS_PROMPT_VERSION,
    DIGITAL_NEED_TO_APP_CONTEXTS,
    DigitalNeedsBlock,
)
from proto.app_entry.planner import DigitalAppEntryPlanBlock, decode_compact_plan
from proto.app_entry.rollout import (
    _assert_no_forbidden_evidence,
    _with_plan_opportunities,
)
from proto.app_entry.types import AUDIT_ONLY_APP_CONTEXTS
from proto.hourly_intention import IntentionLedger
from proto.memory.packet import is_prior_episode
from proto.runtime import scheduled_login_for_day
from run_hourly_strategy_factorial import experiment_environment
from run_strategy_memory_pairs import save_json


DAYTIME_INACTIVE = ("day_06_21", "inactive_0_of_3")
PILOT_PLAN_SCHEMAS = {COMPACT_PLAN_V7, COMPACT_PLAN_V8}


def stratum(observation):
    hour = observation["hour"]
    activity = observation["day1_3_habit"]["same_hour_active"]
    require(
        activity["seen"] == 3 and 0 <= activity["active"] <= 3,
        "Incomplete three-day clock-hour history",
    )
    active = activity["active"]
    goal = observation["current_intention"]
    actionable = (
        observation["goal_review_due"]
        if goal
        else bool(observation["available_opportunities"])
    )
    return (
        "day_06_21" if 6 <= hour < 22 else "night_22_05",
        ["inactive_0_of_3", "mixed_1_or_2_of_3", "mixed_1_or_2_of_3", "active_3_of_3"][
            active
        ],
        "task" if actionable else "no_task",
    )


def check_pre_hour(packet, day, hour):
    _assert_no_forbidden_evidence(packet)
    require(
        (packet["talkingdata_day"], packet["simulation_day"], packet["hour"])
        == (day, day - 1, hour),
        "Archived observations disagree with clock",
    )
    for row in packet["recent_simulated_bundles"]:
        require(
            (row["talkingdata_day"], row["hour"]) < (day, hour),
            "Current/future app activity in input",
        )
    for episode in packet["recent_task_episodes"]:
        require(
            "day" in episode and is_prior_episode(episode, day - 1, hour * 3600),
            "Current, future or undated task result in input",
        )
    now = (day - 1) * 24 + hour
    for offer in packet.get("available_opportunities", []):
        require(
            offer["visible_from_sim_hour"] <= now
            and offer["offered_at_sim_hour"] <= now,
            "Opportunity not visible at this hour",
        )


def plan_candidates(packet, needs, top_k):
    hour, hist = packet["hour"], packet["day1_3_habit"]
    return build_rollout_app_context_candidates(
        habit_memory={
            "context_by_hour": {str(hour): hist["same_hour_context_counts"]},
            "context_total_counts": hist["overall_context_counts"],
        },
        hour=hour,
        need_pressures=needs.need_pressures,
        need_context_mapping=DIGITAL_NEED_TO_APP_CONTEXTS,
        top_k=top_k,
        allow_empty=True,
        actionable_only=True,
    )


async def check_plan_fixtures(kwargs):
    """Exercise no phone and a single selected opening with the same visible menu."""
    scores = {
        "additional_apps": [],
        "reason": "Offline contract fixture.",
        "confidence": 1,
        "attitude": 0.5,
        "subjective_norm": 0.5,
        "perceived_control": 0.5,
    }
    probe = RecordedReplies([json.dumps({**scores, "action": "no_app"})])
    plan = await DigitalAppEntryPlanBlock().forward(llm=probe, **kwargs)
    require(
        plan.intent["kind"] == "no_app"
        and not plan.active
        and not plan.app_context_counts,
        "Valid no-phone decision was lost",
    )
    request = probe.requests[0]
    body = request_payload(request)
    channel = next(c for c in body["channels"] if c not in AUDIT_ONLY_APP_CONTEXTS)
    action = f"habitual_app@open:{channel}"
    require(action in body["actions"], "Missing daily App action")
    probe = RecordedReplies([json.dumps({**scores, "action": action})])
    opening = await DigitalAppEntryPlanBlock().forward(llm=probe, **kwargs)
    packet = kwargs["input_payload"]
    bundle = opening.to_bundle(
        device_id="offline", day=packet["talkingdata_day"], hour=packet["hour"]
    )
    require(
        probe.requests == [request]
        and opening.intent["kind"] == "habitual_app"
        and bundle.active
        and bundle.active_event_app_exposures == 1
        and bundle.app_context_counts == {channel: 1},
        "Daily App decision did not preserve its selected opening",
    )
    return request


async def check_hour(slot, rows, top_k, *, plan_schema=COMPACT_PLAN_VERSION):
    day, hour, rank = slot
    source = event(rows, "app_needs", "request", phase="initial")
    packet = request_payload(source)["inputs"]
    check_pre_hour(packet, day, hour)
    replies = [
        event(rows, "app_needs", "response", phase=p)["raw"]
        for p in ("initial", "repair")
    ]
    replay = RecordedReplies(replies)
    needs = await DigitalNeedsBlock().forward(
        llm=replay,
        input_payload=packet,
        prompt_version=COMPACT_NEEDS_PROMPT_VERSION,
        timeout=source["parameters"]["timeout"],
        retries=source["parameters"]["retries"],
    )
    # Replaying the old echo must still require correction; it supplies no fresh behavioral evidence.
    require(
        needs.audit["parse_status"] == "ok_repaired" and len(replay.requests) == 2,
        "Archived Needs echo was adopted or its valid correction lost",
    )
    require(
        all(request_payload(r) == {"inputs": packet} for r in replay.requests),
        "Needs evidence changed",
    )
    route = event(rows, "hourly_intention", "hourly_intention")
    check_plan_calls(rows, route)
    old = request_payload(event(rows, "app_plan", "request", phase="initial"))
    kwargs = rebuild_plan_kwargs(rows, expected_version=COMPACT_PLAN_V4)
    check_pre_hour(kwargs["input_payload"], day, hour)
    require(
        kwargs["needs"].to_dict(include_audit=False)
        == needs.to_dict(include_audit=False),
        "Accepted Needs changed during replay",
    )
    request = await check_plan_fixtures(
        {
            **kwargs,
            "compact_schema_version": plan_schema,
            "candidate_contexts": plan_candidates(packet, needs, top_k),
            "needs": needs,
        }
    )
    body = request_payload(request)
    require(
        body["schema_version"] == plan_schema
        and body["inputs"] == old["inputs"]
        and body["digital_needs"] == compact_needs(needs.to_dict(include_audit=False), plan_schema),
        "Plan observation, history or forwarded Needs differ from source",
    )
    require(
        not AUDIT_ONLY_APP_CONTEXTS.intersection(body["channels"])
        and all(
            not any(token.endswith("@open:" + c) for c in AUDIT_ONLY_APP_CONTEXTS)
            for token in body["actions"]
        ),
        "Audit category offered as an action",
    )
    status = "archived_plan_technical_failure"
    if route.get("accepted_choice") is not None:
        phase = "repair" if route["repair_count"] else "initial"
        raw = parse_compact_reply(
            event(rows, "app_plan", "response", phase=phase)["raw"]
        )
        original = decode_compact_plan(raw, old)
        if AUDIT_ONLY_APP_CONTEXTS.intersection(original["app_context_counts"]):
            status = "archived_valid_includes_audit_category"
        else:
            require(
                decode_compact_plan(reexpress_valid(raw, old), body) == original,
                f"An ordinary valid decision changed at {slot}",
            )
            status = (
                "archived_no_app_preserved"
                if raw["action"] == "no_app"
                else "archived_other_valid_preserved"
            )
    return (
        stratum(kwargs["input_payload"]),
        status,
        {
            "origin": "archived",
            "day": day,
            "hour": hour,
            "rank": rank,
            "source_needs_call_id": source["call_id"],
            "needs": replay.requests[0],
            "plan_given_archived_needs": request,
        },
    )


def with_daytime_login(needs_packet, original, agent_id):
    """Add a visible login to a quiet archived hour using the production task and menu builders."""
    require(
        stratum(original) == DAYTIME_INACTIVE + ("no_task",)
        and original["current_intention"] is None
        and not original["available_opportunities"],
        "Constructed fixture needs a daytime historically inactive hour with no competing goal or offer",
    )
    day, hour = needs_packet["simulation_day"], needs_packet["hour"]
    check_pre_hour(needs_packet, day + 1, hour)
    check_pre_hour(original, day + 1, hour)
    require(
        original["monotonic_sim_hour"] == day * 24 + hour
        and all(original[k] == v for k, v in needs_packet.items()),
        "Archived base and Plan observations do not match",
    )
    task = scheduled_login_for_day(
        hour=hour,
        agent_id=agent_id,
        day=day,
        tick_seconds=hour * 3600 + 1,
        env=needs_packet["environment_cues"],
        existing_task=None,
        last_scheduled_day=-1,
    )
    require(task is not None, "Controlled login did not materialize")
    ledger = IntentionLedger()
    offer = ledger.publish(
        task, source="scheduled_login", sim_hour=original["monotonic_sim_hour"]
    )
    packet = _with_plan_opportunities(
        needs_packet,
        "opportunity_v1",
        [offer],
        None,
        original["goal_review_due"],
        original["max_defer_hours"],
        needs_packet["recent_task_episodes"],
    )
    check_pre_hour(packet, day + 1, hour)
    require(
        stratum(packet) == DAYTIME_INACTIVE + ("task",),
        "Constructed fixture missed its stratum",
    )
    return packet


async def check_archive(folder, *, plan_schema=COMPACT_PLAN_VERSION):
    require(plan_schema in PILOT_PLAN_SCHEMAS, "Unsupported stratified pilot Plan schema")
    slots, source = load_archive(folder)
    top_k = json.loads((folder / "resolved_config.json").read_text())["runtime"][
        "proto_app_entry_rollout_top_k"
    ]
    strata = defaultdict(Counter)
    representatives = {}
    for slot, rows in sorted(slots.items()):
        category, status, stimulus = await check_hour(slot, rows, top_k, plan_schema=plan_schema)
        strata[category][status] += 1
        # Selection uses only the visible stratum and clock/rank, independent of either reply.
        distance = abs(stimulus["hour"] - (12 if category[0] == "day_06_21" else 3))
        tie_break = (min(distance, 24 - distance), slot)
        if category not in representatives or tie_break < representatives[category][0]:
            representatives[category] = tie_break, stimulus
    table = []
    for cell in product(
        ("day_06_21", "night_22_05"),
        ("inactive_0_of_3", "mixed_1_or_2_of_3", "active_3_of_3"),
        ("no_task", "task"),
    ):
        statuses = strata[cell]
        table.append({"stratum": list(cell), "hours": statuses.total(), **statuses})
    prompts = [{"stratum": list(k), **v[1]} for k, v in sorted(representatives.items())]
    missing = DAYTIME_INACTIVE + ("task",)
    baseline = DAYTIME_INACTIVE + ("no_task",)
    if missing not in representatives and baseline in representatives:
        _, anchor = representatives[baseline]
        slot = (anchor["day"], anchor["hour"], anchor["rank"])
        rows = slots[slot]
        source_request = event(rows, "app_needs", "request", phase="initial")
        needs_packet = request_payload(anchor["needs"])["inputs"]
        kwargs = rebuild_plan_kwargs(rows, expected_version=COMPACT_PLAN_V4)
        constructed = with_daytime_login(
            needs_packet, kwargs["input_payload"], source_request["agent_id"]
        )
        request = await check_plan_fixtures(
            {
                **kwargs,
                "compact_schema_version": plan_schema,
                "input_payload": constructed,
                "candidate_contexts": plan_candidates(
                    needs_packet, kwargs["needs"], top_k
                ),
            }
        )
        prompts.append(
            {
                **anchor,
                "stratum": list(missing),
                "origin": "constructed",
                "source_stratum": list(baseline),
                "intervention": "Offer a scheduled login at the archived hour. Needs and prior history come from the source hour.",
                "plan_given_archived_needs": request,
            }
        )
    report = {
        "source": source,
        "hours": len(slots),
        "new_model_requests": 0,
        "needs_prompt": COMPACT_NEEDS_PROMPT_VERSION,
        "plan_schema": plan_schema,
        "archived_needs_echoes_rejected": len(slots),
        "archived_needs_corrections_reaccepted": len(slots),
        "no_app_contract_fixtures_accepted": len(slots),
        "daily_app_bundle_fixtures_accepted": len(slots),
        "archived_strata": len(representatives),
        "constructed_strata": [
            p["stratum"] for p in prompts if p["origin"] == "constructed"
        ],
        "strata_with_contract_fixtures": len(prompts),
        "scope": "Counts of archived hours exclude constructed prompts. No-phone and daily App replies are offline contract fixtures. No fresh behavioral rates.",
        "strata": table,
    }
    return report, prompts


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path)
    cli.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New directory for local summary and representative prompts",
    )
    args = cli.parse_args()
    with experiment_environment({"PROTO_LLM_TRACE_DIR": None}):
        report, prompts = asyncio.run(check_archive(args.archive))
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    save_json(args.output_dir / "summary.json", report)
    save_json(args.output_dir / "stimuli.json", prompts)
    print(
        f"{report['hours']} archived person-hours in {report['archived_strata']} strata; "
        f"{len(prompts)} strata with offline fixtures, 0 online requests. {args.output_dir}"
    )


if __name__ == "__main__":
    main()
