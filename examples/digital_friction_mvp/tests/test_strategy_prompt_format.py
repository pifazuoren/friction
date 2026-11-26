"""Matched strategy prompts and cache isolation across output instruction formats."""
import asyncio
import json

import pytest

from probe_strategy_memory_pair import run_pair_member
from proto.llm_psychology import clear_llm_psychology_caches


class RecordingLLM:
    def __init__(self):
        self.requests = []

    async def atext_request(self, *, dialog, **parameters):
        self.requests.append((dialog, parameters))
        return json.dumps({
            "attempt_self_score": .6, "seek_help_score": .3, "avoid_score": .1,
            "dominant_strategy": "attempt_self", "judge_confidence": .9,
            "reason": f"Local response {len(self.requests)}",
        })


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_STRATEGY_DELIBERATION_ENABLED", "true")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "false")
    monkeypatch.delenv("PROTO_LLM_TRACE_DIR", raising=False)
    clear_llm_psychology_caches()
    yield RecordingLLM()
    clear_llm_psychology_caches()


def test_output_field_rules_only_replace_the_scored_example(llm):
    asyncio.run(run_pair_member(llm, "success", .5))
    asyncio.run(run_pair_member(llm, "success", .5, prompt_format="scored_example"))
    result = asyncio.run(run_pair_member(llm, "success", .5, prompt_format="field_rules"))

    default, explicit, rules = llm.requests
    assert explicit == default
    (original_dialog, original_params), (new_dialog, new_params) = default, rules
    assert original_params == new_params and original_dialog[0] == new_dialog[0]
    prefix, raw = original_dialog[1]["content"].split("\n", 1)
    new_prefix, new_raw = new_dialog[1]["content"].split("\n", 1)
    assert prefix == new_prefix and original_dialog[1]["role"] == new_dialog[1]["role"]
    before, after = json.loads(raw), json.loads(new_raw)
    example = before.pop("output_schema_example")
    field_rules = after.pop("output_field_rules")
    assert before == after
    assert example == {
        "attempt_self_score": .18, "seek_help_score": .57, "avoid_score": .25,
        "dominant_strategy": "seek_help_then_attempt", "judge_confidence": .8,
        "reason": "Low control and decent support history make help-seeking the most acceptable option.",
    }
    assert field_rules.keys() == example.keys()
    assert set(field_rules.values()) == {
        "number in [0, 1]", "string from allowed_strategies matching the highest score",
        "string of at most 120 characters",
    }
    assert result["prompt_format"] == "field_rules" and result["source"] == "hybrid_blended"
    with pytest.raises(ValueError, match="Unknown strategy prompt format"):
        asyncio.run(run_pair_member(llm, "success", .5, prompt_format="invalid"))
    assert len(llm.requests) == 3


@pytest.mark.parametrize("condition", ["success", "failure"])
def test_hidden_priors_remove_one_prompt_field_and_keep_rule_blending(llm, condition):
    shown = asyncio.run(run_pair_member(llm, condition, .5, prompt_format="field_rules"))
    hidden = asyncio.run(run_pair_member(llm, condition, .5, prompt_format="field_rules_no_priors"))
    (visible_dialog, params), (hidden_dialog, hidden_params) = llm.requests
    assert hidden_params == params and hidden_dialog[0] == visible_dialog[0]
    prefix, raw_visible = visible_dialog[1]["content"].split("\n", 1)
    visible = json.loads(raw_visible)
    assert visible.pop("rule_weights") == hidden["rule_weights"] == shown["rule_weights"]
    expected = dict(visible_dialog[1], content=prefix + "\n" + json.dumps(visible, ensure_ascii=False))
    assert hidden_dialog[1] == expected
    assert hidden["source"] == "hybrid_blended"
    assert hidden["final_weights"] == shown["final_weights"]
    assert hidden["final_weights"] != hidden["llm_weights"]
    assert hidden["final_weights"] != hidden["rule_weights"]


def test_strategy_cache_isolates_formats_and_keeps_the_default_entry(llm, monkeypatch):
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "true")
    default = asyncio.run(run_pair_member(llm, "failure", .5))
    rules = asyncio.run(run_pair_member(llm, "failure", .5, prompt_format="field_rules"))
    hidden = asyncio.run(run_pair_member(llm, "failure", .5, prompt_format="field_rules_no_priors"))
    runs = [default, rules, hidden]
    assert all(not r["cache_hit"] for r in runs)
    assert len({r["reason"] for r in runs}) == 3
    for original in runs:
        fmt = original["prompt_format"]
        cached = asyncio.run(run_pair_member(llm, "failure", .5, prompt_format=fmt))
        assert cached["cache_hit"] and cached["reason"] == original["reason"]
    assert len(llm.requests) == 3
