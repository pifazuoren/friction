"""Prepare the paired Plan experiment or its two-case V4 smoke check. Only --online contacts GLM."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import random
from time import monotonic
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from probe_hourly_intention import (
    DAY,
    HOUR,
    MODES,
    NEEDS,
    PROFILE,
    PROFILE_ID,
    SIM_HOUR,
    controlled_rule_window,
    load_history,
    login_offer,
    prior_episode,
    routed_choice,
    rule_reference,
    run_plan,
)
from proto.llm_trace import bind_trace_context, traced_agent_tick
from proto.app_entry.intention_contract import COMPACT_PLAN_V4, compact_needs, compact_observation
from proto.paired_random import PairedRandomProvider
from run_strategy_memory_pairs import (
    ENDPOINT,
    EXAMPLE,
    MODEL,
    ROOT,
    SEED,
    ZhipuStrategyClient,
    save_json,
    schedule,
)

REFERENCE_DIR = ROOT / "agentsociety_data/elderly/10person_v3"
SMOKE_PURPOSE = "plan_schema_smoke"
SMOKE_HTTP_LIMIT = 4


class SmokeRequestBudget:
    """Enforce the cap immediately before HTTP dispatch, including any extra client attempts."""

    def __init__(self, *, limit=SMOKE_HTTP_LIMIT):
        self.limit = limit
        self.dispatched = 0
        self.case_dispatched = 0

    async def before_send(self, request):
        if self.dispatched >= self.limit or self.case_dispatched >= 2:
            raise RuntimeError("Schema smoke HTTP budget exhausted before dispatch")
        self.dispatched += 1
        self.case_dispatched += 1



class CapturePlan:
    """Offline double at the transport boundary; its valid, inert reply carries no study data."""

    def __init__(self, mode, *, action="no_app"):
        self.mode = mode
        self.action = action
        self.requests = []

    async def atext_request(self, *, dialog, **parameters):
        self.requests.append({"messages": deepcopy(dialog), "parameters": parameters})
        reply = {
            "active": False,
            "app_context_counts": {},
            "attitude": 0.5,
            "subjective_norm": 0.5,
            "perceived_control": 0.5,
            "confidence": 0.8,
            "reasoning": "Offline contract check.",
        }
        if self.mode == "opportunity_v1":
            reply = {
                "action": self.action, "additional_apps": [], "reason": "Offline contract check.",
                **{k: reply[k] for k in ("attitude", "subjective_norm", "perceived_control", "confidence")},
            }
        return json.dumps(reply)


def verify_contrast(success, failure, mode, *, scene="S0"):
    """Compare the emitted HTTP messages, including exact instructions and sampling settings."""
    if success["parameters"] != failure["parameters"]:
        raise ValueError("The two treatments use different model parameters")
    left, right = deepcopy(success["messages"]), deepcopy(failure["messages"])
    if len(left) != 2 or len(right) != 2 or left[0] != right[0] or left[1]["role"] != right[1]["role"]:
        raise ValueError("The system instructions or roles differ")
    normalized = []
    for messages, condition in ((left, "success"), (right, "failure")):
        prefix, payload = messages[1]["content"].split("\n", 1)
        body = json.loads(payload)
        packet = body["inputs"]
        episodes = packet["recent_task_episodes"]
        expected = prior_episode(condition)
        if len(episodes) != 1 or any(episodes[0].get(k) != expected[k] for k in expected):
            raise ValueError("The actual request lost its uniquely identified prior episode")
        if ("available_opportunities" in packet) != (mode == "opportunity_v1"):
            raise ValueError("The actual observation is for the wrong policy")
        if mode == "legacy" and "intent" in body["output_schema"]["required"]:
            raise ValueError("The legacy Plan was asked for a high-level intent")
        if mode == "opportunity_v1":
            _, _, offered = login_offer(scene=scene)
            handles = [alias for alias, target in body["targets"].items() if target == offered["opportunity_id"]]
            if len(handles) != 1:
                raise ValueError("The offered task must map to exactly one action handle")
            handle, = handles
            now, latest = packet["monotonic_sim_hour"], packet["monotonic_sim_hour"] + packet["max_defer_hours"]
            if offered["known_deadline_sim_hour"] is not None:
                latest = min(latest, offered["known_deadline_sim_hour"])
            legal_deferrals = {f"defer_goal@{handle}@{h}" for h in range(now + 1, latest + 1)}
            admission = f"engage_goal@{handle}@open:{offered['required_channel']}"
            if (body["schema_version"] != COMPACT_PLAN_V4 or "output_schema" in body
                    or packet["available_opportunities"] != [offered] or packet["current_intention"]
                    or packet["monotonic_sim_hour"] != SIM_HOUR
                    or set(body["actions"]) != {"no_app", "habitual_app", f"drop_goal@{handle}", admission}
                    or set(body["defer_options"][handle]) != legal_deferrals
                    or offered["required_channel"] not in body["channels"]):
                raise ValueError("The new Plan did not receive the known current offer and time")
        for k in ("outcome_type", "negative_feedback"):
            episodes[0].pop(k)
        normalized.append((prefix, body))
    if normalized[0] != normalized[1]:
        raise ValueError("The emitted requests differ outside the two preregistered episode fields")


def verify_shared_person(stimuli):
    """Check shared experimental inputs at the actual model boundary, across the two policies."""
    if not all(mode in stimuli for mode in MODES):
        return
    for condition in ("success", "failure"):
        old, new = (json.loads(stimuli[mode][condition]["messages"][1]["content"].split("\n", 1)[1])
                    for mode in MODES)
        shared = compact_observation(old["inputs"])
        if any(k not in new["inputs"] or new["inputs"][k] != v for k, v in shared.items()):
            raise ValueError("The two policies received different shared observations")
        if compact_needs(old["digital_needs"], new["schema_version"]) != new["digital_needs"]:
            raise ValueError("The two policies received different fixed Needs")


async def prepare(history, modes=MODES):
    stimuli = {}
    for mode in modes:
        stimuli[mode] = {}
        for condition in ("success", "failure"):
            transport = CapturePlan(mode)
            await run_plan(transport, mode=mode, condition=condition, history=history)
            if len(transport.requests) != 1:
                raise ValueError("Expected exactly one initial Plan request in offline verification")
            stimuli[mode][condition] = transport.requests[0]
        verify_contrast(stimuli[mode]["success"], stimuli[mode]["failure"], mode)
    verify_shared_person(stimuli)
    return stimuli


def request_order():
    rng = random.Random(SEED + 1)
    rows = []
    for index, pair in enumerate(schedule(), 1):
        for arm in pair["order"]:
            versions = list(MODES)
            rng.shuffle(versions)
            for mode in versions:
                rows.append(
                    {
                        "mode": mode,
                        "pair_id": pair["pair_id"],
                        "kind": pair["kind"],
                        "member": arm,
                        "condition": pair["conditions"][arm],
                        "pair_seed": SEED + index,
                        "stimulus": [mode, pair["conditions"][arm]],
                    }
                )
    return rows


def smoke_order():
    return [
        {"purpose": SMOKE_PURPOSE, "mode": "opportunity_v1", "pair_id": "smoke-01", "kind": "schema_smoke",
         "member": member, "condition": condition, "pair_seed": SEED, "stimulus": ["opportunity_v1", condition]}
        for member, condition in (("A", "success"), ("B", "failure"))
    ]


def smoke_summary(rows, http_attempts):
    complete = len(rows) == 2
    valid = sum(row["plan_valid"] for row in rows)
    return {
        "purpose": SMOKE_PURPOSE, "expected_decisions": 2, "recorded_decisions": len(rows),
        "complete": complete, "schema_check_passed": complete and valid == 2, "model": MODEL,
        "http_request_limit": SMOKE_HTTP_LIMIT, "http_requests_dispatched": http_attempts,
        "initial_responses_received": sum(row["initial_response_valid"] is not None for row in rows),
        "initial_responses_valid": sum(row["initial_response_valid"] is True for row in rows),
        "repair_requests": sum(row["repairs"] for row in rows),
        "final_valid_decisions": valid,
        "adopted_initial": sum(row["adopted_from"] == "initial" for row in rows),
        "adopted_repair": sum(row["adopted_from"] == "repair" for row in rows),
        "technical_failures": sum(not row["plan_valid"] for row in rows),
        "trace_directory": "trace", "decision_file": "decisions.jsonl",
        "decisions_by_prior_history": {
            row["condition"]: {
                "first_response_valid": row["initial_response_valid"], "final_valid": row["plan_valid"],
                "adopted_from": row["adopted_from"], "accepted_intent": row["accepted_intent_kind"],
                "next_review_at_sim_hour": row["next_review_at_sim_hour"], "task_admitted": row["task_admitted"],
            }
            for row in rows
        },
        "tests_memory_effect": False, "actual_low_level_attempts": 0,
    }


def describe_comparisons(rows, mode, kind):
    records = {}
    for row in rows:
        if row["kind"] != kind or row["mode"] != mode:
            continue
        group = records.setdefault(row["pair_id"], {})
        if row["member"] in group:
            raise ValueError("Duplicate scheduled pair member")
        group[row["member"]] = row
    valid = [
        (g["A"], g["B"])
        for g in records.values()
        if set(g) == {"A", "B"} and all(r["plan_valid"] for r in g.values())
    ]

    def differing(field):
        pairs = [(a[field], b[field]) for a, b in valid if a[field] is not None and b[field] is not None]
        return {"comparable_pairs": len(pairs), "different_pairs": sum(a != b for a, b in pairs)}

    effects = {}
    if valid and kind == "contrast":
        for action in sorted({r["policy_choice"] for p in valid for r in p}):
            effects[action] = sum(
                (b["policy_choice"] == action) - (a["policy_choice"] == action) for a, b in valid
            ) / len(valid)
    return {
        "expected_pairs": 10 if kind == "contrast" else 3,
        "pairs_with_two_valid_plans": len(valid),
        "choice_rate_difference_failure_minus_success": effects if kind == "contrast" else None,
        "raw_valid_model_intent": differing("first_valid_intent_kind"),
        "accepted_model_intent": differing("accepted_intent_kind"),
        "app_active_decision": differing("active"),
        "policy_choice": differing("policy_choice"),
        "task_admission": differing("task_admitted"),
        "review_hour_difference_pairs": sum(
            a["next_review_at_sim_hour"] != b["next_review_at_sim_hour"] for a, b in valid
        ),
    }


def summary(rows, rule_result=None):
    grouped = {}
    for mode in MODES:
        subset = [r for r in rows if r["mode"] == mode]
        valid = [r for r in subset if r["plan_valid"]]
        grouped[mode] = {
            "planned": 26,
            "recorded": len(subset),
            "valid": len(valid),
            "valid_rate": len(valid) / len(subset) if subset else None,
            "technical_failures": len(subset) - len(valid),
            "actual_requests": sum(r["requests"] for r in subset),
            "repair_requests": sum(r["repairs"] for r in subset),
            "elapsed_seconds": sum(r["elapsed_seconds"] for r in subset),
            "accepted_policy_counts": dict(Counter(r["policy_choice"] for r in valid)),
            **{k: describe_comparisons(rows, mode, k) for k in ("contrast", "repeat")},
        }
    if rule_result is not None:
        grouped["rule"] = {**rule_result, "same_for_all_pairs": True, "independent_model_repetitions": 0}
    old, new = grouped["legacy"], grouped["opportunity_v1"]
    complete = all(group["recorded"] == group["planned"] for group in (old, new))
    relative_cost = {}
    for field in ("actual_requests", "elapsed_seconds"):
        ratio = None
        if complete and old["valid"] and new["valid"] and old[field] > 0:
            ratio = (new[field] / new["valid"]) / (old[field] / old["valid"])
        relative_cost[field + "_per_valid_plan_ratio"] = ratio
    return {
        "profiles": 1,
        "conditions": grouped,
        "genuine_help_dispatches": 0,
        "actual_low_level_attempts": 0,
        "task_admission_only": True,
        "external_human_validation": "not_measured",
        "pilot_review": {
            "complete": complete, "min_valid_rate": 0.95, "budget_warning_ratio": 1.20,
            "below_validity_target": complete and new["valid_rate"] < 0.95,
            "above_request_or_latency_budget": any(v is not None and v > 1.20 for v in relative_cost.values()),
            **relative_cost,
        },
    }


@traced_agent_tick
async def measure(transport, spec, history):
    mode, condition = spec["mode"], spec["condition"]
    bind_trace_context(
        mode=mode, condition=condition, pair_id=spec["pair_id"], pair_kind=spec["kind"],
        member=spec["member"], pair_seed=spec["pair_seed"], stimulus=spec["stimulus"],
        profile_id=PROFILE_ID, simulation_day=DAY, hour=HOUR, monotonic_sim_hour=SIM_HOUR,
        purpose=spec.get("purpose", "paired_intention_study"),
    )
    start = monotonic()
    try:
        plan = await run_plan(transport, mode=mode, condition=condition, history=history)
    except ValueError as exc:
        if not transport.requests:
            raise  # Invalid experiment input, before any model response.
        plan = None
        audit = getattr(exc, "audit", {})
        failure = str(exc)[:600]
    else:
        audit = plan.audit
        failure = None
    route = routed_choice(mode, plan)
    intent = plan.intent if plan is not None and mode == "opportunity_v1" else None
    first_valid = intent if intent and audit.get("parse_status") == "ok" else None
    return {
        **spec,
        **route,
        "plan_valid": plan is not None,
        "parse_status": audit.get("parse_status"),
        "technical_failure": failure,
        "active": plan.active if plan else None,
        "app_context_counts": plan.app_context_counts if plan else None,
        "raw_choice": audit.get("raw_choice"),
        "repaired_choice": audit.get("repaired_choice"),
        "accepted_choice": intent,
        "initial_response_valid": (
            audit.get("parse_status") == "ok" if transport.returned_models or plan is not None else None
        ),
        "adopted_from": ("repair" if audit.get("parse_status") == "ok_repaired" else "initial") if plan else None,
        "first_valid_intent_kind": first_valid["kind"] if first_valid else None,
        "accepted_intent_kind": intent["kind"] if intent else None,
        "next_review_at_sim_hour": intent.get("next_review_at_sim_hour") if intent else None,
        "task_admitted": route["routed_task_id"] is not None,
        "requests": transport.requests,
        "repairs": max(0, transport.requests - 1),
        "transport_errors": transport.transport_errors,
        "returned_models": transport.returned_models,
        "elapsed_seconds": round(monotonic() - start, 5),
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online",
        action="store_true",
        help="Send the selected manifest to GLM. Without --smoke the full experiment has 52 initial requests",
    )
    parser.add_argument("--smoke", action="store_true",
                        help="Schema check only: opportunity_v1, one success and one failure history; at most 4 HTTP requests online")
    parser.add_argument("--output-dir", type=Path, help="Create a new run directory at this path")
    data = parser.add_mutually_exclusive_group()
    data.add_argument(
        "--reference-dir",
        type=Path,
        default=REFERENCE_DIR,
        help="Directory with the Day 1–3 bundle and ranking",
    )
    data.add_argument(
        "--synthetic-history",
        action="store_true",
        help="Use a deterministic 72-hour fixture instead of private replay data",
    )
    args = parser.parse_args()
    os.umask(0o077)
    os.environ.pop("PROTO_LLM_TRACE_DIR", None)  # Verification doubles never enter online traces.
    history = load_history(None if args.synthetic_history else args.reference_dir)
    stimuli = await prepare(history, modes=("opportunity_v1",) if args.smoke else MODES)
    orders = smoke_order() if args.smoke else request_order()
    study_name = "intention_smoke" if args.smoke else "intention_pairs"
    run_id = study_name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
    directory = args.output_dir or (ROOT / "agentsociety_data/runs" / ("hourly_" + study_name) / run_id)
    directory.mkdir(parents=True, exist_ok=False)
    _, _, offer = login_offer()
    sources = [
        EXAMPLE / name
        for name in (
            "run_hourly_intention_pairs.py",
            "probe_hourly_intention.py",
            "config_runtime.py",
            "run_strategy_memory_pairs.py",
            "probe_strategy_memory_pair.py",
            "analysis_strategy_memory_pairs.py",
            "compare_strategy_prompt_runs.py",
            "analysis_entry_calibration_comparison.py",
            "analysis_app_entry_validation.py",
        )
    ]
    sources.extend((EXAMPLE / "proto").rglob("*.py"))
    hashes = {}
    archive_path = directory / "experiment_source.zip"
    with ZipFile(archive_path, "x", compression=ZIP_DEFLATED) as archive:
        for source in sorted(sources):
            name = str(source.relative_to(EXAMPLE))
            content = source.read_bytes()
            hashes[name] = hashlib.sha256(content).hexdigest()
            archive.writestr(name, content)
    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    save_json(
        directory / "shared_input.json",
        {
            "profile_id": PROFILE_ID,
            "profile": PROFILE,
            "history": asdict(history),
            "fixed_needs": NEEDS.to_dict(include_audit=False, legacy_tiebreak=True),
            "opportunity": offer,
            "episode_source": "constructed independent Day 4 login; no downstream aggregate or state changes",
        },
    )
    save_json(directory / "stimuli.json", stimuli)
    save_json(directory / "request_manifest.json", orders)
    rule_result = None
    formal_design = {}
    if not args.smoke:
        rule_result = rule_reference(history)
        save_json(directory / "rule_reference.json", rule_result)
        save_json(directory / "rule_controlled_window.json", controlled_rule_window(history))
        draws = {}
        for spec in orders:
            provider = PairedRandomProvider(spec["pair_seed"])
            draws[spec["pair_id"]] = {
                m: provider.rng(PROFILE_ID, offer["opportunity_id"], 1, m).random()
                for m in ("strategy", "help_availability", "outcome")
            }
        formal_design = {
            "pilot_review_thresholds": {"min_valid_rate": 0.95, "budget_warning_ratio": 1.20},
            "rule_policy": "Handle the fresh login at the first hour predicted active by personal same-hour history; if none in 24 h, drop.",
            "control_policy": "A uses legacy assignment under shared harness inputs, not a rerun of the archived experiment",
            "common_random_preview_only_no_environment_draws_consumed": draws,
        }
    save_json(
        directory / "design.json",
        {
            "model": MODEL,
            "history_source": history.source,
            "mode": "online" if args.online else "offline_preparation",
            "expected_initial_plan_requests": len(orders),
            "purpose": SMOKE_PURPOSE if args.smoke else "paired_intention_study",
            "included_modes": list(stimuli),
            "opportunity_plan_schema": COMPACT_PLAN_V4,
            "extra_repair_requests_max": len(orders),
            "sdk_retries": 0,
            "planned_needs_low_level_help_outcome_requests": 0,
            "manipulated_fields": [
                "inputs.recent_task_episodes[0].outcome_type",
                "inputs.recent_task_episodes[0].negative_feedback",
            ],
            **({"http_request_limit": SMOKE_HTTP_LIMIT} if args.smoke else formal_design),
            "source_sha256": hashes,
            "source_archive_sha256": archive_hash,
        },
    )
    if args.smoke:
        print(f"小额格式检查已准备两次首轮 Plan 请求，含修复最多发出 4 次 HTTP 请求。结果目录 {directory}", flush=True)
    else:
        print(f"已保存 52 次首轮 Plan 请求清单、核对过的提示、共同快照和规则基线：{directory}", flush=True)
    if not args.online:
        print("离线准备完成，在线调用 0 次。")
        return 0
    import httpx
    from openai import AsyncOpenAI

    key = (os.environ.get("LLM_API_KEY") or os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    if not key or key == "<YOUR-API-KEY>":
        key = getpass("智谱 API Key（输入隐藏）：").strip()
    if not key or key == "<YOUR-API-KEY>":
        parser.exit(2, "没有提供模型凭证，在线请求未启动。\n")
    os.environ.update(
        LLM_API_KEY=key,  # Also redact a credential entered through the hidden prompt from local request traces.
        PROTO_LLM_TRACE_DIR=str(directory / "trace"),
        PARALLEL_GROUP_NAME=run_id,
        PROTO_RUN_SOURCE_SHA256=archive_hash,
    )
    rows = []
    budget = SmokeRequestBudget() if args.smoke else None
    http_options = {"trust_env": False}
    if budget is not None:
        http_options.update(event_hooks={"request": [budget.before_send]}, follow_redirects=False)
    async with AsyncOpenAI(
        api_key=key, base_url=ENDPOINT, max_retries=0, http_client=httpx.AsyncClient(**http_options)
    ) as client:
        with (directory / "decisions.jsonl").open("x", encoding="utf-8") as handle:
            for spec in orders:
                if budget is not None:
                    budget.case_dispatched = 0
                expected = stimuli[spec["mode"]][spec["condition"]]["messages"]
                transport = ZhipuStrategyClient(client, expected)
                row = await measure(transport, spec, history)
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                rows.append(row)
                report = smoke_summary(rows, budget.dispatched) if budget is not None else summary(rows, rule_result)
                save_json(directory / "summary.json", report)
                if any(e["http_status"] in {401, 403, 429} for e in transport.transport_errors):
                    parser.exit(2, "鉴权或限流错误，已保存部分记录并停止。\n")
    if args.smoke:
        print(f"格式检查完成。首答有效 {report['initial_responses_valid']}/2，最终采纳 "
              f"{report['final_valid_decisions']}/2，实际发出 {budget.dispatched} 次请求。")
    print(f"在线 Plan 决策汇总：{directory / 'summary.json'}")
    return 1 if args.smoke and not report["schema_check_passed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
