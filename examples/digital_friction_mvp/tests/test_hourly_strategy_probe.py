import asyncio
import json

import pytest

from probe_hourly_intention import (
    DAY,
    PROFILE_ID,
    SIM_HOUR,
    TICK,
    login_offer,
    prior_episode,
)
from probe_hourly_strategy import FROZEN_RUNTIME_ENV, measure_admitted


APPRAISAL = {
    "perceived_task_difficulty": 40,
    "perceived_task_risk": 40,
    "felt_control": 60,
    "expected_help_effectiveness": 60,
    "task_value": 50,
    "judge_confidence": 0.8,
    "reason": "Manageable.",
}
STRATEGY = {
    "attempt_self_score": 0.2,
    "seek_help_score": 0.7,
    "avoid_score": 0.1,
    "dominant_strategy": "seek_help_then_attempt",
    "judge_confidence": 0.8,
    "reason": "Ask for advice.",
}


@pytest.fixture(autouse=True)
def freeze_runtime(monkeypatch):
    for key, value in FROZEN_RUNTIME_ENV.items():
        monkeypatch.setenv(key, value)


class Responses:
    def __init__(self, *items):
        self.dialogs = []
        self.items = iter(items)

    async def atext_request(self, *, dialog, **kwargs):
        self.dialogs.append(dialog)
        item = next(self.items)
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)


def routed_task(scene="S0"):
    _, ledger, offer = login_offer(scene=scene)
    return ledger.apply(
        dict(
            kind="engage_goal",
            opportunity_id=offer["opportunity_id"],
            goal_id=None,
            next_review_at_sim_hour=None,
            reason="Log in.",
        ),
        sim_hour=SIM_HOUR,
    )


def measure(llm, *, condition="success", scene="S0", draw=0.0):
    return asyncio.run(
        measure_admitted(
            llm, task=routed_task(scene), condition=condition, sample_u=draw
        )
    )


def payload(dialog):
    return json.loads(dialog[1]["content"].split("\n", 1)[1])


@pytest.mark.parametrize("scene", ["S0", "S1"])
def test_actual_appraisal_strategy_messages_frozen_except_episode(scene):
    by_condition = {}
    for condition in ("success", "failure"):
        transport = Responses(APPRAISAL, STRATEGY)
        row = measure(transport, condition=condition, scene=scene)
        assert row["lower_valid"] and row["strategy_source"] == "hybrid_blended"
        assert len(transport.dialogs) == 2
        messages = [payload(d) for d in transport.dialogs]
        for body, mkey, tkey in zip(
            messages,
            ("Task-Specific Memory", "task_relevant_memory"),
            ("Current Task", "task"),
        ):
            assert body[mkey].pop("recent_task_episodes") == [prior_episode(condition)]
            _, _, offer = login_offer(scene=scene)
            assert body[tkey] == {
                **routed_task(scene).to_dict(),
                "visible_description": offer["visible_description"],
            }
        assert "rule_weights" not in messages[1]
        by_condition[condition] = messages, row["rule_weights"], row["final_weights"]
    assert by_condition["success"] == by_condition["failure"]


def test_same_condition_only_changes_visible_sentence_across_both_lower_prompts():
    scenes = []
    descriptions = []
    for scene in ("S0", "S1"):
        transport = Responses(APPRAISAL, STRATEGY)
        measure(transport, scene=scene)
        appraisal, strategy = map(payload, transport.dialogs)
        sentence = appraisal["Current Task"].pop("visible_description")
        assert strategy["task"].pop("visible_description") == sentence
        descriptions.append(sentence)
        scenes.append((appraisal, strategy))
    assert scenes[0] == scenes[1]
    assert descriptions[0] != descriptions[1]


def test_production_draw_and_actual_dispatch_end_at_request_receiver(monkeypatch):
    monkeypatch.setenv("PROTO_LLM_TRACE_DIR", "")
    baseline = measure(Responses(APPRAISAL, STRATEGY))
    lower, upper = (
        baseline["final_weights"]["attempt_self"],
        1 - baseline["final_weights"]["avoid"],
    )
    assert baseline["sampled_action"] == "attempt_self"
    assert not baseline["help_request_dispatched"] and baseline["help_request"] is None
    for draw, action in (
        ((lower + upper) / 2, "seek_help_then_attempt"),
        ((upper + 1) / 2, "avoid"),
    ):
        observed = measure(Responses(APPRAISAL, STRATEGY), draw=draw)
        assert observed["sampled_action"] == action
        if action == "seek_help_then_attempt":
            assert observed["help_request_dispatched"]
            assert observed["help_request"]["requester_agent_id"] == PROFILE_ID
            assert observed["help_request"]["task_id"] == routed_task().task_id
            assert (
                observed["help_request"]["task_appraisal"]["felt_control"]
                == APPRAISAL["felt_control"]
            )
            assert (
                observed["help_request"]["day"],
                observed["help_request"]["tick"],
            ) == (DAY, TICK)
        else:
            assert (
                observed["help_request"] is None
                and not observed["help_request_dispatched"]
            )
        assert observed["help_delivery_status"] == "unobserved"


def test_fallback_preserves_validated_low_confidence_scores_and_realized_rule_action():
    transport = Responses({}, {}, {**STRATEGY, "judge_confidence": 0.2})
    row = measure(transport)
    assert len(transport.dialogs) == 3
    assert not row["lower_valid"] and row["appraisal"]["source"].startswith(
        "rule_fallback"
    )
    assert row["strategy_source"] == "rule_fallback_low_confidence"
    assert row["raw_scores"]["seek_help_then_attempt"] == 0.7
    assert row["rule_weights"] == pytest.approx(row["final_weights"])
    assert row["sampled_action"] == "attempt_self"


def test_failed_strategy_retains_fallback_and_missing_llm_scores():
    transport = Responses(APPRAISAL, RuntimeError("provider unavailable"))
    row = measure(transport, draw=0.99)
    assert len(transport.dialogs) == 2
    assert not row["lower_valid"] and row["strategy_status"] == "request_error"
    assert row["raw_scores"] is None and row["llm_weights"] is None
    assert row["final_weights"] == pytest.approx(row["rule_weights"])
    assert row["sampled_action"] == "avoid" and row["help_request_dispatched"] is False


def test_disabled_cache_is_required_before_contact(monkeypatch):
    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "true")
    transport = Responses()
    with pytest.raises(ValueError, match="CACHE_ENABLED=false"):
        measure(transport)
    assert not transport.dialogs


def test_production_caches_separate_distinct_visible_scenes_and_episode_outcomes(
    monkeypatch,
):
    from proto.llm_psychology import (
        clear_llm_psychology_caches,
        resolve_strategy_deliberation,
        resolve_task_appraisal,
    )

    monkeypatch.setenv("PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED", "true")
    clear_llm_psychology_caches()

    async def run():
        replies = Responses(*([APPRAISAL, STRATEGY] * 3))
        for scene, condition, expected_cached in [
            ("S0", "success", False),
            ("S0", "success", True),
            ("S1", "success", False),
            ("S1", "failure", False),
        ]:
            common = dict(
                llm=replies,
                task=routed_task(scene),
                task_self_efficacy=50,
                help_success_rate_smoothed=0.5,
                recent_episode_summary={},
                digital_emotion_state={},
                profile_summary={},
                task_relevant_memory={
                    "recent_task_episodes": [prior_episode(condition)]
                },
            )
            appraisal = await resolve_task_appraisal(
                **common, stage_key="", world_context={}, helplessness_now=50
            )
            strategy = await resolve_strategy_deliberation(
                **common,
                task_appraisal=appraisal.to_dict(),
                effective_helplessness=50,
                recent_negative_feedback_ratio=0,
                recent_same_task_failure_count=0,
                daily_reflection={},
                rule_weights={
                    "attempt_self": 0.4,
                    "seek_help_then_attempt": 0.3,
                    "avoid": 0.3,
                },
            )
            assert appraisal.cache_hit == strategy.cache_hit == expected_cached
        assert len(replies.dialogs) == 6

    try:
        asyncio.run(run())
    finally:
        clear_llm_psychology_caches()


@pytest.mark.parametrize(
    "invalid", [75, -1, "0.7", True, None, float("nan"), float("inf"), "NaN"]
)
def test_strict_strategy_reports_raw_initial_and_separate_repaired_choice(invalid):
    bad = {**STRATEGY, "seek_help_score": invalid, "judge_confidence": 8}
    row = measure(Responses(APPRAISAL, bad, STRATEGY))
    assert row["lower_valid"] is True
    audit = row["reply_audit"]["strategy"]
    assert audit["adopted_from"] == "repair" and audit["repair_requests"] == 1
    assert audit["initial"]["status"] == "invalid_schema"
    assert audit["initial"]["invalid_score_fields"] == [
        "judge_confidence",
        "seek_help_score",
    ]
    recorded = audit["initial"]["reported_scores"]
    assert recorded["judge_confidence"] == 8
    if isinstance(invalid, float):
        assert recorded["seek_help_score"] == {"nonfinite_number": repr(invalid)}
    else:
        assert recorded["seek_help_score"] == invalid
    assert (
        audit["repair"]["reported_scores"]["seek_help_score"]
        == row["raw_scores"]["seek_help_then_attempt"]
        == 0.7
    )
    assert audit["repair"]["status"] == "ok" and audit["parse_status"] == "ok_repaired"
    assert row["reply_audit"]["appraisal"]["adopted_from"] == "initial"
    assert row["reply_audit"]["appraisal"]["repair"] is None
    json.dumps(row, allow_nan=False)


def test_strict_appraisal_discards_non_numeric_value_and_marks_fallback_without_accepting_it():
    bad = {**APPRAISAL, "felt_control": "70", "expected_help_effectiveness": 120}
    row = measure(Responses(bad, bad, STRATEGY))
    audit = row["reply_audit"]["appraisal"]
    assert audit["adopted_from"] == "rule_fallback"
    assert audit["actual_requests"] == 2 and audit["parse_status"] == "invalid_schema"
    assert audit["repair"]["reported_scores"]["felt_control"] == "70"
    assert audit["repair"]["invalid_score_fields"] == [
        "expected_help_effectiveness",
        "felt_control",
    ]
    assert row["appraisal"]["source"] == "rule_fallback_invalid_schema"
    assert row["appraisal"]["felt_control"] == 50
    assert row["lower_valid"] is False
    assert row["reply_audit"]["strategy"]["adopted_from"] == "initial"


def test_low_confidence_valid_reply_keeps_reported_scores_and_marks_rule_fallback():
    row = measure(Responses(APPRAISAL, {**STRATEGY, "judge_confidence": 0.2}))
    audit = row["reply_audit"]["strategy"]
    assert audit["adopted_from"] == "rule_fallback" and audit["repair"] is None
    assert audit["initial"]["status"] == "ok" and audit["parse_status"] == "ok"
    assert row["strategy_status"] == "low_confidence"
    assert row["raw_scores"]["seek_help_then_attempt"] == 0.7


def test_legacy_sanitizers_preserve_compatibility():
    from proto.llm_psychology import (
        _sanitize_strategy_deliberation,
        _sanitize_task_appraisal,
    )

    legacy, status = _sanitize_strategy_deliberation(
        {**STRATEGY, "seek_help_score": 75, "judge_confidence": 8}
    )
    assert (
        status == "ok" and legacy["seek_help_score"] == legacy["judge_confidence"] == 1
    )
    legacy, status = _sanitize_task_appraisal(
        {**APPRAISAL, "felt_control": "70", "expected_help_effectiveness": 120}
    )
    assert (
        status == "ok"
        and legacy["felt_control"] == 70
        and legacy["expected_help_effectiveness"] == 100
    )
