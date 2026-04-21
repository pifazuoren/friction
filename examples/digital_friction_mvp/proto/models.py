from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TaskFamily = Literal[
    "login_verification",
    "appointment_registration",
    "payment_checkout",
    "health_info_lookup",
]

FrictionType = Literal[
    "verification",
    "form_complexity",
    "payment_risk_popup",
    "information_overload",
]

AttemptStrategyType = Literal[
    "attempt_self",
    "seek_help_then_attempt",
    "avoid",
    "abandon_midway",
]

OutcomeType = Literal[
    "success_self",
    "success_with_help",
    "failure_after_attempt",
    "failure_even_with_help",
    "abandon_midway",
    "avoid_without_attempt",
]

EventAttributionLocus = Literal[
    "self",
    "mixed",
    "situation",
    "not_applicable",
]

EventAttributionStability = Literal[
    "transient",
    "mixed",
    "stable",
    "not_applicable",
]

EventAttributionScope = Literal[
    "task_specific",
    "mixed",
    "family_generalizing",
    "not_applicable",
]


@dataclass(slots=True)
class DigitalTask:
    task_id: str
    task_family: TaskFamily
    friction_type: FrictionType
    difficulty: float
    need_type: str
    support_sensitivity: float
    assigned_tick: int
    defer_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DigitalTask":
        return cls(
            task_id=str(payload.get("task_id", "")),
            task_family=str(payload.get("task_family", "login_verification")),  # type: ignore[arg-type]
            friction_type=str(payload.get("friction_type", "verification")),  # type: ignore[arg-type]
            difficulty=float(payload.get("difficulty", 0.5)),
            need_type=str(payload.get("need_type", "daily_task")),
            support_sensitivity=float(payload.get("support_sensitivity", 0.5)),
            assigned_tick=int(payload.get("assigned_tick", 0)),
            defer_count=int(payload.get("defer_count", 0)),
        )


@dataclass(slots=True)
class AttemptStrategy:
    strategy_type: AttemptStrategyType
    support_requested: bool = False
    rationale: str = ""
    weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AttemptOutcome:
    outcome_type: OutcomeType
    success: bool
    help_used: bool
    negative_feedback: bool
    support_quality: int
    event_level_uncontrollability: int
    friction_tier: int
    success_probability: float
    abandon_probability: float
    note: str = ""
    rule_event_level_uncontrollability: int = 0
    uncontrollability_source: str = "rule"
    uncontrollability_llm_value: int | None = None
    uncontrollability_llm_confidence: float = 0.0
    uncontrollability_llm_reason: str = ""
    uncontrollability_status: str = "not_called"
    uncontrollability_cache_hit: bool = False
    avoid_reason: str = "not_applicable"
    avoid_reason_source: str = "not_applicable"
    avoid_reason_confidence: float = 0.0
    avoid_reason_note: str = ""
    support_mode: str = "not_applicable"
    support_mode_source: str = "not_applicable"
    event_attribution_locus: EventAttributionLocus = "not_applicable"
    event_attribution_stability: EventAttributionStability = "not_applicable"
    event_attribution_scope: EventAttributionScope = "not_applicable"
    event_attribution_explanation: str = ""
    event_attribution_confidence: float = 0.0
    event_attribution_source: str = "not_applicable"
    event_attribution_status: str = "not_called"
    event_attribution_cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HelplessnessUpdateInput:
    helplessness_now: float
    outcome_type: OutcomeType
    consecutive_failures: int
    support_quality: int
    event_level_uncontrollability: int
    task_self_efficacy: float
    felt_control: float
    expected_help_effectiveness: float
    avoid_reason: str
    controllable_success_memory: float
    support_mode: str


@dataclass(slots=True)
class HelplessnessUpdateResult:
    helplessness_before: float
    helplessness_after: float
    delta: float
    base_delta: float
    uncontrollability_delta: float
    efficacy_loss_term: float
    recovery_bonus: float
    mastery_recovery_term: float
    raw_delta_before_damping: float
    damping_factor: float
    avoid_reason_multiplier: float
    controllable_success_protection: float
    next_consecutive_failures: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EventAttributionResult:
    mode: str
    status: str
    source: str
    event_attribution_locus: EventAttributionLocus
    event_attribution_stability: EventAttributionStability
    event_attribution_scope: EventAttributionScope
    event_attribution_explanation: str
    judge_confidence: float
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskDomainState:
    task_self_efficacy: float
    controllable_success_memory: float = 0.0
    dominant_attribution_stability: str = "mixed"
    dominant_attribution_scope: str = "task_specific"
    recent_stable_attribution_ratio: float = 0.0
    recent_generalizing_attribution_ratio: float = 0.0
    attribution_summary: str = ""
    attempt_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avoid_count: int = 0
    same_task_failure_streak: int = 0
    recent_negative_feedback_ema: float = 0.0
    last_outcome: str = ""
    last_updated_day: int = -1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TaskDomainState":
        payload = payload or {}
        return cls(
            task_self_efficacy=float(payload.get("task_self_efficacy", 50.0)),
            controllable_success_memory=float(
                payload.get("controllable_success_memory", 0.0)
            ),
            dominant_attribution_stability=str(
                payload.get("dominant_attribution_stability", "mixed")
            ),
            dominant_attribution_scope=str(
                payload.get("dominant_attribution_scope", "task_specific")
            ),
            recent_stable_attribution_ratio=float(
                payload.get("recent_stable_attribution_ratio", 0.0)
            ),
            recent_generalizing_attribution_ratio=float(
                payload.get("recent_generalizing_attribution_ratio", 0.0)
            ),
            attribution_summary=str(payload.get("attribution_summary", "")),
            attempt_count=int(payload.get("attempt_count", 0)),
            success_count=int(payload.get("success_count", 0)),
            failure_count=int(payload.get("failure_count", 0)),
            avoid_count=int(payload.get("avoid_count", 0)),
            same_task_failure_streak=int(payload.get("same_task_failure_streak", 0)),
            recent_negative_feedback_ema=float(
                payload.get("recent_negative_feedback_ema", 0.0)
            ),
            last_outcome=str(payload.get("last_outcome", "")),
            last_updated_day=int(payload.get("last_updated_day", -1)),
        )


@dataclass(slots=True)
class HelpEffectState:
    help_attempt_count: int = 0
    help_success_count: int = 0
    help_failure_count: int = 0
    help_success_rate_smoothed: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "HelpEffectState":
        payload = payload or {}
        return cls(
            help_attempt_count=int(payload.get("help_attempt_count", 0)),
            help_success_count=int(payload.get("help_success_count", 0)),
            help_failure_count=int(payload.get("help_failure_count", 0)),
            help_success_rate_smoothed=float(
                payload.get("help_success_rate_smoothed", 0.5)
            ),
        )


@dataclass(slots=True)
class RecentEpisode:
    day: int
    task_family: TaskFamily
    strategy_type: AttemptStrategyType
    outcome_type: OutcomeType
    avoid_reason: str
    help_used: bool
    help_source: str
    negative_feedback: bool
    event_level_uncontrollability: int
    helplessness_delta: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RecentEpisode":
        payload = payload or {}
        return cls(
            day=int(payload.get("day", 0)),
            task_family=str(payload.get("task_family", "login_verification")),  # type: ignore[arg-type]
            strategy_type=str(payload.get("strategy_type", "avoid")),  # type: ignore[arg-type]
            outcome_type=str(payload.get("outcome_type", "avoid_without_attempt")),  # type: ignore[arg-type]
            avoid_reason=str(payload.get("avoid_reason", "not_applicable")),
            help_used=bool(payload.get("help_used", False)),
            help_source=str(payload.get("help_source", "none")),
            negative_feedback=bool(payload.get("negative_feedback", False)),
            event_level_uncontrollability=int(
                payload.get("event_level_uncontrollability", 0)
            ),
            helplessness_delta=float(payload.get("helplessness_delta", 0.0)),
        )


@dataclass(slots=True)
class MemoryFeatures:
    effective_helplessness: float
    task_self_efficacy: float
    controllable_success_memory: float
    task_specific_pressure: float
    help_success_rate_smoothed: float
    help_confidence_bonus: float
    recent_negative_feedback_ratio: float
    recent_avoid_ratio: float
    recent_help_seek_ratio: float
    recent_same_task_failure_count: int
    recent_failure_pressure: float
    emotion_pressure: float = 0.0
    task_appraisal_shift: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DigitalEmotionState:
    anxiety: float = 4.0
    frustration: float = 3.0
    relief: float = 2.0
    confidence: float = 5.0
    last_updated_day: int = -1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "DigitalEmotionState":
        payload = payload or {}
        return cls(
            anxiety=float(payload.get("anxiety", 4.0)),
            frustration=float(payload.get("frustration", 3.0)),
            relief=float(payload.get("relief", 2.0)),
            confidence=float(payload.get("confidence", 5.0)),
            last_updated_day=int(payload.get("last_updated_day", -1)),
        )


@dataclass(slots=True)
class EventAppraisalResult:
    mode: str
    status: str
    source: str
    confidence: float
    reason: str
    cache_hit: bool
    emotion_before: dict[str, float]
    rule_after: dict[str, float]
    llm_after: dict[str, float] | None
    final_after: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskAppraisalResult:
    mode: str
    status: str
    source: str
    confidence: float
    reason: str
    cache_hit: bool
    perceived_task_difficulty: float = 50.0
    perceived_task_risk: float = 50.0
    felt_control: float = 50.0
    expected_help_effectiveness: float = 50.0
    task_value: float = 50.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TaskAppraisalResult":
        payload = payload or {}
        return cls(
            mode=str(payload.get("mode", "off")),
            status=str(payload.get("status", "disabled")),
            source=str(payload.get("source", "rule")),
            confidence=float(payload.get("confidence", 0.0)),
            reason=str(payload.get("reason", "")),
            cache_hit=bool(payload.get("cache_hit", False)),
            perceived_task_difficulty=float(
                payload.get("perceived_task_difficulty", 50.0)
            ),
            perceived_task_risk=float(payload.get("perceived_task_risk", 50.0)),
            felt_control=float(payload.get("felt_control", 50.0)),
            expected_help_effectiveness=float(
                payload.get("expected_help_effectiveness", 50.0)
            ),
            task_value=float(payload.get("task_value", 50.0)),
        )


@dataclass(slots=True)
class DailyReflection:
    day: int
    dominant_task_family: str
    help_effective: bool
    mastery_signal: str
    text: str
    confidence: float = 0.0
    source: str = "rule"
    status: str = "not_called"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "DailyReflection":
        payload = payload or {}
        return cls(
            day=int(payload.get("day", -1)),
            dominant_task_family=str(payload.get("dominant_task_family", "")),
            help_effective=bool(payload.get("help_effective", False)),
            mastery_signal=str(payload.get("mastery_signal", "mixed")),
            text=str(payload.get("text", "")),
            confidence=float(payload.get("confidence", 0.0)),
            source=str(payload.get("source", "rule")),
            status=str(payload.get("status", "not_called")),
        )


@dataclass(slots=True)
class StrategyDeliberationResult:
    mode: str
    status: str
    source: str
    confidence: float
    reason: str
    cache_hit: bool
    dominant_strategy: str = ""
    attempt_self_score: float = 0.0
    seek_help_score: float = 0.0
    avoid_score: float = 0.0
    rule_weights: dict[str, float] = field(default_factory=dict)
    llm_weights: dict[str, float] | None = None
    final_weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, payload: dict[str, Any] | None
    ) -> "StrategyDeliberationResult":
        payload = payload or {}
        rule_weights = (
            {
                str(key): float(value)
                for key, value in payload.get("rule_weights", {}).items()
            }
            if isinstance(payload.get("rule_weights"), dict)
            else {}
        )
        llm_weights = (
            {
                str(key): float(value)
                for key, value in payload.get("llm_weights", {}).items()
            }
            if isinstance(payload.get("llm_weights"), dict)
            else None
        )
        final_weights = (
            {
                str(key): float(value)
                for key, value in payload.get("final_weights", {}).items()
            }
            if isinstance(payload.get("final_weights"), dict)
            else {}
        )
        return cls(
            mode=str(payload.get("mode", "off")),
            status=str(payload.get("status", "disabled")),
            source=str(payload.get("source", "rule")),
            confidence=float(payload.get("confidence", 0.0)),
            reason=str(payload.get("reason", "")),
            cache_hit=bool(payload.get("cache_hit", False)),
            dominant_strategy=str(payload.get("dominant_strategy", "")),
            attempt_self_score=float(payload.get("attempt_self_score", 0.0)),
            seek_help_score=float(payload.get("seek_help_score", 0.0)),
            avoid_score=float(payload.get("avoid_score", 0.0)),
            rule_weights=rule_weights,
            llm_weights=llm_weights,
            final_weights=final_weights,
        )


@dataclass(slots=True)
class StageInterviewResult:
    stage_name: str
    stage_index: int
    main_difficulty_source: str
    support_comment: str
    future_intention: str
    short_quote: str
    confidence: float = 0.0
    source: str = "rule"
    status: str = "not_called"
    raw_answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "StageInterviewResult":
        payload = payload or {}
        return cls(
            stage_name=str(payload.get("stage_name", "")),
            stage_index=int(payload.get("stage_index", 0)),
            main_difficulty_source=str(payload.get("main_difficulty_source", "")),
            support_comment=str(payload.get("support_comment", "")),
            future_intention=str(payload.get("future_intention", "")),
            short_quote=str(payload.get("short_quote", "")),
            confidence=float(payload.get("confidence", 0.0)),
            source=str(payload.get("source", "rule")),
            status=str(payload.get("status", "not_called")),
            raw_answer=str(payload.get("raw_answer", "")),
        )


@dataclass(slots=True)
class FinalInterviewResult:
    overall_trajectory: str
    main_barrier: str
    support_takeaway: str
    future_orientation: str
    short_quote: str
    confidence: float = 0.0
    source: str = "rule"
    status: str = "not_called"
    raw_answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FinalInterviewResult":
        payload = payload or {}
        return cls(
            overall_trajectory=str(payload.get("overall_trajectory", "")),
            main_barrier=str(payload.get("main_barrier", "")),
            support_takeaway=str(payload.get("support_takeaway", "")),
            future_orientation=str(payload.get("future_orientation", "")),
            short_quote=str(payload.get("short_quote", "")),
            confidence=float(payload.get("confidence", 0.0)),
            source=str(payload.get("source", "rule")),
            status=str(payload.get("status", "not_called")),
            raw_answer=str(payload.get("raw_answer", "")),
        )
