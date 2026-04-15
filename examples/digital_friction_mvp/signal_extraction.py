from __future__ import annotations

from collections import Counter
from typing import Any


def build_event_explanation_vector(
    *,
    env_levels: dict[str, Any],
    profile: dict[str, Any],
    status: dict[str, Any],
    step_signal: dict[str, Any],
    scenario_name: str,
    outcome: str,
    digital_exposure: dict[str, bool],
    scenario_match_source: str,
    llm_match_confidence: float,
    llm_match_reason: str,
) -> dict[str, Any]:
    friction_sum = (
        float(env_levels.get("friction", 0))
        + float(env_levels.get("malicious", 0))
        + float(env_levels.get("complexity", 0))
        + float(env_levels.get("risk", 0))
    )
    support_sum = (
        float(env_levels.get("assist", 0))
        + float(env_levels.get("accessibility", 0))
        + float(env_levels.get("human_support", 0))
    )
    failure_pressure = max(0.0, float(step_signal.get("failure_pressure", 0.0) or 0.0))
    success_support = max(0.0, float(step_signal.get("success_support", 0.0) or 0.0))
    trust_value = float(status.get("trust", 0.0) or 0.0)
    helplessness_value = float(status.get("helplessness", 0.0) or 0.0)
    digital_experience = float(profile.get("digital_experience", 0.5) or 0.5)

    reason_weights = {
        "friction_pressure": round(max(0.0, friction_sum - support_sum) / 12.0, 4),
        "support_buffer": round(max(0.0, support_sum - friction_sum) / 12.0, 4),
        "failure_pressure": round(min(1.0, failure_pressure / 2.0), 4),
        "success_support": round(min(1.0, success_support / 2.0), 4),
        "trust_level": round(min(1.0, max(0.0, trust_value / 100.0)), 4),
        "helplessness_level": round(min(1.0, max(0.0, helplessness_value / 100.0)), 4),
        "digital_experience": round(min(1.0, max(0.0, digital_experience)), 4),
    }

    tags: list[str] = []
    if friction_sum >= support_sum + 2:
        tags.append("high_friction")
    if support_sum >= friction_sum + 2:
        tags.append("high_support")
    if failure_pressure >= 0.8:
        tags.append("recent_failure")
    if success_support >= 0.8:
        tags.append("recent_success")
    if digital_exposure.get("from_action", False):
        tags.append("digital_action_signal")
    if digital_exposure.get("from_status", False):
        tags.append("digital_status_signal")
    if digital_exposure.get("from_intention", False):
        tags.append("digital_intention_signal")
    if digital_exposure.get("from_signal", False):
        tags.append("digital_step_signal")
    if scenario_match_source:
        tags.append(f"match_{scenario_match_source}")
    if scenario_name:
        tags.append(f"scenario_{scenario_name}")
    if llm_match_confidence >= 0.7:
        tags.append("llm_match_high_confidence")
    elif llm_match_confidence > 0:
        tags.append("llm_match_low_confidence")

    if outcome == "negative":
        reason_primary = "high_friction_with_low_buffer"
        if failure_pressure >= 0.8:
            reason_primary = "step_failure_under_friction"
        elif trust_value < 45:
            reason_primary = "low_trust_amplified_negative"
        reason_secondary = (
            llm_match_reason[:200]
            if llm_match_reason
            else "friction pressure exceeds support buffer"
        )
    elif outcome == "positive":
        reason_primary = "supportive_context_or_success_signal"
        if success_support >= 0.8:
            reason_primary = "recent_step_success_supports_positive"
        elif support_sum >= friction_sum + 2:
            reason_primary = "support_buffer_offsets_friction"
        reason_secondary = (
            llm_match_reason[:200]
            if llm_match_reason
            else "supportive factors outweigh contextual friction"
        )
    else:
        reason_primary = "threshold_not_reached"
        if friction_sum > support_sum and failure_pressure >= 0.8:
            reason_primary = "negative_risk_detected_but_probability_gate_blocked"
        reason_secondary = (
            llm_match_reason[:200]
            if llm_match_reason
            else "attempt evaluated but event probability/roll did not trigger"
        )

    return {
        "reason_primary": reason_primary,
        "reason_secondary": reason_secondary,
        "reason_tags": tags,
        "reason_weights": reason_weights,
    }


def summarize_stage_explanations(event_log: list[dict[str, Any]], top_k: int = 3) -> dict[str, Any]:
    negative_counter: Counter[str] = Counter()
    positive_counter: Counter[str] = Counter()
    primary_counter: Counter[str] = Counter()

    for item in event_log:
        if not isinstance(item, dict):
            continue
        decision = item.get("decision", {})
        if not isinstance(decision, dict):
            continue
        outcome = str(item.get("outcome", "")).strip().lower()
        reason_primary = str(decision.get("reason_primary", "")).strip()
        reason_tags = decision.get("reason_tags", [])
        if reason_primary:
            primary_counter[reason_primary] += 1
        if isinstance(reason_tags, list):
            if outcome == "negative":
                negative_counter.update(str(tag).strip() for tag in reason_tags if str(tag).strip())
            elif outcome == "positive":
                positive_counter.update(str(tag).strip() for tag in reason_tags if str(tag).strip())

    top_negative = [tag for tag, _ in negative_counter.most_common(top_k)]
    top_positive = [tag for tag, _ in positive_counter.most_common(top_k)]
    top_primary = [tag for tag, _ in primary_counter.most_common(top_k)]
    return {
        "top_negative_tags": top_negative,
        "top_positive_tags": top_positive,
        "top_primary_reasons": top_primary,
        "negative_tag_counts": dict(negative_counter),
        "positive_tag_counts": dict(positive_counter),
        "primary_reason_counts": dict(primary_counter),
    }
