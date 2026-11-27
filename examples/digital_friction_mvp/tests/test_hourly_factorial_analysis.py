from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis_hourly_factorial import summarize


PLAN_SCORES = dict.fromkeys(("attitude", "subjective_norm", "perceived_control", "confidence"), 0.7)
WEIGHTS = {"attempt_self": .5, "seek_help_then_attempt": .35, "avoid": .15}


def design():
    manifest = []
    for scene in ("S0", "S1"):
        for number in range(6):
            kind = "contrast" if number < 5 else "repeat"
            pair = f"{scene}-{kind}-{number}"
            for member in ("A", "B"):
                condition = ("success" if member == "A" else "failure") if kind == "contrast" else (
                    "success" if scene == "S0" else "failure"
                )
                manifest.append(dict(scene=scene, condition=condition, member=member, pair_id=pair,
                                     pair_seed=100+number, kind=kind, sample_u=0.5))
    return manifest


def record(slot, policy):
    entered = policy == "engage_goal"
    return {**slot, "policy_choice": policy, "task_admitted": entered if policy else None,
            "plan_valid": bool(policy), "plan_scores": PLAN_SCORES if policy else None,
            "plan_reason": "today" if policy else None,
            "defer_hours": 4 if policy == "defer_goal" else None, "lower": None}


def measured(row, action, *, fallback=False):
    result = {"sampled_action": action, "sample_u": row["sample_u"], "lower_valid": not fallback,
              "help_request_dispatched": action == "seek_help_then_attempt", "help_delivery_status": "unobserved",
              "help_request": {"request_id": "local-only"} if action == "seek_help_then_attempt" else None,
              "strategy_source": "rule_fallback" if fallback else "hybrid_blended", "strategy_status": "fixed",
              "appraisal": {"source": "hybrid_blended", "status": "fixed"},
              "rule_weights": WEIGHTS.copy(), "final_weights": WEIGHTS.copy(),
              "blended_weights": WEIGHTS.copy(), "llm_weights": None if fallback else WEIGHTS.copy(),
              "raw_scores": None if fallback else WEIGHTS.copy()}
    return dict(row, lower=result)


def test_partial_refuses_unfinished_research_contrasts():
    manifest = design()
    report = summarize(manifest, [record(manifest[0], None)])
    assert report["complete"] is False and report["coverage"]["recorded_decisions"] == 1
    assert len(report["coverage"]["missing_decisions"]) == 23
    assert report["technical"]["plan_failures"] == 1
    assert "by_scene" not in report and "cells" not in report


def test_counts_use_both_denominators_and_keep_nonadmission_failures_and_fallback_distinct():
    manifest = design()
    rows = [record(s, "no_app") for s in manifest]
    rows[0] = measured(record(manifest[0], "engage_goal"), "attempt_self")
    rows[1] = measured(record(manifest[1], "engage_goal"), "seek_help_then_attempt")
    rows[2] = record(manifest[2], "defer_goal")
    rows[3] = record(manifest[3], None)
    rows[4] = measured(record(manifest[4], "engage_goal"), "seek_help_then_attempt", fallback=True)
    rows[5] = record(manifest[5], "engage_goal")  # lost after Plan, no observed lower result
    report = summarize(manifest, list(reversed(rows)))
    overall = report["overall"]
    assert overall["admission"]["confirmed_yes"] == 4
    assert overall["admission"]["unknown"] == 1
    assert overall["help_all_decisions"]["denominator"] == 24
    assert overall["help_all_decisions"]["confirmed_yes"] == 2
    assert overall["help_all_decisions"]["unknown"] == 2
    assert overall["help_among_confirmed_admissions"]["denominator"] == 4
    assert overall["help_among_confirmed_admissions"]["unknown"] == 1
    assert overall["defer_hours"] == [4]
    assert report["technical"] == {"plan_failures": 1, "admitted_without_lower_record": 1, "lower_fallbacks": 1}
    assert report["cells"]["S0"]["success"]["decisions"] == 5
    assert report["repeat_controls"]["decisions"] == 4
    matched = report["by_scene"]["S0"]["contrast"]
    assert matched["admission"]["observed_pairs"] == 4
    assert matched["lower_model_valid_both"]["pairs"] == 1
    assert matched["lower_model_valid_both"]["strategy"]["flips"] == 1


def test_contrast_direction_and_repeat_noise_including_plan_scores():
    manifest = design()
    rows = [measured(record(s, "engage_goal"), "attempt_self") for s in manifest]
    for r in rows:
        scores = dict(WEIGHTS)
        extra = 0.1 if r["member"] == "A" else 0
        scores.update(attempt_self=.5 + extra, avoid=.15 - extra)
        r["lower"]["raw_scores"] = scores
        r["plan_scores"] = dict(PLAN_SCORES, confidence=.9 - extra)
    report = summarize(manifest, rows)
    for scene in ("S0", "S1"):
        contrast = report["by_scene"][scene]["contrast"]
        repeat = report["by_scene"][scene]["repeat"]
        c = contrast["lower_model_valid_both"]["mean_score_differences"]["raw_scores"]
        n = repeat["lower_model_valid_both"]["mean_score_differences"]["raw_scores"]
        assert c["attempt_self"] == pytest.approx(-.1) and n["attempt_self"] == pytest.approx(.1)
        assert c["avoid"] == pytest.approx(.1) and n["avoid"] == pytest.approx(.1)
        assert contrast["mean_plan_score_differences"]["confidence"] == pytest.approx(.1)


def test_manifest_and_observation_integrity():
    manifest = design()
    row = record(manifest[0], "no_app")
    for broken, rows in ((manifest[:-1], []),
                         (manifest, [row, row]),
                         (manifest, [dict(row, sample_u=.51)]),
                         (manifest, [dict(row, sample_u=True)]),
                         (manifest, [dict(row, task_admitted=True)]),
                         (manifest, [dict(row, lower={})]),
                         (manifest, [dict(row, pair_id="unexpected")])):
        with pytest.raises(ValueError):
            summarize(broken, rows)
    corrupt = deepcopy(manifest)
    corrupt[1]["sample_u"] = .7
    with pytest.raises(ValueError):
        summarize(corrupt, [])


def test_help_requires_an_observed_request_and_valid_lower_values():
    manifest = design()
    cell = measured(record(manifest[0], "engage_goal"), "seek_help_then_attempt")
    for patch in ({"help_request": None}, {"sample_u": .4},
                  {"final_weights": {**WEIGHTS, "avoid": float("nan")}},
                  {"help_delivery_status": "delivered"}):
        with pytest.raises(ValueError):
            summarize(manifest, [dict(cell, lower={**cell["lower"], **patch})])
