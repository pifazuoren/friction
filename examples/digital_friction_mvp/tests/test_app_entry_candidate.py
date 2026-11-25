from __future__ import annotations

import pytest

from proto.app_entry.candidate import build_rollout_app_context_candidates


def test_candidates_include_same_device_same_hour_observations() -> None:
    candidates = build_rollout_app_context_candidates(
        habit_memory={
            "context_by_hour": {
                "9": {
                    "finance_context": 4,
                    "communication_social_context": 1,
                }
            }
        },
        hour=9,
        top_k=5,
    )

    assert set(candidates) == {
        "finance_context",
        "communication_social_context",
    }
    assert sum(candidates.values()) == pytest.approx(1.0)


def test_candidates_can_add_confirmed_need_mapped_contexts() -> None:
    candidates = build_rollout_app_context_candidates(
        habit_memory={
            "context_by_hour": {"9": {"finance_context": 2}},
        },
        hour=9,
        need_pressures={"health_need": 0.8},
        need_context_mapping={
            "health_need": ("health_service_context",),
        },
        top_k=5,
    )

    assert "health_service_context" in candidates


def test_candidates_reject_validation_like_inputs_and_no_app_context() -> None:
    with pytest.raises(ValueError, match="unknown app context"):
        build_rollout_app_context_candidates(
            habit_memory={
                "context_by_hour": {
                    "9": {"validation_primary_context": 1}
                }
            },
            hour=9,
        )

    with pytest.raises(ValueError, match="candidate pool is empty"):
        build_rollout_app_context_candidates(
            habit_memory={"context_by_hour": {"9": {}}},
            hour=9,
            need_pressures={"no_app_need": 1.0},
            need_context_mapping={"no_app_need": ("no_app_context",)},
        )
