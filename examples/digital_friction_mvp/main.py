import asyncio
import copy
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from agentsociety.cityagent import (
    EconomyBlock,
    EconomyBlockParams,
    MobilityBlock,
    MobilityBlockParams,
    OtherBlock,
    OtherBlockParams,
    SocialBlock,
    SocialBlockParams,
    SocietyAgent,
    SocietyAgentConfig,
    default,
)
from agentsociety.cityagent.memory_config import (
    DEFAULT_DISTRIBUTIONS,
    memory_config_societyagent,
)
from agentsociety.configs import (
    AgentsConfig,
    Config,
    EnvConfig,
    ExpConfig,
    LLMConfig,
    MapConfig,
)
from agentsociety.configs.agent import AgentConfig
from agentsociety.configs.exp import AgentFilterConfig, WorkflowStepConfig, WorkflowType
from agentsociety.environment import EnvironmentConfig
from agentsociety.llm import LLMProviderType
from agentsociety.simulation import AgentSociety
from agentsociety.storage import DatabaseConfig

from config_runtime import load_runtime_config
from persistence import (
    append_stage_explanation_csv,
    ensure_stage_explanation_table,
    stage_explanation_table_name,
    write_stage_explanation_rows,
)
from proto.agent import DigitalHelplessnessAgent
from proto.logical_clock import (
    enable_proto_logical_clock,
    is_proto_logical_clock_enabled,
)
from proto.metrics import (
    attempt_rows_table_name,
    ensure_attempt_rows_table,
    ensure_stage_summary_table,
    stage_summary_table_name,
    summarize_stage_attempts,
    write_attempt_rows,
    write_stage_summary_rows,
)
from proto.models import FinalInterviewResult, StageInterviewResult
from proto.state_schema import (
    build_initial_proto_status,
    build_survey_measurement_updates,
)
from signal_extraction import summarize_stage_explanations
from surveys import tech_acceptance_survey


EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parent.parent
DEFAULT_MAP_PATH = REPO_ROOT / "agentsociety_data" / "beijing.pb"
PROFILES_PATH = Path(
    os.getenv("DIGITAL_FRICTION_PROFILES_PATH", str(EXAMPLE_DIR / "profiles.json"))
)
MAP_FILE_PATH = os.getenv("MAP_FILE_PATH", str(DEFAULT_MAP_PATH))
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("ZHIPUAI_API_KEY") or "<YOUR-API-KEY>"
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flashx")
AGENT_COUNT = int(os.getenv("AGENT_COUNT", "10"))
AGENT_PLAN_PROMPT_PROFILE = os.getenv("AGENT_PLAN_PROMPT_PROFILE", "off").strip().lower()
EXP_SEED = int(os.getenv("EXP_SEED", "101"))
RNG = random.Random(EXP_SEED)
LOGGER = logging.getLogger("agentsociety")

WORLD_PRESETS = {
    "baseline_low_friction": {
        "friction_level": 1,
        "malicious_friction_level": 1,
        "complexity_level": 1,
        "risk_level": 1,
        "assist_level": 1,
        "accessibility_level": 1,
        "human_support_level": 1,
    },
    "high_friction_low_assist": {
        "friction_level": 3,
        "malicious_friction_level": 3,
        "complexity_level": 3,
        "risk_level": 3,
        "assist_level": 0,
        "accessibility_level": 0,
        "human_support_level": 0,
    },
    "high_friction_high_assist": {
        "friction_level": 3,
        "malicious_friction_level": 3,
        "complexity_level": 3,
        "risk_level": 3,
        "assist_level": 3,
        "accessibility_level": 3,
        "human_support_level": 3,
    },
    "low_friction_high_assist": {
        "friction_level": 0,
        "malicious_friction_level": 0,
        "complexity_level": 0,
        "risk_level": 1,
        "assist_level": 3,
        "accessibility_level": 3,
        "human_support_level": 3,
    },
}
WORLD_NAME = os.getenv("WORLD_NAME", "baseline_low_friction")
if WORLD_NAME not in WORLD_PRESETS:
    raise ValueError(
        f"Invalid WORLD_NAME={WORLD_NAME}. Expected one of: {sorted(WORLD_PRESETS.keys())}"
    )

DEFAULT_STAGE_PLAN = [
    {"name": "steady", "delta": {}},
    {
        "name": "shock",
        "delta": {
            "friction_level": 1,
            "malicious_friction_level": 1,
            "complexity_level": 1,
            "risk_level": 1,
            "assist_level": -1,
            "accessibility_level": -1,
            "human_support_level": -1,
        },
    },
    {
        "name": "recovery",
        "delta": {
            "assist_level": 1,
            "accessibility_level": 1,
            "human_support_level": 1,
        },
    },
]
STAGE_MODE = os.getenv("STAGE_MODE", "full").strip().lower()
if STAGE_MODE == "single":
    stage_single_name = os.getenv("STAGE_SINGLE_NAME", "steady").strip().lower()
    stage_lookup = {
        str(stage_cfg.get("name", "")).strip().lower(): stage_cfg
        for stage_cfg in DEFAULT_STAGE_PLAN
    }
    if stage_single_name not in stage_lookup:
        raise ValueError(
            "Invalid STAGE_SINGLE_NAME="
            f"{stage_single_name}. Expected one of: {sorted(stage_lookup.keys())}"
        )
    STAGE_PLAN = [copy.deepcopy(stage_lookup[stage_single_name])]
elif STAGE_MODE == "full":
    STAGE_PLAN = copy.deepcopy(DEFAULT_STAGE_PLAN)
else:
    raise ValueError("STAGE_MODE must be one of: full, single")

STAGE_DAYS = int(os.getenv("STAGE_DAYS", "4"))
_STAGE_NAME_TO_INDEX = {
    str(stage_cfg.get("name", f"stage_{idx + 1}")).strip(): idx
    for idx, stage_cfg in enumerate(STAGE_PLAN)
}
EVENT_DECISION_INTERVAL_MINUTES = max(
    1, int(os.getenv("EVENT_DECISION_INTERVAL_MINUTES", "15"))
)
if (24 * 60) % EVENT_DECISION_INTERVAL_MINUTES != 0:
    raise ValueError(
        "EVENT_DECISION_INTERVAL_MINUTES must divide 1440 exactly "
        "(e.g., 5, 10, 15, 20, 30, 60)"
    )
EVENT_DECISION_INTERVAL_TICKS = EVENT_DECISION_INTERVAL_MINUTES * 60
DECISION_INTERVALS_PER_DAY = int((24 * 60) / EVENT_DECISION_INTERVAL_MINUTES)

_LEVEL_KEYS = [
    "friction_level",
    "malicious_friction_level",
    "complexity_level",
    "risk_level",
    "assist_level",
    "accessibility_level",
    "human_support_level",
]

BASE_WORLD_ENV = WORLD_PRESETS[WORLD_NAME]
EXP_NAME = os.getenv("EXP_NAME", f"digital_friction_mvp_{WORLD_NAME}_seed{EXP_SEED}")
EXP_MODE = os.getenv("EXP_MODE", "normal").strip().lower()
EXPERIMENT_ENGINE = os.getenv("EXPERIMENT_ENGINE", "proto").strip().lower()
if EXPERIMENT_ENGINE not in {"proto", "legacy"}:
    raise ValueError("EXPERIMENT_ENGINE must be one of: proto, legacy")
RUNTIME_CONFIG = load_runtime_config()
EXPERIMENT_MODE = RUNTIME_CONFIG.experiment_mode
WORLD_BATCH = RUNTIME_CONFIG.world_batch
PARALLEL_GROUP_NAME = RUNTIME_CONFIG.parallel_group_name
RUN_METADATA_PATH = os.getenv("RUN_METADATA_PATH", "").strip()
CLOSE_TIMEOUT_SECONDS = max(0, int(os.getenv("CLOSE_TIMEOUT_SECONDS", "90")))
CLOSE_TIMEOUT_CANCEL_WAIT_SECONDS = max(
    1, int(os.getenv("CLOSE_TIMEOUT_CANCEL_WAIT_SECONDS", "5"))
)
RAY_SHUTDOWN_ON_FINISH = (
    os.getenv("RAY_SHUTDOWN_ON_FINISH", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
PARALLEL_FORCE_EXIT_ON_FINISH = (
    os.getenv("PARALLEL_FORCE_EXIT_ON_FINISH", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
PROTO_LOGICAL_CLOCK_ENABLED = (
    os.getenv("PROTO_LOGICAL_CLOCK_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
try:
    PARALLEL_PAIR_INDEX = int(os.getenv("PARALLEL_PAIR_INDEX", "-1"))
except ValueError:
    PARALLEL_PAIR_INDEX = -1
try:
    PARALLEL_PAIR_SEED = int(os.getenv("PARALLEL_PAIR_SEED", str(EXP_SEED)))
except ValueError:
    PARALLEL_PAIR_SEED = int(EXP_SEED)
try:
    PARALLEL_WORLD_ORDER = int(os.getenv("PARALLEL_WORLD_ORDER", "-1"))
except ValueError:
    PARALLEL_WORLD_ORDER = -1
PARALLEL_CONFIG_FINGERPRINT = os.getenv("PARALLEL_CONFIG_FINGERPRINT", "").strip()
STATUS_TABLE_SUFFIX = "mvp_status"
_STATUS_TABLE_CREATED: set[str] = set()
_PROFILE_INDEX: dict[int, dict[str, Any]] = {}
_PROFILE_INDEX_BY_NAME: dict[str, dict[str, Any]] = {}
_PROFILE_LIST: list[dict[str, Any]] = []
_LAST_SURVEY_SYNC_CURSOR: tuple[int, float, int] | None = None
_LAST_INTERVIEW_SYNC_ROWID: int | None = None
_STAGE_INTERVIEW_PREFIX = "[PROTO_STAGE_INTERVIEW_V1]"
_FINAL_INTERVIEW_PREFIX = "[PROTO_FINAL_INTERVIEW_V1]"
_STAGE_INTERVIEW_PATTERN = re.compile(
    r"^\[PROTO_STAGE_INTERVIEW_V1\]\[stage=(?P<stage_name>[^\]]+)\]\[index=(?P<stage_index>\d+)\]"
)
SMOKE_MODE_ENABLED = EXP_MODE in {"smoke", "debug_smoke", "stress"}
EVENT_MIN_STAGE_EVENT_FORCE_TOTAL_PROB = max(
    0.0,
    min(0.95, float(os.getenv("EVENT_MIN_STAGE_EVENT_FORCE_TOTAL_PROB", "0.7"))),
)
EVENT_OVEREXPOSED_GAP = max(0, int(os.getenv("EVENT_OVEREXPOSED_GAP", "1")))
EVENT_OVEREXPOSED_SCALE = max(
    0.1,
    min(1.0, float(os.getenv("EVENT_OVEREXPOSED_SCALE", "0.65"))),
)
EVENT_UNDEREXPOSED_GAP = max(0, int(os.getenv("EVENT_UNDEREXPOSED_GAP", "1")))
EVENT_UNDEREXPOSED_SCALE = max(
    1.0,
    min(2.5, float(os.getenv("EVENT_UNDEREXPOSED_SCALE", "1.25"))),
)
MOBILITY_NUDGE_PROB = max(
    0.0, min(1.0, float(os.getenv("MOBILITY_NUDGE_PROB", "0.15")))
)
MOBILITY_NUDGE_START_HOUR = int(os.getenv("MOBILITY_NUDGE_START_HOUR", "8"))
MOBILITY_NUDGE_END_HOUR = int(os.getenv("MOBILITY_NUDGE_END_HOUR", "20"))
MOBILITY_NUDGE_PENDING_MAX_HOURS = max(
    1, int(os.getenv("MOBILITY_NUDGE_PENDING_MAX_HOURS", "6"))
)
ECONOMY_BLOCK_ENABLED = (
    os.getenv("ECONOMY_BLOCK_ENABLED", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
ECONOMY_BINDING_AUDIT_STRICT = (
    os.getenv("ECONOMY_BINDING_AUDIT_STRICT", "0").strip().lower()
    not in {"0", "false", "no", "off"}
)
SURVEY_FIELDS = (
    "tech_acceptance",
    "trust_in_apps",
    "avoidance_tendency",
    "helpless_control_loss",
    "helpless_expect_failure",
    "helpless_effort_futile",
    "helpless_low_self_efficacy",
    "behavior_delay_online",
    "behavior_proxy_reliance",
    "behavior_offline_switch",
    "digital_self_efficacy",
    "perceived_effective_support",
    "perceived_usefulness",
    "digital_anxiety",
)
SURVEY_HELPLESS_FIELDS = (
    "helpless_control_loss",
    "helpless_expect_failure",
    "helpless_effort_futile",
    "helpless_low_self_efficacy",
)
SURVEY_WITHDRAWAL_FIELDS = (
    "behavior_delay_online",
    "behavior_proxy_reliance",
    "behavior_offline_switch",
)


def _load_profile_index() -> dict[int, dict[str, Any]]:
    global _PROFILE_INDEX, _PROFILE_INDEX_BY_NAME, _PROFILE_LIST
    if _PROFILE_INDEX or _PROFILE_LIST:
        return _PROFILE_INDEX
    try:
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        if isinstance(profiles, list):
            _PROFILE_LIST = [p for p in profiles if isinstance(p, dict)]
        else:
            _PROFILE_LIST = []
        _PROFILE_INDEX = {
            int(p["id"]): p
            for p in _PROFILE_LIST
            if "id" in p and str(p.get("id")).strip() != ""
        }
        _PROFILE_INDEX_BY_NAME = {
            _clean_intention(p.get("name")).lower(): p
            for p in _PROFILE_LIST
            if _clean_intention(p.get("name"))
        }
    except FileNotFoundError:
        _PROFILE_INDEX = {}
        _PROFILE_INDEX_BY_NAME = {}
        _PROFILE_LIST = []
    return _PROFILE_INDEX


def _resolve_profile_for_agent(
    agent_id: int,
    agent_name: str = "",
    ordered_agent_ids: list[int] | None = None,
) -> dict[str, Any]:
    _load_profile_index()
    if agent_id in _PROFILE_INDEX:
        return _PROFILE_INDEX[agent_id]
    normalized_name = _clean_intention(agent_name).lower()
    if normalized_name and normalized_name in _PROFILE_INDEX_BY_NAME:
        return _PROFILE_INDEX_BY_NAME[normalized_name]
    if ordered_agent_ids and _PROFILE_LIST:
        try:
            position = ordered_agent_ids.index(agent_id)
        except ValueError:
            position = -1
        if 0 <= position < len(_PROFILE_LIST):
            return _PROFILE_LIST[position]
    return {}


async def _safe_gather_status(
    simulation: AgentSociety,
    key: str,
    agent_ids: list[int],
) -> dict[int, Any]:
    try:
        values = await simulation.gather(key, agent_ids, keep_id=True)
        if isinstance(values, dict):
            return values
    except KeyError:
        pass
    return {agent_id: None for agent_id in agent_ids}


def _resolve_stage_env(stage_cfg: dict[str, Any]) -> dict[str, Any]:
    stage_name = str(stage_cfg.get("name", "stage"))
    delta = stage_cfg.get("delta", {}) or {}
    env: dict[str, Any] = {
        "digital_stage": f"{WORLD_NAME}:{stage_name}",
        "world_name": WORLD_NAME,
        "stage_name": stage_name,
    }
    for key in _LEVEL_KEYS:
        base_value = _level(BASE_WORLD_ENV, key)
        delta_value = _level(delta, key)
        env[key] = max(0, min(3, base_value + delta_value))
    return env
def _clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def _level(env: dict[str, Any], key: str) -> int:
    value = env.get(key, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean_intention(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _is_empty_intention(value: str) -> bool:
    lowered = value.lower().strip()
    return lowered in {"", "planning", "i am doing nothing", "none", "n/a", "unknown"}


def _decode_json_object_list(raw_value: Any) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        payload = raw_value
    elif isinstance(raw_value, str):
        raw_text = raw_value.strip()
        if not raw_text:
            return []
        try:
            payload = json.loads(raw_text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    else:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _normalize_aoi_position(
    raw_value: Any,
    valid_aoi_ids: set[int],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        aoi_position = raw_value.get("aoi_position", {})
        if isinstance(aoi_position, dict):
            aoi_id = aoi_position.get("aoi_id")
            try:
                aoi_id = int(aoi_id)
            except (TypeError, ValueError):
                aoi_id = None
            if aoi_id is not None and (not valid_aoi_ids or aoi_id in valid_aoi_ids):
                return {"aoi_position": {"aoi_id": aoi_id}}
    try:
        raw_id = int(raw_value)
    except (TypeError, ValueError):
        raw_id = None
    if raw_id is not None and (not valid_aoi_ids or raw_id in valid_aoi_ids):
        return {"aoi_position": {"aoi_id": raw_id}}
    return fallback


def _extract_survey_result_values(payload: Any) -> dict[str, float]:
    def _get_case_insensitive(item: dict[str, Any], key: str) -> Any:
        if key in item:
            return item.get(key)
        lowered = key.lower()
        for k, v in item.items():
            if str(k).lower() == lowered:
                return v
        return None

    parsed: Any = payload
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            parsed = None
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            parsed = None
    values: dict[str, float] = {}
    entries: list[Any]
    if isinstance(parsed, list):
        entries = list(parsed)
    elif isinstance(parsed, dict):
        entries = [parsed]
    else:
        return values

    for idx, entry in enumerate(entries):
        item = entry
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError:
                item = item.strip()
        if isinstance(item, dict):
            key = _clean_intention(
                _get_case_insensitive(item, "name")
                or _get_case_insensitive(item, "key")
            ).lower()
            raw_value = _get_case_insensitive(item, "answer")
            if raw_value is None:
                raw_value = _get_case_insensitive(item, "rating")
            if raw_value is None:
                raw_value = _get_case_insensitive(item, "value")
            if raw_value is None:
                raw_value = _get_case_insensitive(item, "response")
            if raw_value is None:
                raw_value = _get_case_insensitive(item, "score")
            if key in SURVEY_FIELDS and raw_value is not None:
                values[key] = _clamp(_safe_float(raw_value, 0.0), 0.0, 100.0)
                continue
            for field in SURVEY_FIELDS:
                field_value = _get_case_insensitive(item, field)
                if field_value is not None:
                    values[field] = _clamp(_safe_float(field_value, 0.0), 0.0, 100.0)
            if raw_value is not None and idx < len(SURVEY_FIELDS):
                values.setdefault(
                    SURVEY_FIELDS[idx], _clamp(_safe_float(raw_value, 0.0), 0.0, 100.0)
                )
            continue
        if idx < len(SURVEY_FIELDS):
            values[SURVEY_FIELDS[idx]] = _clamp(_safe_float(item, 0.0), 0.0, 100.0)
    return values


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _average_survey_fields(values: dict[str, float], fields: tuple[str, ...]) -> float | None:
    bucket: list[float] = []
    for field in fields:
        if field in values:
            bucket.append(_clamp(_safe_float(values.get(field), 0.0), 0.0, 100.0))
    if not bucket:
        return None
    return float(sum(bucket) / len(bucket))


def _derive_survey_indices(values: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    helplessness_index = _average_survey_fields(values, SURVEY_HELPLESS_FIELDS)
    withdrawal_index = _average_survey_fields(values, SURVEY_WITHDRAWAL_FIELDS)
    if helplessness_index is not None:
        result["survey_helplessness_index"] = helplessness_index
    if withdrawal_index is not None:
        result["survey_withdrawal_index"] = withdrawal_index
    for field in SURVEY_WITHDRAWAL_FIELDS:
        if field in values:
            result[field] = _clamp(_safe_float(values[field], 0.0), 0.0, 100.0)
    if "digital_self_efficacy" in values:
        result["survey_self_efficacy_index"] = _clamp(
            _safe_float(values["digital_self_efficacy"], 0.0),
            0.0,
            100.0,
        )
    if "perceived_effective_support" in values:
        result["survey_support_index"] = _clamp(
            _safe_float(values["perceived_effective_support"], 0.0),
            0.0,
            100.0,
        )
    if "perceived_usefulness" in values:
        result["survey_usefulness_index"] = _clamp(
            _safe_float(values["perceived_usefulness"], 0.0),
            0.0,
            100.0,
        )
    if "digital_anxiety" in values:
        result["survey_anxiety_index"] = _clamp(
            _safe_float(values["digital_anxiety"], 0.0),
            0.0,
            100.0,
        )
    return result


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _clean_intention(value).lower()
    if text in {
        "true",
        "1",
        "yes",
        "ok",
        "success",
        "succeeded",
        "passed",
        "完成",
        "成功",
        "顺利",
    }:
        return True
    if text in {
        "false",
        "0",
        "no",
        "fail",
        "failed",
        "error",
        "失败",
        "错误",
        "卡住",
    }:
        return False
    return None


def _extract_json_object(raw_text: Any) -> dict[str, Any] | None:
    text = _clean_intention(raw_text)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


def _build_stage_interview_message(stage_name: str, stage_index: int) -> str:
    return (
        f"{_STAGE_INTERVIEW_PREFIX}[stage={stage_name}][index={int(stage_index)}] "
        "请你只返回一段 JSON，概括这一阶段里你最难的地方、帮助是否有用，以及接下来更想自己试、求助还是回避。"
    )


def _build_final_interview_message() -> str:
    return (
        f"{_FINAL_INTERVIEW_PREFIX} "
        "请你只返回一段 JSON，总结整个实验里的变化轨迹、主要障碍、帮助体验，以及未来面对数字任务时的总体倾向。"
    )


def _parse_stage_interview_payload(
    payload: dict[str, Any] | None,
    *,
    stage_name: str,
    stage_index: int,
    raw_answer: str,
) -> StageInterviewResult:
    payload = payload or {}
    main_difficulty_source = _clean_intention(payload.get("main_difficulty_source"))
    support_comment = _clean_intention(payload.get("support_comment"))
    future_intention = _clean_intention(payload.get("future_intention"))
    short_quote = _clean_intention(payload.get("short_quote"))[:120]
    confidence = _clamp(
        _safe_float(payload.get("judge_confidence", payload.get("confidence", 0.0)), 0.0),
        0.0,
        1.0,
    )
    valid = (
        main_difficulty_source
        in {
            "verification_friction",
            "form_complexity",
            "risk_concern",
            "info_overload",
            "low_control",
            "mixed",
        }
        and support_comment in {"helpful", "limited", "ineffective", "not_used"}
        and future_intention in {"try_self", "seek_help", "avoid", "mixed"}
        and bool(short_quote)
    )
    if not valid:
        return StageInterviewResult(
            stage_name=stage_name,
            stage_index=int(stage_index),
            main_difficulty_source="",
            support_comment="",
            future_intention="",
            short_quote="",
            confidence=0.0,
            source="stored_raw",
            status="parse_failed",
            raw_answer=_clean_intention(raw_answer)[:600],
        )
    return StageInterviewResult(
        stage_name=stage_name,
        stage_index=int(stage_index),
        main_difficulty_source=main_difficulty_source,
        support_comment=support_comment,
        future_intention=future_intention,
        short_quote=short_quote,
        confidence=confidence,
        source=_clean_intention(payload.get("source")) or "llm",
        status=_clean_intention(payload.get("status")) or "ok",
        raw_answer="",
    )


def _parse_final_interview_payload(
    payload: dict[str, Any] | None,
    *,
    raw_answer: str,
) -> FinalInterviewResult:
    payload = payload or {}
    overall_trajectory = _clean_intention(payload.get("overall_trajectory"))
    main_barrier = _clean_intention(payload.get("main_barrier"))
    support_takeaway = _clean_intention(payload.get("support_takeaway"))
    future_orientation = _clean_intention(payload.get("future_orientation"))
    short_quote = _clean_intention(payload.get("short_quote"))[:120]
    confidence = _clamp(
        _safe_float(payload.get("judge_confidence", payload.get("confidence", 0.0)), 0.0),
        0.0,
        1.0,
    )
    valid = (
        overall_trajectory in {"improved", "worsened", "mixed", "stable"}
        and main_barrier
        in {
            "verification_friction",
            "form_complexity",
            "risk_concern",
            "info_overload",
            "low_control",
            "mixed",
        }
        and support_takeaway in {"helpful", "limited", "ineffective", "not_needed"}
        and future_orientation in {"try_self", "seek_help", "avoid", "mixed"}
        and bool(short_quote)
    )
    if not valid:
        return FinalInterviewResult(
            overall_trajectory="",
            main_barrier="",
            support_takeaway="",
            future_orientation="",
            short_quote="",
            confidence=0.0,
            source="stored_raw",
            status="parse_failed",
            raw_answer=_clean_intention(raw_answer)[:600],
        )
    return FinalInterviewResult(
        overall_trajectory=overall_trajectory,
        main_barrier=main_barrier,
        support_takeaway=support_takeaway,
        future_orientation=future_orientation,
        short_quote=short_quote,
        confidence=confidence,
        source=_clean_intention(payload.get("source")) or "llm",
        status=_clean_intention(payload.get("status")) or "ok",
        raw_answer="",
    )


def _extract_step_evaluation_signal(plan: Any) -> dict[str, Any]:
    signal: dict[str, Any] = {
        "step_type": "",
        "step_intention": "",
        "status_text": "",
        "step_success": None,
        "step_outcome": "unknown",
        "step_consumed_time": 0.0,
        "step_eval_text": "",
        "failure_pressure": 0.0,
        "success_support": 0.0,
        "effort_bucket": "unknown",
    }
    if not isinstance(plan, dict):
        return signal
    steps = plan.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return signal
    index = plan.get("index", 0)
    if not isinstance(index, int):
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0
    if index < 0 or index >= len(steps):
        return signal
    current_step = steps[index]
    if not isinstance(current_step, dict):
        return signal

    signal["step_type"] = _clean_intention(current_step.get("type", ""))
    signal["step_intention"] = _clean_intention(current_step.get("intention", ""))

    evaluation = current_step.get("evaluation", {})
    success_value: bool | None = None
    consumed_time = 0.0
    eval_text = ""
    if isinstance(evaluation, dict):
        success_value = _coerce_bool(evaluation.get("success"))
        consumed_time = max(0.0, _safe_float(evaluation.get("consumed_time"), 0.0))
        eval_text = _clean_intention(evaluation.get("evaluation", ""))
    elif evaluation is not None:
        eval_text = _clean_intention(evaluation)

    if success_value is None and eval_text:
        lowered = eval_text.lower()
        failure_keywords = [
            "fail",
            "error",
            "stuck",
            "unable",
            "couldn't",
            "cannot",
            "失败",
            "错误",
            "卡住",
            "无助",
        ]
        success_keywords = [
            "success",
            "completed",
            "done",
            "resolved",
            "成功",
            "完成",
            "顺利",
        ]
        if any(word in lowered for word in failure_keywords):
            success_value = False
        elif any(word in lowered for word in success_keywords):
            success_value = True

    failure_pressure = 0.0
    success_support = 0.0
    if success_value is False:
        failure_pressure += 1.0
    elif success_value is True:
        success_support += 1.0
    if consumed_time >= 90:
        failure_pressure += 0.5
    elif consumed_time >= 45:
        failure_pressure += 0.25
    elif consumed_time > 0 and consumed_time <= 15 and success_value is True:
        success_support += 0.25

    if success_value is True:
        step_outcome = "success"
    elif success_value is False:
        step_outcome = "failure"
    else:
        step_outcome = "unknown"

    if consumed_time >= 90:
        effort_bucket = "high"
    elif consumed_time >= 45:
        effort_bucket = "mid"
    elif consumed_time > 0:
        effort_bucket = "low"
    else:
        effort_bucket = "unknown"

    signal.update(
        {
            "step_success": success_value,
            "step_outcome": step_outcome,
            "step_consumed_time": consumed_time,
            "step_eval_text": eval_text[:180],
            "failure_pressure": failure_pressure,
            "success_support": success_support,
            "effort_bucket": effort_bucket,
        }
    )
    return signal


async def _record_stage_summary_memory(
    simulation: AgentSociety,
    agent_id: int,
    stage_name: str,
    summary_text: str,
) -> None:
    agent_map = getattr(simulation, "_id2agent", {})
    agent = agent_map.get(agent_id)
    if agent is None or not hasattr(agent, "memory"):
        return
    description = _clean_intention(summary_text)
    if not description:
        return
    try:
        await agent.memory.stream.add(
            topic="digital_friction_stage_summary",
            description=f"[{stage_name}] {description[:600]}",
        )
    except Exception:
        return


def _status_table_name(exp_id: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_{STATUS_TABLE_SUFFIX}"


def _ensure_status_table(db_path: Path, table_name: str) -> None:
    if table_name in _STATUS_TABLE_CREATED:
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            agent_id INTEGER,
            day INTEGER,
            t REAL,
            intention TEXT,
            helplessness_score REAL,
            trust_in_apps REAL,
            avoidance_tendency REAL,
            negative_event_count INTEGER,
            intercept_count INTEGER,
            help_request_count INTEGER,
            success_count INTEGER,
            failure_count INTEGER,
            status_json TEXT
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_time ON {table_name} (day, t)"
    )
    conn.commit()
    conn.close()
    _STATUS_TABLE_CREATED.add(table_name)


async def log_step_status(simulation: AgentSociety):
    db_writer = getattr(simulation, "_database_writer", None)
    if db_writer is None:
        return
    sqlite_path = getattr(db_writer, "_sqlite_path", None)
    if sqlite_path is None:
        return
    table_name = _status_table_name(db_writer.exp_id)
    _ensure_status_table(Path(sqlite_path), table_name)

    citizen_ids = await simulation.filter(types=EXPERIMENT_AGENT_CLASSES)
    if not citizen_ids:
        return
    day, t = simulation.environment.get_datetime()
    intention_map = await simulation.gather(
        "current_intention", citizen_ids, keep_id=True
    )
    helplessness_map = await simulation.gather(
        "helplessness_score", citizen_ids, keep_id=True
    )
    trust_map = await simulation.gather(
        "trust_in_apps", citizen_ids, keep_id=True
    )
    avoidance_map = await simulation.gather(
        "avoidance_tendency", citizen_ids, keep_id=True
    )
    negative_count_map = await simulation.gather(
        "negative_event_count", citizen_ids, keep_id=True
    )
    intercept_count_map = await simulation.gather(
        "intercept_count", citizen_ids, keep_id=True
    )
    help_count_map = await simulation.gather(
        "help_request_count", citizen_ids, keep_id=True
    )
    success_count_map = await simulation.gather(
        "success_count", citizen_ids, keep_id=True
    )
    failure_count_map = await simulation.gather(
        "failure_count", citizen_ids, keep_id=True
    )
    friction_step_signal_map = await _safe_gather_status(
        simulation, "friction_step_signal", citizen_ids
    )
    mobile_entry_decision_map = await _safe_gather_status(
        simulation, "proto_mobile_entry_decision", citizen_ids
    )
    logical_clock_enabled = is_proto_logical_clock_enabled(simulation.environment)
    if logical_clock_enabled:
        trip_count_map = {}
        travel_distance_map = {}
        travel_time_map = {}
    else:
        trip_count_map = await _safe_gather_status(
            simulation, "num_completed_trips", citizen_ids
        )
        travel_distance_map = await _safe_gather_status(
            simulation, "total_travel_distance", citizen_ids
        )
        travel_time_map = await _safe_gather_status(
            simulation, "total_travel_time", citizen_ids
        )
    survey_helplessness_map = await _safe_gather_status(
        simulation, "survey_helplessness_index", citizen_ids
    )
    survey_withdrawal_map = await _safe_gather_status(
        simulation, "survey_withdrawal_index", citizen_ids
    )
    survey_self_efficacy_map = await _safe_gather_status(
        simulation, "survey_self_efficacy_index", citizen_ids
    )
    survey_anxiety_map = await _safe_gather_status(
        simulation, "survey_anxiety_index", citizen_ids
    )
    survey_support_map = await _safe_gather_status(
        simulation, "survey_support_index", citizen_ids
    )
    survey_usefulness_map = await _safe_gather_status(
        simulation, "survey_usefulness_index", citizen_ids
    )
    behavior_delay_map = await _safe_gather_status(
        simulation, "behavior_delay_online", citizen_ids
    )
    behavior_proxy_map = await _safe_gather_status(
        simulation, "behavior_proxy_reliance", citizen_ids
    )
    behavior_offline_map = await _safe_gather_status(
        simulation, "behavior_offline_switch", citizen_ids
    )
    stage = _clean_intention(simulation.environment.environment.get("digital_stage"))
    if not stage:
        stage = f"{WORLD_NAME}:bootstrap"

    rows = []
    helplessness_values = []
    trust_values = []
    avoidance_values = []
    negative_values = []
    intercept_values = []
    help_values = []
    success_values = []
    failure_values = []
    trip_values = []
    distance_values = []
    travel_time_values = []
    survey_helplessness_values = []
    survey_withdrawal_values = []
    survey_self_efficacy_values = []
    survey_anxiety_values = []
    survey_support_values = []
    survey_usefulness_values = []
    behavior_delay_values = []
    behavior_proxy_values = []
    behavior_offline_values = []
    reflection_count_values = []
    anxiety_values = []
    confidence_values = []
    emotion_map = await _safe_gather_status(
        simulation, "digital_emotion_state", citizen_ids
    )
    reflection_count_map = await _safe_gather_status(
        simulation, "proto_stage_daily_reflection_count", citizen_ids
    )
    for agent_id in citizen_ids:
        intention = _clean_intention(intention_map.get(agent_id, ""))
        if logical_clock_enabled:
            trip_count = 0
            travel_distance = 0.0
            travel_time = 0.0
        else:
            trip_count = int(_safe_float(trip_count_map.get(agent_id, 0), 0))
            travel_distance = _safe_float(travel_distance_map.get(agent_id, 0.0), 0.0)
            travel_time = _safe_float(travel_time_map.get(agent_id, 0.0), 0.0)
        survey_helplessness = _clamp(
            _safe_float(survey_helplessness_map.get(agent_id), 0.0), 0.0, 100.0
        )
        survey_withdrawal = _clamp(
            _safe_float(survey_withdrawal_map.get(agent_id), 0.0), 0.0, 100.0
        )
        survey_self_efficacy = _clamp(
            _safe_float(survey_self_efficacy_map.get(agent_id), 0.0), 0.0, 100.0
        )
        survey_anxiety = _clamp(
            _safe_float(survey_anxiety_map.get(agent_id), 0.0), 0.0, 100.0
        )
        survey_support = _clamp(
            _safe_float(survey_support_map.get(agent_id), 0.0), 0.0, 100.0
        )
        survey_usefulness = _clamp(
            _safe_float(survey_usefulness_map.get(agent_id), 0.0), 0.0, 100.0
        )
        behavior_delay = _clamp(
            _safe_float(behavior_delay_map.get(agent_id), 0.0), 0.0, 100.0
        )
        behavior_proxy = _clamp(
            _safe_float(behavior_proxy_map.get(agent_id), 0.0), 0.0, 100.0
        )
        behavior_offline = _clamp(
            _safe_float(behavior_offline_map.get(agent_id), 0.0), 0.0, 100.0
        )
        emotion_payload = emotion_map.get(agent_id, {})
        anxiety = _clamp(
            _safe_float(
                emotion_payload.get("anxiety", 4.0)
                if isinstance(emotion_payload, dict)
                else 4.0,
                4.0,
            ),
            0.0,
            10.0,
        )
        confidence = _clamp(
            _safe_float(
                emotion_payload.get("confidence", 5.0)
                if isinstance(emotion_payload, dict)
                else 5.0,
                5.0,
            ),
            0.0,
            10.0,
        )
        reflection_count = int(_safe_float(reflection_count_map.get(agent_id, 0), 0.0))
        status_payload = {
            "stage": stage,
            "intention": intention,
            "friction_step_signal": friction_step_signal_map.get(agent_id, {}),
            "proto_mobile_entry_decision": mobile_entry_decision_map.get(agent_id, {}),
            "helplessness_score": float(helplessness_map.get(agent_id, 0)),
            "trust_in_apps": float(trust_map.get(agent_id, 0)),
            "avoidance_tendency": float(avoidance_map.get(agent_id, 0)),
            "survey_helplessness_index": survey_helplessness,
            "survey_withdrawal_index": survey_withdrawal,
            "survey_self_efficacy_index": survey_self_efficacy,
            "survey_anxiety_index": survey_anxiety,
            "survey_support_index": survey_support,
            "survey_usefulness_index": survey_usefulness,
            "behavior_delay_online": behavior_delay,
            "behavior_proxy_reliance": behavior_proxy,
            "behavior_offline_switch": behavior_offline,
            "avg_stage_anxiety": anxiety,
            "avg_stage_confidence": confidence,
            "daily_reflection_count": reflection_count,
            "negative_event_count": int(negative_count_map.get(agent_id, 0)),
            "intercept_count": int(intercept_count_map.get(agent_id, 0)),
            "help_request_count": int(help_count_map.get(agent_id, 0)),
            "success_count": int(success_count_map.get(agent_id, 0)),
            "failure_count": int(failure_count_map.get(agent_id, 0)),
            "num_completed_trips": trip_count,
            "total_travel_distance": travel_distance,
            "total_travel_time": travel_time,
        }
        helplessness_values.append(status_payload["helplessness_score"])
        trust_values.append(status_payload["trust_in_apps"])
        avoidance_values.append(status_payload["avoidance_tendency"])
        negative_values.append(status_payload["negative_event_count"])
        intercept_values.append(status_payload["intercept_count"])
        help_values.append(status_payload["help_request_count"])
        success_values.append(status_payload["success_count"])
        failure_values.append(status_payload["failure_count"])
        trip_values.append(status_payload["num_completed_trips"])
        distance_values.append(status_payload["total_travel_distance"])
        travel_time_values.append(status_payload["total_travel_time"])
        survey_helplessness_values.append(status_payload["survey_helplessness_index"])
        survey_withdrawal_values.append(status_payload["survey_withdrawal_index"])
        survey_self_efficacy_values.append(status_payload["survey_self_efficacy_index"])
        survey_anxiety_values.append(status_payload["survey_anxiety_index"])
        survey_support_values.append(status_payload["survey_support_index"])
        survey_usefulness_values.append(status_payload["survey_usefulness_index"])
        behavior_delay_values.append(status_payload["behavior_delay_online"])
        behavior_proxy_values.append(status_payload["behavior_proxy_reliance"])
        behavior_offline_values.append(status_payload["behavior_offline_switch"])
        reflection_count_values.append(status_payload["daily_reflection_count"])
        anxiety_values.append(status_payload["avg_stage_anxiety"])
        confidence_values.append(status_payload["avg_stage_confidence"])
        rows.append(
            (
                int(agent_id),
                int(day),
                float(t),
                intention,
                status_payload["helplessness_score"],
                status_payload["trust_in_apps"],
                status_payload["avoidance_tendency"],
                status_payload["negative_event_count"],
                status_payload["intercept_count"],
                status_payload["help_request_count"],
                status_payload["success_count"],
                status_payload["failure_count"],
                json.dumps(status_payload, ensure_ascii=False),
            )
        )
    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()
    cur.executemany(
        f"""
        INSERT INTO {table_name} (
            agent_id, day, t, intention,
            helplessness_score, trust_in_apps, avoidance_tendency,
            negative_event_count, intercept_count, help_request_count,
            success_count, failure_count, status_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    def _avg(values: list[float]) -> float:
        return float(sum(values) / len(values)) if values else 0.0

    step = int(day * 100000 + t)
    metrics = [
        ("step.helplessness_avg", _avg(helplessness_values), step),
        ("step.trust_avg", _avg(trust_values), step),
        ("step.avoidance_avg", _avg(avoidance_values), step),
        ("step.negative_event_avg", _avg([float(v) for v in negative_values]), step),
        ("step.intercept_avg", _avg([float(v) for v in intercept_values]), step),
        ("step.help_request_avg", _avg([float(v) for v in help_values]), step),
        ("step.success_avg", _avg([float(v) for v in success_values]), step),
        ("step.failure_avg", _avg([float(v) for v in failure_values]), step),
        ("step.num_completed_trips_avg", _avg([float(v) for v in trip_values]), step),
        ("step.total_travel_distance_avg", _avg(distance_values), step),
        ("step.total_travel_time_avg", _avg(travel_time_values), step),
        ("step.survey_helplessness_avg", _avg(survey_helplessness_values), step),
        ("step.survey_withdrawal_avg", _avg(survey_withdrawal_values), step),
        ("step.survey_self_efficacy_avg", _avg(survey_self_efficacy_values), step),
        ("step.survey_anxiety_avg", _avg(survey_anxiety_values), step),
        ("step.survey_support_avg", _avg(survey_support_values), step),
        ("step.survey_usefulness_avg", _avg(survey_usefulness_values), step),
        ("step.avg_stage_anxiety", _avg(anxiety_values), step),
        ("step.avg_stage_confidence", _avg(confidence_values), step),
        ("step.daily_reflection_count", float(sum(reflection_count_values)), step),
        (
            "step.strategy_deliberation_hybrid_enabled",
            1.0 if RUNTIME_CONFIG.proto_llm_strategy_deliberation_enabled else 0.0,
            step,
        ),
        ("step.behavior_delay_online_avg", _avg(behavior_delay_values), step),
        ("step.behavior_proxy_reliance_avg", _avg(behavior_proxy_values), step),
        ("step.behavior_offline_switch_avg", _avg(behavior_offline_values), step),
    ]
    try:
        await db_writer.log_metric(metrics)
    except Exception:
        return


async def sync_survey_feedback(simulation: AgentSociety):
    global _LAST_SURVEY_SYNC_CURSOR
    db_writer = getattr(simulation, "_database_writer", None)
    if db_writer is None:
        return
    sqlite_path = getattr(db_writer, "_sqlite_path", None)
    if sqlite_path is None:
        return
    table_name = f"as_{db_writer.exp_id.replace('-', '_')}_agent_survey"
    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()
    table_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if not table_exists:
        conn.close()
        return
    if _LAST_SURVEY_SYNC_CURSOR is None:
        rows = cur.execute(
            f"SELECT id, day, t, result FROM {table_name} ORDER BY day, t, id"
        ).fetchall()
    else:
        last_day, last_t, last_agent_id = _LAST_SURVEY_SYNC_CURSOR
        rows = cur.execute(
            f"""
            SELECT id, day, t, result
            FROM {table_name}
            WHERE day > ?
               OR (day = ? AND (t > ? OR (t = ? AND id > ?)))
            ORDER BY day, t, id
            """,
            (
                last_day,
                last_day,
                last_t,
                last_t,
                last_agent_id,
            ),
        ).fetchall()
    conn.close()
    if not rows:
        return

    latest_by_agent: dict[int, tuple[int, float, Any]] = {}
    for agent_id, day, t, result in rows:
        key = int(agent_id)
        current = latest_by_agent.get(key)
        if current is None or (int(day), float(t)) > (current[0], current[1]):
            latest_by_agent[key] = (int(day), float(t), result)
    last_agent_id, last_day, last_t, _ = rows[-1]
    _LAST_SURVEY_SYNC_CURSOR = (int(last_day), float(last_t), int(last_agent_id))

    for agent_id, (day, t, payload) in latest_by_agent.items():
        values = _extract_survey_result_values(payload)
        if not values:
            continue
        derived = _derive_survey_indices(values)
        updates = build_survey_measurement_updates(
            values=values,
            derived=derived,
            day=int(day),
            t=float(t),
        )
        for key, value in updates.items():
            await simulation.update([agent_id], key, value)


async def sync_interview_feedback(simulation: AgentSociety):
    global _LAST_INTERVIEW_SYNC_ROWID
    db_writer = getattr(simulation, "_database_writer", None)
    if db_writer is None:
        return
    sqlite_path = getattr(db_writer, "_sqlite_path", None)
    if sqlite_path is None:
        return
    table_name = f"as_{db_writer.exp_id.replace('-', '_')}_agent_dialog"
    conn = sqlite3.connect(str(sqlite_path))
    cur = conn.cursor()
    table_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if not table_exists:
        conn.close()
        return
    if _LAST_INTERVIEW_SYNC_ROWID is None:
        rows = cur.execute(
            f"SELECT rowid, id, day, t, speaker, content FROM {table_name} ORDER BY rowid"
        ).fetchall()
    else:
        rows = cur.execute(
            f"""
            SELECT rowid, id, day, t, speaker, content
            FROM {table_name}
            WHERE rowid > ?
            ORDER BY rowid
            """,
            (_LAST_INTERVIEW_SYNC_ROWID,),
        ).fetchall()
    conn.close()
    if not rows:
        return

    pending_by_agent: dict[int, dict[str, Any]] = {}
    latest_stage_by_agent: dict[int, StageInterviewResult] = {}
    latest_final_by_agent: dict[int, FinalInterviewResult] = {}
    stage_results: list[StageInterviewResult] = []
    final_results: list[FinalInterviewResult] = []

    for rowid, agent_id, _day, _t, speaker, content in rows:
        agent_key = int(agent_id)
        speaker_text = _clean_intention(speaker)
        content_text = _clean_intention(content)
        stage_match = _STAGE_INTERVIEW_PATTERN.match(content_text)
        if speaker_text == "user" and stage_match:
            pending_by_agent[agent_key] = {
                "kind": "stage",
                "stage_name": _clean_intention(stage_match.group("stage_name")),
                "stage_index": _safe_int(stage_match.group("stage_index"), 0),
            }
            _LAST_INTERVIEW_SYNC_ROWID = int(rowid)
            continue
        if speaker_text == "user" and content_text.startswith(_FINAL_INTERVIEW_PREFIX):
            pending_by_agent[agent_key] = {"kind": "final"}
            _LAST_INTERVIEW_SYNC_ROWID = int(rowid)
            continue
        if speaker_text or agent_key not in pending_by_agent:
            _LAST_INTERVIEW_SYNC_ROWID = int(rowid)
            continue

        pending = pending_by_agent.pop(agent_key)
        payload = _extract_json_object(content_text)
        if pending["kind"] == "stage":
            parsed_result = _parse_stage_interview_payload(
                payload,
                stage_name=str(pending["stage_name"]),
                stage_index=int(pending["stage_index"]),
                raw_answer=content_text,
            )
            latest_stage_by_agent[agent_key] = parsed_result
            stage_results.append(parsed_result)
        else:
            parsed_result = _parse_final_interview_payload(
                payload,
                raw_answer=content_text,
            )
            latest_final_by_agent[agent_key] = parsed_result
            final_results.append(parsed_result)
        _LAST_INTERVIEW_SYNC_ROWID = int(rowid)

    if latest_stage_by_agent:
        history_map = await _safe_gather_status(
            simulation,
            "proto_stage_interview_history",
            list(latest_stage_by_agent.keys()),
        )
        for agent_id, result in latest_stage_by_agent.items():
            history = (
                [item for item in history_map.get(agent_id, []) if isinstance(item, dict)]
                if isinstance(history_map.get(agent_id), list)
                else []
            )
            history.append(result.to_dict())
            await simulation.update([agent_id], "proto_stage_interview", result.to_dict())
            await simulation.update(
                [agent_id],
                "proto_stage_interview_history",
                history[-8:],
            )

    if latest_final_by_agent:
        for agent_id, result in latest_final_by_agent.items():
            await simulation.update([agent_id], "proto_final_interview", result.to_dict())

    step_day, step_t = simulation.environment.get_datetime()
    step = int(step_day * 100000 + step_t)
    metrics: list[tuple[str, float, int]] = []
    stage_name = _clean_intention(
        simulation.environment.environment.get("digital_stage")
        or simulation.environment.environment.get("stage_name")
    ) or "stage"
    valid_stage_results = [
        result for result in stage_results if result.status != "parse_failed"
    ]
    if valid_stage_results:
        stage_total = float(len(valid_stage_results))
        metrics.extend(
            [
                (f"{stage_name}.stage_interview_count", stage_total, step),
                (
                    f"{stage_name}.stage_future_try_self_rate",
                    float(
                        sum(
                            1
                            for result in valid_stage_results
                            if result.future_intention == "try_self"
                        )
                    )
                    / stage_total,
                    step,
                ),
                (
                    f"{stage_name}.stage_future_seek_help_rate",
                    float(
                        sum(
                            1
                            for result in valid_stage_results
                            if result.future_intention == "seek_help"
                        )
                    )
                    / stage_total,
                    step,
                ),
                (
                    f"{stage_name}.stage_future_avoid_rate",
                    float(
                        sum(
                            1
                            for result in valid_stage_results
                            if result.future_intention == "avoid"
                        )
                    )
                    / stage_total,
                    step,
                ),
                (
                    f"{stage_name}.stage_interview_confidence_avg",
                    float(
                        sum(float(result.confidence) for result in valid_stage_results)
                        / stage_total
                    ),
                    step,
                ),
            ]
        )

    valid_final_results = [
        result for result in final_results if result.status != "parse_failed"
    ]
    if valid_final_results:
        metrics.append(("final.interview_count", float(len(valid_final_results)), step))

    if metrics:
        try:
            await db_writer.log_metric(metrics)
        except Exception:
            return


async def init_status(simulation: AgentSociety):
    citizen_ids = await simulation.filter(types=EXPERIMENT_AGENT_CLASSES)
    citizen_ids = sorted(citizen_ids)
    _load_profile_index()
    name_map = await _safe_gather_status(simulation, "name", citizen_ids)
    home_map = await _safe_gather_status(simulation, "home", citizen_ids)
    work_map = await _safe_gather_status(simulation, "work", citizen_ids)
    position_map = await _safe_gather_status(simulation, "position", citizen_ids)
    aoi_ids = simulation.environment.get_aoi_ids()
    valid_aoi_ids = {int(aoi_id) for aoi_id in aoi_ids}
    default_aoi_id = aoi_ids[0] if aoi_ids else 0
    default_position = {"aoi_position": {"aoi_id": default_aoi_id}}
    for agent_id in citizen_ids:
        profile = _resolve_profile_for_agent(
            agent_id=agent_id,
            agent_name=_clean_intention(name_map.get(agent_id, "")),
            ordered_agent_ids=citizen_ids,
        )
        digital_experience = float(profile.get("digital_experience", 0.5))
        vision_limit = float(profile.get("vision_limit", 0.3))
        past_fraud = float(profile.get("past_fraud_experience", 0.2))
        initial_status = build_initial_proto_status(
            digital_experience=digital_experience,
            vision_limit=vision_limit,
            past_fraud_experience=past_fraud,
        )
        home_position = _normalize_aoi_position(
            profile.get("home"),
            valid_aoi_ids,
            _normalize_aoi_position(home_map.get(agent_id), valid_aoi_ids, default_position),
        )
        work_position = _normalize_aoi_position(
            profile.get("work"),
            valid_aoi_ids,
            _normalize_aoi_position(work_map.get(agent_id), valid_aoi_ids, home_position),
        )
        current_position = _normalize_aoi_position(
            position_map.get(agent_id),
            valid_aoi_ids,
            home_position,
        )
        initial_status.update(
            {
                "position": current_position,
                "home": home_position,
                "work": work_position,
                "current_intention": "Planning",
            }
        )
        for key, value in initial_status.items():
            await simulation.update([agent_id], key, value)

async def nudge_mobility_if_stuck(simulation: AgentSociety):
    if EXPERIMENT_ENGINE == "proto":
        return
    db_writer = getattr(simulation, "_database_writer", None)
    day, t = simulation.environment.get_datetime()
    hour = int((float(t) // 3600) % 24)
    window_active = (
        MOBILITY_NUDGE_PROB > 0
        and MOBILITY_NUDGE_START_HOUR <= hour <= MOBILITY_NUDGE_END_HOUR
    )
    step = int(day * 100000 + t)
    citizen_ids = await simulation.filter(types=EXPERIMENT_AGENT_CLASSES)
    candidate_count = float(len(citizen_ids))
    random_hit_count = 0.0
    nudge_sent_count = 0.0
    nudge_accepted_count = 0.0
    if not window_active or not citizen_ids:
        if db_writer is not None:
            try:
                await db_writer.log_metric(
                    [
                        ("step.mobility_nudge_window_active", 1.0 if window_active else 0.0, step),
                        ("step.mobility_nudge_candidate_count", candidate_count, step),
                        ("step.mobility_nudge_random_hit_count", random_hit_count, step),
                        ("step.mobility_nudge_sent_count", nudge_sent_count, step),
                        ("step.mobility_nudge_accepted_count", nudge_accepted_count, step),
                        ("step.mobility_nudge_sent_rate", 0.0, step),
                        ("step.mobility_nudge_accepted_rate", 0.0, step),
                    ]
                )
            except Exception:
                return
        return
    intention_map = await simulation.gather("current_intention", citizen_ids, keep_id=True)
    need_map = await simulation.gather("current_need", citizen_ids, keep_id=True)
    trip_count_map = await _safe_gather_status(
        simulation, "num_completed_trips", citizen_ids
    )
    travel_distance_map = await _safe_gather_status(
        simulation, "total_travel_distance", citizen_ids
    )
    travel_time_map = await _safe_gather_status(
        simulation, "total_travel_time", citizen_ids
    )
    for agent_id in citizen_ids:
        if RNG.random() > MOBILITY_NUDGE_PROB:
            continue
        random_hit_count += 1.0
        intention = _clean_intention(intention_map.get(agent_id, "")).lower()
        need = _clean_intention(need_map.get(agent_id, "")).lower()
        if any(
            token in intention
            for token in {"travel", "commute", "ride", "mobility", "出行", "打车"}
        ):
            continue
        if need in {"travel", "commute", "mobility", "出行", "打车"}:
            continue
        if _is_empty_intention(intention) or any(
            token in intention
            for token in {"stay", "home", "rest", "sleep", "idle", "planning"}
        ):
            baseline_trips = int(_safe_float(trip_count_map.get(agent_id, 0), 0))
            baseline_distance = _safe_float(
                travel_distance_map.get(agent_id, 0.0), 0.0
            )
            baseline_time = _safe_float(travel_time_map.get(agent_id, 0.0), 0.0)
            await simulation.update([agent_id], "current_need", "travel")
            await simulation.update(
                [agent_id], "current_intention", "Travel to nearby service point"
            )
            await simulation.update([agent_id], "mobility_nudge_pending", 1)
            await simulation.update([agent_id], "mobility_nudge_sent_day", int(day))
            await simulation.update([agent_id], "mobility_nudge_sent_t", float(t))
            await simulation.update(
                [agent_id], "mobility_nudge_baseline_trips", baseline_trips
            )
            await simulation.update(
                [agent_id], "mobility_nudge_baseline_distance", baseline_distance
            )
            await simulation.update(
                [agent_id], "mobility_nudge_baseline_time", baseline_time
            )
            nudge_sent_count += 1.0
            nudge_accepted_count += 1.0
    if db_writer is not None:
        sent_rate = nudge_sent_count / candidate_count if candidate_count > 0 else 0.0
        accepted_rate = (
            nudge_accepted_count / nudge_sent_count if nudge_sent_count > 0 else 0.0
        )
        try:
            await db_writer.log_metric(
                [
                    ("step.mobility_nudge_window_active", 1.0, step),
                    ("step.mobility_nudge_candidate_count", candidate_count, step),
                    ("step.mobility_nudge_random_hit_count", random_hit_count, step),
                    ("step.mobility_nudge_sent_count", nudge_sent_count, step),
                    ("step.mobility_nudge_accepted_count", nudge_accepted_count, step),
                    ("step.mobility_nudge_sent_rate", sent_rate, step),
                    ("step.mobility_nudge_accepted_rate", accepted_rate, step),
                ]
            )
        except Exception:
            return


async def stage_settlement(simulation: AgentSociety):
    citizen_ids = await simulation.filter(types=EXPERIMENT_AGENT_CLASSES)
    helplessness_map = await simulation.gather(
        "helplessness_score", citizen_ids, keep_id=True
    )
    trust_map = await simulation.gather(
        "trust_in_apps", citizen_ids, keep_id=True
    )
    avoidance_map = await simulation.gather(
        "avoidance_tendency", citizen_ids, keep_id=True
    )
    negative_count_map = await simulation.gather(
        "negative_event_count", citizen_ids, keep_id=True
    )
    intercept_count_map = await simulation.gather(
        "intercept_count", citizen_ids, keep_id=True
    )
    help_count_map = await simulation.gather(
        "help_request_count", citizen_ids, keep_id=True
    )
    success_count_map = await simulation.gather(
        "success_count", citizen_ids, keep_id=True
    )
    failure_count_map = await simulation.gather(
        "failure_count", citizen_ids, keep_id=True
    )
    cumulative_negative_map = await simulation.gather(
        "cumulative_negative_event_count", citizen_ids, keep_id=True
    )
    cumulative_intercept_map = await simulation.gather(
        "cumulative_intercept_count", citizen_ids, keep_id=True
    )
    cumulative_help_map = await simulation.gather(
        "cumulative_help_request_count", citizen_ids, keep_id=True
    )
    cumulative_success_map = await simulation.gather(
        "cumulative_success_count", citizen_ids, keep_id=True
    )
    cumulative_failure_map = await simulation.gather(
        "cumulative_failure_count", citizen_ids, keep_id=True
    )
    event_log_map = await _safe_gather_status(simulation, "event_log", citizen_ids)
    emotion_map = await _safe_gather_status(
        simulation, "digital_emotion_state", citizen_ids
    )
    reflection_count_map = await _safe_gather_status(
        simulation, "proto_stage_daily_reflection_count", citizen_ids
    )
    survey_self_efficacy_map = await _safe_gather_status(
        simulation, "survey_self_efficacy_index", citizen_ids
    )
    survey_anxiety_map = await _safe_gather_status(
        simulation, "survey_anxiety_index", citizen_ids
    )
    survey_support_map = await _safe_gather_status(
        simulation, "survey_support_index", citizen_ids
    )
    survey_usefulness_map = await _safe_gather_status(
        simulation, "survey_usefulness_index", citizen_ids
    )
    proto_attempt_rows_map: dict[int, Any] = {}
    proto_stage_start_map: dict[int, Any] = {}
    if EXPERIMENT_ENGINE == "proto":
        proto_attempt_rows_map = await _safe_gather_status(
            simulation, "proto_stage_attempt_rows_json", citizen_ids
        )
        proto_stage_start_map = await _safe_gather_status(
            simulation, "proto_stage_start_helplessness", citizen_ids
        )
    env = simulation.environment.environment
    stage_name = _clean_intention(env.get("stage_name"))
    if not stage_name:
        stage_name = _clean_intention(env.get("digital_stage")) or "stage"
    stage_metric_prefix = _clean_intention(env.get("digital_stage")) or stage_name
    stage_index = _STAGE_NAME_TO_INDEX.get(stage_name, 0)
    now_day, now_t = simulation.environment.get_datetime()
    step = int(now_day * 100000 + now_t)
    updated_helplessness: list[float] = []
    updated_trust: list[float] = []
    updated_avoidance: list[float] = []
    negative_counts: list[int] = []
    intercept_counts: list[int] = []
    help_counts: list[int] = []
    success_counts: list[int] = []
    failure_counts: list[int] = []
    cumulative_negative_counts: list[int] = []
    cumulative_intercept_counts: list[int] = []
    cumulative_help_counts: list[int] = []
    cumulative_success_counts: list[int] = []
    cumulative_failure_counts: list[int] = []
    anxiety_values: list[float] = []
    confidence_values: list[float] = []
    reflection_counts: list[int] = []
    survey_self_efficacy_values: list[float] = []
    survey_anxiety_values: list[float] = []
    survey_support_values: list[float] = []
    survey_usefulness_values: list[float] = []
    stage_explanation_db_rows: list[tuple[Any, ...]] = []
    stage_explanation_csv_rows: list[dict[str, Any]] = []
    proto_stage_rows: list[dict[str, Any]] = []

    def _normalize_count_dict(raw: Any) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, int] = {}
        for key, value in raw.items():
            normalized_key = _clean_intention(str(key))
            if not normalized_key:
                continue
            normalized[normalized_key] = int(_safe_float(value, 0.0))
        return normalized

    for agent_id in citizen_ids:
        negative_count = int(negative_count_map.get(agent_id, 0))
        intercept_count = int(intercept_count_map.get(agent_id, 0))
        help_count = int(help_count_map.get(agent_id, 0))
        success_count = int(success_count_map.get(agent_id, 0))
        failure_count = int(failure_count_map.get(agent_id, 0))
        negative_counts.append(negative_count)
        intercept_counts.append(intercept_count)
        help_counts.append(help_count)
        success_counts.append(success_count)
        failure_counts.append(failure_count)
        cumulative_negative_counts.append(
            int(cumulative_negative_map.get(agent_id, 0))
        )
        cumulative_intercept_counts.append(
            int(cumulative_intercept_map.get(agent_id, 0))
        )
        cumulative_help_counts.append(int(cumulative_help_map.get(agent_id, 0)))
        cumulative_success_counts.append(int(cumulative_success_map.get(agent_id, 0)))
        cumulative_failure_counts.append(int(cumulative_failure_map.get(agent_id, 0)))
        helplessness = _clamp(_safe_float(helplessness_map.get(agent_id, 0)))
        trust = _clamp(_safe_float(trust_map.get(agent_id, 0)))
        avoidance = _clamp(_safe_float(avoidance_map.get(agent_id, 0)))
        updated_helplessness.append(helplessness)
        updated_trust.append(trust)
        updated_avoidance.append(avoidance)
        emotion_payload = emotion_map.get(agent_id, {})
        anxiety_values.append(
            _clamp(
                _safe_float(
                    emotion_payload.get("anxiety", 4.0)
                    if isinstance(emotion_payload, dict)
                    else 4.0,
                    4.0,
                ),
                0.0,
                10.0,
            )
        )
        confidence_values.append(
            _clamp(
                _safe_float(
                    emotion_payload.get("confidence", 5.0)
                    if isinstance(emotion_payload, dict)
                    else 5.0,
                    5.0,
                ),
                0.0,
                10.0,
            )
        )
        reflection_counts.append(
            int(_safe_float(reflection_count_map.get(agent_id, 0), 0.0))
        )
        survey_self_efficacy_values.append(
            _clamp(_safe_float(survey_self_efficacy_map.get(agent_id), 0.0), 0.0, 100.0)
        )
        survey_anxiety_values.append(
            _clamp(_safe_float(survey_anxiety_map.get(agent_id), 0.0), 0.0, 100.0)
        )
        survey_support_values.append(
            _clamp(_safe_float(survey_support_map.get(agent_id), 0.0), 0.0, 100.0)
        )
        survey_usefulness_values.append(
            _clamp(_safe_float(survey_usefulness_map.get(agent_id), 0.0), 0.0, 100.0)
        )
        if EXPERIMENT_ENGINE == "proto":
            proto_stage_rows.extend(
                _decode_json_object_list(proto_attempt_rows_map.get(agent_id, "[]"))
            )
            await simulation.update([agent_id], "proto_stage_attempt_rows_json", "[]")
            await simulation.update(
                [agent_id], "proto_stage_start_helplessness", helplessness
            )
        await simulation.update([agent_id], "negative_event_count", 0)
        await simulation.update([agent_id], "intercept_count", 0)
        await simulation.update([agent_id], "help_request_count", 0)
        await simulation.update([agent_id], "success_count", 0)
        await simulation.update([agent_id], "failure_count", 0)
        raw_event_log = event_log_map.get(agent_id, [])
        event_log = raw_event_log if isinstance(raw_event_log, list) else []
        explanation_summary = summarize_stage_explanations(event_log, top_k=3)

        top_negative_tags = [
            _clean_intention(item)
            for item in explanation_summary.get("top_negative_tags", [])
            if _clean_intention(item)
        ]
        top_positive_tags = [
            _clean_intention(item)
            for item in explanation_summary.get("top_positive_tags", [])
            if _clean_intention(item)
        ]
        top_primary_reasons = [
            _clean_intention(item)
            for item in explanation_summary.get("top_primary_reasons", [])
            if _clean_intention(item)
        ]
        negative_tag_counts = _normalize_count_dict(
            explanation_summary.get("negative_tag_counts", {})
        )
        positive_tag_counts = _normalize_count_dict(
            explanation_summary.get("positive_tag_counts", {})
        )
        primary_reason_counts = _normalize_count_dict(
            explanation_summary.get("primary_reason_counts", {})
        )

        if not top_primary_reasons:
            if event_log:
                top_primary_reasons = ["event_emitted_without_reason_tag"]
                primary_reason_counts.setdefault(
                    "event_emitted_without_reason_tag",
                    len(event_log),
                )
            else:
                top_primary_reasons = ["no_emitted_events"]
                primary_reason_counts.setdefault("no_emitted_events", 1)

        summary_text = (
            f"stage={stage_name}; events={len(event_log)}; "
            f"top_primary={','.join(top_primary_reasons) or 'none'}; "
            f"top_negative={','.join(top_negative_tags) or 'none'}; "
            f"top_positive={','.join(top_positive_tags) or 'none'}"
        )
        await _record_stage_summary_memory(
            simulation=simulation,
            agent_id=int(agent_id),
            stage_name=stage_name,
            summary_text=summary_text,
        )

        stage_explanation_db_rows.append(
            (
                int(agent_id),
                int(now_day),
                float(now_t),
                int(step),
                stage_name,
                int(stage_index),
                json.dumps(top_negative_tags, ensure_ascii=False),
                json.dumps(top_positive_tags, ensure_ascii=False),
                json.dumps(top_primary_reasons, ensure_ascii=False),
                json.dumps(negative_tag_counts, ensure_ascii=False),
                json.dumps(positive_tag_counts, ensure_ascii=False),
                json.dumps(primary_reason_counts, ensure_ascii=False),
                summary_text,
            )
        )
        stage_explanation_csv_rows.append(
            {
                "agent_id": int(agent_id),
                "day": int(now_day),
                "t": float(now_t),
                "step": int(step),
                "stage_name": stage_name,
                "stage_index": int(stage_index),
                "top_negative_tags": json.dumps(top_negative_tags, ensure_ascii=False),
                "top_positive_tags": json.dumps(top_positive_tags, ensure_ascii=False),
                "top_primary_reasons": json.dumps(top_primary_reasons, ensure_ascii=False),
                "negative_tag_counts_json": json.dumps(negative_tag_counts, ensure_ascii=False),
                "positive_tag_counts_json": json.dumps(positive_tag_counts, ensure_ascii=False),
                "primary_reason_counts_json": json.dumps(primary_reason_counts, ensure_ascii=False),
                "summary_text": summary_text,
            }
        )
    proto_stage_summary: dict[str, Any] | None = None
    if EXPERIMENT_ENGINE == "proto":
        proto_start_values = [
            _clamp(_safe_float(proto_stage_start_map.get(agent_id, helplessness_map.get(agent_id, 0))))
            for agent_id in citizen_ids
        ]
        proto_start_avg = (
            float(sum(proto_start_values) / len(proto_start_values))
            if proto_start_values
            else 0.0
        )
        proto_end_avg = (
            float(sum(updated_helplessness) / len(updated_helplessness))
            if updated_helplessness
            else 0.0
        )
        proto_stage_summary = summarize_stage_attempts(
            rows=proto_stage_rows,
            helplessness_start_avg=proto_start_avg,
            helplessness_end_avg=proto_end_avg,
            day=int(now_day),
            t=float(now_t),
            step=int(step),
            stage_name=stage_name,
            stage_index=int(stage_index),
            agent_count=len(citizen_ids),
        )
    db_writer = getattr(simulation, "_database_writer", None)
    if db_writer is not None:
        def _avg(values: list[float]) -> float:
            return float(sum(values) / len(values)) if values else 0.0

        metrics = [
            (
                f"{stage_metric_prefix}.helplessness_avg",
                _avg(updated_helplessness),
                step,
            ),
            (f"{stage_metric_prefix}.trust_avg", _avg(updated_trust), step),
            (f"{stage_metric_prefix}.avoidance_avg", _avg(updated_avoidance), step),
            (
                f"{stage_metric_prefix}.negative_event_avg",
                _avg([float(v) for v in negative_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.intercept_avg",
                _avg([float(v) for v in intercept_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.help_request_avg",
                _avg([float(v) for v in help_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.success_avg",
                _avg([float(v) for v in success_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.failure_avg",
                _avg([float(v) for v in failure_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.cumulative_negative_avg",
                _avg([float(v) for v in cumulative_negative_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.cumulative_intercept_avg",
                _avg([float(v) for v in cumulative_intercept_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.cumulative_help_avg",
                _avg([float(v) for v in cumulative_help_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.cumulative_success_avg",
                _avg([float(v) for v in cumulative_success_counts]),
                step,
            ),
            (
                f"{stage_metric_prefix}.cumulative_failure_avg",
                _avg([float(v) for v in cumulative_failure_counts]),
                step,
            ),
            (f"{stage_metric_prefix}.avg_stage_anxiety", _avg(anxiety_values), step),
            (
                f"{stage_metric_prefix}.avg_stage_confidence",
                _avg(confidence_values),
                step,
            ),
            (
                f"{stage_metric_prefix}.daily_reflection_count",
                float(sum(reflection_counts)),
                step,
            ),
            (
                f"{stage_metric_prefix}.survey_self_efficacy_avg",
                _avg(survey_self_efficacy_values),
                step,
            ),
            (
                f"{stage_metric_prefix}.survey_anxiety_avg",
                _avg(survey_anxiety_values),
                step,
            ),
            (
                f"{stage_metric_prefix}.survey_support_avg",
                _avg(survey_support_values),
                step,
            ),
            (
                f"{stage_metric_prefix}.survey_usefulness_avg",
                _avg(survey_usefulness_values),
                step,
            ),
            (
                f"{stage_metric_prefix}.strategy_deliberation_hybrid_enabled",
                1.0
                if RUNTIME_CONFIG.proto_llm_strategy_deliberation_enabled
                else 0.0,
                step,
            ),
        ]
        if proto_stage_summary is not None:
            metrics.extend(
                [
                    (
                        f"{stage_metric_prefix}.attempt_rate",
                        float(proto_stage_summary["attempt_rate"]),
                        step,
                    ),
                    (
                        f"{stage_metric_prefix}.success_rate",
                        float(proto_stage_summary["success_rate"]),
                        step,
                    ),
                    (
                        f"{stage_metric_prefix}.help_seek_rate",
                        float(proto_stage_summary["help_seek_rate"]),
                        step,
                    ),
                    (
                        f"{stage_metric_prefix}.abandon_rate",
                        float(proto_stage_summary["abandon_rate"]),
                        step,
                    ),
                    (
                        f"{stage_metric_prefix}.negative_feedback_rate",
                        float(proto_stage_summary["negative_feedback_rate"]),
                        step,
                    ),
                    (
                        f"{stage_metric_prefix}.helplessness_delta",
                        float(proto_stage_summary["helplessness_delta"]),
                        step,
                    ),
                ]
            )
        await db_writer.log_metric(metrics)
        sqlite_path = getattr(db_writer, "_sqlite_path", None)
        if sqlite_path is not None and stage_explanation_db_rows:
            sqlite_file = Path(sqlite_path)
            table_name = stage_explanation_table_name(db_writer.exp_id)
            ensure_stage_explanation_table(sqlite_file, table_name)
            write_stage_explanation_rows(
                sqlite_file,
                table_name,
                stage_explanation_db_rows,
            )
            analysis_csv = (
                EXAMPLE_DIR
                / "analysis"
                / f"stage_explanation_{str(db_writer.exp_id)[:8]}.csv"
            )
            append_stage_explanation_csv(analysis_csv, stage_explanation_csv_rows)
        if sqlite_path is not None and proto_stage_summary is not None:
            sqlite_file = Path(sqlite_path)
            attempt_table = attempt_rows_table_name(db_writer.exp_id)
            stage_summary_table = stage_summary_table_name(db_writer.exp_id)
            ensure_attempt_rows_table(sqlite_file, attempt_table)
            ensure_stage_summary_table(sqlite_file, stage_summary_table)
            write_attempt_rows(sqlite_file, attempt_table, proto_stage_rows)
            write_stage_summary_rows(
                sqlite_file,
                stage_summary_table,
                [proto_stage_summary],
            )


async def reset_stage_event_log(simulation: AgentSociety):
    citizen_ids = await simulation.filter(types=EXPERIMENT_AGENT_CLASSES)
    if not citizen_ids:
        return
    for agent_id in citizen_ids:
        await simulation.update([agent_id], "event_log", [])
        if EXPERIMENT_ENGINE == "proto":
            await simulation.update([agent_id], "proto_stage_attempt_rows_json", "[]")


async def audit_economy_bindings(simulation: AgentSociety):
    if not ECONOMY_BLOCK_ENABLED:
        return
    citizen_ids = await simulation.filter(types=EXPERIMENT_AGENT_CLASSES)
    if not citizen_ids:
        return
    field_maps = {
        "firm_id": await _safe_gather_status(simulation, "firm_id", citizen_ids),
        "bank_id": await _safe_gather_status(simulation, "bank_id", citizen_ids),
        "government_id": await _safe_gather_status(
            simulation, "government_id", citizen_ids
        ),
        "nbs_id": await _safe_gather_status(simulation, "nbs_id", citizen_ids),
    }
    missing_details: list[dict[str, Any]] = []
    for agent_id in citizen_ids:
        missing_fields: list[str] = []
        for field, value_map in field_maps.items():
            try:
                value = int(_safe_float(value_map.get(agent_id), 0.0))
            except Exception:
                value = 0
            if value <= 0:
                missing_fields.append(field)
        if missing_fields:
            missing_details.append(
                {
                    "agent_id": int(agent_id),
                    "missing_fields": missing_fields,
                }
            )
    LOGGER.info(
        "[economy_binding] audit %s",
        json.dumps(
            {
                "enabled": True,
                "citizen_count": len(citizen_ids),
                "missing_count": len(missing_details),
                "missing": missing_details[:20],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    if missing_details and ECONOMY_BINDING_AUDIT_STRICT:
        raise RuntimeError(
            "Economy binding audit failed: missing firm/bank/government/nbs ids "
            f"for {len(missing_details)} agents."
        )


class DigitalFrictionAgent(SocietyAgent):
    survey_recent_alignment = True

    async def after_forward(self):
        await super().after_forward()
        try:
            current_plan = await self.memory.status.get("current_plan", False)
            step_signal = _extract_step_evaluation_signal(current_plan)
            status_text = await self.memory.status.get("status_summary", False)
            step_signal["status_text"] = _clean_intention(status_text)[:500]
            await self.memory.status.update("friction_step_signal", step_signal)
        except Exception:
            return


EXPERIMENT_AGENT_CLASS = (
    DigitalHelplessnessAgent if EXPERIMENT_ENGINE == "proto" else DigitalFrictionAgent
)
EXPERIMENT_AGENT_CLASSES = (EXPERIMENT_AGENT_CLASS,)


workflow_steps = [WorkflowStepConfig(type=WorkflowType.FUNCTION, func=init_status)]
if ECONOMY_BLOCK_ENABLED:
    workflow_steps.append(
        WorkflowStepConfig(type=WorkflowType.FUNCTION, func=audit_economy_bindings)
    )
workflow_steps.extend(
    [
        WorkflowStepConfig(
            type=WorkflowType.SURVEY,
            survey=tech_acceptance_survey(),
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
        ),
        WorkflowStepConfig(type=WorkflowType.FUNCTION, func=sync_survey_feedback),
    ]
)

for stage_idx, stage_cfg in enumerate(STAGE_PLAN, start=1):
    if EXPERIMENT_ENGINE != "proto":
        workflow_steps.append(
            WorkflowStepConfig(type=WorkflowType.FUNCTION, func=reset_stage_event_log)
        )
    stage_env = _resolve_stage_env(stage_cfg)
    for key, value in stage_env.items():
        workflow_steps.append(
            WorkflowStepConfig(
                type=WorkflowType.ENVIRONMENT_INTERVENE,
                key=key,
                value=value,
            )
    )
    for _ in range(STAGE_DAYS):
        for _ in range(DECISION_INTERVALS_PER_DAY):
            workflow_steps.append(
                WorkflowStepConfig(
                    type=WorkflowType.FUNCTION, func=nudge_mobility_if_stuck
                )
            )
            workflow_steps.append(
                WorkflowStepConfig(
                    type=WorkflowType.STEP,
                    steps=1,
                    ticks_per_step=EVENT_DECISION_INTERVAL_TICKS,
                )
            )
        workflow_steps.append(
            WorkflowStepConfig(type=WorkflowType.FUNCTION, func=log_step_status)
        )
    workflow_steps.append(
        WorkflowStepConfig(type=WorkflowType.FUNCTION, func=stage_settlement)
    )
    workflow_steps.append(
        WorkflowStepConfig(
            type=WorkflowType.SAVE_CONTEXT,
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
            key="helplessness_score",
            save_as=f"stage_{stage_idx}_helplessness",
        )
    )
    workflow_steps.append(
        WorkflowStepConfig(
            type=WorkflowType.SAVE_CONTEXT,
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
            key="trust_in_apps",
            save_as=f"stage_{stage_idx}_trust",
        )
    )
    workflow_steps.append(
        WorkflowStepConfig(
            type=WorkflowType.SAVE_CONTEXT,
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
            key="avoidance_tendency",
            save_as=f"stage_{stage_idx}_avoidance",
        )
    )
    workflow_steps.append(
        WorkflowStepConfig(
            type=WorkflowType.SAVE_CONTEXT,
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
            key="event_log",
            save_as=f"stage_{stage_idx}_events",
        )
    )
    workflow_steps.append(
        WorkflowStepConfig(
            type=WorkflowType.SURVEY,
            survey=tech_acceptance_survey(),
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
        )
    )
    workflow_steps.append(
        WorkflowStepConfig(type=WorkflowType.FUNCTION, func=sync_survey_feedback)
    )
    if RUNTIME_CONFIG.proto_llm_stage_interview_enabled:
        workflow_steps.append(
            WorkflowStepConfig(
                type=WorkflowType.INTERVIEW,
                interview_message=_build_stage_interview_message(
                    stage_cfg["name"], stage_idx
                ),
                target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
            )
        )
        workflow_steps.append(
            WorkflowStepConfig(type=WorkflowType.FUNCTION, func=sync_interview_feedback)
        )

if RUNTIME_CONFIG.proto_llm_final_interview_enabled:
    workflow_steps.append(
        WorkflowStepConfig(
            type=WorkflowType.INTERVIEW,
            interview_message=_build_final_interview_message(),
            target_agent=AgentFilterConfig(agent_class=(EXPERIMENT_AGENT_CLASS,)),
        )
    )
    workflow_steps.append(
        WorkflowStepConfig(type=WorkflowType.FUNCTION, func=sync_interview_feedback)
    )


def _resolve_plan_generation_prompt() -> str:
    default_prompt = SocietyAgentConfig().plan_generation_prompt
    profile = AGENT_PLAN_PROMPT_PROFILE
    if profile not in {"off", "medium"}:
        return default_prompt
    if profile == "medium":
        return """As an intelligent agent's plan system, please help me generate specific execution steps based on the selected guidance plan.
The Environment will influence the choice of steps.

Current weather: ${context.weather}
Current temperature: ${context.temperature}
Other information:
-------------------------
${context.other_information}
-------------------------

Plan target: ${context.plan_target}
Current location: ${context.current_position}
Current time: ${context.current_time}
My income/consumption level: ${profile.consumption}
My occupation: ${profile.occupation}
My age: ${profile.age}
My emotion: ${profile.emotion_types}
My thought: ${context.current_thought}
Current need: ${context.current_need}
Optional digital task hint: ${status.digital_task_hint}
Hint need: ${status.digital_task_hint_need}
Hint pending: ${status.digital_task_hint_pending}

Notes:
1. type can only be one of these four: mobility, social, economy, other
    1.1 mobility: large-scale movement and location transition
    1.2 social: social interaction and communication
    1.3 economy: shopping/work/payment and related actions
    1.4 other: other actions such as resting, learning, small daily activities
2. steps should only include actions necessary to fulfill the target (limited to ${context.max_plan_steps} steps)
3. intention in each step must be concise and actionable (start with a concrete verb)
4. Avoid vague intentions such as:
   - "Engage in leisure activities"
   - "Handle things"
   - "Do something"
5. Keep each intention focused on one clear action

Digital guidance (medium, evidence-based):
6. If a digital task hint exists and does not conflict with current target, you may include it as one of the next steps.
7. If hint conflicts with urgent current target, keep current target first and ignore the hint this round.
8. First decide whether this plan is digitally relevant based on explicit evidence in target/thought/other info.
9. Digital evidence examples: app, online, website, portal, account, login, verification, captcha, qr, scan, upload, payment, order, appointment, message app, map app, mini program.
10. If digitally relevant, include at least 1 explicit digital-channel step (max 2 digital steps).
11. A digital-channel step must explicitly mention a digital carrier/action, e.g.:
   - open app / log in account / enter verification code
   - scan QR code / upload document / check order in app
12. If the target is clearly offline (e.g., sleep, rest at home, walk for leisure, cook/eat offline), do NOT force digital steps.

Device-channel decision rules (step-level):
15. For EACH planned step, first decide internally:
    - device_needed: yes/no
    - device_type: mobile / pc / kiosk / none
16. If device_needed=yes:
    - the step intention must include an explicit digital carrier/action
      (e.g., open app, log in account, enter verification code, scan QR, submit in portal).
    - choose device_type by context:
      mobile for daily app tasks, pc for document-heavy tasks, kiosk for on-site self-service terminals.
17. If device_needed=no:
    - write the step as an offline action and avoid digital carrier words.
18. Keep this decision internal; DO NOT add new output fields.

Output constraints:
19. Keep output JSON schema exactly:
{{
  "plan": {{
    "target": "...",
    "steps": [
      {{"intention": "...", "type": "..."}}
    ]
  }}
}}
20. Do not output any extra keys or any text outside JSON.

Please response in json format (Do not return any other text), example:
{{
    "plan": {{
        "target": "Complete today's essential tasks",
        "steps": [
            {{
                "intention": "Open the service app and log in with account verification",
                "type": "other"
            }},
            {{
                "intention": "Submit required information in the portal",
                "type": "economy"
            }}
        ]
    }}
}}
"""
    return default_prompt


def _build_digital_friction_blocks() -> dict[Any, Any]:
    blocks: dict[Any, Any] = {
        MobilityBlock: MobilityBlockParams(),
        SocialBlock: SocialBlockParams(),
        OtherBlock: OtherBlockParams(),
    }
    if ECONOMY_BLOCK_ENABLED:
        blocks[EconomyBlock] = EconomyBlockParams()
    return blocks


config = Config(
    llm=[
        LLMConfig(
            provider=LLMProviderType.ZhipuAI,
            base_url=None,
            api_key=LLM_API_KEY,
            model=LLM_MODEL,
            concurrency=100,
            timeout=60,
        )
    ],
    env=EnvConfig(
        db=DatabaseConfig(
            enabled=True,
            db_type="sqlite",
            pg_dsn=None,
        ),
    ),
    map=MapConfig(
        file_path=MAP_FILE_PATH,
    ),
    agents=AgentsConfig(
        citizens=[
            AgentConfig(
                agent_class=EXPERIMENT_AGENT_CLASS,
                number=AGENT_COUNT,
                agent_params=SocietyAgentConfig(
                    plan_generation_prompt=_resolve_plan_generation_prompt()
                ),
                memory_from_file=str(PROFILES_PATH),
                memory_config_func=copy.deepcopy(memory_config_societyagent),
                blocks=_build_digital_friction_blocks(),
            )
        ],
        firms=[AgentConfig(agent_class="firm", number=1)]
        if ECONOMY_BLOCK_ENABLED
        else [],
        governments=[AgentConfig(agent_class="government", number=1)]
        if ECONOMY_BLOCK_ENABLED
        else [],
        banks=[AgentConfig(agent_class="bank", number=1)]
        if ECONOMY_BLOCK_ENABLED
        else [],
        nbs=[AgentConfig(agent_class="nbs", number=1)]
        if ECONOMY_BLOCK_ENABLED
        else [],
    ),  # type: ignore
    exp=ExpConfig(
        name=EXP_NAME,
        workflow=workflow_steps,
        environment=EnvironmentConfig(
            start_tick=6 * 60 * 60,
        ),
    ),
)
config = default(config)
for citizen_cfg in config.agents.citizens:
    if citizen_cfg.agent_class in {DigitalFrictionAgent, DigitalHelplessnessAgent}:
        if citizen_cfg.memory_config_func is None:
            citizen_cfg.memory_config_func = copy.deepcopy(memory_config_societyagent)
        if citizen_cfg.memory_distributions is None:
            citizen_cfg.memory_distributions = copy.deepcopy(DEFAULT_DISTRIBUTIONS)
        if citizen_cfg.blocks is None:
            citizen_cfg.blocks = _build_digital_friction_blocks()


def _write_run_metadata(
    agentsociety: AgentSociety,
    *,
    status: str,
    error_message: str = "",
    proto_logical_clock_enabled: bool | None = None,
) -> None:
    if not RUN_METADATA_PATH:
        return
    db_writer = getattr(agentsociety, "_database_writer", None)
    if proto_logical_clock_enabled is None:
        proto_logical_clock_enabled = bool(
            is_proto_logical_clock_enabled(getattr(agentsociety, "_environment", None))
        )
    stage_count = int(len(STAGE_PLAN))
    total_days = int(STAGE_DAYS * stage_count)
    opportunities_per_agent = int(total_days * DECISION_INTERVALS_PER_DAY)
    opportunities_total = int(opportunities_per_agent * AGENT_COUNT)
    payload = {
        "status": _clean_intention(status),
        "error_message": _clean_intention(error_message)[:500],
        "exp_name": EXP_NAME,
        "exp_id": str(getattr(db_writer, "exp_id", "")),
        "world_name": WORLD_NAME,
        "seed": int(EXP_SEED),
        "experiment_mode": EXPERIMENT_MODE,
        "parallel_group_name": PARALLEL_GROUP_NAME,
        "world_batch": list(WORLD_BATCH),
        "pair_index": int(PARALLEL_PAIR_INDEX),
        "pair_seed": int(PARALLEL_PAIR_SEED),
        "world_order": int(PARALLEL_WORLD_ORDER),
        "config_fingerprint": PARALLEL_CONFIG_FINGERPRINT,
        "agent_count": int(AGENT_COUNT),
        "stage_mode": STAGE_MODE,
        "stage_count": stage_count,
        "stage_days": int(STAGE_DAYS),
        "total_days": total_days,
        "decision_interval_minutes": int(EVENT_DECISION_INTERVAL_MINUTES),
        "decision_intervals_per_day": int(DECISION_INTERVALS_PER_DAY),
        "opportunities_per_agent": opportunities_per_agent,
        "opportunities_total": opportunities_total,
        "economy_block_enabled": bool(ECONOMY_BLOCK_ENABLED),
        "economy_binding_audit_strict": bool(ECONOMY_BINDING_AUDIT_STRICT),
        "proto_logical_clock_enabled": bool(proto_logical_clock_enabled),
        "agent_plan_prompt_profile": AGENT_PLAN_PROMPT_PROFILE,
        "proto_task_entry_mode": RUNTIME_CONFIG.proto_task_entry_mode,
        "proto_mobile_intention_rerank_top_k": (
            RUNTIME_CONFIG.proto_mobile_intention_rerank_top_k
        ),
        "proto_mobile_intention_rerank_schedule_path": (
            RUNTIME_CONFIG.proto_mobile_intention_rerank_schedule_path
        ),
        "proto_mobile_intention_rerank_schedule_role": (
            RUNTIME_CONFIG.proto_mobile_intention_rerank_schedule_role
        ),
        "proto_mobile_intention_rerank_run_id": (
            RUNTIME_CONFIG.proto_mobile_intention_rerank_run_id
        ),
        "written_at": datetime.now().isoformat(timespec="seconds"),
    }
    metadata_path = Path(RUN_METADATA_PATH)
    try:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        return


def _best_effort_ray_shutdown() -> None:
    try:
        import ray  # type: ignore
    except Exception:
        return
    try:
        if ray.is_initialized():
            ray.shutdown()
    except Exception:
        return


async def main():
    agentsociety = AgentSociety.create(config)
    run_status = "failed"
    run_error_message = ""
    logical_clock_enabled = False
    try:
        await agentsociety.init()
        if PROTO_LOGICAL_CLOCK_ENABLED:
            if EXPERIMENT_ENGINE != "proto":
                LOGGER.warning(
                    "Ignoring PROTO_LOGICAL_CLOCK_ENABLED because EXPERIMENT_ENGINE=%s",
                    EXPERIMENT_ENGINE,
                )
            else:
                enable_proto_logical_clock(agentsociety)
        logical_clock_enabled = bool(
            is_proto_logical_clock_enabled(getattr(agentsociety, "_environment", None))
        )
        await agentsociety.run()
        run_status = "ok"
    except Exception as exc:
        run_error_message = str(exc)
        raise
    finally:
        close_timed_out = False
        close_failed = False
        close_error_message = ""
        close_timeout_seconds = int(CLOSE_TIMEOUT_SECONDS)
        if close_timeout_seconds > 0:
            close_task = asyncio.create_task(agentsociety.close())
            try:
                await asyncio.wait_for(close_task, timeout=float(close_timeout_seconds))
            except asyncio.TimeoutError:
                close_timed_out = True
                close_error_message = (
                    f"agentsociety.close timeout after {close_timeout_seconds}s"
                )
                close_task.cancel()
                try:
                    await asyncio.wait_for(
                        close_task,
                        timeout=float(CLOSE_TIMEOUT_CANCEL_WAIT_SECONDS),
                    )
                except Exception:
                    pass
            except Exception as close_exc:
                close_failed = True
                close_error_message = f"agentsociety.close failed: {close_exc}"
        else:
            try:
                await agentsociety.close()
            except Exception as close_exc:
                close_failed = True
                close_error_message = f"agentsociety.close failed: {close_exc}"

        close_should_fail_process = (
            run_status == "ok" and (close_timed_out or close_failed)
        )
        if close_timed_out:
            LOGGER.error(close_error_message)
            if run_status == "ok":
                run_status = "failed_close_timeout"
        elif close_failed:
            LOGGER.error(close_error_message)
            if run_status == "ok":
                run_status = "failed_close_error"

        if close_error_message:
            if run_error_message:
                if close_error_message not in run_error_message:
                    run_error_message = (
                        f"{run_error_message}; {close_error_message}"
                    )
            else:
                run_error_message = close_error_message

        _write_run_metadata(
            agentsociety,
            status=run_status,
            error_message=run_error_message,
            proto_logical_clock_enabled=logical_clock_enabled,
        )
        if RAY_SHUTDOWN_ON_FINISH:
            _best_effort_ray_shutdown()
        if EXPERIMENT_MODE == "parallel_worlds" and PARALLEL_FORCE_EXIT_ON_FINISH:
            exit_code = 0 if run_status == "ok" else 1
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(exit_code)
        if close_should_fail_process:
            raise RuntimeError(close_error_message)


if __name__ == "__main__":
    asyncio.run(main())
