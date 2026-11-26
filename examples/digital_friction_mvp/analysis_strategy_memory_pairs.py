"""Descriptive summaries for the ten contrast pairs and three same-input repeats."""

from collections import Counter, defaultdict
import math
from statistics import fmean


ACTIONS = ("attempt_self", "seek_help_then_attempt", "avoid")
PLANNED = {"contrast": 10, "repeat": 3}


def _pair_metrics(pairs, kind):
    signed = kind == "contrast"
    key = "mean_weight_difference_B_minus_A" if signed else "mean_absolute_weight_difference"
    means = {}
    for action in ACTIONS:
        diffs = [b["final_weights"][action] - a["final_weights"][action] for a, b in pairs]
        means[action] = fmean(diffs if signed else map(abs, diffs)) if diffs else None
    metrics = {
        "pairs": len(pairs),
        key: means,
        "action_flips": sum(a["sampled_action"] != b["sampled_action"] for a, b in pairs),
    }
    if signed:
        means_by_arm, counts_by_arm = {}, {}
        for index, label in enumerate(("A_success", "B_failure")):
            arms = [pair[index] for pair in pairs]
            counts = Counter(arm["sampled_action"] for arm in arms)
            means_by_arm[label] = {
                action: fmean(arm["final_weights"][action] for arm in arms) if arms else None
                for action in ACTIONS
            }
            counts_by_arm[label] = {action: counts[action] for action in ACTIONS}
        metrics["mean_weights_by_arm"] = means_by_arm
        metrics["sampled_action_counts_by_arm"] = counts_by_arm
    return metrics


def summarize(rows):
    """Count every recorded request; use each complete, unambiguous A/B pair once."""
    groups = defaultdict(list)
    statuses, sources = Counter(), Counter()
    arm_sources = defaultdict(list)
    requests = 0
    for row in rows:
        pair_id, kind, arm = row["pair_id"], row["kind"], row["arm"]
        if not isinstance(pair_id, str) or not pair_id.strip() or kind not in PLANNED or arm not in ("A", "B"):
            raise ValueError(f"invalid pair identity: {(pair_id, kind, arm)!r}")
        count = row["requests"]
        if type(count) is not int or count < 0:
            raise ValueError(f"{pair_id}/{arm}: requests must be a nonnegative integer")
        weights = row["final_weights"]
        if (not isinstance(weights, dict) or set(weights) != set(ACTIONS) or row["sampled_action"] not in ACTIONS
                or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in weights.values())
                or not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-5)):
            raise ValueError(f"{pair_id}/{arm}: invalid final weights or action")
        if row["condition"] not in ("success", "failure"):
            raise ValueError(f"{pair_id}/{arm}: invalid historical condition")
        groups[pair_id].append(row)
        arm_sources[pair_id, arm].append(row["source"])
        requests += count
        sources[row["source"]] += 1
        statuses[row["status"]] += 1

    pairs = {k: [] for k in PLANNED}
    observed_counts = Counter()
    excluded = {}
    for pair_id, records in sorted(groups.items()):
        kinds = {r["kind"] for r in records}
        if len(kinds) != 1:
            excluded[pair_id] = "conflicting kinds"
            continue
        kind = kinds.pop()
        observed_counts[kind] += 1
        arms = {r["arm"]: r for r in records}
        if len(arms) != len(records):
            excluded[pair_id] = "duplicate arm"
            continue
        if len(arms) != 2:
            excluded[pair_id] = "missing arm " + ("B" if "A" in arms else "A")
            continue
        a, b = arms["A"], arms["B"]
        conditions = (a["condition"], b["condition"])
        if (kind == "contrast" and conditions != ("success", "failure")
                or kind == "repeat" and conditions[0] != conditions[1]):
            excluded[pair_id] = "condition mismatch"
            continue
        pairs[kind].append((a, b))

    complete = sum(map(len, pairs.values()))
    distinct_sources = Counter(items[0] for items in arm_sources.values() if len(items) == 1)
    fallback_arms = sum(n for source, n in distinct_sources.items() if source.startswith("rule_fallback"))
    result = {
        "coverage": {"planned_pairs": sum(PLANNED.values()), "observed_pairs": len(groups),
                     "complete_pairs": complete, "planned_arms": 2 * sum(PLANNED.values()),
                     "observed_arms": len(arm_sources), "recorded_rows": sum(sources.values()),
                     "hybrid_arms": distinct_sources["hybrid_blended"], "fallback_arms": fallback_arms,
                     "other_arms": sum(distinct_sources.values()) - fallback_arms - distinct_sources["hybrid_blended"],
                     "duplicate_arms": len(arm_sources) - sum(distinct_sources.values()),
                     "complete_as_planned": all(len(pairs[k]) == n for k, n in PLANNED.items()) and not excluded},
        "requests_total": requests, "status_counts": dict(statuses), "source_counts": dict(sources),
        "excluded_pairs": excluded,
    }
    for kind, complete_pairs in pairs.items():
        hybrid = [(a, b) for a, b in complete_pairs if a["source"] == b["source"] == "hybrid_blended"]
        result[kind] = {
            "planned_pairs": PLANNED[kind], "observed_pairs": observed_counts[kind],
            "complete_pairs": len(complete_pairs), "hybrid_only_pairs": len(hybrid),
            "all_complete": _pair_metrics(complete_pairs, kind), "hybrid_only": _pair_metrics(hybrid, kind),
        }
    return result
