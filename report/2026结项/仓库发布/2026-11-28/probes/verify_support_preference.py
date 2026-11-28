# ruff: noqa: E402
# Load the experiment modules from this checkout after locating its root.
"""Reconcile the two-day controlled support probe using only its on-disk evidence."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "examples/digital_friction_mvp").is_dir()
)
sys.path.insert(0, str(ROOT / "examples/digital_friction_mvp"))

from check_hourly_intention_run import check_plan_calls, request_payload
from proto.app_entry.intention_contract import parse_compact_reply
from proto.llm_psychology import _extract_json_object
from proto.support_protocol import (
    REQUESTED_SUPPORT_STYLES,
    SUPPORT_RESPONSE_MIN_CONFIDENCE,
    SUPPORT_RESPONSE_KEYS,
    SupportResponse,
    classify_support_delivery,
)


MODEL = "glm-4-flashx"
FACTS = (
    "task_id",
    "day",
    "hour",
    "episode_id",
    "outcome_type",
    "help_used",
    "support_request_id",
    "support_delivery_status",
    "requested_support_style",
    "requested_support_style_source",
    "support_style",
    "instruction_quality",
    "autonomy_preservation",
    "proxy_completion_level",
)


def select(rows, module, kind, **fields):
    return [
        r
        for r in rows
        if r.get("module") == module
        and r.get("kind") == kind
        and all(r.get(key) == val for key, val in fields.items())
    ]


def exactly_one(rows, label):
    if len(rows) != 1:
        raise ValueError(f"{label}: expected one record, found {len(rows)}")
    return rows[0]


def content_hash(messages):
    wire = json.dumps(
        messages, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(wire.encode()).hexdigest()


def stage(rows, module):
    requests = select(rows, module, "request")
    parses = select(rows, module, "parse")
    ids = {r["call_id"] for r in requests}
    if any(r["call_id"] not in ids for r in parses):
        raise ValueError(f"{module}: orphan parse")
    return {
        "calls": len(requests),
        "parse_statuses": [r.get("status") for r in parses],
        "accepted": [r for r in parses if r.get("status") in ("ok", "ok_repaired")],
    }


def verify_case(case, traces):
    agent = case["agent_id"]
    result = {"agent_id": agent, "issues": [], "stages": {}, "next_day_recall": {}}
    issues = result["issues"]

    def require(ok, message):
        if not ok:
            issues.append(message)

    d4, d5 = (
        [
            r
            for r in traces
            if str(r.get("agent_id")) == str(agent) and r.get("talkingdata_day") == day
        ]
        for day in (4, 5)
    )
    for day, rows, modules in (
        (4, d4, ("strategy", "support_preference", "helper")),
        (5, d5, ("app_needs", "app_plan", "strategy", "support_preference", "helper")),
    ):
        for mod in modules:
            info = stage(rows, mod)
            result["stages"][f"d{day}_{mod}"] = {
                "calls": info["calls"],
                "parse_statuses": info["parse_statuses"],
                "accepted_parses": len(info["accepted"]),
            }
    episode = case.get("d4_episode") or {}
    exchange = case.get("d4_exchange") or {}
    req, resp = exchange.get("request") or {}, exchange.get("response") or {}
    choice = req.get("requested_support_style")
    result.update(
        requested=choice,
        preference_source=req.get("requested_support_style_source"),
        helper_response=resp.get("support_style"),
        helper_takeover=resp.get("proxy_completion_level"),
        delivery=episode.get("support_delivery_status"),
        d4_outcome=episode.get("outcome_type"),
    )
    preference = stage(d4, "support_preference")["accepted"]
    preference_requests = select(d4, "support_preference", "request")
    require(
        len(preference_requests) == 1,
        "day 4 preference elicitation count differs from one",
    )
    if len(preference) == 1:
        p = preference[0]
        wire = exactly_one(
            select(d4, "support_preference", "response", call_id=p["call_id"]),
            "day 4 preference reply",
        )
        expected = {"requested_support_style": choice}
        require(
            parse_compact_reply(wire["raw"]) == p["parsed"] == expected
            and choice in REQUESTED_SUPPORT_STYLES,
            "preference raw reply, parse and stored request disagree",
        )
    else:
        issues.append("day 4 resident preference was not a valid model judgment")
    if not req or not resp or not episode:
        failures = select(d4, "task", "decision", status="technical_failure")
        result["d4_failure_status"] = [r.get("support_status") for r in failures]
        issues.append("day 4 has no complete recorded help exchange and task episode")
    else:
        require(
            req.get("requested_support_style_source") == "llm",
            "day 4 preference missing or from fallback",
        )
        require(
            bool(req.get("request_id"))
            and req["request_id"]
            == resp.get("request_id")
            == episode.get("support_request_id"),
            "day 4 request, response and episode identifiers disagree",
        )
        require(
            str(req.get("requester_agent_id"))
            == str(resp.get("requester_agent_id"))
            == str(agent)
            and req.get("helper_agent_id") is not None
            and req["helper_agent_id"] == resp.get("helper_agent_id"),
            "day 4 requester/helper identity mismatch",
        )
        helper_call = exactly_one(
            select(d4, "helper", "request", phase="initial"),
            "day 4 helper first request",
        )
        helper_input = request_payload(helper_call)
        require(
            helper_input.get("requested_support_style") == choice
            and helper_input["task"]["task_id"]
            == req.get("task_id")
            == episode.get("task_id")
            and helper_input["relationship"]["mapped_helper_agent_id"]
            == req["helper_agent_id"],
            "day 4 helper did not receive the recorded preference for this person and task",
        )
        helper_parses = stage(d4, "helper")["accepted"]
        require(
            len(helper_parses) == 1,
            "day 4 helper has no unique accepted model judgment",
        )
        if helper_parses:
            accepted = helper_parses[-1]
            parsed = accepted["parsed"]
            raw = exactly_one(
                select(d4, "helper", "response", call_id=accepted["call_id"]),
                "accepted day 4 helper raw response",
            )
            raw_object = _extract_json_object(raw["raw"]) or {}
            if raw_object.get("task_id") == req["task_id"]:
                raw_object.pop("task_id")
            require(
                set(raw_object) == SUPPORT_RESPONSE_KEYS,
                "day 4 helper raw reply has wrong fields",
            )
            decoded = SupportResponse.from_dict(raw_object).to_dict()
            require(
                all(
                    decoded.get(key) == parsed.get(key) for key in SUPPORT_RESPONSE_KEYS
                ),
                "day 4 helper raw reply does not reproduce the accepted parse",
            )
            require(
                all(
                    parsed.get(k) == resp.get(k)
                    for k in (
                        "support_style",
                        "instruction_quality",
                        "autonomy_preservation",
                        "proxy_completion_level",
                        "response_delay",
                        "responded",
                        "emotional_tone",
                        "confidence",
                    )
                ),
                "day 4 helper model parse differs from stored actual response",
            )
            require(
                resp.get("confidence", 0) >= SUPPORT_RESPONSE_MIN_CONFIDENCE
                and resp.get("source") == "llm_family_helper",
                "day 4 helper reply low confidence or fallback",
            )
        require(
            classify_support_delivery(resp) == episode.get("support_delivery_status"),
            "day 4 delivery mismatch",
        )
        require(
            episode.get("requested_support_style") == choice
            and episode.get("requested_support_style_source") == "llm"
            and all(
                episode.get(k) == resp.get(k)
                for k in (
                    "support_style",
                    "instruction_quality",
                    "autonomy_preservation",
                    "proxy_completion_level",
                )
            ),
            "day 4 stored episode did not preserve the preference and actual assistance",
        )
        decision = exactly_one(
            select(d4, "task", "decision", status="completed"), "day 4 settled task"
        )
        require(
            decision.get("episode_id") == episode.get("episode_id")
            and decision.get("outcome") == episode.get("outcome_type")
            and decision.get("requested_support_style") == choice,
            "day 4 settled decision differs from stored episode",
        )

    next_episode = case.get("d5_episode") or {}
    routes = select(d5, "hourly_intention", "hourly_intention")
    if routes:
        route = exactly_one(routes, "day 5 route")
        check_plan_calls(d5, route)
        result.update(
            d5_plan=route.get("executed_choice"), d5_plan_status=route.get("status")
        )
        require(route.get("status") == "accepted", "day 5 planning failed")
        opened = route.get("executed_choice") in ("engage_goal", "continue_goal")
    else:
        issues.append("no day 5 hourly intention route")
        opened = bool(next_episode)
    for mod in ("app_needs", "app_plan", "strategy"):
        calls = select(d5, mod, "request", phase="initial")
        should_call = mod != "strategy" or opened
        if not calls and not should_call:
            result["next_day_recall"][mod] = "not_reached"
            continue
        require(bool(calls), f"day 5 required {mod} was not called")
        require(should_call, f"day 5 {mod} called without task admission")
        if not calls:
            result["next_day_recall"][mod] = "missing"
            continue
        require(
            bool(stage(d5, mod)["accepted"]), f"day 5 {mod} has no valid model response"
        )
        visible = []
        for call in calls:
            payload = request_payload(call)
            observation = (
                payload["task_relevant_memory"]
                if mod == "strategy"
                else payload["inputs"]
            )
            prior = [
                r
                for r in observation.get("recent_task_episodes", [])
                if episode.get("episode_id")
                and r.get("episode_id") == episode["episode_id"]
            ]
            matches = len(prior) == 1 and all(
                prior[0].get(k) == episode.get(k) for k in FACTS
            )
            visible.append(matches)
            require(
                matches,
                f"day 5 {mod} did not receive matching day 4 episode and help facts",
            )
        result["next_day_recall"][mod] = (
            "verified" if all(visible) else "missing_or_different"
        )
    if opened:
        settled = select(d5, "task", "decision", status="completed")
        failed = select(d5, "task", "decision", status="technical_failure")
        result["d5_task_status"] = (
            "completed" if settled else "technical_failure" if failed else "missing"
        )
        if settled:
            d = exactly_one(settled, "day 5 settled task")
            samples = select(d5, "strategy", "sample")
            s = exactly_one(samples, "day 5 strategy sampling")
            result.update(
                d5_strategy=s.get("action"),
                d5_strategy_source=d.get("strategy_source"),
                d5_strategy_status=d.get("strategy_status"),
                d5_outcome=d.get("outcome"),
            )
            require(
                d.get("strategy_source") == "hybrid_blended",
                "day 5 model strategy fell back or was not adopted",
            )
            require(
                next_episode.get("episode_id") == d.get("episode_id")
                and next_episode.get("requested_strategy_type") == s.get("action")
                and next_episode.get("outcome_type") == d.get("outcome"),
                "day 5 executed task mismatch",
            )
        else:
            issues.append("day 5 admitted task did not settle")
    else:
        require(
            not next_episode and not select(d5, "task", "decision"),
            "day 5 unadmitted task produced a decision",
        )
    return result


def verify(folder):
    cases = json.loads((folder / "cases.json").read_text())
    http = json.loads((folder / "http.json").read_text())
    traces = [
        json.loads(line)
        for p in sorted((folder / "trace").glob("llm-requests-*.jsonl"))
        for line in p.read_text().splitlines()
        if line.strip()
    ]
    report = {
        "cases": [],
        "issues": [],
        "http_calls": len(http),
        "returned_models": dict(Counter(str(r.get("model")) for r in http)),
        "reported_tokens": sum(
            (r.get("usage") or {}).get("total_tokens", 0) for r in http
        ),
    }
    if len(cases) != 2 or len({str(c["agent_id"]) for c in cases}) != 2:
        report["issues"].append("expected exactly two distinct residents")
    requests = [r for r in traces if r.get("kind") == "request"]
    sends = Counter((str(r["agent_id"]), r["day"], r["messages_sha256"]) for r in http)
    traced = Counter(
        (str(r["agent_id"]), r["talkingdata_day"], content_hash(r["messages"]))
        for r in requests
    )
    report["trace_requests"] = len(requests)
    report["wire_hashes_matched"] = sends == traced
    if not report["wire_hashes_matched"]:
        report["issues"].append(
            "HTTP dispatches and actual application prompt hashes differ"
        )
    if any(
        str(r.get("model", "")).lower() != MODEL or r.get("status") != 200 for r in http
    ):
        report["issues"].append("wrong served model or unsuccessful HTTP request")
    ids = [r["call_id"] for r in requests]
    if not all(ids) or len(set(ids)) != len(ids):
        report["issues"].append("duplicated or missing traced call ID")
    completed = Counter(
        r.get("call_id") for r in traces if r.get("kind") in ("response", "error")
    )
    if completed != Counter(ids):
        report["issues"].append(
            "HTTP trace has missing, duplicated or unlinked responses"
        )
    for case in cases:
        try:
            result = verify_case(case, traces)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            result = {"agent_id": case.get("agent_id"), "issues": [str(exc)]}
        report["cases"].append(result)
    report["passed"] = not report["issues"] and all(
        not case["issues"] for case in report["cases"]
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    folder = parser.parse_args().run_dir
    try:
        result = verify(folder)
    except (KeyError, IndexError, TypeError, ValueError, FileNotFoundError) as exc:
        result = {"passed": False, "issues": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(int(not result["passed"]))
