from __future__ import annotations

import pytest

from proto.support_protocol import (
    SupportRequest,
    SupportResponse,
    support_style_to_support_mode,
)


def _request_payload() -> dict:
    return {
        "request_id": "r1",
        "requester_agent_id": 1,
        "helper_agent_id": 2,
        "day": 0,
        "tick": 32400.0,
        "task_id": "task-1",
        "task_family": "account_login_verification",
        "friction_type": "verification",
        "difficulty": 0.6,
        "need_type": "daily_task",
        "support_sensitivity": 0.7,
        "strategy_type": "seek_help_then_attempt",
        "support_need": "step by step help",
        "task_appraisal": {"felt_control": 42},
        "memory_context": {"same_task_failure_count": 1},
        "env_context": {"friction_level": 2},
        "profile_summary": {"age_bucket": "65plus"},
        "relationship": {"relationship_type": "family"},
    }


def test_support_request_round_trips() -> None:
    request = SupportRequest.from_dict(_request_payload())
    assert SupportRequest.from_dict(request.to_dict()).to_dict() == request.to_dict()


def test_support_response_round_trips_and_maps_style() -> None:
    response = SupportResponse.from_dict(
        {
            "request_id": "r1",
            "requester_agent_id": 1,
            "helper_agent_id": 2,
            "support_style": "enabling",
            "instruction_quality": "high",
            "autonomy_preservation": "high",
            "proxy_completion_level": "none",
            "emotional_tone": "patient",
            "response_delay": "immediate",
            "confidence": 0.82,
            "responded": True,
            "response_text": "I can guide you one step at a time.",
            "rationale": "patient stepwise guidance",
            "source": "llm_family_helper",
            "audit_status": "ok",
        }
    )
    assert SupportResponse.from_dict(response.to_dict()).to_dict() == response.to_dict()
    assert support_style_to_support_mode("enabling") == "enabling_support"
    assert support_style_to_support_mode("substituting") == "substituting_support"
    assert support_style_to_support_mode("unavailable") == "not_applicable"


def test_forbidden_keys_are_rejected_recursively() -> None:
    payload = _request_payload()
    payload["task_appraisal"] = {"helplessness_delta": 3}
    with pytest.raises(ValueError, match="forbidden"):
        SupportRequest.from_dict(payload)

    with pytest.raises(ValueError, match="forbidden"):
        SupportResponse.from_dict(
            {
                "support_style": "enabling",
                "instruction_quality": "high",
                "autonomy_preservation": "high",
                "proxy_completion_level": "none",
                "emotional_tone": "patient",
                "response_delay": "immediate",
                "confidence": 0.7,
                "responded": True,
                "response_text": "",
                "rationale": "",
                "source": "llm",
                "audit_status": "ok",
                "success": True,
            }
        )


def test_label_ranges_are_strict() -> None:
    with pytest.raises(ValueError, match="support_style"):
        SupportResponse(support_style="helpful")  # type: ignore[arg-type]


def test_unavailable_fallback_contains_no_outcome_or_helplessness_keys() -> None:
    response = SupportResponse.unavailable(
        request=SupportRequest.from_dict(_request_payload()),
        source="llm_unavailable",
        audit_status="request_error",
    )
    assert response.support_style == "unavailable"
    assert response.responded is False
    assert not {"outcome_type", "success", "helplessness_delta"} & set(
        response.to_dict()
    )
