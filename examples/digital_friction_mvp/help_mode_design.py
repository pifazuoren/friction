"""Matched Day 5 decisions after a controlled Day 4 family-assisted login."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import random

from probe_hourly_intention import (
    DAY,
    ENVIRONMENT,
    HOUR,
    NEEDS,
    PROFILE,
    SIM_HOUR,
    SharedHistory,
    load_history,
    login_offer,
    plan_from_observation,
    route_opportunity_choice,
)
from proto.app_entry.intention_contract import COMPACT_PLAN_VERSION, compact_needs
from proto.paired_random import PairedRandomProvider
from run_hourly_intention_pairs import CapturePlan
from run_strategy_memory_pairs import SEED

CONDITIONS = ("guided", "proxy")
SCENE = "S1"
PROFILE_FILE = Path(__file__).resolve().with_name("profiles.json")
COMPLETION_ACTION = {
    "guided": "The family member described the login steps. The resident entered the code and pressed confirm.",
    "proxy": "The family member described the login steps. The family member entered the code and pressed confirm.",
}


def digest(value) -> str:
    data = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HelpResident:
    profile_id: int
    rank: int
    profile: dict
    history: SharedHistory


def load_residents(
    reference_dir: Path | None, profiles_path: Path = PROFILE_FILE
) -> dict[int, HelpResident]:
    """Use the same profile-ID order to reference-rank assignment as the continuous study."""
    profiles = json.loads(Path(profiles_path).read_text(encoding="utf-8"))
    if sorted(row["id"] for row in profiles) != list(range(1, 11)):
        raise ValueError("Expected the ten distinct study resident IDs 1–10")
    residents = {}
    for rank, row in enumerate(sorted(profiles, key=lambda p: p["id"]), 1):
        person = row["id"]
        history = load_history(reference_dir, selected_rank=rank)
        if history.habits["total_hours_seen"] != 72 or history.habits[
            "replay_days"
        ] != [1, 2, 3]:
            raise ValueError(
                "Each resident needs their own complete three-day App history"
            )
        # Match the stable traits exposed by the Plan and post-admission prompts.
        residents[person] = HelpResident(
            person, rank, {k: row[k] for k in PROFILE}, history
        )
    return residents


def help_episodes(profile_id: int, condition: str) -> list[dict]:
    """Prescribe the same two unsuccessful attempts and one completed login in both arms."""
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown family help condition {condition!r}")
    prior_task, _, _ = login_offer(day=DAY - 1, profile_id=profile_id)
    episodes = []
    for attempt, hour in enumerate((9, 10, 11), 1):
        helped = attempt == 3
        strategy = "seek_help_then_attempt" if helped else "attempt_self"
        row = {
            "episode_id": f"{prior_task.task_id}-attempt-{attempt}",
            "task_id": prior_task.task_id,
            "day": DAY - 1,
            "tick_seconds": hour * 3600 + 1,
            "task_family": prior_task.task_family,
            "requested_strategy_type": strategy,
            "strategy_type": strategy,
            "outcome_type": "success_with_help" if helped else "failure_after_attempt",
            "help_used": helped,
            "support_delivery_status": "delivered" if helped else "not_requested",
            "negative_feedback": not helped,
        }
        if helped:
            row.update(
                help_source="family", completion_action=COMPLETION_ACTION[condition]
            )
        episodes.append(row)
    return episodes


async def run_help_plan(llm, resident: HelpResident, condition: str):
    """D5 Plan uses matched needs, numeric state and service conditions, with one factual contrast."""
    return await plan_from_observation(
        llm,
        history=resident.history,
        mode="opportunity_v1",
        scene=SCENE,
        profile_id=resident.profile_id,
        profile=resident.profile,
        episodes=help_episodes(resident.profile_id, condition),
        helplessness=50.0,
        trust=50.0,
        avoidance=50.0,
    )


def route_help_plan(plan, resident: HelpResident):
    return route_opportunity_choice(plan, scene=SCENE, profile_id=resident.profile_id)


def verify_plan_pair(resident: HelpResident, stimuli: dict) -> None:
    """Check the treatment actually delivered to Plan and compare every other wire field."""
    if set(stimuli) != set(CONDITIONS):
        raise ValueError("Expected guided and proxy Plan stimuli")
    neutralized = []
    task, _, offer = login_offer(scene=SCENE, profile_id=resident.profile_id)
    for condition in CONDITIONS:
        stimulus = deepcopy(stimuli[condition])
        if len(stimulus["messages"]) != 2:
            raise ValueError("Unexpected number of Plan messages")
        message = stimulus["messages"][1]
        prefix, raw = message["content"].split("\n", 1)
        body = json.loads(raw)
        packet = body["inputs"]
        expected = help_episodes(resident.profile_id, condition)
        if packet["recent_task_episodes"] != expected or packet[
            "related_task_episode_ids"
        ] != [e["episode_id"] for e in expected]:
            raise ValueError(
                "Plan must receive two matched failures and the assigned completed action"
            )
        offers = packet["available_opportunities"]
        if (
            len(offers) != 1
            or offers[0]["opportunity_id"] != offer["opportunity_id"]
            or (
                offers[0]["visible_description"] != task.visible_description
                or task.task_id in {e["task_id"] for e in expected}
            )
        ):
            raise ValueError(
                "The new Day 5 login must be distinct from yesterday's task"
            )
        if (
            body["schema_version"] != COMPACT_PLAN_VERSION
            or packet["stable_profile"] != resident.profile
            or packet["pre_hour_psychology"]
            != {"helplessness": 50, "trust_in_apps": 50, "avoidance_tendency": 50}
            or packet["environment_cues"] != ENVIRONMENT
            or packet["monotonic_sim_hour"] != SIM_HOUR
            or packet["hour"] != HOUR
            or packet["current_intention"] is not None
            or packet["latest_reflection"]
            or packet["recent_simulated_bundles"]
            or body["digital_needs"]
            != compact_needs(NEEDS.to_dict(include_audit=False))
        ):
            raise ValueError("Preregistered Plan conditions changed")
        # The single permitted treatment field is removed only after checking its exact value.
        del packet["recent_task_episodes"][-1]["completion_action"]
        message["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
        neutralized.append(stimulus)
    if neutralized[0] != neutralized[1]:
        raise ValueError("Plan stimuli differ beyond the actor completing the login")


def _manifest(residents, stimuli):
    pairs = []
    for person, resident in residents.items():
        offer_id = login_offer(scene=SCENE, profile_id=person)[2]["opportunity_id"]
        for replicate in range(1, 5):
            kind = "repeat" if replicate == 4 else "contrast"
            condition = CONDITIONS[(resident.rank - 1) % 2]
            arms = (condition, condition) if kind == "repeat" else CONDITIONS
            pair_seed = SEED + replicate
            draw = (
                PairedRandomProvider(pair_seed)
                .rng(person, offer_id, 1, "strategy")
                .random()
            )
            members = [
                {
                    "profile_id": person,
                    "selected_rank": resident.rank,
                    "kind": kind,
                    "pair_id": f"r{resident.rank:02}-{kind}-{replicate:02}",
                    "replicate": replicate,
                    "member": member,
                    "condition": arm,
                    "pair_seed": pair_seed,
                    "sample_u": draw,
                    "plan_stimulus_sha256": digest(stimuli[str(person)][arm]),
                }
                for member, arm in zip(("A", "B"), arms)
            ]
            if (resident.rank + replicate) % 2:
                members.reverse()
            pairs.append(members)
    random.Random(SEED).shuffle(pairs)
    return [row for pair in pairs for row in pair]


async def prepare_design(residents: dict[int, HelpResident]) -> dict:
    """Freeze twenty verified initial requests before any of the 80 fresh decisions."""
    if sorted(residents) != list(range(1, 11)):
        raise ValueError("The study requires all ten resident backgrounds")
    stimuli, profiles = {}, []
    for person, resident in sorted(residents.items()):
        cells = {}
        for condition in CONDITIONS:
            capture = CapturePlan("opportunity_v1")
            plan = await run_help_plan(capture, resident, condition)
            if plan.intent["kind"] != "no_app" or len(capture.requests) != 1:
                raise ValueError("Expected one captured production Plan request")
            cells[condition] = capture.requests[0]
        verify_plan_pair(resident, cells)
        stimuli[str(person)] = cells
        history = resident.history
        profiles.append(
            {
                "profile_id": person,
                "selected_rank": resident.rank,
                "profile": dict(resident.profile),
                "history_source": history.source,
                "reference_hours": history.habits["total_hours_seen"],
                "history_sha256": digest(history.habits),
                "reference_hash_prefix": history.reference_hash,
                "mapping_hash_prefix": history.mapping_hash,
            }
        )
    return {
        "manifest": _manifest(residents, stimuli),
        "stimuli": stimuli,
        "profiles": profiles,
    }
