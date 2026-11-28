import asyncio
from copy import deepcopy
import json

import pytest

from check_hourly_channel_replay import RecordedReplies
from check_hourly_intention_run import request_payload
from check_stratified_needs_plan import (
    check_plan_fixtures,
    check_pre_hour,
    stratum,
    with_daytime_login,
)
from config_runtime import load_runtime_config
from proto.app_entry.candidate import build_rollout_app_context_candidates
from proto.app_entry.intention_contract import COMPACT_PLAN_V5, COMPACT_PLAN_V6
from proto.app_entry.needs import (
    COMPACT_NEEDS_PROMPT_VERSION,
    DIGITAL_NEEDS_PROMPT_VERSION,
    DigitalNeedsBlock,
)
from proto.app_entry.planner import DigitalAppEntryPlanBlock, decode_compact_plan
from proto.app_entry.types import AUDIT_ONLY_APP_CONTEXTS, HISTORICAL_CATEGORY_GUIDANCE
from test_app_entry_needs import _payload
from test_app_entry_planner import _needs
from test_daily_channel_choices import SOCIAL, wire
from test_hourly_intention_plan import packet


@pytest.mark.parametrize(
    "calibrated,expected",
    [(False, COMPACT_NEEDS_PROMPT_VERSION), (True, DIGITAL_NEEDS_PROMPT_VERSION)],
)
def test_opportunity_mode_picks_auditable_needs_version(
    monkeypatch, calibrated, expected
):
    monkeypatch.setenv("STAGE_MODE", "single")
    monkeypatch.setenv("PROTO_APP_ENTRY_REPLAY_DAYS", "1,2,3")
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "app_context_replay_then_llm_rollout")
    monkeypatch.setenv("PROTO_HOURLY_INTENTION_MODE", "opportunity_v1")
    monkeypatch.setenv(
        "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION",
        "app_entry_plan_v4_calibrated" if calibrated else "app_entry_plan_v3",
    )
    monkeypatch.delenv("PROTO_APP_ENTRY_NEEDS_PROMPT_VERSION", raising=False)
    assert load_runtime_config().proto_app_entry_needs_prompt_version == expected


def test_compact_needs_delivers_output_instructions_and_keeps_full_evidence_on_repair():
    observation = packet()
    echo = json.dumps({"inputs": observation})
    llm = RecordedReplies([echo, json.dumps(_payload())])
    result = asyncio.run(
        DigitalNeedsBlock().forward(
            llm=llm,
            input_payload=observation,
            prompt_version=COMPACT_NEEDS_PROMPT_VERSION,
        )
    )
    assert result.audit["parse_status"] == "ok_repaired"
    assert result.audit["json_attempts_configured"] == 1
    assert all(request_payload(r) == {"inputs": observation} for r in llm.requests)
    for request in llm.requests:
        instructions = request["messages"][0]["content"]
        assert HISTORICAL_CATEGORY_GUIDANCE in instructions
        assert all(
            k in instructions for k in [*_payload(), *_payload()["need_pressures"]]
        )
    direct = RecordedReplies([json.dumps(_payload())])
    first = asyncio.run(
        DigitalNeedsBlock().forward(
            llm=direct,
            input_payload=observation,
            prompt_version=COMPACT_NEEDS_PROMPT_VERSION,
        )
    )
    assert first.audit["parse_status"] == "ok" and len(direct.requests) == 1


def test_filter_precedes_top_k_and_uses_residents_overall_history_when_clock_hour_is_all_unclassified():
    uncertain = "unknown_or_unmapped"
    history = {
        "context_by_hour": {"2": {uncertain: 80}},
        "context_total_counts": {uncertain: 100, SOCIAL: 5},
    }
    common = dict(habit_memory=history, hour=2, top_k=1, allow_empty=True)
    assert build_rollout_app_context_candidates(**common) == {uncertain: 1.0}
    assert build_rollout_app_context_candidates(**common, actionable_only=True) == {
        SOCIAL: 1.0
    }
    assert history["context_by_hour"]["2"] == {uncertain: 80}


def test_v6_prohibits_all_audit_categories_in_primary_and_extra_openings_but_preserves_history_and_v5():
    input_packet = packet(hourly_intention_mode="opportunity_v1")
    input_packet["day1_3_habit"]["same_hour_context_counts"] = {
        category: 1 for category in AUDIT_ONLY_APP_CONTEXTS
    }
    candidates = dict.fromkeys([SOCIAL, *AUDIT_ONLY_APP_CONTEXTS], 1.0)
    kwargs = dict(
        needs=_needs(),
        candidate_contexts=candidates,
        input_payload=input_packet,
        intensity_profile={"active_exposure_cap": 4},
    )
    cases = {}
    for version in (COMPACT_PLAN_V5, COMPACT_PLAN_V6):
        capture = RecordedReplies([json.dumps(wire("no_app", []))])
        asyncio.run(
            DigitalAppEntryPlanBlock().forward(
                llm=capture, compact_schema_version=version, **kwargs
            )
        )
        assert (
            HISTORICAL_CATEGORY_GUIDANCE
            in capture.requests[0]["messages"][0]["content"]
        ) == (version == COMPACT_PLAN_V6)
        cases[version] = request_payload(capture.requests[0])
    old, new = cases[COMPACT_PLAN_V5], cases[COMPACT_PLAN_V6]
    assert old["inputs"] == new["inputs"]
    assert (
        set(new["inputs"]["day1_3_habit"]["same_hour_historical_share"])
        == AUDIT_ONLY_APP_CONTEXTS
    )
    assert new["channels"] == [SOCIAL]
    assert decode_compact_plan(wire("habitual_app@open:" + SOCIAL, []), new)["active"]
    for category in AUDIT_ONLY_APP_CONTEXTS:
        for alternative in (
            wire("habitual_app@open:" + category, []),
            wire("habitual_app@open:" + SOCIAL, [category]),
        ):
            assert (
                category in decode_compact_plan(alternative, old)["app_context_counts"]
            )
            with pytest.raises(ValueError):
                decode_compact_plan(alternative, new)


def test_strata_and_guard_use_only_what_was_visible_before_the_hour():
    observation = packet(hourly_intention_mode="opportunity_v1")
    observation["day1_3_habit"]["same_hour_active"] = {"seen": 3, "active": 0}
    assert stratum(observation) == ("day_06_21", "inactive_0_of_3", "no_task")
    check_pre_hour(observation, 4, 9)
    bad = {**observation, "recent_task_episodes": [{"day": 3, "hour": 9}]}
    with pytest.raises(ValueError, match="task result"):
        check_pre_hour(bad, 4, 9)
    with pytest.raises(ValueError, match="not visible"):
        check_pre_hour(
            {
                **observation,
                "available_opportunities": [
                    {"offered_at_sim_hour": 80, "visible_from_sim_hour": 82}
                ],
            },
            4,
            9,
        )


def test_constructed_quiet_hour_keeps_archived_history_and_emits_executable_login_and_daily_choices():
    base = packet()
    base["day1_3_habit"]["same_hour_active"] = {"seen": 3, "active": 0}
    base["recent_task_episodes"][0]["task_family"] = "account_login_verification"
    original = {
        **base,
        "available_opportunities": [],
        "current_intention": None,
        "goal_review_due": True,
        "monotonic_sim_hour": 81,
        "max_defer_hours": 24,
        "related_task_episode_ids": [],
    }
    before = deepcopy(original)
    constructed = with_daytime_login(base, original, agent_id=6)
    assert original == before
    assert stratum(constructed) == ("day_06_21", "inactive_0_of_3", "task")
    assert all(constructed[key] == value for key, value in base.items())
    assert constructed["related_task_episode_ids"] == ["previous"]
    (offer,) = constructed["available_opportunities"]
    assert offer["offered_at_sim_hour"] == offer["visible_from_sim_hour"] == 81
    assert "template" not in offer
    request = asyncio.run(
        check_plan_fixtures(
            {
                "input_payload": constructed,
                "candidate_contexts": {SOCIAL: 1.0},
                "intensity_profile": {"active_exposure_cap": 2},
                "needs": _needs(),
            }
        )
    )
    body = request_payload(request)
    assert "engage_goal@o1@open:" + offer["required_channel"] in body["actions"]
    assert "habitual_app@open:" + SOCIAL in body["actions"]
    assert "no_app" in body["actions"]
    # A goal waiting for review also counts as no_task; it must never be overwritten.
    with pytest.raises(ValueError, match="no competing goal"):
        with_daytime_login(
            base,
            {
                **original,
                "goal_review_due": False,
                "current_intention": {"goal_id": "g"},
            },
            6,
        )
