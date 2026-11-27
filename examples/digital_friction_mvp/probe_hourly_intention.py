"""Day-five controlled V4 Plan probe with frozen or production-updated D4 feedback."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from analysis_entry_calibration_comparison import Prediction, build_history
from proto.app_entry.bundle import HourlyAppEntryBundle, derive_primary_context
from proto.app_entry.bundle_loader import get_replay_source
from proto.app_entry.candidate import build_rollout_app_context_candidates
from proto.app_entry.habit_memory import build_rollout_intensity_profile, update_habit_memory_from_bundle
from proto.app_entry.intention_contract import COMPACT_PLAN_V4
from proto.app_entry.needs import DIGITAL_NEED_TO_APP_CONTEXTS, DIGITAL_NEED_LABELS, DigitalNeedsResult
from proto.app_entry.planner import DigitalAppEntryPlanBlock
from proto.app_entry.rollout import build_rollout_input_packet
from proto.hourly_intention import IntentionLedger
from proto.logical_clock import monotonic_sim_hour
from proto.runtime import scheduled_login_for_day

DAY, HOUR = 4, 9  # The engine's day four is the fifth day in the report.
TICK = HOUR * 3600 + 1  # Engine tick after the initialization step.
SIM_HOUR = monotonic_sim_hour(DAY, TICK)
PROFILE_ID = 1
PROFILE = {
    "age": 67,
    "gender": "女",
    "education": "小学",
    "digital_experience": 0.2,
    "vision_limit": 0.6,
    "past_fraud_experience": 0.4,
}
ENVIRONMENT = {"friction_level": 1, "risk_level": 1, "assist_level": 1}
EPISODE_ID = "controlled-day4-login-episode"
MODES = ("legacy", "opportunity_v1")
SCENES = ("S0", "S1")
DEFERRABLE_SERVICE_DESCRIPTION = (
    "Sign into your account to view general service information. "
    "You can also view it tomorrow. Your benefits are unaffected if you do not check today."
)
# Controlled latent needs, shared across all cells. No Needs request is sent.
NEEDS = DigitalNeedsResult.from_sanitized(
    {
        "need_pressures": dict.fromkeys(DIGITAL_NEED_LABELS, 0.3),
        "active_intent": 0.5,
        "intensity_hint": 0.5,
        "confidence": 0.8,
        "reasoning": "Daily needs are moderate.",
    }
)


@dataclass
class SharedHistory:
    habits: dict
    clock_predictions: dict[int, Prediction]
    source: str
    reference_hash: str | None
    mapping_hash: str | None

    def next_active_hour(self, sim_hour: int) -> int | None:
        return next(
            (sim_hour + n for n in range(1, 25) if self.clock_predictions[(sim_hour + n) % 24].count), None
        )


def load_history(reference_dir: Path | None) -> SharedHistory:
    """Use one audited set of 72 observations in all conditions, without raw device IDs."""
    source = None
    if reference_dir is not None:
        prefix = "talkingdata_elderly_10_"
        source = get_replay_source(
            bundle_path=str(reference_dir / f"{prefix}reference_hourly_bundle_day1_3.csv"),
            device_mapping_path=str(reference_dir / f"{prefix}selected_devices.csv"),
            replay_days=(1, 2, 3),
        )
        device = source.selected_devices[0][1]
    observations, habits = {}, {}
    for day in (1, 2, 3):
        for hour in range(24):
            if source is not None:
                bundle = source.bundle_for_device(device_id=device, talkingdata_day=day, hour=hour)
            else:
                # Explicitly synthetic, deterministic alternative for a checkout without private data.
                counts = {"communication_social_context": day} if hour in (9, 18, 20) else {}
                bundle = HourlyAppEntryBundle(
                    "fixture",
                    day,
                    hour,
                    bool(counts),
                    sum(counts.values()),
                    counts,
                    derive_primary_context(counts),
                    "synthetic",
                )
            observations["resident", day, hour] = Prediction(
                bundle.active_event_app_exposures,
                derive_primary_context(bundle.app_context_counts),
            )
            habits = update_habit_memory_from_bundle(habits, bundle)
    habits.pop("device_id")  # No identifier is needed to reconstruct these inputs.
    by_hour = build_history(observations, {("resident", DAY + 1, h) for h in range(24)})
    return SharedHistory(
        habits,
        {h: by_hour["resident", DAY + 1, h] for h in range(24)},
        "reference_rank_1" if source else "synthetic_72_hours",
        source.bundle_hash if source else None,
        source.device_mapping_hash if source else None,
    )


def login_offer(day=DAY, *, scene="S0"):
    if scene not in SCENES:
        raise ValueError(f"Unknown login scene {scene!r}")
    task = scheduled_login_for_day(
        hour=HOUR,
        agent_id=PROFILE_ID,
        day=day,
        tick_seconds=TICK,
        env=ENVIRONMENT,
        existing_task=None,
        last_scheduled_day=-1,
    )
    if task is None:
        raise RuntimeError(f"The scheduled Day {day + 1} login must be available at 09:00")
    if scene == "S1":
        task.visible_description = DEFERRABLE_SERVICE_DESCRIPTION
    ledger = IntentionLedger()
    offer = ledger.publish(task, source="scheduled_login", sim_hour=monotonic_sim_hour(day, TICK))
    return task, ledger, offer


def prior_episode(condition: str) -> dict:
    if condition not in {"success", "failure"}:
        raise ValueError("Unknown historical outcome")
    return {
        "episode_id": EPISODE_ID,
        "task_id": "controlled-day4-login",
        "day": DAY - 1,
        "tick_seconds": TICK,
        "task_family": "account_login_verification",
        "strategy_type": "attempt_self",
        "requested_strategy_type": "attempt_self",
        "outcome_type": "success_self" if condition == "success" else "failure_after_attempt",
        "negative_feedback": condition == "failure",
        "help_used": False,
        "support_delivery_status": "not_requested",
    }


def checked_feedback_state(feedback_state, condition):
    """Accept the in-memory branch or its JSON archive, always matched to the assigned arm."""
    if feedback_state is None:
        return None
    from hourly_feedback_state import FeedbackState

    if isinstance(feedback_state, dict):
        feedback_state = FeedbackState.from_dict(feedback_state)
    if not isinstance(feedback_state, FeedbackState) or feedback_state.condition != condition:
        raise ValueError("D4 feedback state does not match the assigned condition")
    return feedback_state


async def run_plan(
    llm, *, mode: str, condition: str, history: SharedHistory, scene: str = "S0", feedback_state=None,
):
    """Call the same packet builder and Plan block as the continuous run; bypass only Needs."""
    if mode not in MODES:
        raise ValueError(f"Unknown intention condition {mode!r}")
    state = checked_feedback_state(feedback_state, condition)
    _, ledger, _ = login_offer(scene=scene)
    intensity = build_rollout_intensity_profile(history.habits, hour=HOUR, absolute_cap=12)
    packet = build_rollout_input_packet(
        simulation_day=DAY,
        talkingdata_day=DAY + 1,
        hour=HOUR,
        stable_profile=PROFILE,
        habit_memory=history.habits,
        recent_rollout_rows=[],
        recent_task_episodes=state.episodes if state else [prior_episode(condition)],
        latest_reflection={},
        helplessness=state.helplessness if state else 50.0,
        trust=state.trust if state else 50.0,
        avoidance=state.avoidance if state else 50.0,
        environment=ENVIRONMENT,
        intensity_profile=intensity,
        hourly_intention_mode=mode,
        available_opportunities=ledger.visible(SIM_HOUR),
        current_intention=ledger.goal,
        goal_review_due=ledger.review_due(SIM_HOUR),
    )
    candidates = build_rollout_app_context_candidates(
        habit_memory=history.habits,
        hour=HOUR,
        need_pressures=NEEDS.need_pressures,
        need_context_mapping=DIGITAL_NEED_TO_APP_CONTEXTS,
        top_k=5,
    )
    return await DigitalAppEntryPlanBlock().forward(
        llm=llm,
        needs=NEEDS,
        candidate_contexts=candidates,
        input_payload=packet,
        intensity_profile=intensity,
        prompt_version="app_entry_plan_v3",
        compact_schema_version=COMPACT_PLAN_V4 if mode == "opportunity_v1" else None,
        min_confidence=0.5,
        timeout=45,
        retries=1,
        json_attempts=1,
    )


def routed_choice(mode, plan):
    """Stop exactly at the task admission boundary; no task strategy/help/outcome call."""
    if mode == "legacy":
        # In the fixed-task control, assignment precedes the Plan, even if the Plan fails.
        task, _, _ = login_offer()
        return {
            "policy_choice": "legacy_assigned",
            "choice_source": "legacy_scheduled_policy",
            "routed_task_id": task.task_id,
            "goal_after": None,
        }
    return route_opportunity_choice(plan)[0]


def route_opportunity_choice(plan, *, scene="S0"):
    """Apply the chosen intent to a fresh ledger for the same advertised scene."""
    task, ledger, offer = login_offer(scene=scene)
    if plan is None:
        return {
            "policy_choice": None,
            "choice_source": "technical_failure",
            "routed_task_id": None,
            "goal_after": None,
        }, None
    selected = ledger.apply(plan.intent, sim_hour=SIM_HOUR)
    if selected and selected.task_id != task.task_id:
        raise RuntimeError(f"Intent did not route the advertised opportunity {offer['opportunity_id']}")
    return {
        "policy_choice": plan.intent["kind"],
        "choice_source": "validated_model_intent",
        "routed_task_id": selected.task_id if selected else None,
        "goal_after": deepcopy(ledger.state["goal"]),
    }, selected


def _rule_step(history, sim_hour, ledger=None, offer=None):
    prediction = history.clock_predictions[sim_hour % 24]
    goal = ledger.goal if ledger else None
    if ledger is None or not ledger.review_due(sim_hour):
        kind = "habitual_app" if prediction.count else "no_app"
        return {
            "mode": "rule",
            "policy_choice": kind,
            "choice_source": "frozen_rule",
            "routed_task_id": None,
            "reference_app_count": prediction.count,
            "reference_app_context": prediction.context,
            "active": bool(prediction.count),
            "app_context_counts": {prediction.context: prediction.count} if prediction.count else {},
            "goal_after": deepcopy(goal),
            "model_requests": 0,
        }
    if prediction.count:
        kind, next_hour = ("continue_goal" if goal else "engage_goal"), None
    elif history.next_active_hour(sim_hour) is not None:
        kind, next_hour = "defer_goal", history.next_active_hour(sim_hour)
    else:
        kind, next_hour = "drop_goal", None
    intent = {
        "kind": kind,
        "opportunity_id": offer["opportunity_id"],
        "goal_id": goal["goal_id"] if goal else None,
        "next_review_at_sim_hour": next_hour,
        "reason": "Fixed same-hour history rule.",
    }
    selected = ledger.apply(intent, sim_hour=sim_hour)
    counts = {}
    if selected:
        counts[offer["required_channel"]] = 1
        if prediction.count > 1:
            context = prediction.context
            counts[context] = counts.get(context, 0) + prediction.count - 1
    return {
        "mode": "rule",
        "policy_choice": kind,
        "choice_source": "frozen_rule",
        "routed_task_id": selected.task_id if selected else None,
        "app_context_counts": counts,
        "active": bool(counts),
        "reference_app_count": prediction.count,
        "reference_app_context": prediction.context,
        "goal_after": deepcopy(ledger.state["goal"]),
        "model_requests": 0,
    }


def rule_reference(history: SharedHistory) -> dict:
    """Frozen C policy at the Day 5 opportunity in the paired, single-observation probe."""
    _, ledger, offer = login_offer()
    return _rule_step(history, SIM_HOUR, ledger, offer)


def controlled_rule_window(history: SharedHistory) -> dict:
    """48 contiguous hours of opportunity intake. A hand-off closes observation of that task."""
    queued, rows, records = [], [], {}
    for day in (3, 4):  # Reporting Days 4 and 5.
        for hour in range(24):
            now = monotonic_sim_hour(day, hour * 3600 + 1)
            published = []
            if hour == HOUR:
                _, ledger, offer = login_offer(day)
                oid = offer["opportunity_id"]
                queued.append((ledger, offer))
                published.append(oid)
                records[oid] = {
                    "opportunity_id": oid,
                    "published_at": now,
                    "deferred_at": [],
                    "first_handled_at": None,
                    "intake_status": "offered",
                }
            visible = [offer["opportunity_id"] for _, offer in queued]
            if queued:
                ledger, offer = queued[0]
                decision = _rule_step(history, now, ledger, offer)
                record = records[offer["opportunity_id"]]
                if decision["routed_task_id"]:
                    record.update(first_handled_at=now, intake_status="handed_to_executor_boundary")
                    queued.pop(0)
                elif decision["policy_choice"] == "defer_goal":
                    record["deferred_at"].append(
                        {"at": now, "review_at": ledger.goal["next_review_at_sim_hour"]}
                    )
                    record["intake_status"] = "deferred"
                elif decision["policy_choice"] == "drop_goal":
                    record["intake_status"] = "dropped"
                    queued.pop(0)
            else:
                decision = _rule_step(history, now)
            rows.append(
                {
                    "report_day": day + 1,
                    "hour": hour,
                    "monotonic_sim_hour": now,
                    "published_ids": published,
                    "visible_ids": visible,
                    **decision,
                }
            )
    return {
        "policy": "frozen_same_hour_history_first_active_slot",
        "scope": "scheduled_opportunity_intake_only",
        "reference_replay_hours": history.habits["total_hours_seen"],
        "generated_hours": len(rows),
        "coverage": "Only scheduled offers. End tracking at first admission; subsequent task outcomes, "
        "retries, real help and psychology are unobserved.",
        "profile_id": PROFILE_ID,
        "model_requests": 0,
        "low_level_attempts_observed": None,
        "help_deliveries_observed": None,
        "opportunities": list(records.values()),
        "hours": rows,
    }
