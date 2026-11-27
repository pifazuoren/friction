"""Use the actual SDK with an in-memory HTTP transport; no request leaves this process."""

import asyncio
from collections import Counter
from hashlib import sha256
import json
import sys
from zipfile import ZipFile

import httpx
import pytest

from probe_hourly_intention import DEFERRABLE_SERVICE_DESCRIPTION
from run_hourly_strategy_factorial import HTTPBudget, main


def read(folder, name):
    return json.loads((folder / name).read_text())


def test_offline_archive_is_not_a_behavioral_result(tmp_path, monkeypatch):
    folder = tmp_path / "prepared"
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path / "external"))
    assert asyncio.run(main(["--synthetic-history", "--output-dir", str(folder)])) == 0
    design = read(folder, "design.json")
    assert design["history_source"] == "synthetic_72_hours"
    assert design["expected_decisions"] == 24 and not design["online_requested"]
    assert len(read(folder, "request_manifest.json")) == 24
    assert (
        not (folder / "decisions.jsonl").exists()
        and not (tmp_path / "external").exists()
    )
    assert not (folder / "trace").exists()
    with ZipFile(folder / "experiment_source.zip") as sources:
        assert "probe_hourly_strategy.py" in sources.namelist()
        assert "proto/support/routing.py" in sources.namelist()


@pytest.fixture
def real_sdk(monkeypatch):
    # Some legacy AgentSociety tests leave type-only OpenAI stubs in the import table.
    for name in ("openai", "openai.types", "openai.types.chat"):
        module = sys.modules.get(name)
        if module is not None and module.__spec__ is None:
            monkeypatch.delitem(sys.modules, name)


@pytest.mark.usefixtures("real_sdk")
@pytest.mark.parametrize(
    "mode,denied",
    [
        ("frozen", None),
        ("updated", None),
        ("frozen", "first_plan"),
        ("frozen", "last_appraisal"),
    ],
)
def test_collect_via_real_sdk_and_local_http(tmp_path, monkeypatch, mode, denied):
    folder = tmp_path / "controlled_transport"
    calls = Counter()

    def reply(request):
        req = json.loads(request.content)
        assert req["model"] == "glm-4-flashx" and req["temperature"] == 0.1
        if denied == "first_plan":
            calls["denied"] += 1
            return httpx.Response(
                401, json={"error": {"message": "invalid test credential"}}
            )
        prompt = json.loads(req["messages"][1]["content"].split("\n", 1)[1])
        if "schema_version" in prompt and "actions" in prompt:
            calls["plan"] += 1
            (offer,) = prompt["inputs"]["available_opportunities"]
            action = next(a for a in prompt["actions"] if a.startswith("engage_goal"))
            if (
                offer["visible_description"] == DEFERRABLE_SERVICE_DESCRIPTION
                and denied != "last_appraisal"
            ):
                action = prompt["defer_options"]["o1"][-1]
            raw = dict(
                action=action,
                additional_apps=[],
                attitude=0.6,
                subjective_norm=0.5,
                perceived_control=0.5,
                confidence=0.85,
                reason="Controlled Plan response.",
            )
        elif "World / Stage Context" in prompt:
            calls["appraisal"] += 1
            if denied == "last_appraisal" and calls["plan"] == 24:
                return httpx.Response(
                    429, json={"error": {"message": "paused in local test"}}
                )
            raw = dict(
                perceived_task_difficulty=40,
                perceived_task_risk=40,
                felt_control=60,
                expected_help_effectiveness=60,
                task_value=50,
                judge_confidence=0.85,
                reason="Controlled appraisal.",
            )
        else:
            calls["strategy"] += 1
            raw = dict(
                attempt_self_score=0.02,
                seek_help_score=0.95,
                avoid_score=0.03,
                dominant_strategy="seek_help_then_attempt",
                judge_confidence=0.85,
                reason="Controlled strategy.",
            )
        return httpx.Response(
            200,
            json={
                "id": "local-reply",
                "object": "chat.completion",
                "model": req["model"],
                "created": 0,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(raw)},
                    }
                ],
            },
        )

    class LocalClient(httpx.AsyncClient):
        def __init__(self, **options):
            assert options["follow_redirects"] is False
            super().__init__(transport=httpx.MockTransport(reply), **options)

    monkeypatch.setattr(httpx, "AsyncClient", LocalClient)
    monkeypatch.setenv("LLM_API_KEY", "local-simulation-credential")
    status = asyncio.run(
        main(
            [
                "--online",
                "--synthetic-history",
                "--feedback-mode",
                mode,
                "--output-dir",
                str(folder),
            ]
        )
    )
    report = read(folder, "summary.json")
    trace = next((folder / "trace").glob("*.jsonl")).read_text()
    assert "local-simulation-credential" not in trace
    events = [json.loads(line) for line in trace.splitlines()]
    rows = [
        json.loads(line)
        for line in (folder / "decisions.jsonl").read_text().splitlines()
    ]
    design = read(folder, "design.json")
    assert design["feedback_mode"] == report["feedback_mode"] == mode
    if mode == "updated":
        states = read(folder, design["feedback_states_file"])
        assert (
            sha256((folder / "feedback_states.json").read_bytes()).hexdigest()
            == design["feedback_states_sha256"]
        )
        digests = {
            condition: sha256(
                json.dumps(
                    state, ensure_ascii=False, sort_keys=True, allow_nan=False
                ).encode()
            ).hexdigest()
            for condition, state in states.items()
        }
        assert digests["success"] != digests["failure"]
    else:
        digests = {"success": None, "failure": None}
        assert not (folder / "feedback_states.json").exists()
    for record in [*rows, *events]:
        assert record["feedback_mode"] == mode
        assert record["feedback_state_sha256"] == digests[record["condition"]]
    assert (
        report["http_requests"]
        == sum(calls.values())
        == sum(row["http_requests"] for row in rows)
    )
    counts = Counter(e["module"] for e in events if e["kind"] == "request")
    if denied == "first_plan":
        assert (
            status != 0
            and not report["complete"]
            and report["stop_reason"] == "provider_error"
        )
        assert len(rows) == 1 and rows[0]["task_admitted"] is None
        assert rows[0]["lower"] is None and report["http_requests"] == 1
        assert "by_scene" not in report
        return
    if denied == "last_appraisal":
        assert status != 0 and not report["complete"] and "by_scene" not in report
        assert len(rows) == 24 and report["http_requests"] == 71
        assert rows[-1]["task_admitted"] and rows[-1]["lower"] is None
        assert rows[-1]["interrupted_stage"] == "post_admission"
        assert counts["strategy"] == 23
        assert report["technical"]["admitted_without_lower_record"] == 1
        return
    assert status == 0 and report["complete"] and report["stop_reason"] is None
    assert calls == {"plan": 24, "appraisal": 12, "strategy": 12}
    assert counts == {"app_plan": 24, "task_appraisal": 12, "strategy": 12}
    received = [
        e
        for e in events
        if e["module"] == "probe_helper" and e["kind"] == "request_received"
    ]
    assert received
    for row in rows:
        if row["scene"] == "S1":
            assert row["defer_hours"] == 24 and row["lower"] is None
        else:
            low = row["lower"]
            assert low["lower_valid"] and low["help_delivery_status"] == "unobserved"
            matching = [
                e
                for e in received
                if (e["pair_id"], e["member"]) == (row["pair_id"], row["member"])
            ]
            assert len(matching) == int(low["help_request_dispatched"])
    assert report["overall"]["help_all_decisions"]["confirmed_yes"] == len(received)
    assert report["overall"]["help_among_confirmed_admissions"]["denominator"] == 12


def test_http_budget_includes_repairs():
    budget = HTTPBudget()

    async def exercise():
        for _ in range(24):
            budget.case_start = budget.count
            for _ in range(6):
                await budget.before_send(None)
            with pytest.raises(RuntimeError):
                await budget.before_send(None)
        budget.case_start = budget.count
        with pytest.raises(RuntimeError):
            await budget.before_send(None)

    asyncio.run(exercise())
    assert budget.count == 144
