import asyncio
from collections import Counter
import json
from types import SimpleNamespace

import pytest

from run_strategy_memory_pairs import MODEL, check_stimuli, schedule, study, verify_reference


@pytest.mark.parametrize("prompt_format", ["scored_example", "field_rules", "field_rules_no_priors"])
def test_entire_pair_design_through_strategy_messages_and_sampler(monkeypatch, tmp_path, prompt_format):
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MODE", "hybrid")
    monkeypatch.setenv("PROTO_LLM_STRATEGY_DELIBERATION_ENABLED", "true")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "false")
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_MIN_CONFIDENCE", "0.65")
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "fixed_assignment")
    monkeypatch.delenv("PROTO_LLM_TRACE_DIR", raising=False)
    stimuli = asyncio.run(check_stimuli(prompt_format))
    pairs = schedule()
    assert pairs == schedule()
    assert len({p["pair_id"] for p in pairs}) == 13
    assert Counter(p["order"][0] for p in pairs if p["kind"] == "contrast") == {"A": 5, "B": 5}
    replies = []

    async def create(*, model, messages, **kwargs):
        assert model == MODEL
        assert messages in stimuli.values()
        failed = messages == stimuli["failure"]
        reply = json.dumps({
            "attempt_self_score": .1 if failed else .8, "seek_help_score": .8 if failed else .1,
            "avoid_score": .1, "dominant_strategy": "seek_help_then_attempt" if failed else "attempt_self",
            "judge_confidence": .92, "reason": "Synthetic deterministic fixture.",
        })
        replies.append(reply)
        return SimpleNamespace(model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", str(tmp_path / "trace"))
    asyncio.run(study(client, tmp_path, stimuli, pairs, prompt_format))
    rows = [json.loads(row) for row in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert len(replies) == len(rows) == 26
    for pair in pairs:
        arms = [r for r in rows if r["pair_id"] == pair["pair_id"]]
        assert [r["arm"] for r in arms] == list(pair["order"])
        assert all(r["sample_u"] == pair["sample_u"] for r in arms)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["coverage"]["complete_as_planned"]
    assert summary["repeat"]["all_complete"]["action_flips"] == 0
    assert summary["contrast"]["all_complete"]["mean_weight_difference_B_minus_A"]["seek_help_then_attempt"] > 0
    trace_path, = (tmp_path / "trace").glob("*.jsonl")
    requests = [r for line in trace_path.read_text().splitlines() if (r := json.loads(line))["kind"] == "request"]
    assert len(requests) == 26
    assert all(r["messages"] == stimuli[r["condition"]] and r["arm"] in ("A", "B") for r in requests)

    if prompt_format != "scored_example":
        monkeypatch.delenv("PROTO_LLM_TRACE_DIR")
        reference_format = "field_rules" if prompt_format == "field_rules_no_priors" else "scored_example"
        original = asyncio.run(check_stimuli(reference_format))
        (tmp_path / "stimuli.json").write_text(json.dumps(original))
        (tmp_path / "design.json").write_text(json.dumps({"model": MODEL, "pairs": pairs}))
        verify_reference(tmp_path, stimuli, pairs, prompt_format)
        stimuli["success"][0]["content"] += " unrelated change"
        with pytest.raises(ValueError, match="system prompt"):
            verify_reference(tmp_path, stimuli, pairs, prompt_format)
