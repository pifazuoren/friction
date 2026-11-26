import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_strategy_prompt_runs import ACTIONS, compare_runs


def archive(folder, revised=False, drift=None, prompt_format=None):
    folder.mkdir()
    (folder / "trace").mkdir()
    rows, pairs, traces, stimuli = [], [], [], {}
    example = {"attempt_self_score": .2, "seek_help_score": .5, "avoid_score": .3, "judge_confidence": .8}
    rules = dict(zip(ACTIONS, (.2,.5,.3)))
    prompt_format = prompt_format or ("field_rules" if revised else "scored_example")
    for condition in ("success", "failure"):
        spec = ({"output_schema_example": example} if prompt_format == "scored_example"
                else {"output_field_rules": dict.fromkeys(example, "number")})
        body = {"condition": condition, "prompt_version": "changed" if drift == "prompt" else "shared", **spec}
        if prompt_format != "field_rules_no_priors" or drift == "visible":
            body["rule_weights"] = rules
        stimuli[condition] = [{"role": "system", "content": "Decide"},
                              {"role": "user", "content": "Return JSON.\n" + json.dumps(body, indent=2 if revised else None)}]
    for index in range(13):
        kind = "contrast" if index < 10 else "repeat"
        conditions = {"A": "success", "B": "failure" if index < 10 else "success"}
        pairs.append(dict(pair_id=str(index), kind=kind, order=["A","B"], conditions=conditions, sample_u=.5))
        for arm in ("A", "B"):
            fallback = revised and index == 0 and arm == "B"
            condition = conditions[arm]
            weights = dict(zip(ACTIONS, (.4,.4,.2) if revised and arm == "B" else (.2,.5,.3)))
            row = dict(pair_id=str(index), kind=kind, arm=arm, condition=condition, sample_u=.5,
                       final_weights=weights, raw_scores=None if fallback else weights, rule_weights=rules,
                       source="rule_fallback_invalid_schema" if fallback else "hybrid_blended",
                       status="invalid_schema" if fallback else "ok", confidence=.8, sampled_action="attempt_self",
                       requests=1, returned_models=["different" if drift == "model" else "model"], transport_errors=[])
            rows.append(row)
            traces.append(dict(pair_id=str(index), arm=arm, condition=condition, sample_u=.5,
                               kind="request", module="strategy", phase="initial", model="model",
                               messages=stimuli[condition], parameters={"temperature": .1}))
    design = dict(model="model", order_and_sampling_seed=101, pairs=pairs, sdk_retries=0, strategy_cache=False,
                  prompt_format=prompt_format)
    if drift == "backend":
        rows[0]["rule_weights"] = dict(zip(ACTIONS, (.5,.2,.3)))
    if drift == "order":
        rows[0], rows[1] = rows[1], rows[0]
    if drift == "trace":
        traces[0]["messages"] = stimuli["failure"]
    for filename, value in (("design.json", design), ("stimuli.json", stimuli)):
        (folder/filename).write_text(json.dumps(value))
    for filename, values in (("decisions.jsonl", rows), ("trace/llm-requests-1.jsonl", traces)):
        (folder/filename).write_text("\n".join(map(json.dumps, values)))


def test_matched_runs_expose_noise_and_example_denominators(tmp_path):
    old, new = tmp_path/"old", tmp_path/"new"
    archive(old)
    archive(new, revised=True)
    result = compare_runs(old, new)
    assert result["matched_design"]
    assert result["original"]["raw_match_to_original_example"]["three_scores_equal_original_example"] == 26
    matches = result["revised"]["raw_match_to_original_example"]
    assert matches["three_scores_equal_original_example"] == 13 and matches["accepted_with_raw_scores"] == 25
    assert matches["three_scores_equal_input_rule_weights"] == 13 and matches["accepted_with_rule_and_raw_scores"] == 25
    assert result["revised"]["coverage"]["fallback_arms"] == 1
    difference = result["revised_minus_original_all_complete"]
    assert difference["contrast"]["attempt_self"] == pytest.approx(.2)
    assert difference["repeat"]["attempt_self"] == pytest.approx(.2)
    assert difference["contrast_mean_weights_by_arm"]["B_failure"]["attempt_self"] == pytest.approx(.2)


@pytest.mark.parametrize("drift,key", [("prompt","only_output_spec_changed"), ("model","same_returned_model_as_requested"),
                                        ("order","both_complete_and_verified"), ("trace","both_complete_and_verified")])
def test_unmatched_changes_are_visible(tmp_path, drift, key):
    old, new = tmp_path/"old", tmp_path/"new"
    archive(old)
    archive(new, revised=True, drift=drift)
    report = compare_runs(old, new)
    assert not report["matched_design"] and not report["comparison_checks"][key]
    assert "revised_minus_original_all_complete" not in report


@pytest.mark.parametrize("drift,failed_check", [(None, None), ("visible", "only_rule_weights_removed"),
                                               ("backend", "same_backend_rule_weights"),
                                               ("prompt", "only_rule_weights_removed")])
def test_hide_only_visible_rules_while_keeping_backend_rules(tmp_path, drift, failed_check):
    old, new = tmp_path/"visible", tmp_path/"blind"
    archive(old, prompt_format="field_rules")
    archive(new, revised=True, prompt_format="field_rules_no_priors", drift=drift)
    report = compare_runs(old, new)
    if failed_check:
        assert not report["matched_design"]
        assert not report["comparison_checks"][failed_check]
        assert "revised_minus_original_all_complete" not in report
    else:
        assert report["matched_design"]
        matches = report["revised"]["raw_match_to_backend_rule_weights"]
        assert matches["three_scores_equal_backend_rule_weights"] == 13
        assert matches["accepted_with_rule_and_raw_scores"] == 25
        assert "raw_match_to_original_example" not in report["revised"]
