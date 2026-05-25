from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

try:
    from agentsociety.agent import CitizenAgentBase, MemoryAttribute
except Exception:  # pragma: no cover - lightweight local-test fallback
    @dataclass
    class MemoryAttribute:
        name: str
        type: type
        default_or_value: Any
        description: str = ""
        whether_embedding: bool = False

    class CitizenAgentBase:
        StatusAttributes: list[MemoryAttribute] = []

        def __init__(
            self,
            id: int,
            name: str,
            toolbox: Any,
            memory: Any,
            agent_params: Any = None,
            blocks: Any = None,
        ) -> None:
            self._id = id
            self._name = name
            self._toolbox = toolbox
            self._memory = memory
            self.params = agent_params
            self.blocks = blocks or []

        @property
        def id(self) -> int:
            return self._id

        @property
        def toolbox(self) -> Any:
            return self._toolbox

        @property
        def memory(self) -> Any:
            return self._memory

        @property
        def status(self) -> Any:
            return self._memory.status

        async def update_motion(self) -> None:
            return None

from .support_protocol import SupportRequest, SupportResponse
from .support_response_block import SupportResponseBlock


class FamilyHelperAgent(CitizenAgentBase):
    StatusAttributes = [
        MemoryAttribute(
            name="helper_persona",
            type=dict,
            default_or_value={
                "role": "family_member",
                "support_orientation": "patient_step_by_step",
            },
            description="family helper persona for digital support",
        ),
        MemoryAttribute(
            name="relationship_profiles",
            type=dict,
            default_or_value={},
            description="relationship profiles by requester agent id",
        ),
        MemoryAttribute(
            name="support_histories",
            type=dict,
            default_or_value={},
            description="structured support histories by requester agent id",
        ),
        MemoryAttribute(
            name="chat_histories",
            type=dict,
            default_or_value={},
            description="helper chat histories by requester agent id",
        ),
    ]

    description = "A lightweight family helper agent that returns bounded support responses."

    async def forward(self) -> float:
        await self.update_motion()
        return 0.0

    async def provide_support(self, request: SupportRequest) -> SupportResponse:
        response_block = self._support_response_block()
        response = await response_block.generate_response(request)
        await self._record_support_exchange(request=request, response=response)
        return response

    async def do_chat(self, message: Any) -> str:
        payload = message.payload if isinstance(message.payload, dict) else {}
        content = payload.get("content", {})
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {}
        if not isinstance(content, dict):
            content = {}
        try:
            request_payload = content.get("support_request", content)
            request = SupportRequest.from_dict(request_payload)
        except ValueError:
            response = SupportResponse.unavailable(
                source="chat_unavailable",
                audit_status="invalid_request",
            )
            return json.dumps(response.to_dict(), ensure_ascii=False)
        response = await self.provide_support(request)
        return json.dumps(response.to_dict(), ensure_ascii=False)

    def _support_response_block(self) -> SupportResponseBlock:
        for block in getattr(self, "blocks", []) or []:
            if isinstance(block, SupportResponseBlock):
                return block
        block = SupportResponseBlock(
            toolbox=self.toolbox,
            agent_memory=self.memory,
        )
        block.set_agent(self)
        return block

    async def _record_support_exchange(
        self,
        *,
        request: SupportRequest,
        response: SupportResponse,
    ) -> None:
        requester_key = str(request.requester_agent_id)
        histories = await self.memory.status.get("support_histories", {})
        if not isinstance(histories, dict):
            histories = {}
        requester_history = histories.get(requester_key)
        if not isinstance(requester_history, list):
            requester_history = []
        requester_history.append(
            {
                "request": request.to_dict(),
                "response": response.to_dict(),
            }
        )
        histories[requester_key] = requester_history[-12:]
        await self.memory.status.update("support_histories", histories)

        chat_histories = await self.memory.status.get("chat_histories", {})
        if not isinstance(chat_histories, dict):
            chat_histories = {}
        chat_tail = chat_histories.get(requester_key)
        if not isinstance(chat_tail, list):
            chat_tail = []
        chat_tail.append(
            {
                "request_id": request.request_id,
                "task_family": request.task_family,
                "support_style": response.support_style,
                "responded": response.responded,
                "audit_status": response.audit_status,
            }
        )
        chat_histories[requester_key] = chat_tail[-12:]
        await self.memory.status.update("chat_histories", chat_histories)
