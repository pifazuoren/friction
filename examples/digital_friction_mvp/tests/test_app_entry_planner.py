from __future__ import annotations

import asyncio
import json

import pytest

from proto.app_entry.needs import DigitalNeedsResult
from proto.app_entry.planner import DigitalAppEntryPlanBlock, sanitize_app_entry_plan_payload


class FakeLLM:
    def __init__(self, responses: list[object]):
        self._responses = list(responses)
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    async def atext_request(self, **kwargs):
        self.calls += 1
        self.requests.append(dict(kwargs))
        if not self._responses:
            raise RuntimeError("no fake response configured")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _needs() -> DigitalNeedsResult:
    return DigitalNeedsResult(
        need_pressures={
            "social_need": 0.4,
            "entertainment_need": 0.2,
            "finance_need": 0.7,
            "tool_need": 0.1,
            "health_need": 0.1,
            "habitual_check_need": 0.5,
            "idle_browse_need": 0.2,
            "avoidance_need": 0.3,
            "no_app_need": 0.1,
        },
        active_intent=0.8,
        intensity_hint=0.5,
        confidence=0.9,
        reasoning="Stable finance-use pressure.",
    )


def _active_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "active": True,
        "app_context_counts": {
            "finance_context": 3,
            "communication_social_context": 1,
        },
        "attitude": 0.72,
        "subjective_norm": 0.4,
        "perceived_control": 0.38,
        "confidence": 0.74,
        "reasoning": "Habit supports use while recent failures reduce control.",
    }
    payload.update(overrides)
    return payload


def _run(
    llm: FakeLLM,
    *,
    min_confidence: float = 0.6,
    cap: int = 6,
    json_attempts: int = 1,
):
    return asyncio.run(
        DigitalAppEntryPlanBlock().forward(
            llm=llm,
            needs=_needs(),
            candidate_contexts={
                "finance_context": 0.7,
                "communication_social_context": 0.3,
            },
            input_payload={"day": 4, "hour": 9, "habit_strength": 0.8},
            intensity_profile={
                "same_hour_mean_exposures": 3.5,
                "active_exposure_cap": cap,
            },
            min_confidence=min_confidence,
            json_attempts=json_attempts,
        )
    )


def test_plan_block_accepts_valid_active_plan_and_records_audit() -> None:
    llm = FakeLLM([json.dumps(_active_payload())])

    result = _run(llm)

    assert result.active is True
    assert result.active_event_app_exposures == 4
    assert result.primary_context == "finance_context"
    assert result.app_context_counts == {
        "finance_context": 3,
        "communication_social_context": 1,
    }
    assert result.audit["parse_status"] == "ok"
    assert result.audit["json_attempts_configured"] == 1
    assert result.audit["json_attempts_used"] == 1
    assert result.audit["actual_requests"] == 1
    assert result.audit["repair_requests"] == 0
    for key in (
        "prompt_hash",
        "schema_hash",
        "candidate_hash",
        "payload_hash",
        "response_hash",
    ):
        assert len(result.audit[key]) == 16

    user_content = llm.requests[0]["dialog"][1]["content"]
    assert '"active_exposure_maximum": 6' in user_content
    assert '"minimum_confidence": 0.6' in user_content
    assert '"allowed_app_contexts": ["communication_social_context", "finance_context"]' in user_content


def test_plan_block_accepts_valid_inactive_plan() -> None:
    payload = _active_payload(
        active=False,
        app_context_counts={},
    )

    result = _run(FakeLLM([json.dumps(payload)]))

    assert result.active is False
    assert result.active_event_app_exposures == 0
    assert result.app_context_counts == {}
    assert result.primary_context == "no_app_context"


@pytest.mark.parametrize(
    ("active", "weights", "expected"),
    [
        (False, {}, {}),
        (True, {"finance_context": 1, "communication_social_context": 1},
         {"finance_context": 1, "communication_social_context": 2}),
        (True, {"finance_context": 0}, None),
        (True, {"finance_context": 101}, None),
        (True, {"invented_context": 1}, None),
        (False, {"finance_context": 1}, None),
    ],
)
def test_calibrated_plan_allocates_fixed_total_or_returns_explicit_error(active, weights, expected):
    payload = _active_payload(active=active)
    del payload["app_context_counts"]
    payload["app_context_weights"] = weights
    result, status = sanitize_app_entry_plan_payload(
        payload, candidate_contexts={"finance_context": 1, "communication_social_context": 1},
        calibrated=True, active_exposure_cap=3,
    )
    if expected is None:
        assert result is None and status == "invalid_schema"
    else:
        assert status == "ok"
        assert result["app_context_counts"] == expected
        assert result["active_event_app_exposures"] == (3 if active else 0)


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (
            _active_payload(
                app_context_counts={"health_service_context": 4}
            ),
            "invalid_schema",
        ),
        (
            _active_payload(
                app_context_counts={"finance_context": 1.5},
            ),
            "invalid_schema",
        ),
        (
            _active_payload(
                app_context_counts={},
            ),
            "invalid_schema",
        ),
        (
            _active_payload(
                app_context_counts={"finance_context": 7},
            ),
            "invalid_schema",
        ),
        (
            _active_payload(active_event_app_exposures=4),
            "invalid_schema",
        ),
        (_active_payload(confidence=0.2), "low_confidence"),
        (_active_payload(primary_context="finance_context"), "invalid_schema"),
        (_active_payload(device_id="held-by-runtime"), "invalid_schema"),
    ],
)
def test_plan_block_rejects_invalid_llm_output(
    payload: dict[str, object], status: str
) -> None:
    encoded = json.dumps(payload)
    llm = FakeLLM([encoded, encoded])

    with pytest.raises(ValueError, match=status):
        _run(llm)

    assert llm.calls == 2


def test_plan_block_rejects_broken_inactive_contract() -> None:
    payload = _active_payload(active=False)
    encoded = json.dumps(payload)

    with pytest.raises(ValueError, match="invalid_schema"):
        _run(FakeLLM([encoded, encoded]))


def test_plan_block_derives_exposures_from_context_counts() -> None:
    payload = _active_payload(
        app_context_counts={
            "finance_context": 2,
            "communication_social_context": 2,
        }
    )

    result = _run(FakeLLM([json.dumps(payload)]))

    assert result.active_event_app_exposures == 4
    assert result.to_bundle(device_id="device-a", day=4, hour=9).to_dict()[
        "active_event_app_exposures"
    ] == 4


def test_plan_block_accepts_valid_repair_and_audits_requests() -> None:
    llm = FakeLLM(["not json", json.dumps(_active_payload())])

    result = _run(llm)

    assert result.audit["parse_status"] == "ok_repaired"
    assert result.audit["json_attempts_used"] == 1
    assert result.audit["actual_requests"] == 2
    assert result.audit["repair_requests"] == 1
    assert llm.calls == 2


def test_plan_block_exhausts_bounded_attempts_without_fallback() -> None:
    llm = FakeLLM(["not json"] * 4)

    with pytest.raises(ValueError, match="after bounded attempts: parse_failed"):
        _run(llm, json_attempts=2)

    assert llm.calls == 4


def test_plan_block_failure_reports_last_schema_error_without_raw_text() -> None:
    invalid = _active_payload(primary_context="finance_context")
    encoded = json.dumps(invalid)

    with pytest.raises(ValueError) as captured:
        _run(FakeLLM([encoded, encoded]))

    message = str(captured.value)
    assert "invalid_schema" in message
    assert "last_validation_error=app entry plan output keys do not match" in message
    assert "json_attempts_used=1" in message
    assert "actual_requests=2" in message
    assert "repair_requests=1" in message
    assert encoded not in message


def test_plan_block_rejects_invalid_candidate_pool_before_calling_llm() -> None:
    llm = FakeLLM([json.dumps(_active_payload())])

    with pytest.raises(ValueError, match="unknown app context"):
        asyncio.run(
            DigitalAppEntryPlanBlock().forward(
                llm=llm,
                needs=_needs(),
                candidate_contexts={"invented_context": 1.0},
                input_payload={"day": 4, "hour": 9},
                intensity_profile={"active_exposure_cap": 6},
                min_confidence=0.6,
            )
        )

    assert llm.calls == 0


def test_plan_block_bounds_json_attempts_and_keeps_prompt_version_in_audit() -> None:
    llm = FakeLLM([json.dumps(_active_payload())])

    result = asyncio.run(
        DigitalAppEntryPlanBlock().forward(
            llm=llm,
            needs=_needs(),
            candidate_contexts={
                "finance_context": 0.7,
                "communication_social_context": 0.3,
            },
            input_payload={"day": 4, "hour": 9},
            intensity_profile={"active_exposure_cap": 6},
            prompt_version="app_entry_plan_test_v2",
            json_attempts=99,
        )
    )

    assert result.audit["prompt_version"] == "app_entry_plan_test_v2"
    assert result.audit["json_attempts_configured"] == 5
    assert len(result.audit["prompt_hash"]) == 16
