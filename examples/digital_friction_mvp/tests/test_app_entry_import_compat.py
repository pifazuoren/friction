from __future__ import annotations

from dataclasses import is_dataclass

from proto.task_assignment import (
    MobileEntryDecision,
    app_context_candidate_hash,
    decode_task,
    encode_task,
    evaluate_mobile_entry_for_agent,
    select_task_for_agent,
    top_app_context_candidates,
)


def test_task_assignment_legacy_app_entry_imports_remain_available() -> None:
    assert is_dataclass(MobileEntryDecision)
    assert callable(evaluate_mobile_entry_for_agent)
    assert callable(select_task_for_agent)
    assert callable(encode_task)
    assert callable(decode_task)
    assert callable(top_app_context_candidates)
    assert callable(app_context_candidate_hash)
