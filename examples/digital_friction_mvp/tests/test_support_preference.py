import asyncio
import json

import pytest

from proto.llm_trace import LLMRunInterrupted, TraceWriteError
from proto.models import DigitalTask
from proto.support.preference import resolve_requested_support_style


class ResidentLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def atext_request(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


PROFILE = {"background_summary": "I would like to learn how to make my next appointment."}
MEMORY = {"recent_task_episodes": [{
    "episode_id": "yesterday-visit", "requested_support_style": "guidance",
    "support_style": "substituting", "outcome_type": "success_with_help",
}]}
TASK = DigitalTask(
    task_id="next-appointment", task_family="service_application_submission",
    visible_description="Schedule the follow-up appointment.", friction_type="verification",
    difficulty=0.5, need_type="health", support_sensitivity=0.6, assigned_tick=1,
)


def choose(llm, *, enabled=True):
    return asyncio.run(resolve_requested_support_style(
        llm=llm, task=TASK, profile_summary=PROFILE, task_relevant_memory_packet=MEMORY,
        enabled=enabled, timeout=37,
    ))


@pytest.mark.parametrize("style", ["guidance", "proxy", "unspecified"])
def test_resident_choice_uses_current_task_and_prior_actual_help(style, tmp_path, monkeypatch):
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path))
    llm = ResidentLLM(json.dumps({"requested_support_style": style}))
    assert choose(llm) == (style, "llm")
    (call,) = llm.calls
    assert call["retries"] == 1 and call["timeout"] == 37
    payload = json.loads(call["dialog"][1]["content"])
    assert payload["task"]["description"] == TASK.visible_description
    assert payload["resident"] == PROFILE and payload["prior_task_memory"] == MEMORY
    trace_file, = tmp_path.glob("llm-requests-*.jsonl")
    records = [json.loads(line) for line in trace_file.read_text().splitlines()]
    assert [(r["module"], r["kind"]) for r in records] == [
        ("support_preference", k) for k in ("request", "response", "parse")
    ]
    assert records[-1]["parsed"] == {"requested_support_style": style}


@pytest.mark.parametrize("reply", [
    "teach me", '{"requested_support_style":"enabling"}', '{"requested_support_style":null}',
    '{"requested_support_style":["guidance"]}', '{"requested_support_style":"guidance","responded":true}',
    '{"requested_support_style":"proxy","requested_support_style":"guidance"}',
])
def test_invalid_responses_are_missing_preferences_without_a_second_request(reply):
    llm = ResidentLLM(reply)
    assert choose(llm) == (None, "invalid_response")
    assert len(llm.calls) == 1


def test_unavailable_measurement_is_distinct_from_a_resident_without_a_preference():
    llm = ResidentLLM(TimeoutError())
    assert choose(llm, enabled=False) == (None, "disabled") and not llm.calls
    assert choose(None) == (None, "missing_llm")
    assert choose(llm) == (None, "request_error") and len(llm.calls) == 1


@pytest.mark.parametrize("error", [TraceWriteError, LLMRunInterrupted])
def test_experiment_interruptions_propagate(error):
    with pytest.raises(error):
        choose(ResidentLLM(error("interrupted")))
