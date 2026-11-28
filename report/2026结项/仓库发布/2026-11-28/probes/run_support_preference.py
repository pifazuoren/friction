# ruff: noqa: E402
# Load the experiment modules from this checkout after locating its root.
"""Two conditional family-help exchanges, then the next day's freely chosen Plan."""

import argparse
import asyncio
from copy import deepcopy
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


OUT: Path
ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "examples/digital_friction_mvp").is_dir()
)
EXAMPLE = ROOT / "examples/digital_friction_mvp"
sys.path[:0] = [str(EXAMPLE), str(EXAMPLE / "tests")]
from proto.llm_trace import LLMRunInterrupted, _redact
from proto.models import AttemptStrategy
from proto.runtime import scheduled_login_for_day
from probe_hourly_intention import load_history
from run_strategy_memory_pairs import ENDPOINT, MODEL, save_json
from run_hourly_strategy_factorial import archive_source

CAP = 24
ENV = {
    "stage_name": "steady",
    "digital_stage": "steady",
    "friction_level": 1,
    "complexity_level": 1,
    "risk_level": 1,
    "assist_level": 1,
    "human_support_level": 1,
    "accessibility_level": 1,
}
SETTINGS = {
    "LLM_MODEL": MODEL,
    "EXP_SEED": "101",
    "PARALLEL_PAIR_SEED": "101",
    "STAGE_MODE": "single",
    "STAGE_DAYS": "5",
    "WORLD_NAME": "baseline_low_friction",
    "PROTO_OUTCOME_MODEL_MODE": "rule_v1",
    "PROTO_LLM_PSYCHOLOGY_MODE": "hybrid",
    "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED": "true",
    "PROTO_LLM_STRATEGY_PROMPT_FORMAT": "field_rules_no_priors",
    "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED": "false",
    "PROTO_LLM_TASK_APPRAISAL_ENABLED": "false",
    "PROTO_LLM_EVENT_APPRAISAL_ENABLED": "false",
    "PROTO_LLM_DAILY_REFLECTION_ENABLED": "false",
    "PROTO_LLM_UNCONTROLLABILITY_MODE": "off",
    "PROTO_STREAM_EPISODE_RECORDING_ENABLED": "false",
    "PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED": "false",
    "PROTO_STREAM_ATTRIBUTION_RETRIEVAL_ENABLED": "false",
    "PROTO_SUPPORT_ECOLOGY_MODE": "family_helper_llm",
    "PROTO_SCHEDULED_LOGIN_HOUR": "9",
    "PROTO_TASK_OCCURRENCE_GATE_ENABLED": "false",
    "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION": "app_entry_plan_v3",
    "PROTO_LLM_PSYCHOLOGY_RETRIES": "1",
    "PROTO_LLM_PSYCHOLOGY_TIMEOUT": "60",
}


def digest(messages):
    return hashlib.sha256(
        json.dumps(
            messages, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def dump(name, val):
    save_json(OUT / name, val)


class Meter:
    def __init__(self):
        self.rows = []
        self.context = {}
        self.stop = False

    async def send(self, req):
        if self.stop or len(self.rows) >= CAP:
            raise LLMRunInterrupted("Stopped before dispatch")
        if req.method != "POST" or str(req.url) != ENDPOINT + "chat/completions":
            raise LLMRunInterrupted("Unexpected destination")
        body = json.loads(req.content)
        msgs = body["messages"]
        assert body["model"] == MODEL
        self.rows.append(
            {
                **self.context,
                "index": len(self.rows) + 1,
                "status": None,
                "model": None,
                "messages_sha256": digest(msgs),
                "trace_messages_sha256": digest(_redact(msgs, ())),
            }
        )
        dump("http.json", self.rows)

    async def receive(self, resp):
        row = self.rows[-1]
        row["status"] = resp.status_code
        if resp.status_code >= 400:
            self.stop = True
        try:
            await resp.aread()
            ans = resp.json()
            row.update(
                model=ans.get("model"),
                usage=ans.get("usage"),
                response_id=ans.get("id"),
            )
        finally:
            dump("http.json", self.rows)
        print(
            f"request {row['index']} resident {row['agent_id']} day {row['day']} {row['role']} HTTP {resp.status_code}",
            flush=True,
        )


class Live:
    def __init__(self, client, meter, person, role):
        self.client = client
        self.meter = meter
        self.person = person
        self.role = role
        self.day = 4
        self.configs = [SimpleNamespace(model=MODEL)]

    async def atext_request(
        self, *, dialog, temperature, max_tokens, timeout, retries, **opts
    ):
        self.meter.context = dict(agent_id=self.person, day=self.day, role=self.role)
        if self.meter.stop or len(self.meter.rows) >= CAP:
            raise LLMRunInterrupted("Stopped before dispatch")
        try:
            res = await self.client.chat.completions.create(
                model=MODEL,
                messages=dialog,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as exc:
            if self.meter.stop:
                raise LLMRunInterrupted(
                    f"HTTP {getattr(exc, 'status_code', None)}"
                ) from None
            raise
        if res.model != MODEL:
            self.meter.stop = True
            raise LLMRunInterrupted("Unexpected provider model")
        return res.choices[0].message.content or ""


def assumed_help(**kwargs):
    return AttemptStrategy(
        strategy_type="seek_help_then_attempt",
        support_requested=True,
        rationale="The day-4 probe conditions on asking family for help.",
        weights=kwargs.get("precomputed_final_weights") or {},
    )


async def run_case(profile, client, meter, case):
    # Import runtime dependencies before loading the fixture, which stubs absent modules.
    import qdrant_client.http.models  # noqa: F401
    import fastembed  # noqa: F401
    import grpc.aio  # noqa: F401
    from proto.agent import DigitalHelplessnessAgent
    from proto.family_helper_agent import FamilyHelperAgent
    from proto.state_schema import build_initial_proto_status
    from test_proto_agent_status_summary import _FakeEnvironment, _FakeStatusStore

    i = profile["id"]
    helper_id = 100 + i
    resident_llm = Live(client, meter, i, "resident")
    helper_llm = Live(client, meter, i, "helper")
    env = _FakeEnvironment(day=3, tick_seconds=32401, time_text="09:00:01", env=ENV)
    status = build_initial_proto_status(
        **{
            k: profile[k]
            for k in ("digital_experience", "vision_limit", "past_fraud_experience")
        }
    )
    status.update(profile)
    task = scheduled_login_for_day(
        hour=9,
        agent_id=i,
        day=3,
        tick_seconds=32401,
        env=ENV,
        existing_task=None,
        last_scheduled_day=-1,
    )
    status.update(
        proto_assigned_task_json=json.dumps(task.to_dict()),
        family_helper_agent_id=helper_id,
    )
    status["digital_emotion_state"]["last_updated_day"] = 3
    person = DigitalHelplessnessAgent.__new__(DigitalHelplessnessAgent)
    person._id = i
    person.step_count = 0
    person._memory = SimpleNamespace(status=_FakeStatusStore(status))
    person._toolbox = SimpleNamespace(environment=env, llm=resident_llm)
    helper = FamilyHelperAgent(
        id=helper_id,
        name="family",
        toolbox=SimpleNamespace(
            llm=helper_llm,
            environment=env,
            messager=None,
            embedding=None,
            database_writer=None,
        ),
        memory=SimpleNamespace(status=_FakeStatusStore({})),
        agent_params=None,
        blocks=[],
    )
    person.set_support_helper_registry({helper_id: helper})
    state = person.memory.status.data
    os.environ.update(
        PROTO_TASK_ENTRY_MODE="fixed_assignment",
        PROTO_HOURLY_INTENTION_MODE="legacy",
        PROTO_SCHEDULED_LOGIN_HOUR="",
    )
    with patch("proto.agent.choose_attempt_strategy", assumed_help):
        await person.forward()
    (prior,) = state["recent_episode_buffer"]
    (exchange,) = helper.memory.status.data["support_histories"][str(i)]
    day4row = json.loads(
        json.loads(state["proto_stage_attempt_rows_json"])[-1]["payload_json"]
    )
    case.update(
        d4_episode=deepcopy(prior),
        d4_exchange=deepcopy(exchange),
        d4_decision=deepcopy(state["event_log"][-1]["decision"]),
        d4_payload=day4row,
    )
    dump("cases.json", CASES)
    os.environ.update(
        PROTO_TASK_ENTRY_MODE="app_context_replay_then_llm_rollout",
        PROTO_HOURLY_INTENTION_MODE="opportunity_v1",
        PROTO_SCHEDULED_LOGIN_HOUR="9",
    )
    state.update(
        proto_app_entry_replay_device_id=f"s{i}",
        proto_app_entry_replay_selected_rank=i,
        proto_day4_replay_snapshot={"schema_version": "synthetic_fixture"},
        proto_app_entry_habit_memory=load_history(None, selected_rank=i).habits,
    )
    resident_llm.day = helper_llm.day = 5
    env._day = 4
    await person.forward()
    case["d5_ledger"] = state.get("proto_goal_state_json")
    case["d5_rows"] = state.get("proto_app_entry_rollout_rows_json", [])
    later = [e for e in state["recent_episode_buffer"] if e.get("day") == 4]
    case["d5_episode"] = later[-1] if later else None
    case["d5_exchange"] = next(
        (
            e
            for e in helper.memory.status.data["support_histories"][str(i)]
            if e["request"]["day"] == 4
        ),
        None,
    )


CASES = []


async def main():
    import httpx
    from openai import AsyncOpenAI

    os.umask(0o077)
    settings = {
        **SETTINGS,
        "PARALLEL_GROUP_NAME": OUT.name,
        "PROTO_LLM_TRACE_DIR": str(OUT / "trace"),
    }
    os.environ.update(settings)
    assert (
        ENDPOINT == "https://open.bigmodel.cn/api/paas/v4/" and MODEL == "glm-4-flashx"
    )
    os.environ["PROTO_RUN_SOURCE_SHA256"] = archive_source(OUT)
    profiles = json.loads((EXAMPLE / "profiles.json").read_text())[:2]
    dump(
        "design.json",
        dict(
            model=MODEL,
            max_requests=CAP,
            profiles=profiles,
            environment=ENV,
            settings=settings,
            archived_source_sha256=os.environ["PROTO_RUN_SOURCE_SHA256"],
            day4="09:00, synthetic profile, common scheduled login and externally assigned seek-help strategy; resident preference and family response are live.",
            day5="09:00 next day, 72-hour synthetic background, new same-family scheduled offer, free live Needs/Plan, strategy if entered; no intervening hours.",
            outcome="Seeded rule model; no real accounts, no actual interface. No prompt retry beyond the existing stage-specific format rules.",
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    key = getpass.getpass("API credential (hidden): ").strip()
    if not key:
        raise ValueError("missing credential")
    meter = Meter()
    async with httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [meter.send], "response": [meter.receive]},
    ) as http:
        async with AsyncOpenAI(
            api_key=key, base_url=ENDPOINT, max_retries=0, http_client=http
        ) as client:
            for p in profiles:
                case = {
                    "agent_id": p["id"],
                    "d4_episode": None,
                    "d4_exchange": None,
                    "d5_episode": None,
                    "d5_ledger": None,
                }
                CASES.append(case)
                try:
                    await run_case(p, client, meter, case)
                except Exception as exc:
                    case["error_type"] = type(exc).__name__
                    import traceback

                    case["last_frames"] = [
                        (Path(f.filename).name, f.lineno, f.name)
                        for f in traceback.extract_tb(exc.__traceback__)[-6:]
                    ]
                    print(
                        "case stopped",
                        p["id"],
                        type(exc).__name__,
                        case["last_frames"],
                        flush=True,
                    )
                dump("cases.json", CASES)
                if meter.stop:
                    break
    dump("http.json", meter.rows)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--online",
        action="store_true",
        required=True,
        help="Obtain fresh GLM replies (at most 24 requests)",
    )
    cli.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New private directory for run outputs",
    )
    args = cli.parse_args()
    OUT = args.output_dir.resolve()
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=False)
    asyncio.run(main())
