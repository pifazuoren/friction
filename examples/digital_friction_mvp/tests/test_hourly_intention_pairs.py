import asyncio
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
import hashlib
import sys
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from probe_hourly_intention import (
    HOUR,
    MODES,
    SIM_HOUR,
    controlled_rule_window,
    load_history,
    login_offer,
    rule_reference,
)
from proto.paired_random import PairedRandomProvider
from run_hourly_intention_pairs import (
    main,
    measure,
    prepare,
    request_order,
    summary,
    verify_contrast,
    verify_shared_person,
)


class FixedTransport:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = 0
        self.transport_errors = []
        self.returned_models = []

    async def atext_request(self, **kwargs):
        self.requests += 1
        return json.dumps(next(self.responses))


def plan_response(kind, offer=None, hour=None):
    using_app = kind == "engage_goal"
    if kind != "legacy":
        token = kind if offer is None else f"{kind}@o1"
        if using_app:
            token += "@open:public_service_context"
        if hour is not None:
            token += f"@{hour}"
        return {
            "action": token,
            "additional_apps": [],
            "attitude": 0.5,
            "subjective_norm": 0.5,
            "perceived_control": 0.5,
            "confidence": 0.8,
            "reason": "Fixed test intent.",
        }
    reply = {
        "active": using_app,
        "app_context_counts": {"public_service_context": 1} if using_app else {},
        "attitude": 0.5,
        "subjective_norm": 0.5,
        "perceived_control": 0.5,
        "confidence": 0.8,
        "reasoning": "Fixed reply.",
    }
    return reply


def test_manifest_pairs_inputs_and_failure_when_any_unregistered_field_changes():
    history = load_history(None)
    stimuli = asyncio.run(prepare(history))
    rows = request_order()
    assert rows == request_order()
    assert Counter(r["mode"] for r in rows) == dict.fromkeys(MODES, 26)
    for mode in MODES:
        by_pair = {}
        for row in rows:
            if row["mode"] == mode:
                by_pair.setdefault(row["pair_id"], []).append(row)
        assert len(by_pair) == 13
        for pair, members in by_pair.items():
            assert {m["member"] for m in members} == {"A", "B"}
            assert len({m["pair_seed"] for m in members}) == 1
            assert len({m["condition"] for m in members}) == (2 if pair.startswith("contrast") else 1)
        success = stimuli[mode]["success"]
        failure = deepcopy(stimuli[mode]["failure"])
        pp, body = failure["messages"][1]["content"].split("\n", 1)
        payload = json.loads(body)
        payload["inputs"]["pre_hour_psychology"]["helplessness"] += 1
        failure["messages"][1]["content"] = pp + "\n" + json.dumps(payload)
        with pytest.raises(ValueError, match="preregistered"):
            verify_contrast(success, failure, mode)
    # A shared treatment bias can evade both within-policy contrast checks.
    for request in stimuli["opportunity_v1"].values():
        prefix, body = request["messages"][1]["content"].split("\n", 1)
        packet = json.loads(body)
        packet["inputs"]["pre_hour_psychology"]["helplessness"] += 1
        request["messages"][1]["content"] = prefix + "\n" + json.dumps(packet)
    verify_contrast(
        stimuli["opportunity_v1"]["success"], stimuli["opportunity_v1"]["failure"], "opportunity_v1"
    )
    with pytest.raises(ValueError, match="shared observations"):
        verify_shared_person(stimuli)


def test_legacy_policy_and_validated_intent_route_different_tasks_under_the_same_ledger():
    history = load_history(None)
    offer = login_offer()[2]["opportunity_id"]
    rows = []
    for spec in request_order():
        mode = spec["mode"]
        if mode == "legacy":
            payload = plan_response("legacy")
        elif spec["condition"] == "success":
            payload = plan_response("engage_goal", offer)
        else:
            payload = plan_response("defer_goal", offer, SIM_HOUR + 4)
        rows.append(asyncio.run(measure(FixedTransport(payload), spec, history)))
    report = summary(rows)
    old, new = (report["conditions"][m] for m in MODES)
    assert old["contrast"]["accepted_model_intent"]["comparable_pairs"] == 0
    assert old["contrast"]["task_admission"] == {"comparable_pairs": 10, "different_pairs": 0}
    assert new["contrast"]["task_admission"] == {"comparable_pairs": 10, "different_pairs": 10}
    assert new["repeat"]["task_admission"] == {"comparable_pairs": 3, "different_pairs": 0}
    for row in rows:
        if row["mode"] == "opportunity_v1":
            if row["condition"] == "success":
                assert row["routed_task_id"] == login_offer()[0].task_id
                assert row["app_context_counts"] == {"public_service_context": 1}
            else:
                assert row["next_review_at_sim_hour"] == SIM_HOUR + 4
                assert row["routed_task_id"] is None and row["app_context_counts"] == {}
    assert report["actual_low_level_attempts"] == 0
    assert rule_reference(history)["routed_task_id"] == login_offer()[0].task_id


def test_invalid_output_has_technical_failure_and_is_never_measured_as_a_valid_no_app():
    history = load_history(None)
    spec = next(r for r in request_order() if r["mode"] == "opportunity_v1")
    row = asyncio.run(measure(FixedTransport({}, {}), spec, history))
    assert row["technical_failure"] and row["repairs"] == 1
    assert row["active"] is None and row["choice_source"] == "technical_failure"
    assert row["task_admitted"] is False
    assert summary([row])["conditions"]["opportunity_v1"]["valid"] == 0


def test_bare_old_goal_cannot_claim_that_an_unrelated_app_admitted_the_login():
    history = load_history(None)
    spec = next(r for r in request_order() if r["mode"] == "opportunity_v1")
    previous_wire = plan_response("engage_goal", login_offer()[2]["opportunity_id"])
    previous_wire.pop("additional_apps")
    previous_wire.update(action="engage_goal@o1", apps=["health_service_context"])
    row = asyncio.run(measure(FixedTransport(previous_wire, previous_wire), spec, history))
    assert not row["plan_valid"] and not row["task_admitted"]
    assert row["goal_after"] is None and row["repairs"] == 1


def test_common_draws_follow_opportunity_and_low_level_decision_not_world_or_time():
    offer = login_offer()[2]["opportunity_id"]
    provider = PairedRandomProvider(101)
    draw = provider.rng(1, offer, 1, "strategy").random()
    assert draw == PairedRandomProvider(101).rng("1", offer, 1, "strategy").random()
    assert (
        len(
            {
                draw,
                provider.rng(1, offer, 2, "strategy").random(),
                provider.rng(1, offer, 1, "outcome").random(),
                provider.rng(1, offer, 1, "help_availability").random(),
                PairedRandomProvider(102).rng(1, offer, 1, "strategy").random(),
            }
        )
        == 5
    )


def test_rule_control_defers_to_next_predicted_activity_or_drops_if_all_hours_idle():
    history = load_history(None)
    idle = replace(history.clock_predictions[HOUR], count=0, context="no_app_context")
    inactive = replace(history, clock_predictions={**history.clock_predictions, HOUR: idle})
    deferred = rule_reference(inactive)
    assert deferred["policy_choice"] == "defer_goal"
    assert deferred["goal_after"]["next_review_at_sim_hour"] == history.next_active_hour(SIM_HOUR)
    dropped = rule_reference(replace(inactive, clock_predictions=dict.fromkeys(range(24), idle)))
    assert dropped["policy_choice"] == "drop_goal"
    assert not dropped["active"] and dropped["routed_task_id"] is None
    window = controlled_rule_window(inactive)
    assert window["generated_hours"] == 48 and len(window["opportunities"]) == 2
    assert window["low_level_attempts_observed"] is None
    for offer in window["opportunities"]:
        assert offer["first_handled_at"] - offer["published_at"] == 9
        assert offer["deferred_at"] == [
            {"at": offer["published_at"], "review_at": offer["first_handled_at"]}
        ]
    assert [r["hour"] for r in window["hours"] if r["routed_task_id"]] == [18, 18]


def test_opt_in_transport_and_artifacts_end_to_end_with_in_memory_client(tmp_path, monkeypatch):
    calls = []

    class SDK:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.reply))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def reply(self, *, messages, model, **parameters):
            calls.append(messages)
            _, body = messages[1]["content"].split("\n", 1)
            with_intent = json.loads(body)["schema_version"] == "hourly_plan_compact_v4"
            text = json.dumps(plan_response("no_app" if with_intent else "legacy"))
            return SimpleNamespace(
                model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
            )

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=SDK))
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=lambda **kwargs: None))
    monkeypatch.setenv("LLM_API_KEY", "test-placeholder")
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", "")
    monkeypatch.setenv("PARALLEL_GROUP_NAME", "")
    monkeypatch.setenv("PROTO_RUN_SOURCE_SHA256", "")
    for online in (False, True):
        folder = tmp_path / ("online-double" if online else "offline")
        args = ["run_hourly_intention_pairs.py", "--synthetic-history", "--output-dir", str(folder)]
        monkeypatch.setattr(sys, "argv", args + (["--online"] if online else []))
        asyncio.run(main())
        assert len(calls) == (52 if online else 0)
        assert (folder / "decisions.jsonl").is_file() is online
    report = json.loads((folder / "summary.json").read_text())
    assert report["conditions"]["opportunity_v1"]["valid"] == 26
    assert report["conditions"]["opportunity_v1"]["actual_requests"] == 26
    assert report["conditions"]["rule"]["model_requests"] == 0
    (trace_file,) = (folder / "trace").glob("*.jsonl")
    events = [json.loads(line) for line in trace_file.read_text().splitlines()]
    assert Counter(e["kind"] for e in events) == {
        "request": 52,
        "response": 52,
        "parse": 52,
        "intent_validation": 26,
    }
    manifest = {(row["mode"], row["pair_id"], row["member"]): row for row in request_order()}
    observed = {}
    for event in events:
        member = (event["mode"], event["pair_id"], event["member"])
        assert event["pair_kind"] == manifest[member]["kind"]
        if event["kind"] != "intent_validation":
            observed.setdefault(event["call_id"], []).append(event)
    assert len(observed) == len(manifest)
    assert {(rows[0]["mode"], rows[0]["pair_id"], rows[0]["member"]) for rows in observed.values()} == set(
        manifest
    )
    for request, response, parsed in observed.values():
        assert [request["kind"], response["kind"], parsed["kind"]] == ["request", "response", "parse"]
        assert request["messages"] and response["raw"] and parsed["status"] == "ok"
        for key in ("query_id", "mode", "pair_id", "member", "pair_kind"):
            assert request[key] == response[key] == parsed[key]
    design = json.loads((folder / "design.json").read_text())
    archive = folder / "experiment_source.zip"
    assert design["source_archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    with ZipFile(archive) as contents:
        for name, digest in design["source_sha256"].items():
            assert hashlib.sha256(contents.read(name)).hexdigest() == digest
        assert {
            "proto/agent.py",
            "proto/paired_random.py",
            "proto/app_entry/planner.py",
            "probe_hourly_intention.py",
            "analysis_entry_calibration_comparison.py",
        } <= set(contents.namelist())
