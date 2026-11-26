"""Compare two archived strategy-prompt studies without making model requests."""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from analysis_strategy_memory_pairs import ACTIONS, summarize


SCORE_KEYS = dict(zip(ACTIONS, ("attempt_self_score", "seek_help_score", "avoid_score")))


def _dialog(messages):
    if len(messages) != 2 or [m["role"] for m in messages] != ["system", "user"]:
        raise ValueError("expected one system and one user message")
    prefix, body = messages[1]["content"].split("\n", 1)
    return messages[0], prefix, json.loads(body)


def stimuli_match(original, revised, revised_format):
    """Verify that exactly the planned change was made to each archived dialog."""
    if set(original) != {"success", "failure"} or original.keys() != revised.keys():
        return False
    for condition in original:
        system, prefix, body = _dialog(original[condition])
        new_system, new_prefix, new_body = _dialog(revised[condition])
        if revised_format == "field_rules":
            example = body.pop("output_schema_example", None)
            rules = new_body.pop("output_field_rules", None)
            if not isinstance(example, dict) or not isinstance(rules, dict) or set(example) != set(rules):
                return False
        elif revised_format == "field_rules_no_priors":
            weights = body.pop("rule_weights", None)
            if (not _valid_rule_weights(weights) or not isinstance(body.get("output_field_rules"), dict)
                    or "output_schema_example" in body):
                return False
        else:
            return False
        if (system, prefix, body) != (new_system, new_prefix, new_body):
            return False
    return True


def _valid_rule_weights(weights):
    return (isinstance(weights, dict) and set(weights) == set(ACTIONS)
            and all(type(v) in (float, int) and 0 <= v <= 1 for v in weights.values())
            and math.isclose(sum(weights.values()), 1, abs_tol=1e-5))


def _match_counts(rows, examples=None):
    accepted = [row for row in rows if row["source"] == "hybrid_blended"]
    parsed = matched = with_confidence = rule_matched = with_rule = 0
    for row in accepted:
        scores = row.get("raw_scores")
        if not isinstance(scores, dict) or not all(type(scores.get(k)) in (int, float) for k in ACTIONS):
            continue
        parsed += 1
        example = examples.get(row["condition"]) if examples else None
        if example and all(math.isclose(scores[k], example[SCORE_KEYS[k]], abs_tol=1e-12, rel_tol=0) for k in ACTIONS):
            matched += 1
            with_confidence += math.isclose(row["confidence"], example["judge_confidence"], abs_tol=1e-12, rel_tol=0)
        rules = row.get("rule_weights", {})
        if all(type(rules.get(k)) in (int, float) for k in ACTIONS):
            with_rule += 1
            rule_matched += all(math.isclose(scores[k], rules[k], abs_tol=1e-12, rel_tol=0) for k in ACTIONS)
    result = {"accepted_model_arms": len(accepted), "accepted_with_raw_scores": parsed,
              "accepted_with_rule_and_raw_scores": with_rule, "three_scores_equal_backend_rule_weights": rule_matched}
    if examples:
        result.update(three_scores_equal_original_example=matched,
                      three_scores_and_confidence_equal_original_example=with_confidence,
                      three_score_match_rate=matched / parsed if parsed else None,
                      three_scores_equal_input_rule_weights=rule_matched)
    return result


def _load(folder):
    folder = Path(folder)
    design = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    stimuli = json.loads((folder / "stimuli.json").read_text(encoding="utf-8"))
    with (folder / "decisions.jsonl").open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    metrics = summarize(rows)
    schedule = [(pair["pair_id"], arm, pair["kind"], pair["conditions"][arm], pair["sample_u"])
                for pair in design["pairs"] for arm in pair["order"]]
    observed = [(r["pair_id"], r["arm"], r["kind"], r["condition"], r["sample_u"]) for r in rows]
    returned = Counter(model for row in rows for model in row["returned_models"])
    ids_complete = all(len(r["returned_models"]) + len(r["transport_errors"]) == r["requests"]
                       and (r["source"] != "hybrid_blended" or r["returned_models"]) for r in rows)
    expected_inputs = {(r["pair_id"], r["arm"]): (r["condition"], r["sample_u"]) for r in rows}
    actual_requests, initial_arms, parameters = Counter(), set(), defaultdict(set)
    trace_ok = True
    for path in sorted((folder / "trace").glob("llm-requests-*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                trace = json.loads(line)
                if trace["kind"] != "request" or trace["module"] != "strategy":
                    continue
                key = trace["pair_id"], trace["arm"]
                actual_requests[key] += 1
                if trace["phase"] != "initial":
                    continue
                initial_arms.add(key)
                cond = trace["condition"]
                trace_ok &= (expected_inputs.get(key) == (cond, trace["sample_u"]) and cond in stimuli
                             and _dialog(trace["messages"]) == _dialog(stimuli[cond])
                             and trace["model"] == design["model"])
                parameters[key].add(json.dumps(trace["parameters"], sort_keys=True))
    expected_counts = {(r["pair_id"], r["arm"]): r["requests"] for r in rows}
    audit = {
        "complete_as_planned": metrics["coverage"]["complete_as_planned"],
        "actual_order_matches_design": bool(rows) and schedule == observed,
        "requests_match_recorded_stimuli": bool(rows) and trace_ok and initial_arms == expected_inputs.keys()
                                         and actual_requests == expected_counts,
        "returned_models": dict(returned), "returned_model_ids_complete": ids_complete,
    }
    return design, stimuli, rows, metrics, audit, parameters


def compare_runs(original_dir, revised_dir):
    old, new = _load(original_dir), _load(revised_dir)
    ref, new_design = old[0], new[0]
    revised_format = new_design.get("prompt_format", "field_rules")
    hiding_priors = revised_format == "field_rules_no_priors"
    input_change = "only_rule_weights_removed" if hiding_priors else "only_output_spec_changed"
    baseline = {cond: _dialog(messages)[2] for cond, messages in old[1].items()}
    examples = {cond: body.get("output_schema_example") for cond, body in baseline.items()}
    checks = {
        input_change: stimuli_match(old[1], new[1], revised_format),
        "same_schedule_and_draws": ref["pairs"] == new_design["pairs"],
        "same_design_settings": all(k in ref and ref[k] == new_design.get(k)
                                    for k in ("model", "order_and_sampling_seed", "sdk_retries", "strategy_cache")),
        "same_initial_request_parameters": bool(old[5]) and old[5] == new[5],
        "same_returned_model_as_requested": all(
            set(run[4]["returned_models"]) == {ref["model"]} and run[4]["returned_model_ids_complete"]
            for run in (old, new)),
        "both_complete_and_verified": all(all(run[4][key] for key in (
            "complete_as_planned", "actual_order_matches_design", "requests_match_recorded_stimuli")) for run in (old, new)),
    }
    if hiding_priors:
        checks["same_backend_rule_weights"] = all(
            _valid_rule_weights(r.get("rule_weights")) and r["rule_weights"] == baseline[r["condition"]].get("rule_weights")
            for run in (old, new) for r in run[2]
        )
    result = {"comparison_checks": checks, "matched_design": all(checks.values())}
    for name, run in (("original", old), ("revised", new)):
        metrics, audit = run[3:5]
        result[name] = {
            "audit": audit, "coverage": metrics["coverage"], "requests": metrics["requests_total"],
            "status_counts": metrics["status_counts"], "source_counts": metrics["source_counts"],
            "contrast": metrics["contrast"], "repeat": metrics["repeat"],
        }
        if hiding_priors:
            result[name]["raw_match_to_backend_rule_weights"] = _match_counts(run[2])
        else:
            result[name]["raw_match_to_original_example"] = _match_counts(run[2], examples)
    # Only subtract when both runs completed the same design with the intended input change.
    if result["matched_design"]:
        differences = {}
        for kind, name in (("contrast", "mean_weight_difference_B_minus_A"), ("repeat", "mean_absolute_weight_difference")):
            previous = old[3][kind]["all_complete"][name]
            current = new[3][kind]["all_complete"][name]
            differences[kind] = {key: current[key] - previous[key] for key in ACTIONS}
        old_arms = old[3]["contrast"]["all_complete"]["mean_weights_by_arm"]
        new_arms = new[3]["contrast"]["all_complete"]["mean_weights_by_arm"]
        differences["contrast_mean_weights_by_arm"] = {
            arm: {k: new_arms[arm][k] - old_arms[arm][k] for k in ACTIONS} for arm in old_arms
        }
        result["revised_minus_original_all_complete"] = differences
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("revised", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare_runs(args.original, args.revised), ensure_ascii=False, indent=2, allow_nan=False))
