"""Matched scenes, D4 feedback arms and offline preflight for the 24-point V4 probe."""

from copy import deepcopy
import json
import random

from probe_hourly_intention import (
    DAY,
    DEFERRABLE_SERVICE_DESCRIPTION,
    ENVIRONMENT,
    HOUR,
    NEEDS,
    PROFILE,
    PROFILE_ID,
    SCENES,
    SIM_HOUR,
    TICK,
    checked_feedback_state,
    login_offer,
    route_opportunity_choice,
    run_plan,
)
from proto.app_entry.intention_contract import compact_needs
from proto.memory.packet import compact_recent_episodes
from proto.paired_random import PairedRandomProvider
from run_hourly_intention_pairs import CapturePlan, verify_contrast
from run_strategy_memory_pairs import SEED


def request_manifest():
    """Counterbalance member order; match the same replicate's strategy draw across both scenes."""
    offer_id = login_offer()[2]["opportunity_id"]
    pairs = []
    for scene_index, scene in enumerate(SCENES):
        for replicate in range(1, 7):
            kind = "contrast" if replicate <= 5 else "repeat"
            pair_number = replicate if kind == "contrast" else 1
            seed = SEED + replicate
            draw = PairedRandomProvider(seed).rng(PROFILE_ID, offer_id, 1, "strategy").random()
            conditions = ("success", "failure") if kind == "contrast" else (
                ("success", "success") if scene == "S0" else ("failure", "failure")
            )
            members = [
                {
                    "pair_id": f"{scene}-{kind}-{pair_number:02}",
                    "kind": kind,
                    "scene": scene,
                    "member": member,
                    "condition": condition,
                    "pair_seed": seed,
                    "sample_u": draw,
                }
                for member, condition in zip(("A", "B"), conditions)
            ]
            if (replicate + scene_index) % 2 == 0:
                members.reverse()
            pairs.append(members)
    random.Random(SEED).shuffle(pairs)
    return [member for members in pairs for member in members]


def verify_design_stimuli(stimuli, *, feedback_states=None, frozen_stimuli=None):
    """Compare the initial messages at the Plan transport, with only the preregistered changes."""
    if feedback_states is not None:
        if frozen_stimuli is None:
            raise ValueError("Updated feedback verification requires matched frozen reference stimuli")
        verify_design_stimuli(frozen_stimuli)
        for scene in SCENES:
            for condition in ("success", "failure"):
                state = checked_feedback_state(feedback_states[condition], condition)
                expected = deepcopy(frozen_stimuli[scene][condition])
                message = expected["messages"][1]
                prefix, raw = message["content"].split("\n", 1)
                body = json.loads(raw)
                inputs = body["inputs"]
                episodes = compact_recent_episodes(state.episodes, simulation_day=DAY, tick_seconds=HOUR * 3600)
                if len(state.episodes) != 1 or len(episodes) != 1:
                    raise ValueError("Updated feedback must expose one completed prior D4 episode")
                episode, = episodes
                previous_task = login_offer(day=DAY - 1)[0]
                if any(episode.get(k) != v for k, v in {
                    "day": DAY - 1, "tick_seconds": TICK, "task_id": previous_task.task_id,
                    "task_family": previous_task.task_family, "strategy_type": "attempt_self",
                    "outcome_type": "success_self" if condition == "success" else "failure_after_attempt",
                    "negative_feedback": condition == "failure", "help_used": False,
                }.items()) or not episode.get("episode_id"):
                    raise ValueError("Updated feedback lost the matched D4 login or its assigned outcome")
                inputs["recent_task_episodes"] = episodes
                inputs["related_task_episode_ids"] = [episode["episode_id"]]
                inputs["pre_hour_psychology"] = {
                    "helplessness": state.helplessness,
                    "trust_in_apps": state.trust,
                    "avoidance_tendency": state.avoidance,
                }
                message["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
                if expected != stimuli[scene][condition]:
                    raise ValueError(f"{scene}/{condition}: Plan request differs outside its D4 state and episode, or lost them")
        return

    for scene in SCENES:
        cells = stimuli[scene]
        verify_contrast(cells["success"], cells["failure"], "opportunity_v1", scene=scene)
    for condition in ("success", "failure"):
        original = deepcopy(stimuli["S0"][condition])
        message = original["messages"][1]
        prefix, payload = message["content"].split("\n", 1)
        body = json.loads(payload)
        observation = body["inputs"]
        frozen = {
            "stable_profile": PROFILE,
            "hour": HOUR,
            "talkingdata_day": 5,
            "pre_hour_psychology": {"helplessness": 50.0, "trust_in_apps": 50.0, "avoidance_tendency": 50.0},
            "environment_cues": ENVIRONMENT,
            "recent_simulated_bundles": [],
            "latest_reflection": {},
            "current_intention": None,
        }
        if any(observation[k] != v for k, v in frozen.items()) or body["digital_needs"] != compact_needs(
            NEEDS.to_dict(include_audit=False)
        ):
            raise ValueError("The preregistered resident, observation time, psychology or Needs changed")
        only_offer, = observation["available_opportunities"]
        if only_offer["visible_description"] != "Sign into your account to access a service.":
            raise ValueError("S0 must retain the original scheduled login description")
        only_offer["visible_description"] = DEFERRABLE_SERVICE_DESCRIPTION
        message["content"] = prefix + "\n" + json.dumps(body, ensure_ascii=False)
        if original != stimuli["S1"][condition]:
            raise ValueError("Scenes differ beyond the one preregistered visible_description")


async def _verify_routes(history, scene, expected, feedback_state=None):
    """Exercise the production Plan parser and ledger under the prior-failure condition."""
    expected_task, _, offer = login_offer(scene=scene)
    choices = {
        "engage_goal": f"engage_goal@o1@open:{offer['required_channel']}",
        "defer_goal": f"defer_goal@o1@{SIM_HOUR + 24}",
        "drop_goal": "drop_goal@o1",
        "no_app": "no_app",
    }
    routes = {}
    for kind, token in choices.items():
        capture = CapturePlan("opportunity_v1", action=token)
        plan = await run_plan(
            capture, mode="opportunity_v1", condition="failure", history=history, scene=scene,
            feedback_state=feedback_state,
        )
        route, selected_task = route_opportunity_choice(plan, scene=scene)
        if capture.requests != [expected] or route["policy_choice"] != kind:
            raise ValueError(f"{scene} failed the first-reply preflight for {kind}")
        if selected_task != (expected_task if kind == "engage_goal" else None):
            raise ValueError(f"{scene} routed an unexpected task for {kind}")
        review = plan.intent["next_review_at_sim_hour"]
        goal = route["goal_after"]
        expected_status = {"engage_goal": "engaged", "defer_goal": "deferred", "drop_goal": "dropped", "no_app": None}
        if (goal and goal["status"]) != expected_status[kind] or review != (SIM_HOUR + 24 if kind == "defer_goal" else None):
            raise ValueError(f"{scene} did not preserve the intended goal state for {kind}")
        routes[kind] = {"task_admitted": selected_task is not None, "next_review_at_sim_hour": review}
    return routes


async def _capture_stimuli(history, states):
    stimuli = {}
    for scene in SCENES:
        cells = {}
        for condition in ("success", "failure"):
            capture = CapturePlan("opportunity_v1")
            await run_plan(
                capture, mode="opportunity_v1", condition=condition, history=history, scene=scene,
                feedback_state=states.get(condition),
            )
            request, = capture.requests
            cells[condition] = request
        stimuli[scene] = cells
    return stimuli


async def prepare_design(history, *, feedback_mode="frozen"):
    """Freeze four distinct model inputs and verify all eight alternative routes without HTTP."""
    if feedback_mode not in ("updated", "frozen"):
        raise ValueError(f"Unknown D4 feedback mode {feedback_mode!r}")
    frozen_stimuli = await _capture_stimuli(history, {})
    states = {}
    if feedback_mode == "updated":
        from hourly_feedback_state import build_feedback_state

        states = {condition: build_feedback_state(condition).to_dict() for condition in ("success", "failure")}
        stimuli = await _capture_stimuli(history, states)
        verify_design_stimuli(stimuli, feedback_states=states, frozen_stimuli=frozen_stimuli)
    else:
        stimuli = frozen_stimuli
        verify_design_stimuli(stimuli)
    return {
        "stimuli": stimuli,
        "manifest": request_manifest(),
        "preflight": {
            scene: await _verify_routes(history, scene, stimuli[scene]["failure"], states.get("failure"))
            for scene in SCENES
        },
        **({"feedback_states": states} if states else {}),
    }
