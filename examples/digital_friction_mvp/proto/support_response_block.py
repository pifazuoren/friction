from __future__ import annotations

from typing import Any

from pydantic import BaseModel

try:
    from agentsociety.agent import Block, BlockOutput, BlockParams
except Exception:  # pragma: no cover - lightweight local-test fallback
    class BlockParams(BaseModel):
        pass

    class BlockOutput(BaseModel):
        pass

    class Block:
        ParamsType = BlockParams
        OutputType = None
        NeedAgent = False

        def __init__(
            self,
            toolbox: Any,
            agent_memory: Any = None,
            block_params: Any = None,
        ) -> None:
            self._toolbox = toolbox
            self._agent_memory = agent_memory
            self.params = block_params or self.ParamsType()
            self._agent = None

        @property
        def llm(self) -> Any:
            return self._toolbox.llm

        def set_agent(self, agent: Any) -> None:
            self._agent = agent

from .llm_psychology import _query_json_payload
from .support_protocol import (
    AUTONOMY_PRESERVATION_LEVELS,
    EMOTIONAL_TONES,
    INSTRUCTION_QUALITIES,
    PROXY_COMPLETION_LEVELS,
    RESPONSE_DELAYS,
    SUPPORT_STYLES,
    SupportRequest,
    SupportResponse,
)


SUPPORT_RESPONSE_PROMPT_VERSION = "support_response_v1_family_helper"
SUPPORT_RESPONSE_KEYS = {
    "support_style",
    "instruction_quality",
    "autonomy_preservation",
    "proxy_completion_level",
    "emotional_tone",
    "response_delay",
    "confidence",
    "responded",
    "response_text",
    "rationale",
}
SUPPORT_RESPONSE_MIN_CONFIDENCE = 0.55
SUPPORT_RESPONSE_TIMEOUT_SECONDS = 45
SUPPORT_RESPONSE_RETRIES = 1


class SupportResponseBlockOutput(BlockOutput):
    response: dict[str, Any]


class SupportResponseBlock(Block):
    ParamsType = BlockParams
    OutputType = SupportResponseBlockOutput
    NeedAgent = True
    name = "support_response"
    description = "Generate bounded family helper support responses."

    async def generate_response(self, request: SupportRequest) -> SupportResponse:
        payload, status = await _query_json_payload(
            llm=getattr(self, "llm", None),
            system_prompt=_build_support_system_prompt(),
            user_payload=_build_support_user_payload(request),
            output_keys=SUPPORT_RESPONSE_KEYS,
            repair_schema_text=_support_repair_schema_text(),
            sanitize_fn=lambda value: _sanitize_support_payload(value),
            timeout=SUPPORT_RESPONSE_TIMEOUT_SECONDS,
            retries=SUPPORT_RESPONSE_RETRIES,
            max_tokens=320,
        )
        if payload is None:
            return SupportResponse.unavailable(
                request=request,
                source="llm_unavailable",
                audit_status=status,
            )
        try:
            response = SupportResponse.from_llm_payload(
                request=request,
                payload=payload,
                source="llm_family_helper",
                audit_status=status,
            )
        except ValueError as exc:
            return SupportResponse.unavailable(
                request=request,
                source="llm_unavailable",
                audit_status="invalid_schema",
                rationale=str(exc)[:300],
            )
        if response.confidence < SUPPORT_RESPONSE_MIN_CONFIDENCE:
            return SupportResponse.unavailable(
                request=request,
                source="llm_unavailable",
                audit_status="low_confidence",
                rationale=response.rationale,
            )
        return response

    async def forward(self, agent_context: Any = None) -> SupportResponseBlockOutput:
        request = getattr(agent_context, "support_request", None)
        if isinstance(request, dict):
            request = SupportRequest.from_dict(request)
        if not isinstance(request, SupportRequest):
            raise ValueError("SupportResponseBlock.forward requires support_request")
        response = await self.generate_response(request)
        return SupportResponseBlockOutput(response=response.to_dict())


def _build_support_system_prompt() -> str:
    return """You generate one structured family helper response for a simulated older adult digital task.
You may decide whether help is enabling, substituting, dismissive, or unavailable.
You must not decide the task outcome, success, helplessness, posterior belief, or scope spillover.
Return exactly one JSON object with the requested keys and no extra text."""


def _build_support_user_payload(request: SupportRequest) -> dict[str, Any]:
    return {
        "prompt_version": SUPPORT_RESPONSE_PROMPT_VERSION,
        "task": {
            "task_id": request.task_id,
            "task_family": request.task_family,
            "friction_type": request.friction_type,
            "difficulty": request.difficulty,
            "need_type": request.need_type,
            "support_sensitivity": request.support_sensitivity,
        },
        "strategy_type": request.strategy_type,
        "support_need": request.support_need,
        "task_appraisal": request.task_appraisal,
        "memory_context": request.memory_context,
        "env_context": request.env_context,
        "profile_summary": request.profile_summary,
        "relationship": request.relationship,
        "allowed_labels": {
            "support_style": sorted(SUPPORT_STYLES),
            "instruction_quality": sorted(INSTRUCTION_QUALITIES),
            "autonomy_preservation": sorted(AUTONOMY_PRESERVATION_LEVELS),
            "proxy_completion_level": sorted(PROXY_COMPLETION_LEVELS),
            "emotional_tone": sorted(EMOTIONAL_TONES),
            "response_delay": sorted(RESPONSE_DELAYS),
        },
        "forbidden_outputs": [
            "outcome_type",
            "success",
            "helplessness_delta",
            "helplessness_after",
            "posterior",
            "C_family",
            "scope_spillover_total",
        ],
        "required_json_schema": {
            "support_style": "enabling|substituting|dismissive|unavailable",
            "instruction_quality": "none|low|medium|high",
            "autonomy_preservation": "low|medium|high|not_applicable",
            "proxy_completion_level": "none|partial|full|not_applicable",
            "emotional_tone": "patient|neutral|dismissive|not_applicable",
            "response_delay": "immediate|delayed|no_response",
            "confidence": "0.0 to 1.0",
            "responded": "boolean",
            "response_text": "short helper utterance for audit/replay only",
            "rationale": "brief evidence note",
        },
    }


def _support_repair_schema_text() -> str:
    return (
        "Allowed support_style values: enabling, substituting, dismissive, unavailable.\n"
        "Allowed instruction_quality values: none, low, medium, high.\n"
        "Allowed autonomy_preservation values: low, medium, high, not_applicable.\n"
        "Allowed proxy_completion_level values: none, partial, full, not_applicable.\n"
        "Allowed emotional_tone values: patient, neutral, dismissive, not_applicable.\n"
        "Allowed response_delay values: immediate, delayed, no_response.\n"
        "Do not include outcome_type, success, helplessness_delta, helplessness_after, posterior, C_family, or scope_spillover_total."
    )


def _sanitize_support_payload(payload: Any) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    forbidden = {
        "outcome_type",
        "success",
        "success_label",
        "helplessness_delta",
        "helplessness_after",
        "final_helplessness_score",
        "posterior",
        "posterior_update_weight",
        "C_family",
        "scope_spillover_total",
    }
    if any(key in payload for key in forbidden):
        return None, "invalid_schema"
    if set(payload) - SUPPORT_RESPONSE_KEYS:
        return None, "invalid_schema"
    if not SUPPORT_RESPONSE_KEYS.issubset(set(payload)):
        return None, "invalid_schema"
    try:
        response = SupportResponse(
            support_style=str(payload.get("support_style", "unavailable")),
            instruction_quality=str(payload.get("instruction_quality", "none")),
            autonomy_preservation=str(
                payload.get("autonomy_preservation", "not_applicable")
            ),
            proxy_completion_level=str(
                payload.get("proxy_completion_level", "not_applicable")
            ),
            emotional_tone=str(payload.get("emotional_tone", "not_applicable")),
            response_delay=str(payload.get("response_delay", "no_response")),
            confidence=float(payload.get("confidence", 0.0)),
            responded=bool(payload.get("responded", False)),
            response_text=str(payload.get("response_text", ""))[:800],
            rationale=str(payload.get("rationale", ""))[:300],
            source="llm_family_helper",
            audit_status="ok",
        )
    except (TypeError, ValueError):
        return None, "invalid_schema"
    sanitized = {
        key: response.to_dict()[key]
        for key in SUPPORT_RESPONSE_KEYS
        if key in response.to_dict()
    }
    return sanitized, "ok"
