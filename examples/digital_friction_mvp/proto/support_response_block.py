from __future__ import annotations

import json
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

from .llm_psychology import _extract_json_object, _query_json_payload
from .support_protocol import (
    AUTONOMY_PRESERVATION_LEVELS,
    EMOTIONAL_TONES,
    INSTRUCTION_QUALITIES,
    PROXY_COMPLETION_LEVELS,
    RESPONSE_DELAYS,
    SUPPORT_RESPONSE_KEYS,
    SUPPORT_RESPONSE_MIN_CONFIDENCE,
    SUPPORT_STYLES,
    SupportRequest,
    SupportResponse,
)


SUPPORT_RESPONSE_PROMPT_VERSION = "support_response_v3_requested_style"
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
        context = _build_support_user_payload(request)
        system_prompt = _build_support_system_prompt()
        payload, status = await _query_json_payload(
            trace_module="helper",
            llm=getattr(self, "llm", None),
            system_prompt=system_prompt,
            user_payload=context,
            output_keys=SUPPORT_RESPONSE_KEYS,
            repair_schema_text="",
            repair_dialog_factory=lambda raw, status: _support_repair_dialog(
                system_prompt, context, raw, status
            ),
            sanitize_fn=lambda value: _sanitize_support_payload(value, request.task_id),
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
    choices = {
        "support_style": SUPPORT_STYLES,
        "instruction_quality": INSTRUCTION_QUALITIES,
        "autonomy_preservation": AUTONOMY_PRESERVATION_LEVELS,
        "proxy_completion_level": PROXY_COMPLETION_LEVELS,
        "emotional_tone": EMOTIONAL_TONES,
        "response_delay": RESPONSE_DELAYS,
    }
    labels = "\n".join(f"{key}: {' / '.join(sorted(values))}" for key, values in choices.items())
    return (
        f"Family helper decision, {SUPPORT_RESPONSE_PROMPT_VERSION}. The user supplies facts about "
        "one request for help. The resident may ask for guidance (they operate), proxy help "
        "(you operate), or express no preference (unspecified). Decide what help you actually "
        "provide given the situation. Your response may differ from the request. Output only a new, flat "
        "JSON object. Do not copy the input or continue it. Use exactly these ten fields:\n"
        f"{labels}\nconfidence: JSON number from 0 to 1\nresponded: JSON boolean\n"
        "response_text: short helper utterance, or empty if unavailable\nrationale: brief reason\n"
        "Unavailable requires responded=false, no_response, no instructions, no proxy action, "
        "and not_applicable autonomy. For a reply use responded=true and immediate or delayed. "
        "Enabling or substituting requires concrete guidance or a proxy action. "
        "The task outcome and the older adult's psychological state are decided elsewhere."
    )


def _build_support_user_payload(request: SupportRequest) -> dict[str, Any]:
    return {
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
        **(
            {"requested_support_style": request.requested_support_style}
            if request.requested_support_style is not None else {}
        ),
        "task_appraisal": request.task_appraisal,
        "memory_context": request.memory_context,
        "env_context": request.env_context,
        "profile_summary": request.profile_summary,
        "relationship": request.relationship,
    }


def _support_repair_dialog(system_prompt: str, context: dict, raw: str, status: str) -> list[dict]:
    # A truncated echo of the case has no helper judgment to reformat. Resending that
    # text encouraged the model to finish copying the case during its repair turn.
    parsed = _extract_json_object(raw) or {}
    draft = {
        key: value for key, value in parsed.items()
        if key in SUPPORT_RESPONSE_KEYS and type(value) in (bool, str, int, float)
    }
    message = f"Your previous output failed validation ({status}).\nCase facts:\n"
    message += json.dumps(context, ensure_ascii=False)
    if draft:
        message += "\nKeep any consistent decisions in these prior reply fields:\n"
        message += json.dumps(draft, ensure_ascii=False)
    message += "\nAnswer the request now with one complete ten-field helper reply."
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}]


def _sanitize_support_payload(payload: Any, task_id: str) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(payload, dict):
        return None, "invalid_schema"
    if task_id and payload.get("task_id") == task_id:
        payload = payload.copy()
        del payload["task_id"]
    if set(payload) != SUPPORT_RESPONSE_KEYS:
        return None, "invalid_schema"
    try:
        response = SupportResponse.from_dict(payload)
    except (TypeError, ValueError):
        return None, "invalid_schema"
    values = response.to_dict()
    return {key: values[key] for key in SUPPORT_RESPONSE_KEYS}, "ok"
