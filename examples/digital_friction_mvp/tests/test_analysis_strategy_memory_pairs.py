from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis_strategy_memory_pairs import ACTIONS, summarize


def arm(pair_id, arm, condition, weights, action, *, repeat=False, fallback=False):
    return {"pair_id": pair_id, "arm": arm, "condition": condition, "kind": "repeat" if repeat else "contrast",
            "source": "rule_fallback_parse_failed" if fallback else "hybrid_blended",
            "status": "parse_failed" if fallback else "ok", "requests": 2 if fallback else 1,
            "final_weights": dict(zip(ACTIONS, weights)), "sampled_action": action}


def test_signed_contrast_noise_and_fallbacks():
    rows = [
        arm("1", "B", "failure", (.1,.7,.2), "seek_help_then_attempt"),
        arm("2", "A", "success", (.2,.6,.2), "seek_help_then_attempt"),
        arm("1", "A", "success", (.5,.3,.2), "attempt_self"),
        arm("2", "B", "failure", (.6,.2,.2), "seek_help_then_attempt", fallback=True),
        arm("3", "B", "failure", (.6,.3,.1), "avoid", repeat=True),
        arm("3", "A", "failure", (.5,.2,.3), "avoid", repeat=True),
    ]
    s = summarize(rows)
    assert s["coverage"]["complete_pairs"] == 3 and s["coverage"]["fallback_arms"] == 1
    assert not s["coverage"]["complete_as_planned"]
    assert s["requests_total"] == 7 and s["status_counts"] == {"ok": 5, "parse_failed": 1}
    c = s["contrast"]
    assert c["all_complete"]["mean_weight_difference_B_minus_A"] == pytest.approx(dict.fromkeys(ACTIONS, 0))
    assert c["hybrid_only"]["mean_weight_difference_B_minus_A"] == pytest.approx(dict(zip(ACTIONS, (-.4,.4,0))))
    assert c["all_complete"]["action_flips"] == 1 and c["hybrid_only_pairs"] == 1
    assert c["all_complete"]["mean_weights_by_arm"]["A_success"] == pytest.approx(dict(zip(ACTIONS, (.35,.45,.2))))
    assert c["all_complete"]["sampled_action_counts_by_arm"]["B_failure"] == dict(zip(ACTIONS, (0,2,0)))
    assert c["hybrid_only"]["mean_weights_by_arm"]["B_failure"] == pytest.approx(dict(zip(ACTIONS, (.1,.7,.2))))
    assert c["hybrid_only"]["sampled_action_counts_by_arm"]["A_success"] == dict(zip(ACTIONS, (1,0,0)))
    assert s["repeat"]["all_complete"]["mean_absolute_weight_difference"] == pytest.approx(dict(zip(ACTIONS, (.1,.1,.2))))
    assert s["repeat"]["all_complete"]["action_flips"] == 0


def test_partial_duplicate_and_mismatched_pairs_are_identified():
    a = arm("partial", "A", "success", (.5,.3,.2), "attempt_self")
    rows = [a, dict(a, pair_id="dup"), dict(a, pair_id="dup"), dict(a, pair_id="dup", arm="B", condition="failure"),
            dict(a, pair_id="bad"), dict(a, pair_id="bad", arm="B"),
            dict(a, pair_id="bad_repeat", kind="repeat"), dict(a, pair_id="bad_repeat", kind="repeat", arm="B", condition="failure")]
    s = summarize(rows)
    assert s["coverage"]["complete_pairs"] == 0 and s["coverage"]["observed_arms"] == 7
    assert s["coverage"]["recorded_rows"] == s["requests_total"] == 8
    assert s["excluded_pairs"] == {"partial": "missing arm B", "dup": "duplicate arm",
                                   "bad": "condition mismatch", "bad_repeat": "condition mismatch"}
    assert s["contrast"]["all_complete"]["mean_weight_difference_B_minus_A"]["avoid"] is None
    assert s["contrast"]["all_complete"]["mean_weights_by_arm"]["A_success"]["avoid"] is None
    assert s["contrast"]["hybrid_only"]["sampled_action_counts_by_arm"]["B_failure"]["avoid"] == 0


def test_fixed_design_coverage_and_invalid_outputs():
    rows = []
    for index in range(13):
        repeat = index >= 10
        rows.append(arm(str(index), "A", "success", (.5,.3,.2), "avoid", repeat=repeat))
        rows.append(arm(str(index), "B", "success" if repeat else "failure", (.5,.3,.2), "avoid", repeat=repeat))
    assert summarize(rows)["coverage"]["complete_as_planned"]
    assert not summarize(rows[:-2])["coverage"]["complete_as_planned"]
    assert summarize([])["coverage"]["planned_arms"] == 26
    rows[0]["final_weights"]["avoid"] = float("nan")
    with pytest.raises(ValueError, match="invalid final weights"):
        summarize(rows)
