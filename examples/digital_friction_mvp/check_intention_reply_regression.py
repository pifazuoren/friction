"""Replay a failed paired Plan run through today's planner entirely offline."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

from proto.app_entry.candidate import build_rollout_app_context_candidates
from proto.app_entry.habit_memory import build_rollout_intensity_profile
from proto.app_entry.intention_contract import compact_needs, compact_observation, include_required_channels
from proto.app_entry.needs import DIGITAL_NEEDS_OUTPUT_KEYS, DIGITAL_NEED_TO_APP_CONTEXTS, DigitalNeedsResult
from proto.app_entry.planner import DigitalAppEntryPlanBlock, HourlyIntentionPlanError
from proto.app_entry.rollout import build_rollout_input_packet


class ArchiveError(ValueError):
    """The historical run lacks coherent evidence or a current regression assertion failed."""


def require(condition, message):
    if not condition:
        raise ArchiveError(message)


def json_lines(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def identity(row):
    return row["pair_id"], row["member"]


def indexed_members(rows):
    indexed = {}
    for row in rows:
        if row["mode"] != "opportunity_v1":
            continue
        key = identity(row)
        require(key not in indexed, f"Duplicate opportunity decision {key}")
        indexed[key] = row
    return indexed


def replay_members(folder, expected):
    """A legacy trace used 'kind' for the pair type; identify transport events from payloads and IDs."""
    manifest = indexed_members(json.loads((folder / "request_manifest.json").read_text()))
    decisions = indexed_members(json_lines(folder / "decisions.jsonl"))
    stimuli = json.loads((folder / "stimuli.json").read_text())["opportunity_v1"]
    report = json.loads((folder / "summary.json").read_text())
    if report.get("purpose") == "plan_schema_smoke":
        summary_counts = (report["expected_decisions"], report["recorded_decisions"],
                          report["final_valid_decisions"], report["technical_failures"])
        require(report["http_requests_dispatched"] == 2 * expected and report["adopted_initial"] == 0,
                "Missing historical smoke attempts")
    else:
        summary = report["conditions"]["opportunity_v1"]
        summary_counts = (summary["planned"], summary["recorded"], summary["valid"], summary["technical_failures"])
    require(summary_counts == (expected, expected, 0, expected), "Archived summary does not describe the failed roster")
    design = json.loads((folder / "design.json").read_text())
    require(
        design["source_archive_sha256"]
        == sha256((folder / "experiment_source.zip").read_bytes()).hexdigest(),
        "Archived source hash differs from design.json",
    )
    require(
        len(manifest) == expected and manifest.keys() == decisions.keys(),
        "Incomplete or inconsistent decision roster",
    )
    calls = defaultdict(lambda: defaultdict(list))
    for path in sorted((folder / "trace").glob("*.jsonl")):
        for row in json_lines(path):
            if (
                row.get("module") != "app_plan"
                or row.get("mode") != "opportunity_v1"
                or "call_id" not in row
            ):
                continue
            key = identity(row)
            require(
                key in manifest and row["condition"] == manifest[key]["condition"],
                f"Unexpected trace member {key}",
            )
            calls[key][row["phase"]].append(row)
    require(calls.keys() == manifest.keys(), "Missing Plan transport evidence")
    seen_calls, seen_queries = set(), set()
    for key, decision in decisions.items():
        require(
            not decision["plan_valid"]
            and decision["technical_failure"]
            and not decision["task_admitted"]
            and decision["choice_source"] == "technical_failure"
            and decision["policy_choice"] is None
            and decision["condition"] == manifest[key]["condition"]
            and decision["repairs"] == 1
            and decision["requests"] == 2
            and not decision["transport_errors"],
            f"{key} was not a complete two-response technical failure",
        )
        phases = calls[key]
        require(set(phases) == {"initial", "repair"}, f"Missing initial/repair pair {key}")
        payloads, queries = {}, set()
        for phase, group in phases.items():
            ids = {r["call_id"] for r in group}
            require(
                len(ids) == 1 and not ids.intersection(seen_calls),
                f"Mismatched/duplicate call ID {key}/{phase}",
            )
            seen_calls.update(ids)
            queries.update(r["query_id"] for r in group)
            requests = [r for r in group if "messages" in r]
            responses = [r for r in group if "raw" in r]
            parsed = [r for r in group if "parsed" in r]
            require(len(requests) == len(responses) == len(parsed) == 1, f"Incomplete call {key}/{phase}")
            require(
                parsed[0]["status"] not in {"ok", "ok_repaired"} and parsed[0]["parsed"] is None,
                f"Unexpected archived parse success {key}/{phase}",
            )
            require(isinstance(responses[0]["raw"], str), f"Missing response text {key}/{phase}")
            payloads[phase] = responses[0]["raw"]
            if phase == "initial":
                request = requests[0]["messages"]
                require(
                    request == stimuli[manifest[key]["condition"]]["messages"],
                    f"Initial messages changed {key}",
                )
                payloads["context"] = json.loads(request[1]["content"].split("\n", 1)[1])
        require(
            len(queries) == 1 and not queries.intersection(seen_queries),
            f"Duplicate or unrelated query {key}",
        )
        seen_queries.update(queries)
        for phase, field in (
            ("initial", "last_raw_response_hash"),
            ("repair", "last_repair_response_hash"),
        ):
            digest = sha256(payloads[phase].encode("utf-8")).hexdigest()[:16]
            require(
                f"{field}={digest}" in decision["technical_failure"],
                f"Response/decision digest mismatch {key}/{phase}",
            )
        yield key, payloads


class RecordedReplies:
    def __init__(self, initial, repaired):
        self.replies = (initial, repaired)
        self.calls = 0

    async def atext_request(self, **kwargs):
        self.calls += 1
        if self.calls > 2:
            raise AssertionError("Offline replay exceeded one initial response and one repair")
        return self.replies[self.calls - 1]


def expand_smoke_context(context, shared):
    """Rebuild pre-serialization inputs from the archived snapshot and verify against the actual v2 HTTP body."""
    observed, needs = context["inputs"], shared["fixed_needs"]
    hour, habits = observed["hour"], shared["history"]["habits"]
    intensity = build_rollout_intensity_profile(habits, hour=hour, absolute_cap=12)
    require(intensity["active_exposure_cap"] == context["exposure_cap"], "Archived replay cap disagrees")
    require(compact_needs(needs, context["schema_version"]) == context["digital_needs"], "Archived fixed Needs disagree")
    require(observed["available_opportunities"] == [shared["opportunity"]], "Archived visible opportunity differs")
    psychology = observed["pre_hour_psychology"]
    packet = build_rollout_input_packet(
        simulation_day=observed["simulation_day"], talkingdata_day=observed["talkingdata_day"],
        hour=hour, stable_profile=shared["profile"], habit_memory=habits,
        recent_rollout_rows=observed["recent_simulated_bundles"], recent_task_episodes=observed["recent_task_episodes"],
        latest_reflection=observed["latest_reflection"], helplessness=psychology["helplessness"],
        trust=psychology["trust_in_apps"], avoidance=psychology["avoidance_tendency"],
        environment=observed["environment_cues"], intensity_profile=intensity, hourly_intention_mode="opportunity_v1",
        available_opportunities=observed["available_opportunities"], current_intention=observed["current_intention"],
        goal_review_due=observed["goal_review_due"], max_defer_hours=observed["max_defer_hours"],
    )
    require(compact_observation(packet) == observed, "Archived observation cannot be reconstructed")
    candidates = build_rollout_app_context_candidates(
        habit_memory=habits, hour=hour, need_pressures=needs["need_pressures"],
        need_context_mapping=DIGITAL_NEED_TO_APP_CONTEXTS, top_k=5,
    )
    require(set(include_required_channels(candidates, packet)) == set(context["channels"]), "Archived channels differ")
    return {"inputs": packet, "digital_needs": needs, "intensity_profile": intensity, "prompt_version": "app_entry_plan_v3",
            "candidate_app_contexts": candidates, "runtime_output_constraints": {"minimum_confidence": context["minimum_confidence"]}}


async def current_validation(context, first, second):
    """Use the archived observation, positive priors and settings at the real Plan entry point."""
    transport = RecordedReplies(first, second)
    needs = DigitalNeedsResult.from_sanitized(
        {k: context["digital_needs"][k] for k in DIGITAL_NEEDS_OUTPUT_KEYS}
    )
    candidates = {k: w for k, w in context["candidate_app_contexts"].items() if w > 0}
    try:
        result = await DigitalAppEntryPlanBlock().forward(
            llm=transport,
            needs=needs,
            candidate_contexts=candidates,
            input_payload=deepcopy(context["inputs"]),
            intensity_profile=context["intensity_profile"],
            prompt_version=context["prompt_version"],
            min_confidence=context["runtime_output_constraints"]["minimum_confidence"],
            retries=0,
            json_attempts=1,
        )
    except HourlyIntentionPlanError as exc:
        require(
            exc.audit.get("accepted_choice") is None and exc.audit.get("technical_failure"),
            "A rejected response retained an accepted action",
        )
        result = None
    require(1 <= transport.calls <= 2, "Planner did not validate the supplied response(s)")
    return result


def strict_recorded_json(raw):
    lines = raw.strip().splitlines()
    if lines and lines[0].lower() in {"```json", "```"} and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return json.loads("\n".join(lines))


def observed_faults(context, initial, repaired):
    constraints = context["runtime_output_constraints"]
    (offer,) = context["inputs"]["available_opportunities"]
    counts = repaired["app_context_counts"]
    require(
        all(type(n) is int and n >= 0 for n in counts.values()), "Recorded repair has invalid count types"
    )
    require(
        '"inputs"' in initial and '"intent"' not in initial,
        "Archived initial response did not echo the observation as expected",
    )
    require(
        repaired["intent"]["kind"] == "engage_goal"
        and repaired["intent"]["opportunity_id"] == offer["opportunity_id"],
        "Repair did not name the observed goal",
    )
    require(
        sum(counts.values()) > constraints["active_exposure_maximum"],
        "Archived repair did not exceed its own exposure cap",
    )
    require(
        counts.get(offer["required_channel"], 0) == 0,
        "Archived repair actually used the required service channel",
    )
    return sum(counts.values()), constraints["active_exposure_maximum"], offer


async def check_archive(folder, expected=None):
    totals, caps, null_reviews = Counter(), Counter(), Counter()
    smoke = json.loads((folder / "summary.json").read_text()).get("purpose") == "plan_schema_smoke"
    if expected is None:
        expected = 2 if smoke else 26
    shared = json.loads((folder / "shared_input.json").read_text()) if smoke else None
    count = 0
    for key, evidence in replay_members(folder, expected):
        context, first, second = (evidence[name] for name in ("context", "initial", "repair"))
        if smoke:
            old_response = strict_recorded_json(first)
            require(context["schema_version"] == "hourly_plan_compact_v2", "Expected a historical v2 smoke")
            require(strict_recorded_json(second) == old_response, "Archived repair changed the malformed response")
            offer, = context["inputs"]["available_opportunities"]
            require(old_response.get("action") == f"defer_goal:opportunity:{offer['opportunity_id']}"
                    and "review" in old_response and old_response["review"] in (None, {"review": None}),
                    "Expected a historical deferral with no selected review hour")
            null_reviews["null" if old_response["review"] is None else "nested_null"] += 1
            cap = context["exposure_cap"]
            context = expand_smoke_context(context, shared)
        else:
            total, cap, offer = observed_faults(context, first, strict_recorded_json(second))
            totals[total] += 1
        caps[cap] += 1
        for variant, replies in (("original pair", (first, second)), ("isolated repair", (second, second))):
            accepted = await current_validation(context, *replies)
            require(accepted is None, f"Current planner accepted archived {variant} for {key}")
        if count == 0:
            await boundary_controls(context, offer, cap)
        if not count and not smoke:
            # A structurally valid v1 response still cannot execute under the current contract.
            corrected_old_wire = strict_recorded_json(second)
            corrected_old_wire["app_context_counts"] = {offer["required_channel"]: 1}
            old_wire = json.dumps(corrected_old_wire, ensure_ascii=False)
            require(
                await current_validation(context, old_wire, old_wire) is None,
                "A v1 response with valid counts was reinterpreted as a current action",
            )
        if smoke:
            await timed_defer_controls(context, offer, old_response)
        count += 1
    return {
        "run": folder.name,
        "archived_failed_plans": count,
        "historical_initial_echoes_without_intent": sum(totals.values()),
        "archived_repair_zero_required_channel": sum(totals.values()),
        "archived_defer_review_errors_repeated_in_repair": dict(null_reviews),
        "archived_exposure_totals": dict(totals),
        "archived_exposure_caps": dict(caps),
        "rejected_archived_initial_repair_pairs": count,
        "rejected_historical_repairs_replayed_individually": count,
        "offline_constructed_controls": "passed",
        "boundary_controls": "passed",
        "online_requests": 0,
        "new_model_choices_measured": 0,
    }


async def boundary_controls(context, offer, cap):
    """Acceptance of a genuine decision and independent rejection of exposure/goal violations."""
    channel = offer["required_channel"]
    other = next(c for c in context["candidate_app_contexts"] if c != channel)
    base = {
        "action": f"engage_goal@o1@open:{channel}",
        "additional_apps": [channel] * (cap - 1),
        "attitude": 0.5,
        "subjective_norm": 0.5,
        "perceived_control": 0.5,
        "confidence": 0.9,
        "reason": "Handle the visible service.",
    }

    async def validate(wire):
        raw = json.dumps(wire)
        return await current_validation(context, raw, raw)

    valid = await validate(base)
    require(
        valid is not None
        and valid.audit["parse_status"] == "ok"
        and valid.intent["opportunity_id"] == offer["opportunity_id"]
        and valid.app_context_counts == {channel: cap},
        "Valid choice at the cap failed",
    )
    for invalid in (
        {**base, "additional_apps": [channel] * cap},
        {**base, "additional_apps": ["unlisted_channel"]},
        {**base, "action": f"engage_goal@o1@open:{other}"},
        {**base, "action": f"engage_goal@unknown@open:{channel}"},
        {**base, "action": "engage_goal@o1"},
        {**base, "action": "no_app", "additional_apps": [other]},
    ):
        require(await validate(invalid) is None, "Invalid activity, target or budget was accepted")
    # A pre-v4 raw response did not explicitly select the channel inside the target action.
    # The same JSON must not acquire a different activity or task under the new schema.
    old_wire = {k: v for k, v in base.items() if k != "additional_apps"}
    old_wire.update(action="engage_goal@o1", apps=[other])
    require(await validate(old_wire) is None, "An old invalid goal/channel combination was reinterpreted")
    repaired = await current_validation(context, "incomplete envelope", json.dumps(base))
    require(
        repaired is not None
        and repaired.audit["parse_status"] == "ok_repaired"
        and repaired.audit.get("raw_choice") is None
        and repaired.audit["repair_requests"] == 1,
        "Unrecognizable initial response later repaired must remain a repair-only observation",
    )


async def timed_defer_controls(context, offer, old_response):
    """Construct a choice with a specified hour. It is a counterfactual, never a historical decision."""
    now = context["inputs"]["monotonic_sim_hour"]
    latest = now + context["inputs"]["max_defer_hours"]
    deadline = offer["known_deadline_sim_hour"]
    if deadline is not None:
        latest = min(latest, deadline)
    base = {k: v for k, v in old_response.items() if k not in {"action", "review", "apps"}}
    base["additional_apps"] = old_response["apps"]
    for hour in range(now + 1, latest + 1):
        timed = json.dumps({**base, "action": f"defer_goal@o1@{hour}"})
        valid = await current_validation(context, timed, timed)
        require(valid is not None and valid.audit["parse_status"] == "ok"
                and valid.intent["kind"] == "defer_goal" and valid.intent["opportunity_id"] == offer["opportunity_id"]
                and valid.intent["next_review_at_sim_hour"] == hour, "Legal review hour cannot be selected")
    for bad in ("defer_goal@o1", f"defer_goal@o1@{now}", f"defer_goal@o1@{latest + 1}"):
        raw = json.dumps({**base, "action": bad})
        require(await current_validation(context, raw, raw) is None, "Untimed or out-of-window deferral was admitted")
    # A syntactically incomplete reply stated a particular time. A repair may preserve it but cannot replace it.
    action = f"defer_goal@o1@{now + 1}"
    partial = '{"action":' + json.dumps(action) + ', "additional_apps":[], '
    fixed = json.dumps({**base, "action": action})
    valid = await current_validation(context, partial, fixed)
    require(valid is not None and valid.audit["parse_status"] == "ok_repaired"
            and valid.intent["next_review_at_sim_hour"] == now + 1, "Preserved explicit deferral failed repair")
    changed = json.dumps({**base, "action": f"defer_goal@o1@{now + 2}"})
    require(await current_validation(context, partial, changed) is None, "Repair changed the selected review time")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Archived failed Plan-pair run directory")
    parser.add_argument("--expected-decisions", type=int, help="Override 26 for paired runs or 2 for schema smoke")
    parser.add_argument("--output", type=Path, help="Optionally save the JSON verdict to a new file")
    args = parser.parse_args()
    if args.expected_decisions is not None and args.expected_decisions < 1:
        parser.error("expected-decisions must be positive")
    os.environ.pop("PROTO_LLM_TRACE_DIR", None)
    report = asyncio.run(check_archive(args.run, args.expected_decisions))
    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
