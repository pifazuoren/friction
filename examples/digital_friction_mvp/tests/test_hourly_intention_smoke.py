"""Exercise production Plan parsing behind a local HTTP transport; no network or credentials."""

import asyncio
from collections import Counter
import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from run_hourly_intention_pairs import (
    CapturePlan,
    SMOKE_PURPOSE,
    SmokeRequestBudget,
    main,
)


def test_smoke_preparation_has_two_opportunity_plans_and_never_asks_for_credentials(
    tmp_path, monkeypatch
):
    folder = tmp_path / "prepared"
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["probe", "--smoke", "--synthetic-history", "--output-dir", str(folder)],
    )
    assert asyncio.run(main()) == 0
    manifest = json.loads((folder / "request_manifest.json").read_text())
    design = json.loads((folder / "design.json").read_text())
    assert len(manifest) == design["expected_initial_plan_requests"] == 2
    assert design["purpose"] == SMOKE_PURPOSE and design["included_modes"] == [
        "opportunity_v1"
    ]
    assert {r["condition"] for r in manifest} == {"success", "failure"}
    assert design["http_request_limit"] == 4 and design["sdk_retries"] == 0
    assert not (folder / "decisions.jsonl").exists() and not (folder / "trace").exists()


@pytest.mark.parametrize("repairs,fail_repair", [(1, False), (2, False), (2, True)])
def test_schema_smoke_sends_only_the_selected_cases_and_archives_raw_and_parse_events(
    tmp_path, monkeypatch, repairs, fail_repair
):
    folder = tmp_path / "smoke"
    calls = []

    async def reply(req):
        messages = json.loads(req.content)["messages"]
        content = messages[1]["content"]
        is_repair = content.startswith("{") and "preserve" in json.loads(content)
        calls.append("repair" if is_repair else "initial")
        if (not is_repair and calls.count("initial") <= repairs) or (is_repair and fail_repair):
            return httpx.Response(200, text="{}")
        raw = await CapturePlan("opportunity_v1").atext_request(dialog=messages)
        return httpx.Response(200, text=raw)

    # Exercise actual httpx event hooks; the SDK stand-in can only dispatch to this memory transport.
    real_client = httpx.AsyncClient

    def http_client(**options):
        assert options["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(reply), **options)

    class SDK:
        def __init__(self, *, http_client, max_retries, **_):
            assert max_retries == 0
            self.http = http_client
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        async def create(self, *, messages, model, **_):
            resp = await self.http.post(
                "https://test.invalid/chat", json={"messages": messages}
            )
            return SimpleNamespace(
                model=model,
                choices=[SimpleNamespace(message=SimpleNamespace(content=resp.text))],
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            await self.http.aclose()

    monkeypatch.setattr(httpx, "AsyncClient", http_client)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=SDK))
    monkeypatch.setenv("LLM_API_KEY", "smoke-test-credential")
    for key in (
        "PROTO_LLM_TRACE_DIR",
        "PARALLEL_GROUP_NAME",
        "PROTO_RUN_SOURCE_SHA256",
    ):
        monkeypatch.setenv(key, "")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--synthetic-history",
            "--smoke",
            "--online",
            "--output-dir",
            str(folder),
        ],
    )
    assert asyncio.run(main()) == (1 if fail_repair else 0)

    summary = json.loads((folder / "summary.json").read_text())
    assert summary["purpose"] == SMOKE_PURPOSE and summary["complete"]
    assert summary["schema_check_passed"] is (not fail_repair)
    assert len(calls) == summary["http_requests_dispatched"] == 2 + repairs
    assert (
        summary["initial_responses_valid"] == summary["adopted_initial"] == 2 - repairs
    )
    failed = repairs if fail_repair else 0
    assert summary["technical_failures"] == failed
    assert summary["final_valid_decisions"] == 2 - failed
    assert summary["adopted_repair"] == repairs - failed
    trace = next((folder / "trace").glob("*.jsonl")).read_text()
    assert "smoke-test-credential" not in trace
    rows = [json.loads(line) for line in trace.splitlines()]
    assert {row["purpose"] for row in rows} == {SMOKE_PURPOSE}
    requests = [r for r in rows if r["kind"] == "request"]
    assert Counter(r["phase"] for r in requests) == {"initial": 2, "repair": repairs}
    for request in requests:
        by_call = [r for r in rows if r.get("call_id") == request["call_id"]]
        assert [r["kind"] for r in by_call] == ["request", "response", "parse"]
        assert by_call[0]["messages"] and by_call[1]["raw"]
    by_history = summary["decisions_by_prior_history"]
    assert by_history["success"]["adopted_from"] == (None if fail_repair else "repair")
    assert by_history["failure"]["adopted_from"] == (
        "initial" if repairs == 1 else None if fail_repair else "repair"
    )


def test_real_http_hook_prevents_excess_transport_dispatches_even_if_caller_retries():
    sent = []

    async def run():
        budget = SmokeRequestBudget()

        def receive(request):
            sent.append(request)
            return httpx.Response(200)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(receive),
            event_hooks={"request": [budget.before_send]},
        ) as client:
            for _ in range(2):
                budget.case_dispatched = 0
                for _ in range(2):
                    await client.post("https://test.invalid/chat")
                with pytest.raises(RuntimeError, match="budget exhausted"):
                    await client.post("https://test.invalid/chat")
            budget.case_dispatched = 0
            with pytest.raises(RuntimeError, match="budget exhausted"):
                await client.post("https://test.invalid/chat")

    asyncio.run(run())
    assert len(sent) == 4
