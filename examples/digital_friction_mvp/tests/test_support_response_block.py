from __future__ import annotations

import asyncio
from types import SimpleNamespace

from proto.outcome_model import derive_effective_support_features
from proto.support_protocol import SupportRequest
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


def test_valid_llm_json_generates_support_response() -> None:
    block = _block(
        payload="""{
            "support_style":"enabling",
            "instruction_quality":"high",
            "autonomy_preservation":"high",
            "proxy_completion_level":"none",
            "emotional_tone":"patient",
            "response_delay":"immediate",
            "confidence":0.86,
            "responded":true,
            "response_text":"I will guide you step by step.",
            "rationale":"keeps agency"
        }"""
    )
    response = asyncio.run(block.generate_response(_request()))
    assert response.support_style == "enabling"
    assert response.source == "llm_family_helper"
    assert response.responded is True


def test_invalid_schema_returns_unavailable() -> None:
    block = _block(payload='{"support_style":"enabling","success":true}')
    response = asyncio.run(block.generate_response(_request()))
    assert response.support_style == "unavailable"
    assert response.source == "llm_unavailable"
    assert response.audit_status in {"invalid_schema", "parse_failed"}


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
