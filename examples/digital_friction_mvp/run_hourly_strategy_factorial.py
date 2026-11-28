"""Prepare or run the 24-point V4 login and help-seeking experiment. Default: offline."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from analysis_hourly_factorial import summarize
from config_runtime import load_runtime_config
from hourly_factorial_design import prepare_design
from probe_hourly_intention import (
    DAY,
    HOUR,
    PROFILE_ID,
    SIM_HOUR,
    load_history,
    route_opportunity_choice,
    run_plan,
)
from probe_hourly_strategy import FROZEN_RUNTIME_ENV, measure_admitted
from proto.app_entry.intention_contract import COMPACT_PLAN_V4, COMPACT_SCORES
from proto.app_entry.planner import (
    APP_ENTRY_PLAN_PROMPT_VERSION,
    HourlyIntentionPlanError,
)
from proto.llm_trace import LLMRunInterrupted, bind_trace_context, traced_agent_tick
from run_hourly_intention_pairs import REFERENCE_DIR
from run_strategy_memory_pairs import (
    ENDPOINT,
    EXAMPLE,
    MODEL,
    ROOT,
    ZhipuStrategyClient,
    save_json,
)

EXPECTED_POINTS = 24
MAX_INITIAL_REQUESTS = 3 * EXPECTED_POINTS
MAX_HTTP_REQUESTS = 2 * MAX_INITIAL_REQUESTS
STUDY_RUNTIME = {
    **FROZEN_RUNTIME_ENV,
    "STAGE_MODE": "single",
    "PROTO_APP_ENTRY_REPLAY_DAYS": "1,2,3",
    "PROTO_TASK_ENTRY_MODE": "app_context_replay_then_llm_rollout",
    "PROTO_HOURLY_INTENTION_MODE": "opportunity_v1",
    "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION": APP_ENTRY_PLAN_PROMPT_VERSION,
    "PROTO_HOURLY_INTENTION_MAX_DEFER_HOURS": "24",
    "PROTO_SCHEDULED_LOGIN_HOUR": "9",
    "PROTO_LOGIN_DIFFICULTY_ARM": "",
}


@contextmanager
def experiment_environment(values):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class HTTPBudget:
    """Count dispatches at the wire, including format repairs and unsuccessful calls."""

    def __init__(self, limit=MAX_HTTP_REQUESTS):
        self.limit = limit
        self.count = 0
        self.case_start = 0

    async def before_send(self, _request):
        if self.count >= self.limit or self.count - self.case_start >= 6:
            raise RuntimeError("HTTP request budget exhausted before dispatch")
        self.count += 1


class FactorialClient(ZhipuStrategyClient):
    def __init__(self, client, stimulus):
        super().__init__(client, stimulus["messages"])
        self.plan_parameters = stimulus["parameters"]
        self.contract_error = False

    @property
    def stop_http(self):
        return any(e["http_status"] in {401, 403, 429} for e in self.transport_errors)

    async def atext_request(self, *, dialog, **parameters):
        if not self.requests and (
            dialog != self.expected_dialog or parameters != self.plan_parameters
        ):
            self.contract_error = True
        if self.contract_error:
            raise LLMRunInterrupted("The verified Plan stimulus changed")
        try:
            return await super().atext_request(dialog=dialog, **parameters)
        except Exception as exc:
            if not self.stop_http:
                raise
            stop = LLMRunInterrupted("The provider stopped the run")
            stop.status_code = exc.status_code
            raise stop from exc


@traced_agent_tick
async def measure(transport, spec, history, *, feedback_state=None):
    feedback_mode = "frozen" if feedback_state is None else "updated"
    state_digest = None
    if feedback_state is not None:
        if feedback_state["condition"] != spec["condition"]:
            raise ValueError("Decision assigned the wrong Day 4 feedback state")
        state_digest = sha256(
            json.dumps(
                feedback_state, sort_keys=True, ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        ).hexdigest()
    bind_trace_context(
        purpose="hourly_strategy_factorial",
        scene=spec["scene"],
        pair_id=spec["pair_id"],
        member=spec["member"],
        condition=spec["condition"],
        feedback_mode=feedback_mode,
        feedback_state_sha256=state_digest,
        profile_id=PROFILE_ID,
        simulation_day=DAY,
        talkingdata_day=DAY + 1,
        hour=HOUR,
        monotonic_sim_hour=SIM_HOUR,
    )
    interrupted_stage = None
    try:
        plan = await run_plan(
            transport,
            mode="opportunity_v1",
            history=history,
            condition=spec["condition"],
            scene=spec["scene"],
            feedback_state=feedback_state,
        )
        audit = plan.audit
    except HourlyIntentionPlanError as exc:
        plan, audit = None, exc.audit
    except LLMRunInterrupted:
        if not transport.stop_http:
            raise
        plan, audit, interrupted_stage = None, {}, "plan"
    if transport.contract_error or not transport.requests:
        raise RuntimeError("The dispatched Plan did not match its verified stimulus")
    route, task = route_opportunity_choice(plan, scene=spec["scene"])
    review = plan.intent.get("next_review_at_sim_hour") if plan else None
    plan_requests = transport.requests
    lower = None
    if task is not None:
        try:
            lower = await measure_admitted(
                transport,
                task=task,
                condition=spec["condition"],
                sample_u=spec["sample_u"],
                feedback_state=feedback_state,
            )
        except LLMRunInterrupted:
            if not transport.stop_http:
                raise
            interrupted_stage = "post_admission"
    return {
        **spec,
        **route,
        "feedback_mode": feedback_mode,
        "feedback_state_sha256": state_digest,
        "plan_valid": plan is not None,
        "task_admitted": (task is not None) if plan else None,
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


def archive_source(folder):
    archive = folder / "experiment_source.zip"
    # Include the local program and its transitive experiment modules at execution time.
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as bundle:
        for path in sorted([*EXAMPLE.glob("*.py"), *(EXAMPLE / "proto").rglob("*.py")]):
            bundle.write(path, str(path.relative_to(EXAMPLE)))
    return sha256(archive.read_bytes()).hexdigest()


def prepare_archive(folder, history, prepared, *, online, feedback_mode="frozen"):
    folder.mkdir(parents=True, exist_ok=False)
    source_hash = archive_source(folder)
    for name, data in prepared.items():
        filename = {"manifest": "request_manifest"}.get(name, name)
        save_json(folder / f"{filename}.json", data)
    save_json(
        folder / "design.json",
        {
            "study": "hourly_strategy_factorial",
            "mode": "opportunity_v1",
            "schema": COMPACT_PLAN_V4,
            "model": MODEL,
            "online_requested": online,
            "feedback_mode": feedback_mode,
            "feedback_states_file": "feedback_states.json"
            if feedback_mode == "updated"
            else None,
            "feedback_states_sha256": (
                sha256((folder / "feedback_states.json").read_bytes()).hexdigest()
                if feedback_mode == "updated"
                else None
            ),
            "day4_outcome_source": (
                "controlled rule_v1 outcome and state update"
                if feedback_mode == "updated"
                else "matched prior-episode record; background state frozen"
            ),
            "expected_decisions": EXPECTED_POINTS,
            "max_initial_requests": MAX_INITIAL_REQUESTS,
            "http_request_limit_with_repairs": MAX_HTTP_REQUESTS,
            "sdk_retries": 0,
            "helper_replies_generated": False,
            "day5_outcomes_measured": False,
            "history_source": history.source,
            "reference_hours": history.habits["total_hours_seen"],
            "reference_hash": history.reference_hash,
            "mapping_hash": history.mapping_hash,
            "frozen_runtime": STUDY_RUNTIME,
            "source_archive_sha256": source_hash,
            "manifest_sha256": sha256(
                (folder / "request_manifest.json").read_bytes()
            ).hexdigest(),
            "stimuli_sha256": sha256(
                (folder / "stimuli.json").read_bytes()
            ).hexdigest(),
        },
    )
    return source_hash


async def collect(client, history, prepared, folder, budget, *, feedback_mode="frozen"):
    specs = prepared["manifest"]
    rows = []
    report = summarize(specs, rows)
    report.update(feedback_mode=feedback_mode, http_requests=0, stop_reason=None)
    save_json(folder / "summary.json", report)
    with (folder / "decisions.jsonl").open("x", encoding="utf-8") as log:
        for spec in specs:
            budget.case_start = budget.count
            stimulus = prepared["stimuli"][spec["scene"]][spec["condition"]]
            transport = FactorialClient(client, stimulus)
            try:
                state = (
                    prepared["feedback_states"][spec["condition"]]
                    if feedback_mode == "updated"
                    else None
                )
                row = await measure(transport, spec, history, feedback_state=state)
                row["http_requests"] = budget.count - budget.case_start
                if row["http_requests"] != row["requests"]:
                    raise RuntimeError(
                        "Logged requests disagree with HTTP dispatch count"
                    )
                if any(model != MODEL for model in row["returned_models"]):
                    raise RuntimeError(
                        "Provider returned a different model from the frozen design"
                    )
                next_report = summarize(specs, [*rows, row])
                next_report["feedback_mode"] = feedback_mode
                log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                log.flush()
                rows.append(row)
                report = next_report
            except BaseException as exc:
                # A partially executed point stays out of the completed comparisons.
                report.update(
                    http_requests=budget.count,
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


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online",
        action="store_true",
        help="Send 24 decisions to GLM; at most 144 HTTP calls with repairs",
    )
    parser.add_argument(
        "--feedback-mode",
        choices=("frozen", "updated"),
        default="frozen",
        help="frozen: change the prior episode only; updated: propagate the Day 4 outcome into Day 5 state",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="New directory for this execution"
    )
    history_group = parser.add_mutually_exclusive_group()
    history_group.add_argument("--reference-dir", type=Path, default=REFERENCE_DIR)
    history_group.add_argument(
        "--synthetic-history",
        action="store_true",
        help="Use a synthetic 72-hour fixture",
    )
    args = parser.parse_args(argv)
    previous_umask = os.umask(0o077)
    try:
        return await run_experiment(args)
    finally:
        os.umask(previous_umask)


async def run_experiment(args):
    name = (
        "hourly_strategy_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:6]
    )
    folder = (
        args.output_dir
        or ROOT / "agentsociety_data/runs/hourly_strategy_factorial" / name
    )
    with experiment_environment({**STUDY_RUNTIME, "PROTO_LLM_TRACE_DIR": None}):
        load_runtime_config()  # Check downstream compatibility before the first paid Plan.
        history = load_history(None if args.synthetic_history else args.reference_dir)
        prepared = await prepare_design(history, feedback_mode=args.feedback_mode)
        summarize(
            prepared["manifest"], []
        )  # Validate the complete schedule before any HTTP request.
        source_hash = prepare_archive(
            folder,
            history,
            prepared,
            online=args.online,
            feedback_mode=args.feedback_mode,
        )
        print(
            f"已核对 24 个决策点的计划输入（{args.feedback_mode}）。结果目录 {folder}",
            flush=True,
        )
        if not args.online:
            print("离线准备完成，真实模型请求 0 次。")
            return 0

        from openai import AsyncOpenAI
        import httpx

        key = (os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "").strip()
        if not key or key == "<YOUR-API-KEY>":
            key = getpass("智谱 API Key（输入隐藏）：").strip()
        if not key or key == "<YOUR-API-KEY>":
            print("未提供密钥，实验未启动。")
            return 2
        budget = HTTPBudget()
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
                report = await collect(
                    client,
                    history,
                    prepared,
                    folder,
                    budget,
                    feedback_mode=args.feedback_mode,
                )
        print(
            f"实际发送 {budget.count} 次 HTTP 请求。汇总见 {folder / 'summary.json'}。"
        )
        return int(not report["complete"] or report["stop_reason"] is not None)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
