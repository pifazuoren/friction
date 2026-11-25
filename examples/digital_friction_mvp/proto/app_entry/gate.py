from __future__ import annotations

from typing import Any

from .types import TASK_ELIGIBLE_APP_CONTEXTS, clamp_score, _stable_hash

_TASK_OCCURRENCE_SCHEMA_VERSION = "task_occurrence_prior_by_context_v1"


def _task_occurrence_probability_for_context(
    *,
    app_context: str,
    occurrence_artifact: dict[str, Any],
    multiplier: float,
) -> tuple[float, str]:
    if app_context not in TASK_ELIGIBLE_APP_CONTEXTS:
        return 0.0, "not_applicable_context_only"
    schema_version = str(occurrence_artifact.get("schema_version", "")).strip()
    if schema_version != _TASK_OCCURRENCE_SCHEMA_VERSION:
        raise ValueError(
            "task occurrence artifact schema_version must be "
            f"{_TASK_OCCURRENCE_SCHEMA_VERSION}"
        )
    table = occurrence_artifact.get("task_occurrence_by_context")
    if not isinstance(table, dict):
        raise ValueError(
            "task occurrence artifact must include task_occurrence_by_context"
        )
    expected = set(TASK_ELIGIBLE_APP_CONTEXTS)
    actual = set(str(key) for key in table)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise ValueError(
            "task occurrence artifact missing task-eligible app_contexts: "
            + ", ".join(missing)
        )
    if unexpected:
        raise ValueError(
            "task occurrence artifact has unknown app_contexts: "
            + ", ".join(unexpected)
        )
    try:
        probability = float(table[app_context])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"task occurrence probability for {app_context} must be numeric"
        ) from exc
    if probability < 0.0 or probability > 1.0:
        raise ValueError(
            f"task occurrence probability for {app_context} must be in [0, 1]"
        )
    return clamp_score(probability * float(multiplier)), "task_occurrence_artifact"


def _stable_task_occurrence_gate_roll(
    *,
    app_context: str,
    seed: int,
    agent_id: int,
    day: int,
    tick_seconds: float,
    profile_bucket: str,
) -> float:
    key = _stable_hash(
        {
            "seed": int(seed),
            "agent_id": int(agent_id),
            "day": int(day),
            "tick": int(round(float(tick_seconds))),
            "profile_bucket": profile_bucket,
            "selected_app_context": str(app_context),
            "version": "task_occurrence_gate_v1",
        }
    )
    return int(key[:12], 16) / float(0xFFFFFFFFFFFF)
