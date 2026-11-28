"""Exercise the paid runner with an in-memory HTTP transport. Never contact the model provider."""

import asyncio
from collections import Counter, defaultdict
import json
import sys

import httpx
import pytest

from run_help_mode_pairs import main
import run_help_mode_pairs as runner
from proto.llm_trace import LLMRunInterrupted


def _load(path):
    return json.loads(path.read_text())


def test_offline_archives_rule_and_lower_templates_without_requests(
    tmp_path, monkeypatch
):
    for name in ("LLM_API_KEY", "ZHIPUAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    folder = tmp_path / "offline"
    assert asyncio.run(main(["--synthetic-history", "--output-dir", str(folder)])) == 0
    design = _load(folder / "design.json")
    assert design["max_initial_requests"] == 240
    assert (
        design["http_request_limit_with_repairs"] == 480 and design["sdk_retries"] == 0
    )
    templates = _load(folder / "lower_templates.json")
    assert len(templates) == 10
    for arms in templates.values():
        assert arms["guided"]["rule_inputs"] == arms["proxy"]["rule_inputs"]
        assert arms["guided"]["rule_weights"] == arms["proxy"]["rule_weights"]
    assert not (folder / "decisions.jsonl").exists()
    assert not (folder / "trace").exists()


@pytest.mark.parametrize("case", ["complete", "rate_limit", "tampered_lower"])
def test_verified_pipeline_through_local_http(tmp_path, monkeypatch, case):
    # Some older tests install type-only OpenAI stand-ins during pytest collection.
    for name in ("openai", "openai.types", "openai.types.chat"):
        module = sys.modules.get(name)
        if module is not None and module.__spec__ is None:
            monkeypatch.delitem(sys.modules, name)
    folder = tmp_path / "run"
    counts = Counter()
    last_appraisal = None

    def respond(request):
        nonlocal last_appraisal
        req = json.loads(request.content)
        assert req["model"] == "glm-4-flashx"
        body = json.loads(req["messages"][1]["content"].split("\n", 1)[1])
        if "inputs" in body:
            counts["plan"] += 1
            if case == "rate_limit" and counts["plan"] == 4:
                return httpx.Response(429, json={"error": {"message": "local limit"}})
            action = (
                "no_app"
                if counts["plan"] % 7 == 0
                else next(a for a in body["actions"] if a.startswith("engage_goal@"))
            )
            result = dict(
                action=action,
                additional_apps=[],
                reason="test",
                confidence=0.9,
                attitude=0.5,
                subjective_norm=0.6,
                perceived_control=0.5,
            )
        elif "World / Stage Context" in body:
            counts["appraisal"] += 1
            episodes = body["Task-Specific Memory"]["recent_task_episodes"]
            assert len(episodes) == 3
            last_appraisal = (
                19 if "resident entered" in episodes[-1]["completion_action"] else 71
            )
            result = dict(
                perceived_task_difficulty=last_appraisal,
                perceived_task_risk=25,
                felt_control=60,
                expected_help_effectiveness=60,
                task_value=65,
                reason="test",
                judge_confidence=0.9,
            )
        else:
            counts["strategy"] += 1
            assert body["task_appraisal"]["perceived_task_difficulty"] == last_appraisal
            result = dict(
                attempt_self_score=0.01,
                seek_help_score=0.98,
                avoid_score=0.01,
                dominant_strategy="seek_help_then_attempt",
                judge_confidence=0.8,
                reason="test",
            )
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": req["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(result)},
                    }
                ],
            },
        )

    class OfflineHTTP(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", OfflineHTTP)
    monkeypatch.setenv("LLM_API_KEY", "local-mock-key")
    args = ["--online", "--synthetic-history", "--output-dir", str(folder)]
    if case == "tampered_lower":
        original = runner.capture_lower

        async def tamper(residents, prepared):
            frozen = await original(residents, prepared)
            first = prepared["manifest"][0]
            strategy = frozen[str(first["profile_id"])][first["condition"]]["strategy"]
            strategy["messages"][0]["content"] += " unexpected"
            return frozen

        monkeypatch.setattr(runner, "capture_lower", tamper)
        with pytest.raises(LLMRunInterrupted):
            asyncio.run(main(args))
        report = _load(folder / "summary.json")
        assert (folder / "decisions.jsonl").read_text() == ""
        assert report["http_requests"] == report["uncommitted_point_http_requests"] == 2
        assert counts == {"plan": 1, "appraisal": 1}
        return
    status = asyncio.run(main(args))
    report = _load(folder / "summary.json")
    rows = [
        json.loads(line)
        for line in (folder / "decisions.jsonl").read_text().splitlines()
    ]
    assert (
        sum(r["http_requests"] for r in rows)
        == report["http_requests"]
        == sum(counts.values())
    )
    if case == "rate_limit":
        assert (
            status
            and not report["complete"]
            and report["stop_reason"] == "provider_error"
        )
        assert counts == {"plan": 4, "appraisal": 3, "strategy": 3}
        assert rows[-1]["interrupted_stage"] == "plan"
        return
    assert status == 0 and report["complete"] and not report["stop_reason"]
    assert counts == {"plan": 80, "appraisal": 69, "strategy": 69}
    observed_rules = defaultdict(set)
    received = 0
    for row in rows:
        low = row["lower"]
        if not row["task_admitted"]:
            assert low is None and row["policy_choice"] == "no_app"
            continue
        assert low["operation_started"] is None and low["task_outcome"] is None
        assert low["lower_valid"] and low["help_delivery_status"] == "unobserved"
        observed_rules[row["profile_id"]].add(
            json.dumps([low["rule_inputs"], low["rule_weights"]])
        )
        if low["help_request_dispatched"]:
            req = low["help_request"]
            assert req["requester_agent_id"] == row["profile_id"]
            assert req["helper_agent_id"] == row["selected_rank"] + 10
            received += 1
    assert len(observed_rules) == 10 and all(
        len(v) == 1 for v in observed_rules.values()
    )
    trace = next((folder / "trace").glob("*.jsonl"))
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert 0 < received == sum(e["kind"] == "request_received" for e in events)
    assert all(len(e["assigned_episode_ids"]) == 3 for e in events)
