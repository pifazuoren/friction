import asyncio
from copy import deepcopy
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from check_daily_channel_choices import CASES, choose_cases, reexpress_valid, run_online
from proto.app_entry.intention_contract import (
    COMPACT_PLAN_V4,
    COMPACT_PLAN_V5,
    compact_menu,
)
from proto.app_entry.planner import DigitalAppEntryPlanBlock, decode_compact_plan
from run_hourly_intention_pairs import CapturePlan
from test_app_entry_planner import _needs
from test_hourly_intention_plan import packet


SOCIAL = "communication_social_context"
FINANCE = "finance_context"


def wire(action, additional):
    return {
        "action": action,
        "additional_apps": additional,
        "reason": "I chose this activity.",
        "attitude": 0.55,
        "subjective_norm": 0.4,
        "perceived_control": 0.6,
        "confidence": 0.8,
    }


def body(version):
    observation = {
        "available_opportunities": [],
        "current_intention": None,
        "goal_review_due": True,
        "monotonic_sim_hour": 72,
        "max_defer_hours": 24,
    }
    channels = [SOCIAL, FINANCE]
    return {
        "schema_version": version,
        "inputs": observation,
        "channels": channels,
        "exposure_cap": 3,
        "minimum_confidence": 0.65,
        **compact_menu(observation, version, channels),
    }


def test_v4_reexpression_preserves_recorded_multiplicity_and_no_app():
    for action, openings in [
        ("habitual_app", [FINANCE, SOCIAL, FINANCE]),
        ("no_app", []),
    ]:
        raw = wire(action, openings)
        original = deepcopy(raw)
        encoded = reexpress_valid(raw, body(COMPACT_PLAN_V4))
        assert raw == original
        assert encoded["action"] == (
            "no_app" if action == "no_app" else "habitual_app@open:" + FINANCE
        )
        assert encoded["additional_apps"] == openings[1:]
        assert decode_compact_plan(
            encoded, body(COMPACT_PLAN_V5)
        ) == decode_compact_plan(raw, body(COMPACT_PLAN_V4))


@pytest.mark.parametrize(
    "raw",
    [
        wire("habitual_app", []),
        wire("habitual_app", ["unknown"]),
        {**wire("habitual_app", [FINANCE]), "confidence": 0.4},
    ],
)
def test_invalid_v4_activity_or_scores_cannot_receive_an_explicit_opening(raw):
    with pytest.raises(ValueError):
        reexpress_valid(raw, body(COMPACT_PLAN_V4))


def test_selection_prefers_earliest_hour_before_profile_diversity_and_uses_a_stable_tie_break():
    candidates = [
        ({"stratum": case, "day": 4, "hour": 1, "rank": rank}, None)
        for case in CASES
        for rank in (1, 2, 3, 4, 5, 6)
    ]
    candidates.append(({"stratum": CASES[1], "day": 4, "hour": 0, "rank": 1}, None))
    expected = [1, 1, 2, 3, 4, 5]
    assert [e["rank"] for e, _ in choose_cases(candidates)] == expected
    assert [e["rank"] for e, _ in choose_cases(list(reversed(candidates)))] == expected


def test_six_online_states_have_free_choices_separate_from_original_outcome(
    tmp_path, monkeypatch
):
    # Exercise production prompts, repairs, parsing and real httpx request hooks with a scoped SDK double.
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        first = "preserve" not in json.loads(
            payload["messages"][1]["content"].split("\n")[-1]
        )
        requests.append(first)
        if first and len(requests) == 1:
            content = "incomplete envelope"
        elif sum(requests) in {1, 5}:
            content = json.dumps(wire("habitual_app@open:" + SOCIAL, []))
        else:
            content = json.dumps(wire("no_app", []))
        return httpx.Response(200, text=content)

    class LocalSDK:
        def __init__(self, *, http_client, max_retries, **_):
            assert max_retries == 0
            self.http = http_client
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        async def create(self, *, messages, model, **_):
            response = await self.http.post(
                "https://test.invalid/chat", json={"messages": messages}
            )
            return SimpleNamespace(
                model=model,
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response.text))
                ],
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            await self.http.aclose()

    class LocalClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            assert not kwargs["trust_env"] and not kwargs["follow_redirects"]
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    async def exercise():
        kwargs = {
            "needs": _needs(),
            "input_payload": packet(hourly_intention_mode="opportunity_v1"),
            "candidate_contexts": {SOCIAL: 1.0},
            "intensity_profile": {"active_exposure_cap": 3},
        }
        recorded = CapturePlan("opportunity_v1")
        await DigitalAppEntryPlanBlock().forward(llm=recorded, **kwargs)
        (stimulus,) = recorded.requests
        cases = [
            (
                {
                    "day": 4,
                    "hour": 0,
                    "rank": index,
                    "agent_id": index,
                    "source_call_id": f"source-{index}",
                    "stratum": label,
                },
                kwargs,
                stimulus,
            )
            for index, label in enumerate(CASES, 1)
        ]
        return await run_online(tmp_path, cases)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=LocalSDK))
    monkeypatch.setattr(httpx, "AsyncClient", LocalClient)
    monkeypatch.setenv("LLM_API_KEY", "local-test-only")
    assert asyncio.run(exercise()) == 0
    report = json.loads((tmp_path / "summary.json").read_text())
    assert (
        report["complete"]
        and report["http_requests"] == 7
        and report["http_request_limit"] == 12
    )
    assert report["by_source_group"]["failed"] == {
        "states": 4,
        "first_valid": 3,
        "final_valid": 4,
        "initial_explicit_daily_token": 0,
        "accepted_explicit_daily_token": 1,
    }
    assert report["by_source_group"]["controls"]["initial_explicit_daily_token"] == 1
    assert report["decisions"][4]["accepted_plan"]["intent"]["kind"] == "habitual_app"
    assert report["decisions"][5]["accepted_plan"]["intent"]["kind"] == "no_app"
