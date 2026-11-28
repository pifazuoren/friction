"""Freeze or run the five-day guidance vs proxy-completion decision probe. Default: offline."""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from analysis_help_mode_pairs import summarize
from help_mode_design import (
    digest,
    help_episodes,
    load_residents,
    prepare_design,
    route_help_plan,
    run_help_plan,
)
from probe_hourly_intention import DAY, HOUR, SIM_HOUR, TICK
from probe_hourly_strategy import measure_admitted
from proto.app_entry.intention_contract import COMPACT_SCORES
from proto.app_entry.planner import HourlyIntentionPlanError
from proto.llm_trace import LLMRunInterrupted, bind_trace_context, traced_agent_tick
from proto.memory.packet import compact_recent_episodes
from run_hourly_intention_pairs import CapturePlan, REFERENCE_DIR
from run_hourly_strategy_factorial import (
    FactorialClient,
    HTTPBudget,
    STUDY_RUNTIME,
    archive_source,
    experiment_environment,
)
from run_strategy_memory_pairs import ENDPOINT, MODEL, ROOT, save_json


EXPECTED_POINTS = 80
MAX_INITIAL = 3 * EXPECTED_POINTS
HTTP_LIMIT = 2 * MAX_INITIAL


def _body(stimulus):
    return json.loads(stimulus["messages"][1]["content"].split("\n", 1)[1])


def _with_body(stimulus, body):
    revised = deepcopy(stimulus)
    user = revised["messages"][1]
    prefix = user["content"].split("\n", 1)[0]
    user["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
    return revised


class _TemplateRecorder:
    """Fixed local replies to reach both lower production prompts during offline preparation."""

    def __init__(self):
        self.requests = []

    async def atext_request(self, *, dialog, **parameters):
        self.requests.append({"messages": deepcopy(dialog), "parameters": parameters})
        if len(self.requests) == 1:
            scores = dict.fromkeys(
                (
                    "perceived_task_difficulty",
                    "perceived_task_risk",
                    "felt_control",
                    "expected_help_effectiveness",
                    "task_value",
                ),
                50,
            )
        elif len(self.requests) == 2:
            scores = {
                "attempt_self_score": 0.6,
                "seek_help_score": 0.3,
                "avoid_score": 0.1,
                "dominant_strategy": "attempt_self",
            }
        else:
            raise ValueError("Offline prompt capture unexpectedly needed a repair")
        return json.dumps(
            {**scores, "judge_confidence": 1, "reason": "Offline input check."}
        )


def _check_episode_pair(cells, resident):
    """A contrast must survive in each lower prompt, with all other transmitted fields identical."""
    for stage, memory_key in (
        ("appraisal", "Task-Specific Memory"),
        ("strategy", "task_relevant_memory"),
    ):
        comparable = []
        for arm in ("guided", "proxy"):
            stimulus = cells[arm][stage]
            body = _body(stimulus)
            observed = body[memory_key]["recent_task_episodes"]
            facts = compact_recent_episodes(
                help_episodes(resident.profile_id, arm),
                simulation_day=DAY,
                tick_seconds=TICK,
            )
            if (
                len(facts) != 3
                or observed != facts
                or not observed[-1].get("completion_action")
            ):
                raise ValueError(
                    f"{stage}: actual prompt lost the three assigned episodes"
                )
            observed[-1]["completion_action"] = "<controlled completion fact>"
            comparable.append(_with_body(stimulus, body))
        if comparable[0] != comparable[1]:
            raise ValueError(f"{stage}: the arms differ outside the controlled fact")


async def capture_lower(residents, prepared):
    by_person = {}
    for person, resident in residents.items():
        key = str(person)
        cells = {}
        for arm in ("guided", "proxy"):
            initial = prepared["stimuli"][key][arm]
            (token,) = [
                action
                for action in _body(initial)["actions"]
                if action.startswith("engage_goal@")
            ]
            select = CapturePlan("opportunity_v1", action=token)
            plan = await run_help_plan(select, resident, arm)
            _, task = route_help_plan(plan, resident)
            if select.requests != [initial] or task is None:
                raise ValueError(
                    "Cannot route the frozen Plan's listed task for lower-stage validation"
                )
            recorder = _TemplateRecorder()
            result = await measure_admitted(
                recorder, task=task, condition=arm, sample_u=0, fact_resident=resident
            )
            appraisal, strategy = recorder.requests
            cells[arm] = {
                "appraisal": appraisal,
                "strategy": strategy,
                "rule_inputs": result["rule_inputs"],
                "rule_weights": result["rule_weights"],
            }
        _check_episode_pair(cells, resident)
        for field in ("rule_inputs", "rule_weights"):
            if cells["guided"][field] != cells["proxy"][field]:
                raise ValueError(f"Assigned help facts changed controlled {field}")
        by_person[key] = cells
    return by_person


class _FrozenFirstRequest:
    """Compare the actual lower-stage dispatch, allowing the observed upstream appraisal."""

    def __init__(self, transport, expected):
        self.transport = transport
        self.expected = expected
        self.configs = transport.configs
        self.checked = False

    async def atext_request(self, *, dialog, **parameters):
        if not self.checked:
            if {"messages": dialog, "parameters": parameters} != self.expected:
                raise LLMRunInterrupted(
                    "Lower-stage request differs from the frozen stimulus"
                )
            self.checked = True
        return await self.transport.atext_request(dialog=dialog, **parameters)


@traced_agent_tick
async def measure(transport, spec, resident, lower_template):
    arm = spec["condition"]
    episodes = help_episodes(resident.profile_id, arm)
    episode_ids = [e["episode_id"] for e in episodes]
    bind_trace_context(
        purpose="help_mode_pairs",
        simulation_day=DAY,
        talkingdata_day=DAY + 1,
        hour=HOUR,
        monotonic_sim_hour=SIM_HOUR,
        **{key: value for key, value in spec.items() if key != "kind"},
        pair_kind=spec["kind"],
        assigned_episode_ids=episode_ids,
    )
    interrupted_stage = None
    try:
        plan = await run_help_plan(transport, resident, arm)
        audit = plan.audit
    except HourlyIntentionPlanError as exc:
        plan, audit = None, exc.audit
    except LLMRunInterrupted:
        if not transport.stop_http:
            raise
        plan, audit, interrupted_stage = None, {}, "plan"
    if transport.contract_error or not transport.requests:
        raise RuntimeError("The dispatched Plan did not match its verified stimulus")
    route, task = route_help_plan(plan, resident)
    plan_requests = transport.requests
    review = plan.intent.get("next_review_at_sim_hour") if plan else None
    lower = None
    checked = {}

    def stage_client(stage, actual_appraisal):
        expected = lower_template[stage]
        if stage == "strategy":
            body = _body(expected)
            body["task_appraisal"] = actual_appraisal
            expected = _with_body(expected, body)
        checked[stage] = _FrozenFirstRequest(transport, expected)
        return checked[stage]

    if task is not None:
        try:
            lower = await measure_admitted(
                transport,
                task=task,
                condition=arm,
                sample_u=spec["sample_u"],
                fact_resident=resident,
                stage_client=stage_client,
            )
        except LLMRunInterrupted:
            if not transport.stop_http:
                raise
            interrupted_stage = "post_admission"
        if lower is not None and (
            set(checked) != {"appraisal", "strategy"}
            or not all(c.checked for c in checked.values())
            or any(
                lower[k] != lower_template[k] for k in ("rule_inputs", "rule_weights")
            )
        ):
            raise RuntimeError(
                "Lower stage bypassed the frozen prompts or rule weights"
            )
    return {
        **spec,
        **route,
        "assigned_episode_ids": episode_ids,
        "plan_valid": plan is not None,
        "task_admitted": task is not None if plan else None,
        "defer_hours": review - SIM_HOUR if review is not None else None,
        "plan_scores": {k: getattr(plan, k) for k in COMPACT_SCORES} if plan else None,
        "plan_reason": plan.reasoning if plan else None,
        "plan_audit": audit,
        "lower": lower,
        "interrupted_stage": interrupted_stage,
        "plan_requests": plan_requests,
        "requests": transport.requests,
        "returned_models": transport.returned_models,
        "transport_errors": transport.transport_errors,
    }


async def collect(client, residents, prepared, folder, budget):
    specs = prepared["manifest"]
    rows = []
    report = summarize(specs, rows)
    report.update(http_requests=0, stop_reason=None)
    save_json(folder / "summary.json", report)
    with (folder / "decisions.jsonl").open("x", encoding="utf-8") as log:
        for spec in specs:
            person, arm = spec["profile_id"], spec["condition"]
            budget.case_start = budget.count
            stimulus = prepared["stimuli"][str(person)][arm]
            transport = FactorialClient(client, stimulus)
            try:
                if digest(stimulus) != spec["plan_stimulus_sha256"]:
                    raise ValueError(
                        "Preregistered Plan digest differs from the stimulus"
                    )
                row = await measure(
                    transport,
                    spec,
                    residents[person],
                    prepared["lower_templates"][str(person)][arm],
                )
                row["http_requests"] = budget.count - budget.case_start
                if row["http_requests"] != row["requests"] or any(
                    m != MODEL for m in row["returned_models"]
                ):
                    raise RuntimeError(
                        "Model or actual HTTP dispatch count disagrees with the recorded run"
                    )
                next_report = summarize(specs, [*rows, row])
                log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                log.flush()
                rows.append(row)
                report = next_report
            except BaseException as exc:
                report.update(
                    http_requests=budget.count,
                    uncommitted_point_http_requests=budget.count
                    - sum(r["http_requests"] for r in rows),
                    stop_reason=type(exc).__name__,
                    stopped_at=[spec["pair_id"], spec["member"]],
                )
                save_json(folder / "summary.json", report)
                raise
            report.update(
                http_requests=budget.count,
                stop_reason="provider_error" if transport.stop_http else None,
            )
            save_json(folder / "summary.json", report)
            print(
                f"[{len(rows)}/{len(specs)}] {spec['pair_id']} {spec['member']}",
                flush=True,
            )
            if transport.stop_http:
                break
    return report


async def run_experiment(args):
    folder = args.output_dir or ROOT / "agentsociety_data/runs/help_mode_pairs" / (
        "help_pairs_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
    )
    reference = None if args.synthetic_history else args.reference_dir
    residents = load_residents(
        reference, **({"profiles_path": args.profiles} if args.profiles else {})
    )
    with experiment_environment({**STUDY_RUNTIME, "PROTO_LLM_TRACE_DIR": None}):
        prepared = await prepare_design(residents)
        initial_hashes = {
            (person, arm): digest(stimulus)
            for person, arms in prepared["stimuli"].items()
            for arm, stimulus in arms.items()
        }
        if any(
            initial_hashes[str(spec["profile_id"]), spec["condition"]]
            != spec["plan_stimulus_sha256"]
            for spec in prepared["manifest"]
        ):
            raise ValueError(
                "Cannot archive a schedule with a mismatched Plan stimulus"
            )
        prepared["lower_templates"] = await capture_lower(residents, prepared)
        summarize(prepared["manifest"], [])
        folder.mkdir(parents=True, exist_ok=False)
        source_hash = archive_source(folder)
        hashes = {}
        for name, data in prepared.items():
            filename = "request_manifest.json" if name == "manifest" else f"{name}.json"
            path = folder / filename
            save_json(path, data)
            hashes[filename] = sha256(path.read_bytes()).hexdigest()
        save_json(
            folder / "design.json",
            {
                "study": "help_mode_pairs",
                "model": MODEL,
                "online_requested": args.online,
                "expected_decisions": EXPECTED_POINTS,
                "max_initial_requests": MAX_INITIAL,
                "http_request_limit_with_repairs": HTTP_LIMIT,
                "sdk_retries": 0,
                "source_archive_sha256": source_hash,
                "frozen_input_sha256": hashes,
                "history_source": "synthetic_72_hours_per_rank"
                if args.synthetic_history
                else "10_reference_ranks_days1_3",
                "frozen_runtime": STUDY_RUNTIME,
                "intervention": "Two assigned day-four failures followed by one assigned successful guided or proxy completion.",
                "endpoint": "Day-five Plan, sampled strategy and local helper request receipt. Operation start, delivery and outcome unobserved.",
                "lower_templates": "Offline fixture appraisal. Only task_appraisal is replaced with the actual upstream appraisal at strategy dispatch.",
            },
        )
        print(
            f"已冻结 {len(prepared['manifest'])} 个决策点。结果目录 {folder}",
            flush=True,
        )
        if not args.online:
            print("离线准备完成，真实模型请求 0 次。")
            return 0
        import httpx
        from openai import AsyncOpenAI

        key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
        if not key or key == "<YOUR-API-KEY>":
            key = getpass("智谱 API Key（输入隐藏）：").strip()
        if not key or key == "<YOUR-API-KEY>":
            return 2
        budget = HTTPBudget(limit=HTTP_LIMIT)
        with experiment_environment(
            {
                "LLM_API_KEY": key,
                "PROTO_LLM_TRACE_DIR": str((folder / "trace").resolve()),
                "PARALLEL_GROUP_NAME": folder.name,
                "PROTO_RUN_SOURCE_SHA256": source_hash,
            }
        ):
            http = httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                event_hooks={"request": [budget.before_send]},
            )
            async with AsyncOpenAI(
                api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
            ) as client:
                report = await collect(client, residents, prepared, folder, budget)
        print(f"实际发送 {budget.count} 次 HTTP 请求。见 {folder / 'summary.json'}。")
        return int(not report["complete"] or report["stop_reason"] is not None)


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    history = parser.add_mutually_exclusive_group()
    history.add_argument(
        "--synthetic-history",
        action="store_true",
        help="Use ten synthetic 72-hour traces",
    )
    history.add_argument(
        "--reference-dir",
        type=Path,
        default=REFERENCE_DIR,
        help="Private reference bundle and rank map",
    )
    parser.add_argument("--profiles", type=Path, help="Ten synthetic resident profiles")
    parser.add_argument("--output-dir", type=Path, help="New run directory")
    parser.add_argument(
        "--online", action="store_true", help="Dispatch up to 480 HTTP requests to GLM"
    )
    args = parser.parse_args(argv)
    previous_umask = os.umask(0o077)
    try:
        return await run_experiment(args)
    finally:
        os.umask(previous_umask)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
