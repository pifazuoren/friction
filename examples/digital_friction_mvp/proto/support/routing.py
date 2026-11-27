"""Send a resident's selected help request to the registered family helper."""

from __future__ import annotations

from typing import Any

from ..llm_trace import TraceWriteError
from ..memory.packet import _compact_status_text, _safe_int, compact_support_context
from ..profile_buckets import age_bucket, persona_bucket
from .protocol import SupportRequest, SupportResponse


async def dispatch_family_support_request(
    *,
    requester_id: int,
    helper_id: int,
    registry: dict,
    task: Any,
    strategy: Any,
    task_appraisal: Any,
    task_relevant_memory_packet: dict,
    env: dict,
    profile_summary: dict,
    day: int,
    tick: float,
) -> tuple[SupportRequest, Any, str]:
    """Call the helper for a selected help action. The caller validates the returned response."""
    helper = registry.get(helper_id) if isinstance(registry, dict) else None
    request = SupportRequest(
        request_id=f"{int(requester_id)}-{int(day)}-{int(float(tick))}-{task.task_id}",
        requester_agent_id=int(requester_id),
        helper_agent_id=helper_id if helper_id >= 0 else None,
        day=int(day),
        tick=float(tick),
        task_id=str(task.task_id),
        task_family=str(task.task_family),
        friction_type=str(task.friction_type),
        difficulty=float(task.difficulty),
        need_type=str(task.need_type),
        support_sensitivity=float(task.support_sensitivity),
        strategy_type=str(strategy.strategy_type),
        support_need="help me complete the digital task while preserving my ability to learn",
        task_appraisal={
            "perceived_task_difficulty": float(
                getattr(task_appraisal, "perceived_task_difficulty", 50.0)
            ),
            "perceived_task_risk": float(
                getattr(task_appraisal, "perceived_task_risk", 50.0)
            ),
            "felt_control": float(getattr(task_appraisal, "felt_control", 50.0)),
            "expected_help_effectiveness": float(
                getattr(task_appraisal, "expected_help_effectiveness", 50.0)
            ),
            "task_value": float(getattr(task_appraisal, "task_value", 50.0)),
        },
        memory_context=compact_support_context(task_relevant_memory_packet),
        env_context={
            "digital_stage": str(
                env.get("digital_stage") or env.get("stage_name") or ""
            ),
            "friction_level": _safe_int(env.get("friction_level", 0), 0),
            "complexity_level": _safe_int(env.get("complexity_level", 0), 0),
            "risk_level": _safe_int(env.get("risk_level", 0), 0),
            "assist_level": _safe_int(env.get("assist_level", 0), 0),
            "human_support_level": _safe_int(env.get("human_support_level", 0), 0),
            "accessibility_level": _safe_int(env.get("accessibility_level", 0), 0),
        },
        profile_summary={
            "age_bucket": age_bucket(profile_summary.get("age", -1)),
            "persona_tag": persona_bucket(profile_summary.get("persona", "")),
            "education": _compact_status_text(
                profile_summary.get("education"),
                default="unknown",
            ),
        },
        relationship={
            "relationship_type": "family",
            "mapped_helper_agent_id": helper_id,
        },
    )
    if helper is None or not hasattr(helper, "provide_support"):
        return (
            request,
            SupportResponse.unavailable(
                request=request,
                source="helper_unavailable",
                audit_status="helper_not_found",
            ),
            "helper_not_found",
        )
    try:
        response = await helper.provide_support(request)
    except TraceWriteError:
        raise
    except Exception as exc:
        return (
            request,
            SupportResponse.unavailable(
                request=request,
                source="helper_unavailable",
                audit_status="request_error",
                rationale=str(exc)[:300],
            ),
            "request_error",
        )
    return request, response, "dispatched"
