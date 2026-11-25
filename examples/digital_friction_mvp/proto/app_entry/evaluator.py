from __future__ import annotations

import json
from typing import Any

from .artifacts import (
    _CALIBRATION_CACHE,
    _MAPPING_CACHE,
    _TASK_OCCURRENCE_CACHE,
    _load_json_artifact,
)
from .audit import _context_review_status, _entry_audit
from .candidate import (
    _bucket_for_profile,
    _extract_app_context_prior_from_calibration,
    _extract_prior_from_calibration,
    _normalize_task_opportunity_distribution,
    _stable_select_app_context,
    _stable_select_intention,
    app_context_candidate_hash,
    mobile_intention_candidate_hash,
    top_app_context_candidates,
    top_mobile_intention_candidates,
)
from .gate import (
    _stable_task_occurrence_gate_roll,
    _task_occurrence_probability_for_context,
)
from .task_templates import (
    TASK_OPPORTUNITY_BY_CONTEXT,
    _build_task_from_template,
    _resolve_schedule_seed,
    _task_template_for_family,
    task_pressure_from_env,
)
from .types import (
    CONTEXT_ONLY_MOBILE_INTENTIONS,
    MOBILE_INTENTION_TO_TASK_FAMILY,
    TASK_ELIGIBLE_APP_CONTEXTS,
    MobileEntryDecision,
    clamp_score,
    _hour_for_tick,
    _stable_hash,
)
from ..models import DigitalTask
from .bundle import HourlyAppEntryBundle, NO_APP_CONTEXT


def _mapping_confidence_for_intention(
    *,
    intention: str,
    mapping_artifact: dict[str, Any],
) -> tuple[float, str]:
    default = 1.0 if intention in MOBILE_INTENTION_TO_TASK_FAMILY else 0.0
    if not mapping_artifact:
        return default, "default_mapping"
    candidates = mapping_artifact.get("mobile_intention_mapping", mapping_artifact)
    if not isinstance(candidates, dict):
        return default, "default_mapping"
    row = candidates.get(intention)
    if not isinstance(row, dict):
        return default, "default_mapping"
    try:
        return clamp_score(float(row.get("mapping_confidence", default))), "mapping_artifact"
    except (TypeError, ValueError):
        return default, "mapping_artifact_invalid_confidence"


def _task_opportunity_for_context(
    *,
    app_context: str,
    mapping_artifact: dict[str, Any],
) -> tuple[dict[str, float], str]:
    default = TASK_OPPORTUNITY_BY_CONTEXT.get(app_context, {})
    if not mapping_artifact:
        return dict(default), "default_task_opportunity"
    candidates = mapping_artifact.get("task_opportunity_by_context", mapping_artifact)
    if not isinstance(candidates, dict):
        return dict(default), "default_task_opportunity"
    row = candidates.get(app_context)
    if not isinstance(row, dict):
        return dict(default), "default_task_opportunity"
    return _normalize_task_opportunity_distribution(row), "task_opportunity_artifact"


def _stable_select_task_family_for_context(
    *,
    app_context: str,
    task_distribution: dict[str, float],
    seed: int,
    agent_id: int,
    day: int,
    tick_seconds: float,
    profile_bucket: str,
) -> str | None:
    from .task_templates import TASK_LIBRARY
    from .types import _stable_select_from_distribution

    if app_context not in TASK_ELIGIBLE_APP_CONTEXTS:
        return None
    normalized = _normalize_task_opportunity_distribution(task_distribution)
    task_keys = tuple(str(template["task_family"]) for template in TASK_LIBRARY)
    return _stable_select_from_distribution(
        values=normalized,
        keys=task_keys,
        seed=int(seed),
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        profile_bucket=profile_bucket,
        version=f"task_opportunity_for_{app_context}_v1",
    )


def _evaluate_selected_app_context_entry_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    normalized_mode: str,
    selected_app_context: str,
    rule_selected_app_context: str,
    priors: dict[str, float],
    prior_source: str,
    mapping_artifact: dict[str, Any],
    mapping_hash: str,
    calibration_hash: str,
    occurrence_artifact: dict[str, Any],
    occurrence_hash: str,
    profile_bucket: str,
    rerank_audit: dict[str, Any],
    task_occurrence_gate_enabled: bool,
    task_occurrence_gate_multiplier: float,
    allow_task_generation: bool = True,
    blocked_task_generation_reason: str = "",
) -> MobileEntryDecision:
    selected = str(selected_app_context or "").strip()
    rule_selected = str(rule_selected_app_context or selected).strip()
    task_distribution, mapping_source = _task_opportunity_for_context(
        app_context=selected,
        mapping_artifact=mapping_artifact,
    )
    final_task_eligible = selected in TASK_ELIGIBLE_APP_CONTEXTS
    task_eligible_context_exposure = bool(final_task_eligible)
    task_occurrence_probability = 0.0
    task_occurrence_gate_roll: float | None = None
    task_occurrence_gate_passed = False
    task_occurrence_gate_source = "not_applicable_context_only"
    task_occurrence_gate_reason = "context_not_task_eligible"
    context_only_reason = ""
    task_generation_blocked = bool(final_task_eligible and not allow_task_generation)
    if task_generation_blocked:
        task_occurrence_gate_source = "skipped_existing_task"
        task_occurrence_gate_reason = (
            str(blocked_task_generation_reason or "existing_task_pending")
        )
    elif final_task_eligible:
        if bool(task_occurrence_gate_enabled):
            task_occurrence_probability, task_occurrence_gate_source = (
                _task_occurrence_probability_for_context(
                    app_context=selected,
                    occurrence_artifact=occurrence_artifact,
                    multiplier=float(task_occurrence_gate_multiplier),
                )
            )
            task_occurrence_gate_roll = _stable_task_occurrence_gate_roll(
                app_context=selected,
                seed=_resolve_schedule_seed(),
                agent_id=int(agent_id),
                day=int(day),
                tick_seconds=float(tick_seconds),
                profile_bucket=profile_bucket,
            )
            task_occurrence_gate_passed = (
                task_occurrence_gate_roll <= task_occurrence_probability
            )
            task_occurrence_gate_reason = (
                "gate_passed"
                if task_occurrence_gate_passed
                else "task_occurrence_gate_not_passed"
            )
        else:
            task_occurrence_probability = 1.0
            task_occurrence_gate_roll = 0.0
            task_occurrence_gate_passed = True
            task_occurrence_gate_source = "gate_disabled_legacy"
            task_occurrence_gate_reason = "gate_disabled"
    mapped_task_family = None
    if task_occurrence_gate_passed:
        mapped_task_family = _stable_select_task_family_for_context(
            app_context=selected,
            task_distribution=task_distribution,
            seed=_resolve_schedule_seed(),
            agent_id=int(agent_id),
            day=int(day),
            tick_seconds=float(tick_seconds),
            profile_bucket=profile_bucket,
        )
    mapping_confidence = 1.0 if mapped_task_family else 0.0
    task: DigitalTask | None = None
    if selected == "no_app_context":
        entry_status = "no_app_context_noop"
        context_only_reason = "inactive_hour_no_app_context"
        reason = f"{selected}:inactive_hour:{prior_source}"
    elif selected not in TASK_ELIGIBLE_APP_CONTEXTS:
        if selected == "unknown_or_unmapped":
            entry_status = "unknown_or_unmapped_noop"
        else:
            entry_status = f"{selected}_context_only"
        context_only_reason = "app_context_only"
        reason = f"{selected}:app_context_only:{prior_source}"
    elif task_generation_blocked:
        entry_status = "task_eligible_context_existing_task_pending"
        context_only_reason = str(
            blocked_task_generation_reason or "existing_task_pending"
        )
        reason = f"{selected}:existing_task_pending:{prior_source}"
    elif not task_occurrence_gate_passed:
        entry_status = "task_eligible_context_no_task"
        context_only_reason = "task_occurrence_gate_not_passed"
        reason = (
            f"{selected}:task_occurrence_gate_not_passed:"
            f"{task_occurrence_gate_source}:prior_{prior_source}"
        )
    elif mapped_task_family is None:
        entry_status = "no_task_opportunity_noop"
        context_only_reason = "no_task_opportunity"
        reason = f"{selected}:no_task_opportunity:{mapping_source}"
    else:
        task = _build_task_from_template(
            normalized_mode=normalized_mode,
            mapped_task_family=mapped_task_family,
            agent_id=int(agent_id),
            day=int(day),
            tick_seconds=float(tick_seconds),
            env=env,
        )
        if task is None:
            entry_status = "unknown_or_unmapped_noop"
            context_only_reason = "mapped_family_not_in_task_library"
            reason = f"{selected}:mapped_family_not_in_task_library"
            mapped_task_family = None
        else:
            entry_status = "entered_mapped_digital_task"
            reason = (
                f"{selected}:task_opportunity_via_{mapping_source}:"
                f"prior_{prior_source}"
            )

    rule_prior = float(priors.get(rule_selected, 0.0))
    final_prior = float(priors.get(selected, 0.0))
    rule_task_eligible = rule_selected in TASK_ELIGIBLE_APP_CONTEXTS
    llm_selected = str(rerank_audit.get("rerank_selected_app_context", "")).strip()
    llm_prior = float(priors.get(llm_selected, 0.0)) if llm_selected else 0.0
    llm_task_eligible = llm_selected in TASK_ELIGIBLE_APP_CONTEXTS
    context_audit = {
        "entry_layer": "app_context",
        "candidate_app_contexts": dict(priors),
        "rule_selected_app_context": rule_selected,
        "llm_selected_app_context": llm_selected,
        "final_selected_app_context": selected,
        "rule_selected_prior": rule_prior,
        "llm_selected_prior": llm_prior,
        "final_selected_prior": final_prior,
        "rule_task_eligible": bool(rule_task_eligible),
        "llm_task_eligible": bool(llm_task_eligible) if llm_selected else False,
        "final_task_eligible": bool(final_task_eligible),
        "changed_context_only_to_task_eligible": bool(
            (not rule_task_eligible) and final_task_eligible
        ),
        "changed_to_lower_prior": bool(final_prior < rule_prior),
        "prior_drop_from_rule_to_llm": max(0.0, rule_prior - final_prior),
        "generated_task_family": mapped_task_family or "",
        "task_occurrence_gate_enabled": bool(task_occurrence_gate_enabled),
        "task_occurrence_probability": float(task_occurrence_probability),
        "task_occurrence_multiplier": float(task_occurrence_gate_multiplier),
        "task_occurrence_gate_roll": task_occurrence_gate_roll,
        "task_occurrence_gate_passed": bool(task_occurrence_gate_passed),
        "task_occurrence_gate_source": task_occurrence_gate_source,
        "task_occurrence_gate_reason": task_occurrence_gate_reason,
        "task_eligible_context_exposure": bool(task_eligible_context_exposure),
        "context_only_reason": context_only_reason,
        "task_opportunity_distribution_json": json.dumps(
            task_distribution,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "context_mapping_basis": prior_source,
        "context_review_status": _context_review_status(selected),
    }
    rerank_audit.update(context_audit)
    audit = _entry_audit(
        entry_mode=normalized_mode,
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        hour=_hour_for_tick(tick_seconds),
        selected_mobile_intention="",
        entry_status=entry_status,
        mapped_task_family=mapped_task_family,
        mapping_confidence=mapping_confidence,
        task_generated=task is not None,
        candidate_intentions={},
        calibration_hash=calibration_hash,
        mapping_hash=mapping_hash,
        reason=reason,
        llm_shadow={},
        rerank_audit=rerank_audit,
    )
    audit["profile_bucket"] = profile_bucket
    audit["prior_source"] = prior_source
    audit["mapping_source"] = mapping_source
    audit["task_occurrence_artifact_hash"] = occurrence_hash
    audit["selected_app_context"] = selected
    return MobileEntryDecision(
        entry_evaluated=True,
        selected_mobile_intention="",
        selected_app_context=selected,
        entry_status=entry_status,
        mapped_task_family=mapped_task_family,
        mapping_confidence=mapping_confidence,
        task_generated=task is not None,
        task=task,
        candidate_intentions={},
        candidate_app_contexts=priors,
        audit=audit,
    )


def evaluate_selected_app_context_bundle_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    stable_profile: dict[str, Any] | None,
    bundle: HourlyAppEntryBundle,
    entry_mode: str,
    prior_source: str,
    audit_payload: dict[str, Any],
    calibration_hash: str = "",
    task_opportunity_mapping_path: str = "",
    task_occurrence_gate_enabled: bool = False,
    task_occurrence_prior_path: str = "",
    task_occurrence_gate_multiplier: float = 1.0,
    existing_task_pending: bool = False,
) -> MobileEntryDecision:
    """Evaluate a validated hourly bundle through the shared app-context gate."""
    bundle.validate()
    mapping_artifact, mapping_hash = _load_json_artifact(
        task_opportunity_mapping_path,
        cache=_MAPPING_CACHE,
    )
    occurrence_artifact: dict[str, Any] = {}
    occurrence_hash = ""
    if bool(task_occurrence_gate_enabled) and not bool(existing_task_pending):
        if not str(task_occurrence_prior_path or "").strip():
            raise ValueError(
                "task_occurrence_prior_path is required when gate is enabled"
            )
        occurrence_artifact, occurrence_hash = _load_json_artifact(
            task_occurrence_prior_path,
            cache=_TASK_OCCURRENCE_CACHE,
        )

    priors = bundle.context_share_distribution()
    if bundle.primary_context == NO_APP_CONTEXT:
        priors = {}
    shared_audit = dict(audit_payload)
    decision = _evaluate_selected_app_context_entry_for_agent(
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        env=env,
        normalized_mode=str(entry_mode),
        selected_app_context=bundle.primary_context,
        rule_selected_app_context=bundle.primary_context,
        priors=priors,
        prior_source=str(prior_source),
        mapping_artifact=mapping_artifact,
        mapping_hash=mapping_hash,
        calibration_hash=str(calibration_hash),
        occurrence_artifact=occurrence_artifact,
        occurrence_hash=occurrence_hash,
        profile_bucket=_bucket_for_profile(stable_profile),
        rerank_audit=shared_audit,
        task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
        task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
        allow_task_generation=not bool(existing_task_pending),
        blocked_task_generation_reason="existing_task_pending",
    )
    decision.audit.update(shared_audit)
    decision.audit["task_outcome_may_update_psychology"] = bool(
        decision.task is not None
    )
    decision.audit["task_generated"] = bool(decision.task is not None)
    return decision


def _evaluate_app_context_entry_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    stable_profile: dict[str, Any] | None,
    normalized_mode: str,
    calibration_path: str,
    mapping_path: str,
    selected_app_context_override: str | None,
    rerank_audit_payload: dict[str, Any] | None,
    rerank_top_k: int,
    task_occurrence_gate_enabled: bool,
    task_occurrence_prior_path: str,
    task_occurrence_gate_multiplier: float,
) -> MobileEntryDecision:
    calibration, calibration_hash = _load_json_artifact(
        calibration_path,
        cache=_CALIBRATION_CACHE,
    )
    mapping_artifact, mapping_hash = _load_json_artifact(
        mapping_path,
        cache=_MAPPING_CACHE,
    )
    occurrence_artifact: dict[str, Any] = {}
    occurrence_hash = ""
    if bool(task_occurrence_gate_enabled):
        if not str(task_occurrence_prior_path or "").strip():
            raise ValueError(
                "task_occurrence_prior_path is required when gate is enabled"
            )
        occurrence_artifact, occurrence_hash = _load_json_artifact(
            task_occurrence_prior_path,
            cache=_TASK_OCCURRENCE_CACHE,
        )
    hour = _hour_for_tick(tick_seconds)
    priors, prior_source = _extract_app_context_prior_from_calibration(
        calibration=calibration,
        profile=stable_profile,
        hour=hour,
    )
    profile_bucket = _bucket_for_profile(stable_profile)
    rule_selected = _stable_select_app_context(
        priors=priors,
        seed=_resolve_schedule_seed(),
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        profile_bucket=profile_bucket,
    )
    top_candidates = top_app_context_candidates(priors, top_k=rerank_top_k)
    selected = rule_selected
    rerank_audit = dict(rerank_audit_payload or {})
    if normalized_mode == "app_context_llm_rerank_online_mc":
        override = str(selected_app_context_override or "").strip()
        if not override:
            raise ValueError(
                "selected_app_context_override is required for "
                "app_context_llm_rerank_online_mc"
            )
        fallback_to_rule = bool(rerank_audit.get("fallback_to_rule", False))
        if override not in top_candidates and not (
            fallback_to_rule and override == rule_selected
        ):
            raise ValueError(
                "selected_app_context_override must be one of top-k app contexts"
            )
        selected = override
        rerank_audit.update(
            {
                "rerank_enabled": True,
                "entry_layer": "app_context",
                "rule_selected_app_context": rule_selected,
                "rerank_selected_app_context": selected,
                "rerank_top_k": int(max(1, rerank_top_k)),
                "rerank_candidate_app_contexts": dict(top_candidates),
                "rerank_candidate_hash": app_context_candidate_hash(top_candidates),
                "llm_drives_real_entry": True,
                "uses_post_outcome_information": False,
                "does_not_decide_strategy": True,
                "does_not_decide_outcome": True,
                "does_not_update_psychology": True,
            }
        )
    else:
        rerank_audit.update(
            {
                "rerank_enabled": False,
                "entry_layer": "app_context",
                "rule_selected_app_context": rule_selected,
                "llm_drives_real_entry": False,
            }
        )

    return _evaluate_selected_app_context_entry_for_agent(
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        env=env,
        normalized_mode=normalized_mode,
        selected_app_context=selected,
        rule_selected_app_context=rule_selected,
        priors=priors,
        prior_source=prior_source,
        mapping_artifact=mapping_artifact,
        mapping_hash=mapping_hash,
        calibration_hash=calibration_hash,
        occurrence_artifact=occurrence_artifact,
        occurrence_hash=occurrence_hash,
        profile_bucket=profile_bucket,
        rerank_audit=rerank_audit,
        task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
        task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
    )


def evaluate_mobile_entry_for_agent(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    env: dict[str, Any],
    stable_profile: dict[str, Any] | None = None,
    entry_mode: str = "mobile_intention_rule",
    calibration_path: str = "",
    mapping_path: str = "",
    confidence_threshold: float = 0.70,
    llm_shadow_enabled: bool = False,
    llm_shadow_payload: dict[str, Any] | None = None,
    selected_intention_override: str | None = None,
    rerank_audit_payload: dict[str, Any] | None = None,
    rerank_top_k: int = 5,
    task_occurrence_gate_enabled: bool = False,
    task_occurrence_prior_path: str = "",
    task_occurrence_gate_multiplier: float = 1.0,
) -> MobileEntryDecision:
    normalized_mode = str(entry_mode or "mobile_intention_rule").strip().lower()
    if normalized_mode not in {
        "mobile_intention_rule",
        "mobile_intention_llm_shadow",
        "mobile_intention_llm_rerank_online_mc",
        "app_context_rule",
        "app_context_llm_rerank_online_mc",
    }:
        raise ValueError(
            "mobile entry mode must be one of: mobile_intention_rule, "
            "mobile_intention_llm_shadow, mobile_intention_llm_rerank_online_mc, "
            "app_context_rule, app_context_llm_rerank_online_mc"
        )
    if normalized_mode in {"app_context_rule", "app_context_llm_rerank_online_mc"}:
        return _evaluate_app_context_entry_for_agent(
            agent_id=int(agent_id),
            day=int(day),
            tick_seconds=float(tick_seconds),
            env=env,
            stable_profile=stable_profile,
            normalized_mode=normalized_mode,
            calibration_path=calibration_path,
            mapping_path=mapping_path,
            selected_app_context_override=selected_intention_override,
            rerank_audit_payload=rerank_audit_payload,
            rerank_top_k=int(rerank_top_k),
            task_occurrence_gate_enabled=bool(task_occurrence_gate_enabled),
            task_occurrence_prior_path=task_occurrence_prior_path,
            task_occurrence_gate_multiplier=float(task_occurrence_gate_multiplier),
        )
    calibration, calibration_hash = _load_json_artifact(
        calibration_path,
        cache=_CALIBRATION_CACHE,
    )
    mapping_artifact, mapping_hash = _load_json_artifact(
        mapping_path,
        cache=_MAPPING_CACHE,
    )
    hour = _hour_for_tick(tick_seconds)
    priors, prior_source = _extract_prior_from_calibration(
        calibration=calibration,
        profile=stable_profile,
        hour=hour,
    )
    profile_bucket = _bucket_for_profile(stable_profile)
    rule_selected = _stable_select_intention(
        priors=priors,
        seed=_resolve_schedule_seed(),
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        profile_bucket=profile_bucket,
    )
    top_candidates = top_mobile_intention_candidates(priors, top_k=rerank_top_k)
    selected = rule_selected
    rerank_audit = dict(rerank_audit_payload or {})
    if normalized_mode == "mobile_intention_llm_rerank_online_mc":
        override = str(selected_intention_override or "").strip()
        if not override:
            raise ValueError(
                "selected_intention_override is required for "
                "mobile_intention_llm_rerank_online_mc"
            )
        if override not in top_candidates:
            raise ValueError(
                "selected_intention_override must be one of top-k candidate intentions"
            )
        selected = override
        rerank_audit.update(
            {
                "rerank_enabled": True,
                "rule_selected_mobile_intention": rule_selected,
                "rerank_selected_mobile_intention": selected,
                "rerank_top_k": int(max(1, rerank_top_k)),
                "rerank_candidate_intentions": dict(top_candidates),
                "rerank_candidate_hash": mobile_intention_candidate_hash(top_candidates),
                "llm_drives_real_entry": True,
                "uses_post_outcome_information": False,
                "does_not_decide_strategy": True,
                "does_not_decide_outcome": True,
                "does_not_update_psychology": True,
            }
        )
    else:
        rerank_audit.update(
            {
                "rerank_enabled": False,
                "rule_selected_mobile_intention": rule_selected,
                "llm_drives_real_entry": False,
            }
        )
    mapped_task_family = MOBILE_INTENTION_TO_TASK_FAMILY.get(selected)
    mapping_confidence, mapping_source = _mapping_confidence_for_intention(
        intention=selected,
        mapping_artifact=mapping_artifact,
    )
    threshold = clamp_score(float(confidence_threshold))
    llm_shadow = dict(llm_shadow_payload or {})
    if normalized_mode == "mobile_intention_llm_shadow" or llm_shadow_enabled:
        llm_shadow.setdefault("llm_shadow_enabled", True)
        llm_shadow.setdefault("llm_parse_status", "not_called")
        llm_shadow.setdefault("llm_affected_real_entry", False)
    else:
        llm_shadow.setdefault("llm_shadow_enabled", False)
        llm_shadow.setdefault("llm_affected_real_entry", False)

    task: DigitalTask | None = None
    if selected in CONTEXT_ONLY_MOBILE_INTENTIONS:
        if selected == "communicate_or_seek_help":
            entry_status = "communicate_context_only"
        elif selected == "browse_entertainment":
            entry_status = "browse_context_only"
        elif selected == "no_mobile_action":
            entry_status = "no_mobile_action_noop"
        else:
            entry_status = "unknown_or_unmapped_noop"
        reason = f"{selected}:context_or_noop"
    elif mapped_task_family is None:
        entry_status = "unknown_or_unmapped_noop"
        reason = f"{selected}:no_task_family_mapping"
    elif mapping_confidence < threshold:
        entry_status = "low_confidence_mapping_noop"
        reason = (
            f"{selected}:mapping_confidence_{mapping_confidence:.3f}_below_"
            f"threshold_{threshold:.3f}"
        )
    else:
        template = _task_template_for_family(mapped_task_family)
        if template is None:
            entry_status = "unknown_or_unmapped_noop"
            reason = f"{selected}:mapped_family_not_in_task_library"
            mapped_task_family = None
        else:
            assigned_tick = int(day * 100000 + int(round(float(tick_seconds))))
            eval_slot = int(round(float(tick_seconds))) // 60
            task_id = (
                f"{normalized_mode}_{mapped_task_family}_{agent_id}_{day}_"
                f"{eval_slot}_{int(round(float(tick_seconds)))}"
            )
            task = DigitalTask(
                task_id=task_id,
                task_family=template["task_family"],
                friction_type=template["friction_type"],
                difficulty=task_pressure_from_env(template, env),
                need_type=template["need_type"],
                support_sensitivity=float(template["support_sensitivity"]),
                assigned_tick=assigned_tick,
                defer_count=0,
            )
            entry_status = "entered_mapped_digital_task"
            reason = f"{selected}:mapped_via_{mapping_source}:prior_{prior_source}"

    audit = _entry_audit(
        entry_mode=normalized_mode,
        agent_id=int(agent_id),
        day=int(day),
        tick_seconds=float(tick_seconds),
        hour=hour,
        selected_mobile_intention=selected,
        entry_status=entry_status,
        mapped_task_family=mapped_task_family,
        mapping_confidence=mapping_confidence,
        task_generated=task is not None,
        candidate_intentions=priors,
        calibration_hash=calibration_hash,
        mapping_hash=mapping_hash,
        reason=reason,
        llm_shadow=llm_shadow,
        rerank_audit=rerank_audit,
    )
    audit["profile_bucket"] = profile_bucket
    audit["prior_source"] = prior_source
    audit["mapping_source"] = mapping_source
    return MobileEntryDecision(
        entry_evaluated=True,
        selected_mobile_intention=selected,
        entry_status=entry_status,
        mapped_task_family=mapped_task_family,
        mapping_confidence=mapping_confidence,
        task_generated=task is not None,
        task=task,
        candidate_intentions=priors,
        audit=audit,
    )


def skipped_mobile_entry_decision(
    *,
    agent_id: int,
    day: int,
    tick_seconds: float,
    entry_mode: str,
    reason: str = "not_evaluation_tick",
) -> MobileEntryDecision:
    audit = {
        "agent_id": int(agent_id),
        "day": int(day),
        "tick_seconds": float(tick_seconds),
        "hour": _hour_for_tick(tick_seconds),
        "entry_mode": str(entry_mode),
        "entry_evaluated": False,
        "entry_status": "skipped_eval",
        "task_generated": False,
        "reason": str(reason),
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "is_avoidance": False,
        "is_help_action": False,
        "helper_triggered": False,
    }
    return MobileEntryDecision(
        entry_evaluated=False,
        selected_mobile_intention="",
        entry_status="skipped_eval",
        mapped_task_family=None,
        mapping_confidence=0.0,
        task_generated=False,
        task=None,
        candidate_intentions={},
        audit=audit,
    )


def failed_rollout_entry_decision(
    *,
    agent_id: int,
    device_id: str,
    simulation_day: int,
    talkingdata_day: int,
    tick_seconds: float,
    entry_mode: str,
    error: Exception,
) -> MobileEntryDecision:
    """Record a missing rollout hour without fabricating no-app behavior."""
    error_message = str(error)[:2000]
    audit = {
        "agent_id": int(agent_id),
        "device_id": str(device_id),
        "simulation_day": int(simulation_day),
        "talkingdata_day": int(talkingdata_day),
        "tick_seconds": float(tick_seconds),
        "hour": _hour_for_tick(tick_seconds),
        "entry_mode": str(entry_mode),
        "entry_phase": "llm_rollout",
        "entry_evaluated": True,
        "entry_status": "llm_rollout_error",
        "bundle_generated": False,
        "task_generated": False,
        "error_type": type(error).__name__,
        "error_message": error_message,
        "error_hash": _stable_hash(
            {"error_type": type(error).__name__, "error_message": error_message}
        )[:16],
        "uses_validation_data": False,
        "uses_post_outcome_information": False,
        "does_not_decide_strategy": True,
        "does_not_decide_outcome": True,
        "does_not_update_psychology": True,
        "is_avoidance": False,
        "is_help_action": False,
        "helper_triggered": False,
    }
    return MobileEntryDecision(
        entry_evaluated=True,
        selected_mobile_intention="",
        entry_status="llm_rollout_error",
        mapped_task_family=None,
        mapping_confidence=0.0,
        task_generated=False,
        task=None,
        candidate_intentions={},
        audit=audit,
    )
