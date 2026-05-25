from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SupportStyle = Literal["enabling", "substituting", "dismissive", "unavailable"]

SUPPORT_STYLES = {"enabling", "substituting", "dismissive", "unavailable"}
INSTRUCTION_QUALITIES = {"none", "low", "medium", "high"}
AUTONOMY_PRESERVATION_LEVELS = {"low", "medium", "high", "not_applicable"}
PROXY_COMPLETION_LEVELS = {"none", "partial", "full", "not_applicable"}
EMOTIONAL_TONES = {"patient", "neutral", "dismissive", "not_applicable"}
RESPONSE_DELAYS = {"immediate", "delayed", "no_response"}

FORBIDDEN_SUPPORT_KEYS = {
    "outcome_type",
    "success",
    "success_label",
    "helplessness_delta",
    "helplessness_after",
    "final_helplessness_score",
    "posterior",
    "posterior_update_weight",
    "C_family",
    "scope_spillover_total",
}

SUPPORT_REQUEST_FIELDS = {
    "request_id",
    "requester_agent_id",
    "helper_agent_id",
    "day",
    "tick",
    "task_id",
    "task_family",
    "friction_type",
    "difficulty",
    "need_type",
    "support_sensitivity",
    "strategy_type",
    "support_need",
    "task_appraisal",
    "memory_context",
    "env_context",
    "profile_summary",
    "relationship",
}

SUPPORT_RESPONSE_FIELDS = {
    "request_id",
    "requester_agent_id",
    "helper_agent_id",
    "support_style",
    "instruction_quality",
    "autonomy_preservation",
    "proxy_completion_level",
    "emotional_tone",
    "response_delay",
    "confidence",
    "responded",
    "response_text",
    "rationale",
    "source",
    "audit_status",
}


def _clamp_unit(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc


def _assert_no_forbidden_keys(payload: Any, *, path: str = "") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            if key_text in FORBIDDEN_SUPPORT_KEYS:
                raise ValueError(f"forbidden support key: {path}{key_text}")
            _assert_no_forbidden_keys(value, path=f"{path}{key_text}.")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _assert_no_forbidden_keys(value, path=f"{path}{index}.")


def _validate_allowed_keys(payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError("unknown support protocol keys: " + ", ".join(sorted(unknown)))


def _require_non_empty(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if str(payload.get(field, "")).strip() == ""]
    if missing:
        raise ValueError("missing support protocol fields: " + ", ".join(missing))


def _validate_label(value: Any, allowed: set[str], field_name: str) -> str:
    label = str(value or "").strip().lower()
    if label not in allowed:
        raise ValueError(
            f"{field_name} must be one of: " + ", ".join(sorted(allowed))
        )
    return label


@dataclass(slots=True)
class SupportRequest:
    request_id: str
    requester_agent_id: int
    helper_agent_id: int | None
    day: int
    tick: float
    task_id: str
    task_family: str
    friction_type: str
    difficulty: float
    need_type: str
    support_sensitivity: float
    strategy_type: str = "seek_help_then_attempt"
    support_need: str = ""
    task_appraisal: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)
    env_context: dict[str, Any] = field(default_factory=dict)
    profile_summary: dict[str, Any] = field(default_factory=dict)
    relationship: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        payload = self.to_dict()
        _assert_no_forbidden_keys(payload)
        if self.strategy_type != "seek_help_then_attempt":
            raise ValueError("SupportRequest only supports seek_help_then_attempt")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SupportRequest":
        if not isinstance(payload, dict):
            raise ValueError("SupportRequest payload must be a dict")
        _assert_no_forbidden_keys(payload)
        _validate_allowed_keys(payload, SUPPORT_REQUEST_FIELDS)
        _require_non_empty(
            payload,
            ("request_id", "task_id", "task_family", "friction_type", "need_type"),
        )
        return cls(
            request_id=str(payload.get("request_id", "")),
            requester_agent_id=int(payload.get("requester_agent_id", -1)),
            helper_agent_id=(
                None
                if payload.get("helper_agent_id") in (None, "")
                else int(payload.get("helper_agent_id"))
            ),
            day=int(payload.get("day", 0)),
            tick=float(payload.get("tick", 0.0)),
            task_id=str(payload.get("task_id", "")),
            task_family=str(payload.get("task_family", "")),
            friction_type=str(payload.get("friction_type", "")),
            difficulty=float(payload.get("difficulty", 0.0)),
            need_type=str(payload.get("need_type", "")),
            support_sensitivity=float(payload.get("support_sensitivity", 0.0)),
            strategy_type=str(
                payload.get("strategy_type", "seek_help_then_attempt")
            ).strip(),
            support_need=str(payload.get("support_need", ""))[:300],
            task_appraisal=dict(payload.get("task_appraisal") or {}),
            memory_context=dict(payload.get("memory_context") or {}),
            env_context=dict(payload.get("env_context") or {}),
            profile_summary=dict(payload.get("profile_summary") or {}),
            relationship=dict(payload.get("relationship") or {}),
        )


@dataclass(slots=True)
class SupportResponse:
    request_id: str = ""
    requester_agent_id: int = -1
    helper_agent_id: int | None = None
    support_style: SupportStyle = "unavailable"
    instruction_quality: str = "none"
    autonomy_preservation: str = "not_applicable"
    proxy_completion_level: str = "not_applicable"
    emotional_tone: str = "not_applicable"
    response_delay: str = "no_response"
    confidence: float = 0.0
    responded: bool = False
    response_text: str = ""
    rationale: str = ""
    source: str = "not_called"
    audit_status: str = "not_called"

    def __post_init__(self) -> None:
        payload = self.to_dict()
        _assert_no_forbidden_keys(payload)
        self.support_style = _validate_label(
            self.support_style,
            SUPPORT_STYLES,
            "support_style",
        )  # type: ignore[assignment]
        self.instruction_quality = _validate_label(
            self.instruction_quality,
            INSTRUCTION_QUALITIES,
            "instruction_quality",
        )
        self.autonomy_preservation = _validate_label(
            self.autonomy_preservation,
            AUTONOMY_PRESERVATION_LEVELS,
            "autonomy_preservation",
        )
        self.proxy_completion_level = _validate_label(
            self.proxy_completion_level,
            PROXY_COMPLETION_LEVELS,
            "proxy_completion_level",
        )
        self.emotional_tone = _validate_label(
            self.emotional_tone,
            EMOTIONAL_TONES,
            "emotional_tone",
        )
        self.response_delay = _validate_label(
            self.response_delay,
            RESPONSE_DELAYS,
            "response_delay",
        )
        self.confidence = _clamp_unit(self.confidence)
        if self.support_style == "unavailable":
            self.responded = False
            self.instruction_quality = "none"
            self.autonomy_preservation = "not_applicable"
            self.proxy_completion_level = "not_applicable"
            self.response_delay = "no_response"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SupportResponse":
        if not isinstance(payload, dict):
            raise ValueError("SupportResponse payload must be a dict")
        _assert_no_forbidden_keys(payload)
        _validate_allowed_keys(payload, SUPPORT_RESPONSE_FIELDS)
        return cls(
            request_id=str(payload.get("request_id", "")),
            requester_agent_id=int(payload.get("requester_agent_id", -1)),
            helper_agent_id=(
                None
                if payload.get("helper_agent_id") in (None, "")
                else int(payload.get("helper_agent_id"))
            ),
            support_style=str(payload.get("support_style", "unavailable")),  # type: ignore[arg-type]
            instruction_quality=str(payload.get("instruction_quality", "none")),
            autonomy_preservation=str(
                payload.get("autonomy_preservation", "not_applicable")
            ),
            proxy_completion_level=str(
                payload.get("proxy_completion_level", "not_applicable")
            ),
            emotional_tone=str(payload.get("emotional_tone", "not_applicable")),
            response_delay=str(payload.get("response_delay", "no_response")),
            confidence=float(payload.get("confidence", 0.0)),
            responded=bool(payload.get("responded", False)),
            response_text=str(payload.get("response_text", ""))[:800],
            rationale=str(payload.get("rationale", ""))[:300],
            source=str(payload.get("source", "unknown")),
            audit_status=str(payload.get("audit_status", "unknown")),
        )

    @classmethod
    def from_llm_payload(
        cls,
        *,
        request: SupportRequest,
        payload: dict[str, Any],
        source: str,
        audit_status: str,
    ) -> "SupportResponse":
        merged = {
            "request_id": request.request_id,
            "requester_agent_id": request.requester_agent_id,
            "helper_agent_id": request.helper_agent_id,
            "source": source,
            "audit_status": audit_status,
            **payload,
        }
        return cls.from_dict(merged)

    @classmethod
    def unavailable(
        cls,
        *,
        request: SupportRequest | None = None,
        source: str = "llm_unavailable",
        audit_status: str = "request_error",
        rationale: str = "",
    ) -> "SupportResponse":
        return cls(
            request_id=request.request_id if request is not None else "",
            requester_agent_id=(
                request.requester_agent_id if request is not None else -1
            ),
            helper_agent_id=request.helper_agent_id if request is not None else None,
            support_style="unavailable",
            instruction_quality="none",
            autonomy_preservation="not_applicable",
            proxy_completion_level="not_applicable",
            emotional_tone="not_applicable",
            response_delay="no_response",
            confidence=0.0,
            responded=False,
            response_text="",
            rationale=rationale[:300],
            source=source,
            audit_status=audit_status,
        )


def support_style_to_support_mode(style: str) -> str:
    style = str(style or "").strip().lower()
    if style == "enabling":
        return "enabling_support"
    if style in {"substituting", "dismissive"}:
        return "substituting_support"
    return "not_applicable"
