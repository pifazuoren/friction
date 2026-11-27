"""Opt-in local evidence from the application's actual LLM request boundary."""
from __future__ import annotations

import json
import os
import re
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4


_context: ContextVar[dict | None] = ContextVar("friction_trace_context", default=None)
_write_lock = threading.Lock()
_private_keys = {"device_id", "api_key", "authorization", "access_token", "refresh_token", "password"}
_private_field = re.compile(
    r'("(?:device_id|api_key|authorization|access_token|refresh_token|password)"\s*:\s*)'
    r'(?:"(?:\\.|[^"\\])*"|-?\d+)', re.I,
)


class TraceWriteError(RuntimeError):
    """The current run requested an audit trail that cannot be persisted."""


class LLMRunInterrupted(RuntimeError):
    """The experiment transport stopped the run; downstream fallbacks must not advance it."""


def traced_agent_tick(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        if not os.environ.get("PROTO_LLM_TRACE_DIR"):
            return await function(*args, **kwargs)
        token = _context.set({"tick_id": uuid4().hex})
        try:
            return await function(*args, **kwargs)
        finally:
            _context.reset(token)

    return wrapped


def bind_trace_context(**fields) -> None:
    context = _context.get()
    if context is not None:
        _context.set({**context, **fields})


def _redact(value: Any, private_strings: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in _private_keys else _redact(item, private_strings)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, private_strings) for item in value]
    if not isinstance(value, str):
        return value
    for secret in private_strings:
        value = value.replace(secret, "[redacted]")
    return _private_field.sub(r'\1"[redacted]"', value)


def trace_record(kind: str, *, module: str, **fields) -> None:
    directory = os.environ.get("PROTO_LLM_TRACE_DIR")
    if not directory:
        return
    context = dict(_context.get() or {})
    device_id = str(context.pop("_device_id", ""))
    keys = [
        value for name, value in os.environ.items()
        if name.endswith(("_API_KEY", "_ACCESS_TOKEN", "_AUTH_TOKEN")) and len(value) >= 6
    ]
    if len(device_id) >= 6:
        keys.append(device_id)
    record = {
        "schema_version": 1, "kind": kind, "module": module,
        "group_id": os.environ.get("PARALLEL_GROUP_NAME", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(), **context, **fields,
    }
    if os.environ.get("PROTO_HOURLY_INTENTION_MODE") == "opportunity_v1":
        record.update(hourly_intention_mode="opportunity_v1",
                      code_hash=os.environ.get("PROTO_RUN_SOURCE_SHA256"),
                      plan_prompt_version=os.environ.get("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION"),
                      intention_schema_version="opportunity_v1")
    target = Path(directory) / f"llm-requests-{os.getpid()}.jsonl"
    try:
        data = json.dumps(_redact(record, tuple(keys)), ensure_ascii=False) + "\n"
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with _write_lock:
            fd = os.open(target, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(data)
    except (OSError, TypeError, ValueError) as exc:
        raise TraceWriteError(f"Cannot write requested LLM trace to {target}") from exc


class LLMQueryTrace:
    def __init__(self, module: str, llm: Any):
        self.llm = llm
        self.module = module
        self.enabled = bool(os.environ.get("PROTO_LLM_TRACE_DIR"))
        self.query_id = uuid4().hex if self.enabled else ""
        self.call = {}

    async def request(self, phase: str, attempt: int, **kwargs):
        if not self.enabled:
            return await self.llm.atext_request(**kwargs)
        self.call = dict(query_id=self.query_id, call_id=uuid4().hex, phase=phase, attempt=attempt)
        configs = getattr(self.llm, "configs", None)
        model = None
        if isinstance(configs, list) and len(configs) == 1:
            model = getattr(configs[0], "model", None)
        parameters = {
            key: kwargs[key] for key in ("temperature", "timeout", "retries", "max_tokens")
            if key in kwargs
        }
        trace_record(
            "request", module=self.module, **self.call, model=model,
            messages=kwargs["dialog"], parameters=parameters,
        )
        try:
            raw = await self.llm.atext_request(**kwargs)
        except BaseException as exc:
            # Provider exception messages can contain credentials or HTTP request bodies.
            code = getattr(exc, "status_code", None)
            trace_record("error", module=self.module, **self.call,
                         error_type=type(exc).__name__, http_status=code if type(code) is int else None)
            raise
        trace_record("response", module=self.module, **self.call, raw=raw)
        return raw

    def parsed(self, status: str, payload=None) -> None:
        if self.enabled:
            trace_record("parse", module=self.module, **self.call, status=status, parsed=payload)
