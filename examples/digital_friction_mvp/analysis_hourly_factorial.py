"""Descriptive analysis of the preregistered 24-point V4 login and help probe."""

from collections import Counter, defaultdict
from math import isclose
from statistics import fmean

from analysis_strategy_memory_pairs import ACTIONS


SCENES = ("S0", "S1")
PLAN_SCORES = ("attitude", "subjective_norm", "perceived_control", "confidence")
POLICIES = {"engage_goal", "defer_goal", "drop_goal", "habitual_app", "no_app"}
STRATEGY_MEASURES = ("raw_scores", "llm_weights", "rule_weights", "blended_weights", "final_weights")


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _unit_number(value):
    return type(value) in (int, float) and 0 <= value <= 1


def _check_vector(values, keys, name, *, normalized=False):
    _require(isinstance(values, dict) and set(values) == set(keys)
             and all(_unit_number(v) for v in values.values()), f"Invalid {name}")
    if normalized:
        _require(isclose(sum(values.values()), 1, abs_tol=0.0001), f"Unnormalized {name}")


def _index_design(manifest):
    slots = {}
    pairs = defaultdict(list)
    for slot in manifest:
        pair_id, member = slot["pair_id"], slot["member"]
        key = pair_id, member
        _require(isinstance(pair_id, str) and pair_id and member in ("A", "B") and key not in slots,
                 "Invalid or duplicate manifest member")
        _require(slot["scene"] in SCENES and slot["kind"] in ("contrast", "repeat"),
                 "Invalid scene or pair type")
        _require(_unit_number(slot["sample_u"]) and slot["sample_u"] < 1 and type(slot["pair_seed"]) is int,
                 "Invalid common random input")
        success = member == "A" if slot["kind"] == "contrast" else slot["scene"] == "S0"
        _require(slot["condition"] == ("success" if success else "failure"), "Unexpected historical condition")
        slots[key] = slot
        pairs[pair_id].append(slot)
    counts = Counter()
    for pair in pairs.values():
        _require(len(pair) == 2 and all(pair[0][k] == pair[1][k] for k in ("kind", "scene", "sample_u", "pair_seed")),
                 "Incomplete pair or differing common random input")
        counts[pair[0]["scene"], pair[0]["kind"]] += 1
    expected = {(s, k): n for s in SCENES for k, n in (("contrast", 5), ("repeat", 1))}
    _require(counts == expected, "Expected five contrast pairs and one repeat per scene")
    return slots


def _validate_lower(row):
    lower = row["lower"]
    _require(isinstance(lower, dict) and row["task_admitted"] is True, "Lower result requires admission")
    _require(_unit_number(lower["sample_u"]) and lower["sample_u"] == row["sample_u"],
             "Strategy draw differs from the preregistered sample")
    _require(lower["sampled_action"] in ACTIONS and type(lower["lower_valid"]) is bool,
             "Invalid sampled strategy or model status")
    dispatched = lower["help_request_dispatched"]
    request = lower["help_request"]
    _require(type(dispatched) is bool and lower["help_delivery_status"] == "unobserved",
             "Invalid help observation")
    if dispatched:
        _require(lower["sampled_action"] == "seek_help_then_attempt" and isinstance(request, dict)
                 and bool(request.get("request_id")),
                 "A dispatched request needs an observed support request")
    else:
        _require(request is None, "A received support request cannot be counted as undispatched")
    for field in STRATEGY_MEASURES:
        value = lower[field]
        if value is None and field in ("llm_weights", "raw_scores") and not lower["lower_valid"]:
            continue
        _check_vector(value, ACTIONS, field, normalized=field != "raw_scores")


def _validate_observation(row):
    valid, admitted, choice = row["plan_valid"], row["task_admitted"], row["policy_choice"]
    _require(type(valid) is bool, "Invalid plan_valid")
    if valid:
        _require(choice in POLICIES and admitted is (choice == "engage_goal"),
                 "Plan and recorded task admission disagree")
        _check_vector(row["plan_scores"], PLAN_SCORES, "Plan scores")
        _require(isinstance(row["plan_reason"], str) and row["plan_reason"].strip(), "Missing accepted Plan reason")
    else:
        _require(choice is None and admitted is None, "A failed Plan has no behavioral choice")
    delay = row["defer_hours"]
    _require((type(delay) is int and 1 <= delay <= 24) if choice == "defer_goal" else delay is None,
             "Invalid deferral duration")
    if row["lower"] is not None:
        _validate_lower(row)


def _help(row):
    if row["lower"] is not None:
        return row["lower"]["help_request_dispatched"]
    # A valid decision to stay outside the task implies no request at this point.
    return False if row["task_admitted"] is False else None


def _rate(observations):
    n = len(observations)
    yes = sum(v is True for v in observations)
    unknown = sum(v is None for v in observations)
    return {
        "confirmed_yes": yes, "confirmed_no": n - yes - unknown, "unknown": unknown, "denominator": n,
        "confirmed_yes_over_denominator": yes / n if n else None,
        "rate_if_fully_observed": yes / n if n and not unknown else None,
    }


def _outcomes(rows):
    admitted = [r for r in rows if r["task_admitted"] is True]
    lower = [r["lower"] for r in admitted if r["lower"] is not None]
    return {
        "decisions": len(rows),
        "admission": _rate([r["task_admitted"] for r in rows]),
        "help_all_decisions": _rate([_help(r) for r in rows]),
        "help_among_confirmed_admissions": _rate([_help(r) for r in admitted]),
        "policy_counts": dict(Counter(r["policy_choice"] for r in rows if r["plan_valid"])),
        "defer_hours": [r["defer_hours"] for r in rows if r["defer_hours"] is not None],
        "strategy_counts_including_fallbacks": dict(Counter(r["sampled_action"] for r in lower)),
        "strategy_counts_model_valid": dict(Counter(r["sampled_action"] for r in lower if r["lower_valid"])),
        "strategy_source_counts": dict(Counter(r["strategy_source"] for r in lower)),
    }


def _transitions(values):
    counts = Counter((a, b) for a, b in values if a is not None and b is not None)
    return {"observed_pairs": sum(counts.values()), "flips": sum(n for (a, b), n in counts.items() if a != b),
            "transitions_A_to_B": [{"A": a, "B": b, "pairs": n} for (a, b), n in sorted(counts.items())]}


def _mean_difference(values, repeat):
    differences = [abs(b - a) if repeat else b - a for a, b in values]
    return fmean(differences) if differences else None


def _score_differences(pairs, field, keys, repeat):
    return {k: _mean_difference([(a[field][k], b[field][k]) for a, b in pairs], repeat) for k in keys}


def _paired(pairs, *, repeat):
    valid_plans = [(a, b) for a, b in pairs if a["plan_valid"] and b["plan_valid"]]
    known_lower = [(a["lower"], b["lower"]) for a, b in pairs if a["lower"] is not None and b["lower"] is not None]
    valid_lower = [(a, b) for a, b in known_lower if a["lower_valid"] and b["lower_valid"]]
    deferred_both = [(a["defer_hours"], b["defer_hours"]) for a, b in valid_plans
                     if a["policy_choice"] == b["policy_choice"] == "defer_goal"]
    return {
        "pairs": len(pairs),
        "difference_definition": "mean_absolute_B_minus_A" if repeat else "mean_failure_minus_success",
        "admission": _transitions([(a["task_admitted"], b["task_admitted"]) for a, b in pairs]),
        "help_all_decisions": _transitions([(_help(a), _help(b)) for a, b in pairs]),
        "policy": _transitions([(a["policy_choice"], b["policy_choice"]) for a, b in pairs]),
        "both_deferred_pairs": len(deferred_both),
        "mean_defer_hours_difference_if_both_deferred": _mean_difference(deferred_both, repeat),
        "both_plans_valid": len(valid_plans),
        "mean_plan_score_differences": _score_differences(valid_plans, "plan_scores", PLAN_SCORES, repeat),
        "pairs_differing_in_plan_reason": sum(a["plan_reason"] != b["plan_reason"] for a, b in valid_plans),
        "strategy_including_fallbacks": _transitions([(a["sampled_action"], b["sampled_action"]) for a, b in known_lower]),
        "lower_model_valid_both": {
            "pairs": len(valid_lower),
            "strategy": _transitions([(a["sampled_action"], b["sampled_action"]) for a, b in valid_lower]),
            "help": _transitions([(a["help_request_dispatched"], b["help_request_dispatched"]) for a, b in valid_lower]),
            "mean_score_differences": {field: _score_differences(valid_lower, field, ACTIONS, repeat)
                                       for field in STRATEGY_MEASURES},
        },
    }


def summarize(manifest, rows):
    """Return progress on partial runs, and paired descriptive results once every point is recorded."""
    slots = _index_design(manifest)
    index = {}
    for row in rows:
        key = row["pair_id"], row["member"]
        _require(key in slots and key not in index, f"Unscheduled or duplicate decision {key}")
        for field, expected in slots[key].items():
            received = row.get(field)
            _require(type(received) is type(expected) and received == expected,
                     f"Recorded {field} differs from manifest for {key}")
        _validate_observation(row)
        index[key] = row
    missing = [list(key) for key in slots if key not in index]
    # Use frozen order even when the records are read back out of order.
    rows = [index[key] for key in slots if key in index]
    report = {
        "complete": not missing and not any(r.get("interrupted_stage") for r in rows),
        "coverage": {"planned_decisions": len(slots), "recorded_decisions": len(rows), "missing_decisions": missing},
        "technical": {
            "plan_failures": sum(not r["plan_valid"] for r in rows),
            "admitted_without_lower_record": sum(r["task_admitted"] is True and r["lower"] is None for r in rows),
            "lower_fallbacks": sum(r["lower"] is not None and not r["lower"]["lower_valid"] for r in rows),
        },
    }
    if not report["complete"]:
        return report
    report["interpretation"] = {
        "main_cells": "Four cells of five decisions. Four matched repeat observations are summarized separately.",
        "all_decisions": "Confirmed requests use every decision in the selected group as the denominator. "
                         "Unknown behavior is counted separately.",
        "conditional_help": "Among observed admissions; the set of admitted decisions may differ by condition.",
        "lower_pairs": "An action comparison requires both tasks to be admitted and both strategies observed. "
                       "Model-valid comparisons additionally require both appraisals and strategy judgments to be adopted.",
        "help_endpoint": "Receipt by the simulated request handler. Helper response and delivery are unobserved.",
    }
    report.update(overall=_outcomes(rows), repeat_controls=_outcomes([r for r in rows if r["kind"] == "repeat"]),
                  cells={}, by_scene={})
    for scene in SCENES:
        contrasts = [r for r in rows if r["scene"] == scene and r["kind"] == "contrast"]
        report["cells"][scene] = {c: _outcomes([r for r in contrasts if r["condition"] == c])
                                  for c in ("success", "failure")}
        report["by_scene"][scene] = {}
        for kind in ("contrast", "repeat"):
            pairs = [(a, index[a["pair_id"], "B"]) for a in rows
                     if a["scene"] == scene and a["kind"] == kind and a["member"] == "A"]
            report["by_scene"][scene][kind] = _paired(pairs, repeat=kind == "repeat")
    return report
