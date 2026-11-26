from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from proto.outcome_model import derive_effective_support_features
from proto.support_protocol import SupportRequest, classify_support_delivery
from proto.support_response_block import SupportResponseBlock


class _LLM:
    def __init__(self, payload=None, exc: Exception | None = None):
        self.payload = payload
        self.exc = exc

    async def atext_request(self, *args, **kwargs):
        if self.exc is not None:
            raise self.exc
        return self.payload


def _request() -> SupportRequest:
    return SupportRequest(
        request_id="r1",
        requester_agent_id=1,
        helper_agent_id=2,
        day=0,
        tick=1.0,
        task_id="task",
        task_family="account_login_verification",
        friction_type="verification",
        difficulty=0.6,
        need_type="daily_task",
        support_sensitivity=0.7,
    )


def _block(payload=None, exc: Exception | None = None) -> SupportResponseBlock:
    toolbox = SimpleNamespace(llm=_LLM(payload=payload, exc=exc))
    return SupportResponseBlock(toolbox=toolbox, agent_memory=None)


@pytest.mark.parametrize("echoed_task_id", [False, True])
def test_valid_llm_json_generates_support_response(echoed_task_id: bool) -> None:
    request = _request()
    block = _block(
        payload=json.dumps({
            "support_style": "enabling", "instruction_quality": "high", "autonomy_preservation": "high",
            "proxy_completion_level": "none", "emotional_tone": "patient", "response_delay": "immediate",
            "confidence": 0.86, "responded": True, "response_text": "I will guide you step by step.",
            "rationale": "keeps agency", **({"task_id": request.task_id} if echoed_task_id else {}),
        })
    )
    response = asyncio.run(block.generate_response(request))
    assert response.support_style == "enabling"
    assert response.source == "llm_family_helper"
    assert response.responded is True
    assert response.request_id == request.request_id
    assert response.audit_status == "ok"


def test_invalid_schema_returns_unavailable() -> None:
    block = _block(payload='{"support_style":"enabling","success":true}')
    response = asyncio.run(block.generate_response(_request()))
    assert response.support_style == "unavailable"
    assert response.source == "llm_unavailable"
    assert response.audit_status in {"invalid_schema", "parse_failed"}


@pytest.mark.parametrize("changes", [
    {"task_id": "different-task"}, {"task_id": "task", "request_id": "r1"},
    {"task_id": "task", "success": True}, {"task_id": "task", "responded": "true"},
    {"responded": "false"}, {"responded": 1}, {"responded": False},
    {"support_style": "unavailable"}, {"response_delay": "no_response"},
    {"instruction_quality": "none"},
    {"support_style": "substituting", "instruction_quality": "none", "proxy_completion_level": "not_applicable"},
    {"confidence": "NaN"}, {"confidence": float("nan")}, {"confidence": float("inf")},
    {"confidence": True}, {"confidence": 1.1}, {"confidence": -0.1},
])
def test_malformed_helper_response_is_a_technical_failure(changes: dict) -> None:
    payload = {
        "support_style": "enabling", "instruction_quality": "high",
        "autonomy_preservation": "high", "proxy_completion_level": "none",
        "emotional_tone": "patient", "response_delay": "immediate", "confidence": 0.86,
        "responded": True, "response_text": "Try this.", "rationale": "Can guide.",
        **changes,
    }
    response = asyncio.run(_block(payload=json.dumps(payload)).generate_response(_request()))
    assert response.audit_status == "invalid_schema"
    assert classify_support_delivery(response) == "technical_failure"


def test_well_formed_absent_helper_is_a_social_observation() -> None:
    payload = {
        "support_style": "unavailable", "instruction_quality": "none",
        "autonomy_preservation": "not_applicable", "proxy_completion_level": "none",
        "emotional_tone": "not_applicable", "response_delay": "no_response",
        "confidence": 0.86, "responded": False, "response_text": "", "rationale": "Away.",
    }
    response = asyncio.run(_block(payload=json.dumps(payload)).generate_response(_request()))
    assert response.audit_status == "ok"
    assert classify_support_delivery(response) == "not_delivered"


def test_low_confidence_returns_unavailable() -> None:
    block = _block(
        payload="""{
            "support_style":"enabling",
            "instruction_quality":"high",
            "autonomy_preservation":"high",
            "proxy_completion_level":"none",
            "emotional_tone":"patient",
            "response_delay":"immediate",
            "confidence":0.2,
            "responded":true,
            "response_text":"Try this.",
            "rationale":"low confidence"
        }"""
    )
    response = asyncio.run(block.generate_response(_request()))
    assert response.support_style == "unavailable"
    assert response.audit_status == "low_confidence"


def test_request_failure_returns_unavailable() -> None:
    block = _block(exc=RuntimeError("network down"))
    response = asyncio.run(block.generate_response(_request()))
    assert response.support_style == "unavailable"
    assert response.audit_status == "request_error"


def test_response_text_does_not_drive_numeric_features() -> None:
    request = _request()
    base = {
        "support_style": "enabling",
        "instruction_quality": "medium",
        "autonomy_preservation": "medium",
        "proxy_completion_level": "none",
        "emotional_tone": "patient",
        "response_delay": "immediate",
        "confidence": 0.8,
        "responded": True,
        "rationale": "same",
    }
    left = derive_effective_support_features(
        {
            **base,
            "request_id": request.request_id,
            "requester_agent_id": request.requester_agent_id,
            "helper_agent_id": request.helper_agent_id,
            "response_text": "short",
            "source": "llm",
            "audit_status": "ok",
        },
        {},
    )
    right = derive_effective_support_features(
        {
            **base,
            "request_id": request.request_id,
            "requester_agent_id": request.requester_agent_id,
            "helper_agent_id": request.helper_agent_id,
            "response_text": "a very different audit replay sentence",
            "source": "llm",
            "audit_status": "ok",
        },
        {},
    )
    assert left == right
