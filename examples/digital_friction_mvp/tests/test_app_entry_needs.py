from __future__ import annotations

import asyncio
import json

import pytest

from proto.app_entry.needs import (
    COMPACT_NEEDS_PROMPT_VERSION,
    COMPACT_NEEDS_REPAIR_V1,
    COMPACT_NEEDS_REPAIR_VERSION,
    DIGITAL_NEED_LABELS,
    DIGITAL_NEED_TO_APP_CONTEXTS,
    DigitalNeedsBlock,
    DigitalNeedsResult,
    sanitize_digital_needs_payload,
)
from proto.app_entry.intention_contract import COMPACT_PLAN_VERSIONS, COMPACT_PLAN_V7, COMPACT_PLAN_V8, COMPACT_PLAN_V9, compact_needs
from proto.app_entry.types import APP_CONTEXT_SET, _stable_hash


class FakeLLM:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls = 0
        self.dialogs = []

    async def atext_request(self, **kwargs):
        self.calls += 1
        self.dialogs.append(kwargs["dialog"])
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


@pytest.mark.parametrize("high,current,archived", [
    ([], None, "tool_need"),
    (["health_need", "no_app_need"], None, "no_app_need"),
    (["social_need"], "social_need", "social_need"),
])
def test_only_a_unique_maximum_names_a_need_in_the_current_plan(high, current, archived):
    pressures = dict.fromkeys(DIGITAL_NEED_LABELS, .3)
    for name in high:
        pressures[name] = .8
    needs = DigitalNeedsResult.from_sanitized(_payload(need_pressures=pressures))
    assert needs.dominant_need == needs.to_dict()["dominant_need"] == current
    assert needs.to_dict(legacy_tiebreak=True)["dominant_need"] == archived
    for version in COMPACT_PLAN_VERSIONS:
        rendered = compact_needs(needs.to_dict(), version)
        assert rendered["need_pressures"] == pressures
        assert rendered["dominant_need"] == (current if version in {COMPACT_PLAN_V7, COMPACT_PLAN_V8, COMPACT_PLAN_V9} else archived)


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


def test_actual_stratum_typo_is_explained_only_to_the_repair_and_never_auto_corrected():
    # The twelfth live stratum produced this same misspelling at both attempts.
    wrong = _payload(need_pressures={
        "social_need": .5, "entertainment_need": .2, "finance_need": .1, "tool_need": .3,
        "health_need": .0, "habitant_check_need": .0, "idle_browse_need": .1,
        "avoidance_need": .4, "no_app_need": .0,
    }, active_intent=.3, intensity_hint=.5, confidence=.7)
    raw = "```json\n" + json.dumps(wrong) + "\n```"
    corrected = _payload(need_pressures={**wrong["need_pressures"], "habitual_check_need": .7})
    del corrected["need_pressures"]["habitant_check_need"]
    observation = {"hour": 3}
    common = dict(input_payload=observation, prompt_version=COMPACT_NEEDS_PROMPT_VERSION)
    llm = FakeLLM([raw, json.dumps(corrected)])
    result = asyncio.run(DigitalNeedsBlock().forward(llm=llm, **common))
    assert result.need_pressures["habitual_check_need"] == .7
    assert result.audit["parse_status"] == "ok_repaired"
    assert result.audit["repair_prompt_version"] == COMPACT_NEEDS_REPAIR_VERSION
    assert result.audit["repair_prompt_hash"] == _stable_hash(llm.dialogs[1])[:16]
    diagnostic, data = llm.dialogs[1][1]["content"].split("\n", 1)
    assert "缺少必填键 habitual_check_need" in diagnostic
    assert "含有未定义键 habitant_check_need" in diagnostic
    assert json.loads(data) == {"inputs": observation}
    assert "habitant_check_need" not in llm.dialogs[0][1]["content"]
    old = FakeLLM([raw, raw])
    with pytest.raises(ValueError, match="invalid_schema"):
        asyncio.run(DigitalNeedsBlock().forward(llm=old, compact_repair_version=COMPACT_NEEDS_REPAIR_V1, **common))
    assert old.dialogs[0] == llm.dialogs[0] and "habitant_check_need" not in old.dialogs[1][1]["content"]
    repeated = FakeLLM([raw, raw])
    with pytest.raises(ValueError, match="invalid_schema"):
        asyncio.run(DigitalNeedsBlock().forward(llm=repeated, **common))
    assert repeated.calls == 2


@pytest.mark.parametrize("invalid", ["not json", '{"inputs": {"hour": 3}}', '{"need_pressures": null}'])
def test_repair_does_not_invent_key_errors_for_unparseable_or_echoed_observations(invalid):
    llm = FakeLLM([invalid, json.dumps(_payload())])
    result = asyncio.run(DigitalNeedsBlock().forward(
        llm=llm, input_payload={"hour": 3}, prompt_version=COMPACT_NEEDS_PROMPT_VERSION,
    ))
    instruction, evidence = llm.dialogs[1][1]["content"].split("\n", 1)
    assert "缺少必填键" not in instruction and "未定义键" not in instruction
    assert json.loads(evidence) == {"inputs": {"hour": 3}}
    assert result.audit["parse_status"] == "ok_repaired"


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
