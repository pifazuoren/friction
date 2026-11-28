"""Resident-paired descriptive statistics for the guided versus proxy completion probe."""

from collections import Counter, defaultdict
from statistics import fmean

from analysis_hourly_factorial import PLAN_SCORES, _rate, _validate_observation
from analysis_strategy_memory_pairs import ACTIONS

CONDITIONS = ("guided", "proxy")
ENDPOINTS = (
    "independent_strategy_selected",
    "help_request_received",
    "avoid_after_admission",
    "deferred",
    "dropped",
    "other_app_activity",
    "no_app",
)
STRATEGIES = {
    "attempt_self": "independent_strategy_selected",
    "seek_help_then_attempt": "help_request_received",
    "avoid": "avoid_after_admission",
}
OUTSIDE_TASK = {
    "defer_goal": "deferred",
    "drop_goal": "dropped",
    "habitual_app": "other_app_activity",
    "no_app": "no_app",
}
APPRAISAL_FIELDS = (
    "perceived_task_difficulty",
    "perceived_task_risk",
    "felt_control",
    "expected_help_effectiveness",
    "task_value",
)


def _index_schedule(manifest):
    slots = {}
    pairs = defaultdict(dict)
    by_resident = defaultdict(Counter)
    control_conditions = Counter()
    stimuli = {}
    ranks = {}
    for spec in manifest:
        resident, rank = spec["profile_id"], spec["selected_rank"]
        pair_id, member = spec["pair_id"], spec["member"]
        kind, condition = spec["kind"], spec["condition"]
        key = pair_id, member
        if (
            key in slots
            or not pair_id
            or member not in ("A", "B")
            or kind not in ("contrast", "repeat")
            or condition not in CONDITIONS
            or type(spec["pair_seed"]) is not int
            or type(spec["sample_u"]) not in (int, float)
            or not 0 <= spec["sample_u"] < 1
            or type(resident) is not int
            or type(rank) is not int
        ):
            raise ValueError("Invalid or duplicate scheduled observation")
        if ranks.setdefault(rank, resident) != resident:
            raise ValueError("Profile rank has changed")
        digest = spec["plan_stimulus_sha256"]
        if not digest or stimuli.setdefault((resident, condition), digest) != digest:
            raise ValueError("Inconsistent frozen Plan for this resident and condition")
        slots[key] = spec
        pairs[pair_id][member] = spec
    for arms in pairs.values():
        if set(arms) != {"A", "B"}:
            raise ValueError("Missing scheduled pair member")
        a, b = arms["A"], arms["B"]
        if any(
            a[k] != b[k]
            for k in ("profile_id", "kind", "selected_rank", "pair_seed", "sample_u")
        ):
            raise ValueError("Different profile, type or random draw in a matched pair")
        kind = a["kind"]
        if kind == "contrast":
            if (a["condition"], b["condition"]) != CONDITIONS or a[
                "plan_stimulus_sha256"
            ] == b["plan_stimulus_sha256"]:
                raise ValueError(
                    "Contrast requires guidance in A and proxy completion in B"
                )
        else:
            if a["condition"] != b["condition"]:
                raise ValueError("Same-input controls must use the same condition")
            control_conditions[a["condition"]] += 1
        by_resident[a["profile_id"]][kind] += 1
    if (
        len(by_resident) != 10
        or set(ranks) != set(range(1, 11))
        or any(n != {"contrast": 3, "repeat": 1} for n in by_resident.values())
        or control_conditions != {"guided": 5, "proxy": 5}
    ):
        raise ValueError(
            "Expected three contrasts and one balanced repeat per resident"
        )
    return slots, pairs


def _action(row):
    if not row["plan_valid"]:
        return None
    if not row["task_admitted"]:
        return OUTSIDE_TASK[row["policy_choice"]]
    lower = row["lower"]
    return STRATEGIES[lower["sampled_action"]] if lower is not None else None


def _counts(rows):
    """Count every scheduled first opportunity, including behavior missing after a technical failure."""
    actions = [_action(row) for row in rows]
    rates = {
        label: _rate(
            [None if action is None else action == label for action in actions]
        )
        for label in ENDPOINTS
    }
    return {
        "scheduled_opportunities": len(rows),
        "unknown_action": actions.count(None),
        "endpoints": rates,
    }


def _measures(row):
    """Only adopted judgments contribute model scores. Executed fallback choices remain observable."""
    action = _action(row)
    lower = row["lower"]
    result = {k: None if action is None else int(action == k) for k in ENDPOINTS}
    for name in (
        "independent_strategy_selected",
        "help_request_received",
        "avoid_after_admission",
    ):
        result["model_valid." + name] = (
            None if lower is not None and not lower["lower_valid"] else result[name]
        )
    result.update(
        {
            "plan." + k: row["plan_scores"][k] if row["plan_valid"] else None
            for k in PLAN_SCORES
        }
    )
    for field in APPRAISAL_FIELDS:
        result["appraisal." + field] = (
            lower["appraisal"][field]
            if lower and lower["appraisal"]["source"] == "llm"
            else None
        )
    for strategy in ACTIONS:
        result["raw_score." + strategy] = (
            lower["raw_scores"][strategy]
            if lower
            and lower["raw_scores"] is not None
            and lower["strategy_source"] == "hybrid_blended"
            else None
        )
    return result


def _paired_summary(profile_pairs, repeat):
    """First average matched observations within profile, then weight each observed profile equally."""
    person_means = defaultdict(list)
    per_profile = []
    total_pairs = Counter()
    for resident, pairs in sorted(profile_pairs.items()):
        differences = defaultdict(list)
        disagreements = []
        for a, b in pairs:
            am, bm = _measures(a), _measures(b)
            for name, value in am.items():
                values = differences[name]
                if value is not None and bm[name] is not None:
                    delta = value - bm[name]
                    values.append(abs(delta) if repeat else delta)
            if _action(a) is not None and _action(b) is not None:
                disagreements.append(int(_action(a) != _action(b)))
        differences["any_action_disagreement"] = disagreements
        metrics = {}
        for name, values in differences.items():
            mean = fmean(values) if values else None
            metrics[name] = {"observed_pairs": len(values), "mean": mean}
            total_pairs[name] += len(values)
            if mean is not None:
                person_means[name].append(mean)
        per_profile.append(
            {"profile_id": resident, "scheduled_pairs": len(pairs), "metrics": metrics}
        )
    return {
        "calculation": "absolute same-input difference"
        if repeat
        else "guided minus proxy",
        "per_profile": per_profile,
        "equal_profile_means": {
            name: {
                "profiles": len(person_means[name]),
                "observed_pairs": n,
                "mean": fmean(person_means[name]) if person_means[name] else None,
            }
            for name, n in total_pairs.items()
        },
    }


def summarize(manifest, rows):
    slots, pairs = _index_schedule(manifest)
    index = {}
    rule_baselines = {}
    for row in rows:
        key = row["pair_id"], row["member"]
        if (
            key not in slots
            or key in index
            or any(
                type(row.get(k)) is not type(v) or row.get(k) != v
                for k, v in slots[key].items()
            )
        ):
            raise ValueError("Unscheduled, duplicated, or changed observation")
        _validate_observation(row)
        lower = row["lower"]
        if lower:
            if lower["help_request_dispatched"] != (
                lower["sampled_action"] == "seek_help_then_attempt"
            ):
                raise ValueError(
                    "Help choice lacks the observed local request, or a different action sent one"
                )
            receipt = (lower["rule_inputs"], lower["rule_weights"])
            if not receipt[0] or receipt != rule_baselines.setdefault(
                row["profile_id"], receipt
            ):
                raise ValueError(
                    "Numerical rule inputs or weights changed within one resident"
                )
            if (
                lower["operation_started"] is not None
                or lower["task_outcome"] is not None
            ):
                raise ValueError("This probe ends before an operation or task outcome")
        index[key] = row
    missing = [list(key) for key in slots if key not in index]
    technical = {
        "invalid_plans": sum(not r["plan_valid"] for r in rows),
        "missing_after_admission": sum(
            r["task_admitted"] is True and r["lower"] is None for r in rows
        ),
        "lower_fallbacks": sum(
            r["lower"] is not None and not r["lower"]["lower_valid"] for r in rows
        ),
    }
    report = {
        "complete": not missing and not any(r.get("interrupted_stage") for r in rows),
        "coverage": {
            "profiles": 10,
            "planned_decisions": len(slots),
            "recorded_decisions": len(index),
            "missing_decisions": missing,
        },
        "technical": technical,
    }
    if not report["complete"]:
        return report
    contrast = [r for r in rows if r["kind"] == "contrast"]
    report["by_condition"] = {
        c: _counts([r for r in contrast if r["condition"] == c]) for c in CONDITIONS
    }
    for kind in ("contrast", "repeat"):
        by_profile = defaultdict(list)
        for pair_id, arms in pairs.items():
            a = arms["A"]
            if a["kind"] == kind:
                by_profile[a["profile_id"]].append(
                    (index[pair_id, "A"], index[pair_id, "B"])
                )
        report[kind] = _paired_summary(by_profile, repeat=kind == "repeat")
    report["interpretation"] = {
        "unit": "10 paired synthetic residents. Repeated decisions are nested within each resident.",
        "coverage": "Endpoint counts include all 30 opportunities per treatment; technical failures are unknown. "
        "Model-valid sensitivity marks lower fallbacks as unknown. Paired means only use matched, "
        "observed endpoints; always report their coverage.",
        "noise": "Compare contrast action disagreement to same-input disagreement and inspect per-profile direction. "
        "One repeat pair per resident is a descriptive noise reference, not a significance test.",
        "measurement": "Single first decision. Independent strategy selection and local request receipt are observed; "
        "operation starts, subsequent retries, delivered help and task outcomes are unobserved.",
        "attribution": "Numerical baselines and rule weights are fixed. This estimates the direct effect of the "
        "displayed help facts on simulated choices. A null result is allowed.",
    }
    return report
