"""Elicit the resident's preferred form of assistance after they choose to ask."""

from __future__ import annotations

import json
from typing import Any

from ..app_entry.intention_contract import parse_compact_reply
from ..hourly_intention import visible_task_description
from ..llm_trace import LLMQueryTrace, LLMRunInterrupted, TraceWriteError
from ..models import DigitalTask
from ..support_protocol import REQUESTED_SUPPORT_STYLES


_SYSTEM = (
    "You are the resident described in the input. You have already chosen to ask "
    "your family member for help with the current task. What would you ask them to do? "
    "Choose guidance if you want them to explain while you perform the key steps, "
    "proxy if you want them to perform the key steps for you, or unspecified if "
    "you would ask for help without specifying who should operate. "
    "Give your own preference now. The family member will decide independently how to respond. "
    'Return only a JSON object with the single key "requested_support_style" and your choice.'
)


async def resolve_requested_support_style(
    *,
    llm: Any,
    task: DigitalTask,
    profile_summary: dict,
    task_relevant_memory_packet: dict,
    enabled: bool,
    timeout: int,
) -> tuple[str | None, str]:
    """Return the resident's stated preference and its source, or a missing measurement."""
    if not enabled:
        return None, "disabled"
    if llm is None:
        return None, "missing_llm"

    observation = {
        "task": {"family": task.task_family, "description": visible_task_description(task)},
        "resident": profile_summary,
        "prior_task_memory": task_relevant_memory_packet,
    }
    dialog = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(observation, ensure_ascii=False)},
    ]
    trace = LLMQueryTrace("support_preference", llm)
    try:
        raw = await trace.request(
            "initial", 1, dialog=dialog, temperature=0.2, max_tokens=64,
            timeout=timeout, retries=1,
        )
    except (LLMRunInterrupted, TraceWriteError):
        raise
    except Exception:
        return None, "request_error"

    payload = parse_compact_reply(raw) if isinstance(raw, str) else None
    if payload is not None and payload.keys() == {"requested_support_style"}:
        style = payload["requested_support_style"]
        if isinstance(style, str) and style in REQUESTED_SUPPORT_STYLES:
            trace.parsed("ok", payload)
            return style, "llm"
    trace.parsed("invalid_response")
    return None, "invalid_response"
