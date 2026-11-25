from __future__ import annotations

import asyncio
import json

import pytest

from proto.app_entry.needs import (
    DIGITAL_NEED_LABELS,
    DIGITAL_NEED_TO_APP_CONTEXTS,
    DigitalNeedsBlock,
    sanitize_digital_needs_payload,
)
from proto.app_entry.types import APP_CONTEXT_SET


class FakeLLM:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls = 0

    async def atext_request(self, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "need_pressures": {label: 0.2 for label in DIGITAL_NEED_LABELS},
        "active_intent": 0.7,
        "intensity_hint": 0.5,
        "confidence": 0.8,
        "reasoning": "Observed calibration evidence supports moderate use pressure.",
    }
    payload.update(overrides)
    return payload


def test_needs_sanitizer_requires_exact_nine_need_scores() -> None:
    sanitized, status = sanitize_digital_needs_payload(_payload())

    assert status == "ok"
    assert sanitized is not None
    assert set(sanitized["need_pressures"]) == set(DIGITAL_NEED_LABELS)

    missing = dict(_payload())
    missing["need_pressures"] = dict(sanitized["need_pressures"])
    del missing["need_pressures"][DIGITAL_NEED_LABELS[-1]]
    assert sanitize_digital_needs_payload(missing) == (None, "invalid_schema")


def test_need_context_mapping_is_complete_and_uses_known_contexts() -> None:
    assert set(DIGITAL_NEED_TO_APP_CONTEXTS) == set(DIGITAL_NEED_LABELS)
    assert {
        context
        for contexts in DIGITAL_NEED_TO_APP_CONTEXTS.values()
        for context in contexts
    } <= set(APP_CONTEXT_SET)
    assert DIGITAL_NEED_TO_APP_CONTEXTS["avoidance_need"] == ()
    assert DIGITAL_NEED_TO_APP_CONTEXTS["no_app_need"] == ()


@pytest.mark.parametrize(
    "invalid",
    [
        {"unknown_need": 0.4},
        {"finance_need": 1.1},
    ],
)
def test_needs_sanitizer_rejects_unknown_or_out_of_range_scores(invalid) -> None:
    pressures = {label: 0.2 for label in DIGITAL_NEED_LABELS}
    pressures.update(invalid)
    assert sanitize_digital_needs_payload(
        _payload(need_pressures=pressures)
    ) == (None, "invalid_schema")


def test_needs_block_derives_dominant_need_and_never_accepts_app_bundle_fields() -> None:
    payload = _payload()
    payload["need_pressures"] = {
        **payload["need_pressures"],
        "finance_need": 0.9,
    }
    result = asyncio.run(
        DigitalNeedsBlock().forward(
            llm=FakeLLM([json.dumps(payload)]),
            input_payload={"day": 4, "hour": 9, "habit_active": True},
            json_attempts=1,
        )
    )

    assert result.dominant_need == "finance_need"
    assert "app_context_counts" not in result.to_dict()
    assert "primary_context" not in result.to_dict()


def test_needs_block_exhausts_attempts_without_rule_fallback() -> None:
    llm = FakeLLM(["not json"] * 2)

    with pytest.raises(ValueError, match="failed after bounded attempts"):
        asyncio.run(
            DigitalNeedsBlock().forward(
                llm=llm,
                input_payload={"day": 4, "hour": 9},
                json_attempts=1,
            )
        )

    assert llm.calls == 2


def test_needs_block_bounds_json_attempts_and_records_prompt_schema_hashes() -> None:
    payload = _payload()
    llm = FakeLLM([json.dumps(payload)])

    result = asyncio.run(
        DigitalNeedsBlock().forward(
            llm=llm,
            input_payload={"day": 4, "hour": 9},
            prompt_version="digital_needs_test_v2",
            json_attempts=99,
        )
    )

    assert result.audit["prompt_version"] == "digital_needs_test_v2"
    assert len(result.audit["prompt_hash"]) == 16
    assert len(result.audit["schema_hash"]) == 16
    assert result.audit["json_attempts_configured"] == 5
