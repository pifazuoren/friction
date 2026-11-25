from __future__ import annotations

from copy import deepcopy
from typing import Any


DAY4_REPLAY_SNAPSHOT_SCHEMA_VERSION = "day4_world_specific_replay_snapshot_v1"


def should_create_day4_replay_snapshot(decision: dict[str, Any]) -> bool:
    audit = decision.get("audit", {}) if isinstance(decision, dict) else {}
    if not isinstance(audit, dict):
        return False
    return (
        str(audit.get("entry_mode", "")) == "app_context_replay_bundle"
        and int(audit.get("talkingdata_day", -1)) == 3
        and int(audit.get("hour", -1)) == 23
    )


def build_day4_replay_snapshot(
    *,
    agent_id: int,
    world_name: str,
    decision: dict[str, Any],
    app_entry_habit_memory: dict[str, Any],
    helplessness_score: float,
    trust_in_apps: float,
    avoidance_tendency: float,
    task_domain_memory: Any,
    help_effect_memory: Any,
    recent_episode_buffer: Any,
    bayesian_control_memory: Any,
    bayesian_policy_memory: Any,
    bayesian_controllability_lite_memory: Any,
) -> dict[str, Any]:
    audit = decision.get("audit", {}) if isinstance(decision, dict) else {}
    if not isinstance(audit, dict):
        audit = {}
    return {
        "schema_version": DAY4_REPLAY_SNAPSHOT_SCHEMA_VERSION,
        "agent_id": int(agent_id),
        "device_id": str(audit.get("device_id", "")),
        "selected_rank": int(audit.get("selected_rank", 0) or 0),
        "world": str(world_name or ""),
        "source": "talkingdata_day1_3_replay",
        "completed_replay_days": [1, 2, 3],
        "replay_bundle_hash": str(audit.get("bundle_hash", "")),
        "device_mapping_hash": str(audit.get("device_mapping_hash", "")),
        "helplessness_score": float(helplessness_score),
        "trust_in_apps": float(trust_in_apps),
        "avoidance_tendency": float(avoidance_tendency),
        "task_domain_memory": deepcopy(task_domain_memory),
        "help_effect_memory": deepcopy(help_effect_memory),
        "recent_episode_buffer": deepcopy(recent_episode_buffer),
        "proto_bayesian_control_memory": deepcopy(bayesian_control_memory),
        "proto_bayesian_policy_memory": deepcopy(bayesian_policy_memory),
        "proto_bayesian_controllability_lite_memory": deepcopy(
            bayesian_controllability_lite_memory
        ),
        "app_entry_habit_memory": deepcopy(app_entry_habit_memory),
        "created_at_simulation_day": int(audit.get("simulation_day", audit.get("day", 2))),
        "created_at_talkingdata_day": int(audit.get("talkingdata_day", 3)),
        "created_at_hour": int(audit.get("hour", 23)),
    }
