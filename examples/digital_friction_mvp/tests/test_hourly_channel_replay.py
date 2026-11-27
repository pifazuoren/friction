from copy import deepcopy

import pytest

from check_hourly_channel_replay import encode_valid_choice
from proto.app_entry.intention_contract import COMPACT_PLAN_V4, compact_menu
from proto.app_entry.planner import decode_compact_plan


def archived_plan(apps):
    observation = {
        "available_opportunities": [
            {"opportunity_id": "login", "required_channel": "public_service_context"}
        ],
        "current_intention": None,
        "goal_review_due": True,
        "monotonic_sim_hour": 81,
        "max_defer_hours": 24,
    }
    version = "hourly_plan_compact_v3"
    body = {
        "schema_version": version,
        "inputs": observation,
        **compact_menu(observation, schema_version=version),
        "channels": ["public_service_context", "health_service_context"],
        "exposure_cap": 3,
        "minimum_confidence": 0.0,
    }
    raw = {
        "action": "engage_goal@o1",
        "apps": apps,
        "reason": "I will sign in.",
        "attitude": 0.5,
        "subjective_norm": 0.4,
        "perceived_control": 0.6,
        "confidence": 0.8,
    }
    return body, raw


def test_only_one_already_reported_opening_moves_into_the_explicit_target_token():
    body, raw = archived_plan(["public_service_context", "health_service_context", "public_service_context"])
    original = deepcopy(raw)
    converted = encode_valid_choice(raw, body)
    assert raw == original
    assert converted["action"] == "engage_goal@o1@open:public_service_context"
    assert converted["additional_apps"] == ["health_service_context", "public_service_context"]
    current = {**body, "schema_version": COMPACT_PLAN_V4, **compact_menu(body["inputs"], COMPACT_PLAN_V4)}
    assert decode_compact_plan(converted, current) == decode_compact_plan(raw, body)


@pytest.mark.parametrize("apps", [["health_service_context"], ["account_login_verification_app"], []])
def test_invalid_archived_channel_is_never_rewritten_as_an_observed_opening(apps):
    body, raw = archived_plan(apps)
    with pytest.raises(ValueError):
        encode_valid_choice(raw, body)
