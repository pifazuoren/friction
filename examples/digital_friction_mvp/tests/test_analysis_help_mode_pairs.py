"""Identical inputs can disagree; technical missingness and selecting help are different endpoints."""

from copy import deepcopy
from hashlib import sha256

import pytest

from analysis_help_mode_pairs import APPRAISAL_FIELDS, summarize
from analysis_hourly_factorial import PLAN_SCORES


def schedule():
    rows = []
    for rank in range(1, 11):
        for i in range(4):
            repeat = i == 3
            for member in ("A", "B"):
                condition = (
                    "guided"
                    if (rank % 2 == 0 if repeat else member == "A")
                    else "proxy"
                )
                rows.append(
                    {
                        "profile_id": rank + 100,
                        "selected_rank": rank,
                        "pair_id": f"{rank}-{i}",
                        "member": member,
                        "kind": "repeat" if repeat else "contrast",
                        "condition": condition,
                        "sample_u": 0.25,
                        "pair_seed": 100 * rank + i,
                        "plan_stimulus_sha256": sha256(
                            f"{rank}-{condition}".encode()
                        ).hexdigest(),
                    }
                )
    return rows


def decision(slot, policy="no_app", strategy=None, fallback=False):
    lower = None
    if strategy:
        weights = dict(attempt_self=0.5, seek_help_then_attempt=0.3, avoid=0.2)
        lower = {
            "sampled_action": strategy,
            "sample_u": slot["sample_u"],
            "lower_valid": not fallback,
            "strategy_source": "rule_fallback" if fallback else "hybrid_blended",
            "rule_inputs": {"support_quality": 1},
            "raw_scores": None if fallback else weights,
            "llm_weights": None if fallback else weights,
            "blended_weights": weights,
            "rule_weights": weights,
            "final_weights": weights,
            "help_request_dispatched": strategy == "seek_help_then_attempt",
            "help_request": {"request_id": "receipt"}
            if strategy == "seek_help_then_attempt"
            else None,
            "help_delivery_status": "unobserved",
            "operation_started": None,
            "task_outcome": None,
            "appraisal": {"source": "llm", **dict.fromkeys(APPRAISAL_FIELDS, 50)},
        }
    return {
        **slot,
        "plan_valid": policy is not None,
        "policy_choice": policy,
        "task_admitted": (policy == "engage_goal") if policy else None,
        "plan_scores": dict.fromkeys(PLAN_SCORES, 0.8) if policy else None,
        "plan_reason": "decision" if policy else None,
        "defer_hours": 1 if policy == "defer_goal" else None,
        "lower": lower,
    }


def test_opportunities_remain_denominators_and_pairs_are_resident_weighted():
    spec = schedule()
    rows = [decision(s) for s in spec]
    # Profile 101 has one usable contrast. Profile 102 has three, of which one changes.
    rows[0] = decision(spec[0], "engage_goal", "attempt_self")
    rows[2] = decision(spec[2], None)
    rows[4] = decision(spec[4], None)
    rows[8] = decision(spec[8], "engage_goal", "attempt_self", fallback=True)
    rows[11] = decision(spec[11], "engage_goal", "seek_help_then_attempt")
    rows[7] = decision(spec[7], "defer_goal")
    result = summarize(spec, rows[::-1])
    assert result["complete"] and result["technical"] == {
        "invalid_plans": 2,
        "missing_after_admission": 0,
        "lower_fallbacks": 1,
    }
    rate = result["by_condition"]["guided"]["endpoints"][
        "independent_strategy_selected"
    ]
    assert rate["denominator"] == 30 and rate["confirmed_yes"] == rate["unknown"] == 2
    assert (
        result["by_condition"]["proxy"]["endpoints"]["help_request_received"][
            "confirmed_yes"
        ]
        == 1
    )
    metrics = result["contrast"]["equal_profile_means"]
    assert metrics["independent_strategy_selected"] == {
        "profiles": 10,
        "observed_pairs": 28,
        "mean": pytest.approx((1 + 1 / 3) / 10),
    }
    assert metrics["model_valid.independent_strategy_selected"]["observed_pairs"] == 27
    assert (
        result["repeat"]["equal_profile_means"]["any_action_disagreement"]["mean"]
        == 0.1
    )


def test_identical_behavior_is_retained_as_a_zero_contrast():
    spec = schedule()
    report = summarize(spec, [decision(s, "drop_goal") for s in spec])
    assert (
        report["by_condition"]["guided"]["endpoints"]["dropped"]["confirmed_yes"] == 30
    )
    assert report["contrast"]["equal_profile_means"]["dropped"]["mean"] == 0
    assert (
        report["contrast"]["equal_profile_means"]["appraisal.felt_control"]["mean"]
        is None
    )
    assert "contrast" not in summarize(spec, [decision(spec[0])])


def test_cross_arm_rule_leak_or_unobserved_delivery_is_rejected():
    spec = schedule()
    a, b = [decision(s, "engage_goal", "seek_help_then_attempt") for s in spec[:2]]
    b["lower"]["rule_inputs"]["support_quality"] = 0
    with pytest.raises(ValueError, match="Numerical rule"):
        summarize(spec, [a, b])
    a["lower"]["help_request_dispatched"] = False
    a["lower"]["help_request"] = None
    with pytest.raises(ValueError, match="Help choice"):
        summarize(spec, [a])
    tampered = deepcopy(spec)
    tampered[7]["condition"] = "guided"
    with pytest.raises(ValueError):
        summarize(tampered, [])
