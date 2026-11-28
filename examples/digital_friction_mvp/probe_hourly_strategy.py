"""Day-five post-admission behavior with frozen or updated D4 state.

A single, separately dated login episode is visible in both production LLM prompts.
The local helper endpoint records receipt of a real SupportRequest and stops there.
"""

from __future__ import annotations

from dataclasses import replace

from config_runtime import load_runtime_config
from probe_hourly_intention import (
    DAY,
    ENVIRONMENT,
    PROFILE,
    PROFILE_ID,
    TICK,
    checked_feedback_state,
    prior_episode,
)
from probe_strategy_memory_pair import _PairedDraw
from proto.attempt_strategy import (
    choose_attempt_strategy,
    compute_rule_strategy_weights,
)
from proto.experience_memory import (
    build_initial_help_effect_memory,
    build_initial_task_domain_memory,
    extract_memory_features,
)
from proto.hourly_intention import visible_task_description
from proto.llm_psychology import (
    build_initial_digital_emotion_state,
    resolve_strategy_deliberation,
    resolve_task_appraisal,
)
from proto.llm_trace import trace_record
from proto.memory.packet import build_task_relevant_memory_packet
from proto.models import DigitalTask
from proto.outcome_model import support_quality_from_env
from proto.support.protocol import SupportRequest
from proto.support.routing import dispatch_family_support_request


FROZEN_RUNTIME_ENV = {
    "PROTO_LLM_PSYCHOLOGY_MODE": "hybrid",
    "PROTO_LLM_TASK_APPRAISAL_ENABLED": "true",
    "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED": "true",
    "PROTO_LLM_STRATEGY_PROMPT_FORMAT": "field_rules_no_priors",
    "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED": "false",
    "PROTO_LLM_PSYCHOLOGY_MIN_CONFIDENCE": "0.65",
    "PROTO_LLM_PSYCHOLOGY_TIMEOUT": "45",
    "PROTO_LLM_PSYCHOLOGY_RETRIES": "0",
    "PROTO_SUPPORT_ECOLOGY_MODE": "family_helper_llm",
    "PROTO_BAYESIAN_POLICY_LITE_MODE": "off",
    "PROTO_HUYS_DAYAN_LITE_CONTROLLABILITY_MODE": "off",
}


def _verify_runtime():
    config = load_runtime_config()
    for key, value in FROZEN_RUNTIME_ENV.items():
        actual = getattr(config, key.lower())
        if str(actual).lower() != value:
            raise ValueError(f"Post-admission probe requires {key}={value}")
    return config


class _RequestReceiver:
    """The probe stops at the helper's actual production call boundary."""

    def __init__(self):
        self.request = None

    async def provide_support(self, request: SupportRequest) -> None:
        if self.request is not None:
            raise RuntimeError("Duplicate support request within a decision")
        self.request = request
        trace_record(
            "request_received",
            module="probe_helper",
            request_id=request.request_id,
            task_id=request.task_id,
            recipient_id=request.helper_agent_id,
        )


async def measure_admitted(
    llm,
    *,
    task: DigitalTask,
    condition: str,
    sample_u: float,
    feedback_state=None,
    fact_resident=None,
    stage_client=None,
) -> dict:
    """Appraise the routed task, sample the production strategy and observe dispatch."""
    config = _verify_runtime()
    if (
        not isinstance(task, DigitalTask)
        or task.task_family != "account_login_verification"
    ):
        raise ValueError("A routed login task is required")
    if type(sample_u) not in {float, int} or not 0 <= sample_u < 1:
        raise ValueError("sample_u must be finite and in [0, 1)")
    # Both lower prompts carry the exact description shown at admission, including
    # the standard implicit family description on historical S0 tasks.
    task = replace(task, visible_description=visible_task_description(task))
    state = checked_feedback_state(feedback_state, condition)
    if state is not None and fact_resident is not None:
        raise ValueError(
            "Cannot combine a feedback-updated state and a fact-only intervention"
        )
    profile = fact_resident.profile if fact_resident else PROFILE
    requester_id = fact_resident.profile_id if fact_resident else PROFILE_ID
    helper_id = 10 + fact_resident.rank if fact_resident else 2
    if state is None:
        traits = {
            key: profile[key]
            for key in ("digital_experience", "vision_limit", "past_fraud_experience")
        }
        domain = build_initial_task_domain_memory(**traits)
        help_memory = build_initial_help_effect_memory()
        emotion = build_initial_digital_emotion_state(**traits)
        helplessness, consecutive_failures = 50.0, 0
        if fact_resident is None:
            feature_episodes, visible_episodes = [], [prior_episode(condition)]
        else:
            from help_mode_design import help_episodes

            visible_episodes = help_episodes(requester_id, condition)
            # The experienced outcomes and their ordering match across treatments. Compute
            # numeric summaries from one common history; only the visible completion fact varies.
            feature_episodes = help_episodes(requester_id, "guided")
    else:
        domain, help_memory, emotion = (
            state.domain_memory,
            state.help_memory,
            state.emotion,
        )
        helplessness, consecutive_failures = (
            state.helplessness,
            state.consecutive_failures,
        )
        feature_episodes = visible_episodes = state.episodes
    feature_inputs = dict(
        task=task,
        helplessness_score=helplessness,
        task_domain_memory=domain,
        help_effect_memory=help_memory,
        recent_episode_buffer=feature_episodes,
        digital_emotion_state=emotion,
        psychology_mode=config.proto_llm_psychology_mode,
    )
    baseline = extract_memory_features(**feature_inputs)
    recent = {
        name: getattr(baseline, name)
        for name in (
            "recent_negative_feedback_ratio",
            "recent_avoid_ratio",
            "recent_help_seek_ratio",
            "recent_same_task_failure_count",
            "recent_failure_pressure",
        )
    }
    packet = build_task_relevant_memory_packet(
        task=task,
        task_domain_memory=domain,
        help_effect_memory=help_memory,
        recent_episode_summary=recent,
        event_log=state.event_log if state else [],
        recent_episode_buffer=visible_episodes,
        simulation_day=DAY,
        tick_seconds=TICK,
    )
    if state is None:
        packet["aggregate_memory_scope"] = (
            (
                "Domain and help statistics use fixed pre-intervention starting values. "
                "The recent episode list and its summary describe the three controlled day 4 attempts."
            )
            if fact_resident
            else (
                "Aggregate statistics summarize days 1–3. Recent episodes additionally include day 4."
            )
        )
    shared = dict(
        task=task,
        profile_summary=profile,
        task_relevant_memory=packet,
        recent_episode_summary=recent,
        digital_emotion_state=emotion,
    )
    reply_audit = {"appraisal": {}, "strategy": {}}
    appraisal = await resolve_task_appraisal(
        llm=stage_client("appraisal", None) if stage_client else llm,
        **shared,
        strict_score_audit=reply_audit["appraisal"],
        stage_key="baseline_low_friction",
        world_context=ENVIRONMENT,
        helplessness_now=helplessness,
        task_self_efficacy=baseline.task_self_efficacy,
        help_success_rate_smoothed=baseline.help_success_rate_smoothed,
    )
    # The facts-only design locks rule inputs before the new appraisal. The observed
    # appraisal still reaches the strategy LLM, including under low-confidence fallback.
    features = (
        baseline
        if fact_resident
        else extract_memory_features(
            **feature_inputs, task_appraisal_result=appraisal.to_dict()
        )
    )
    features_used = {
        key: getattr(features, key)
        for key in (
            "effective_helplessness",
            "task_self_efficacy",
            "help_success_rate_smoothed",
            "recent_negative_feedback_ratio",
            "recent_same_task_failure_count",
        )
    }
    rule_inputs = dict(
        **features_used,
        support_quality=support_quality_from_env(ENVIRONMENT),
        task_difficulty=task.difficulty,
        consecutive_failures=consecutive_failures,
    )
    rule_weights = compute_rule_strategy_weights(**rule_inputs)
    deliberation = await resolve_strategy_deliberation(
        llm=stage_client("strategy", appraisal.to_dict()) if stage_client else llm,
        **shared,
        **features_used,
        strict_score_audit=reply_audit["strategy"],
        task_appraisal=appraisal.to_dict(),
        daily_reflection={},
        rule_weights=rule_weights,
        prompt_format=config.proto_llm_strategy_prompt_format,
    )
    strategy = choose_attempt_strategy(
        **rule_inputs,
        strategy_deliberation_result=deliberation,
        rng=_PairedDraw(float(sample_u)),
    )

    receiver = _RequestReceiver()
    if strategy.support_requested:
        request, reply, status = await dispatch_family_support_request(
            requester_id=requester_id,
            helper_id=helper_id,
            registry={helper_id: receiver},
            task=task,
            strategy=strategy,
            task_appraisal=appraisal,
            task_relevant_memory_packet=packet,
            env=ENVIRONMENT,
            profile_summary=profile,
            day=DAY,
            tick=TICK,
        )
        if (
            status != "dispatched"
            or receiver.request is not request
            or reply is not None
        ):
            raise RuntimeError(f"Unexpected diagnostic helper dispatch: {status}")

    if appraisal.cache_hit or deliberation.cache_hit:
        raise RuntimeError("Cached judgments are ineligible for the paired experiment")
    for stage, adopted in (
        ("appraisal", appraisal.source == "llm"),
        ("strategy", deliberation.source == "hybrid_blended"),
    ):
        audit = reply_audit[stage]
        parsed_phase = {"ok": "initial", "ok_repaired": "repair"}.get(
            audit["parse_status"]
        )
        audit["parsed_score_phase"] = parsed_phase
        audit["adopted_from"] = parsed_phase if adopted else "rule_fallback"
        audit["adopted_scores"] = (
            audit[parsed_phase]["reported_scores"] if adopted else None
        )
    raw_scores = None
    if deliberation.llm_weights is not None:
        raw_scores = {
            "attempt_self": deliberation.attempt_self_score,
            "seek_help_then_attempt": deliberation.seek_help_score,
            "avoid": deliberation.avoid_score,
        }
    return {
        **(
            {
                "rule_inputs": rule_inputs,
                "rule_input_source": "fixed_before_day5_appraisal",
                "independent_strategy_selected": strategy.strategy_type
                == "attempt_self",
                "operation_started": None,
                "task_outcome": None,
            }
            if fact_resident
            else {}
        ),
        "lower_valid": appraisal.source == "llm"
        and deliberation.source == "hybrid_blended",
        "reply_audit": reply_audit,
        "appraisal": appraisal.to_dict(),
        "strategy_source": deliberation.source,
        "strategy_status": deliberation.status,
        "strategy_confidence": deliberation.confidence,
        "strategy_reason": deliberation.reason,
        "dominant_strategy": deliberation.dominant_strategy,
        "raw_scores": raw_scores,
        "llm_weights": deliberation.llm_weights,
        "rule_weights": deliberation.rule_weights,
        "blended_weights": deliberation.final_weights,
        "final_weights": strategy.weights,
        "sample_u": float(sample_u),
        "sampled_action": strategy.strategy_type,
        "help_request_dispatched": receiver.request is not None,
        "help_request": receiver.request.to_dict()
        if receiver.request is not None
        else None,
        "help_delivery_status": "unobserved",
    }
