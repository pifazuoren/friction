import asyncio
from hashlib import sha256
import json
import sys

import httpx
import pytest

from check_hourly_channel_replay import RecordedReplies
from check_hourly_intention_run import request_payload
from check_stratified_needs_plan import check_plan_fixtures, plan_candidates, stratum
from proto.app_entry.intention_contract import COMPACT_PLAN_V7, COMPACT_PLAN_VERSION
from proto.app_entry.needs import DigitalNeedsBlock, COMPACT_NEEDS_PROMPT_VERSION
from run_stratified_needs_plan import MODEL, Meter, collect, load_failed_initial
from test_app_entry_needs import _payload
from test_hourly_intention_plan import packet
from test_daily_channel_choices import SOCIAL, wire


async def frozen_case(plan_schema=COMPACT_PLAN_VERSION):
    observation = packet(hourly_intention_mode="opportunity_v1")
    observation["day1_3_habit"].update(
        same_hour_active={"seen": 3, "active": 3},
        same_hour_context_counts={SOCIAL: 2},
        overall_context_counts={SOCIAL: 2},
    )
    base = {
        k: v
        for k, v in observation.items()
        if k
        not in (
            "available_opportunities",
            "current_intention",
            "goal_review_due",
            "monotonic_sim_hour",
            "max_defer_hours",
            "related_task_episode_ids",
        )
    }
    capture = RecordedReplies([json.dumps(_payload())])
    needs = await DigitalNeedsBlock().forward(
        llm=capture,
        input_payload=base,
        prompt_version=COMPACT_NEEDS_PROMPT_VERSION,
    )
    plan = await check_plan_fixtures(
        dict(
            needs=needs,
            compact_schema_version=plan_schema,
            input_payload=observation,
            candidate_contexts=plan_candidates(base, needs, 6),
            intensity_profile={"active_exposure_cap": 2},
        )
    )
    return dict(
        day=4,
        hour=9,
        rank=1,
        stratum=list(stratum(observation)),
        origin="archived",
        needs=capture.requests[0],
        plan_given_archived_needs=plan,
    )


@pytest.mark.parametrize("change", ["schema", "stimulus", "digest"])
def test_retry_rejects_archive_drift_before_reading_any_response(tmp_path, change):
    cases = [asyncio.run(frozen_case(COMPACT_PLAN_V7))]
    data = json.dumps(cases).encode()
    (tmp_path / "stimuli.json").write_bytes(data)
    (tmp_path / "replay.json").write_text(json.dumps({"source": "archive", "plan_schema": COMPACT_PLAN_V7}))
    design = {"plan_schema": COMPACT_PLAN_V7, "stimuli_sha256": sha256(data).hexdigest(),
              "model": MODEL, "needs_prompt": COMPACT_NEEDS_PROMPT_VERSION}
    if change == "schema":
        design["plan_schema"] = COMPACT_PLAN_VERSION
    elif change == "stimulus":
        cases[0]["hour"] += 1
    else:
        design["stimuli_sha256"] = "0" * 64
    (tmp_path / "design.json").write_text(json.dumps(design))
    with pytest.raises(ValueError, match="Prior prompts, experiment version, or source archive mismatch"):
        asyncio.run(load_failed_initial(tmp_path, cases, "archive", COMPACT_NEEDS_PROMPT_VERSION))


@pytest.mark.parametrize(
    "case", ["valid", "invalid_needs", "repaired", "provider_stop", "tamper"]
)
def test_actual_two_stage_wire_dispatch_and_missingness(tmp_path, monkeypatch, case):
    for name in ("openai", "openai.types", "openai.types.chat"):
        if name in sys.modules and sys.modules[name].__spec__ is None:
            monkeypatch.delitem(sys.modules, name)
    from openai import AsyncOpenAI

    stimulus = asyncio.run(frozen_case())
    old = request_payload(stimulus["plan_given_archived_needs"])
    fresh = _payload()
    fresh["need_pressures"].update(
        {k: float(k == "health_need") for k in fresh["need_pressures"]}
    )
    calls = []
    if case == "tamper":
        stimulus["needs"]["messages"][0]["content"] += "unexpected"

    def respond(req):
        data = json.loads(req.content)
        msg = data["messages"][-1]["content"]
        observation = json.loads(msg[msg.index("{") :])
        is_plan = "actions" in observation
        calls.append("plan" if is_plan else "needs")
        if case == "provider_stop":
            return httpx.Response(429, json={"error": {"message": "capacity"}})
        if is_plan:
            assert (
                observation["digital_needs"]["need_pressures"]
                == fresh["need_pressures"]
            )
            assert observation["digital_needs"] != old["digital_needs"]
            output = wire("habitual_app@open:" + observation["channels"][0], [])
        elif case == "invalid_needs" or case == "repaired" and len(calls) == 1:
            output = observation
        else:
            output = fresh
        return httpx.Response(
            200,
            json={
                "model": data["model"],
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    meter = Meter()

    async def run():
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            event_hooks={"request": [meter.before_send], "response": [meter.response]},
        )
        async with AsyncOpenAI(
            api_key="test", max_retries=0, http_client=http
        ) as client:
            return await collect(
                client, meter, tmp_path, [stimulus], 6, COMPACT_NEEDS_PROMPT_VERSION
            )

    if case == "tamper":
        from proto.llm_trace import LLMRunInterrupted

        with pytest.raises(LLMRunInterrupted):
            asyncio.run(run())
        assert not calls
        return
    report = asyncio.run(run())
    row = json.loads((tmp_path / "decisions.jsonl").read_text())
    assert report["http_requests"] == len(calls)
    if case in ("invalid_needs", "provider_stop"):
        assert row["plan"] is None and report["stages"]["plan"]["attempted"] == 0
        assert report["chain_valid"] == 0
        assert len(calls) == (1 if case == "provider_stop" else 2)
        return
    assert report["chain_valid"] == 1 and calls[-1] == "plan"
    assert row["plan"]["usage"] == [
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    ]
    assert row["bundle"]["exposures"] == 1 and row["intent"]["kind"] == "habitual_app"
    assert row["needs"]["first_echoed_inputs"] == (case == "repaired")
    assert report["stages"]["needs"]["first_valid"] == (case == "valid")
    assert report["reported_tokens"]["total_tokens"] == 15 * len(calls)


@pytest.mark.parametrize("result_type", ["repaired", "still_invalid", "invalid_plan"])
@pytest.mark.parametrize("plan_schema", [COMPACT_PLAN_V7, COMPACT_PLAN_VERSION])
def test_real_repair_dispatch_uses_archived_first_and_forwards_new_needs(
    tmp_path, monkeypatch, result_type, plan_schema
):
    from run_stratified_needs_plan import retry_failed, replay_failed_initial
    from proto.app_entry.needs import COMPACT_NEEDS_REPAIR_VERSION

    for name in ("openai", "openai.types", "openai.types.chat"):
        if name in sys.modules and sys.modules[name].__spec__ is None:
            monkeypatch.delitem(sys.modules, name)
    from openai import AsyncOpenAI

    case = asyncio.run(frozen_case(plan_schema))
    invalid = _payload()
    vals = invalid["need_pressures"]
    vals["habitant_check_need"] = vals.pop("habitual_check_need")
    raw = json.dumps(invalid)
    previous, correction = asyncio.run(
        replay_failed_initial(
            case,
            raw,
            raw,
            COMPACT_NEEDS_PROMPT_VERSION,
            COMPACT_NEEDS_REPAIR_VERSION,
        )
    )
    assert previous is None
    assert "缺少必填键 habitual_check_need" in correction["messages"][1]["content"]
    fixture = {
        "source_first_call_id": "archived-call",
        "source_plan_schema": plan_schema,
        "source_initial_raw": raw,
        "new_repair_stimulus": correction,
        "repair_version": COMPACT_NEEDS_REPAIR_VERSION,
    }
    fresh = _payload()
    calls = []

    def respond(req):
        data = json.loads(req.content)
        calls.append(data)
        if len(calls) == 1:
            assert (
                data["messages"] == correction["messages"] and data["temperature"] == 0
            )
            output = raw if result_type == "still_invalid" else json.dumps(fresh)
        else:
            body = json.loads(data["messages"][1]["content"].split("\n", 1)[1])
            assert body["schema_version"] == plan_schema
            assert body["digital_needs"]["need_pressures"] == fresh["need_pressures"]
            output = (
                "invalid"
                if result_type == "invalid_plan"
                else json.dumps(wire("no_app", []))
            )
        return httpx.Response(
            200,
            json={
                "id": "local",
                "object": "chat.completion",
                "created": 0,
                "model": data["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": output},
                    }
                ],
            },
        )

    async def run():
        meter = Meter(2)
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            event_hooks={"request": [meter.before_send], "response": [meter.response]},
        )
        async with AsyncOpenAI(
            api_key="test", max_retries=0, http_client=http
        ) as client:
            return await retry_failed(
                client, meter, case, fixture, tmp_path, 5, COMPACT_NEEDS_PROMPT_VERSION
            )

    report = asyncio.run(run())
    assert (
        report["http_requests"]
        == len(calls)
        == (1 if result_type == "still_invalid" else 2)
    )
    assert report["new_needs_initial_requests"] == 0
    assert report["chain_valid"] == int(result_type == "repaired")
    if result_type == "invalid_plan":
        assert report["plan"]["status"] == "invalid_first_response"
