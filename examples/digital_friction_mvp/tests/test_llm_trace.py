import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from proto.attribution_inference import _query_llm_payload
from proto.llm_psychology import _query_json_payload
from proto.llm_trace import TraceWriteError, bind_trace_context, traced_agent_tick


class FakeLLM:
    configs = [SimpleNamespace(model="fake-model")]

    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.dialogs = []

    async def atext_request(self, **kwargs):
        self.dialogs.append(deepcopy(kwargs["dialog"]))
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return result


def records(path):
    file, = path.glob("llm-requests-*.jsonl")
    return [json.loads(line) for line in file.read_text().splitlines()]


def test_actual_repair_and_error_share_tick_without_logging_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("PARALLEL_GROUP_NAME", "test-run")
    secret = "private-access-key-ABC123"
    monkeypatch.setenv("LLM_API_KEY", secret)
    device = "-5123456789012345678"
    llm = FakeLLM("bad JSON", '{"accepted": true}', RuntimeError(secret))

    @traced_agent_tick
    async def exercise():
        bind_trace_context(agent_id=1, simulation_day=3, talkingdata_day=4, hour=0,
                           tick_seconds=0, _device_id=device)
        result = await _query_json_payload(
            llm=llm, trace_module="strategy", system_prompt="Choose.",
            user_payload={"device_id": device, "note": "Device " + device + " " + secret},
            output_keys={"accepted"}, repair_schema_text="Return accepted.",
            sanitize_fn=lambda obj: (obj, "ok"), timeout=5, retries=1,
        )
        assert result == ({"accepted": True}, "ok_repaired")
        assert await _query_llm_payload(llm=llm, payload={}, timeout=7, retries=1) is None

    asyncio.run(exercise())
    rows = records(tmp_path)
    assert len({r["tick_id"] for r in rows}) == 1
    assert all(r["group_id"] == "test-run" and r["hour"] == 0 for r in rows)
    primary, repair, attribution = [r for r in rows if r["kind"] == "request"]
    assert primary["query_id"] == repair["query_id"] != attribution["query_id"]
    assert primary["call_id"] != repair["call_id"]
    assert repair["phase"] == "repair" and attribution["module"] == "attribution"
    assert [r["status"] for r in rows if r["kind"] == "parse"] == ["parse_failed", "ok_repaired"]
    assert [r["raw"] for r in rows if r["kind"] == "response"] == ["bad JSON", '{"accepted": true}']
    error, = [r for r in rows if r["kind"] == "error"]
    assert error["error_type"] == "RuntimeError" and error["call_id"] == attribution["call_id"]
    assert primary["model"] == "fake-model"
    assert primary["parameters"] == {"temperature": 0.1, "timeout": 5, "retries": 1, "max_tokens": 260}
    for r, dialog in zip([primary, repair, attribution], llm.dialogs):
        expected = [{**msg, "content": msg["content"].replace(device, "[redacted]").replace(secret, "[redacted]")} for msg in dialog]
        assert r["messages"] == expected
    assert device not in str(rows) and secret not in str(rows)
    assert device in llm.dialogs[0][-1]["content"] and secret in llm.dialogs[0][-1]["content"]


def test_disabled_trace_preserves_calls_without_creating_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PROTO_LLM_TRACE_DIR", raising=False)
    llm = FakeLLM("bad")
    assert asyncio.run(_query_llm_payload(llm=llm, payload={}, timeout=5, retries=1)) is None
    assert len(llm.dialogs) == 1 and not list(tmp_path.iterdir())


def test_unwritable_trace_stops_before_the_model_call(monkeypatch, tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("already a file")
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(blocked))
    llm = FakeLLM("unused")
    with pytest.raises(TraceWriteError):
        asyncio.run(_query_llm_payload(llm=llm, payload={}, timeout=5, retries=1))
    assert llm.dialogs == []
