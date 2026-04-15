from __future__ import annotations

from typing import Any

_SUPPORT_SEEKING_TOKENS = ("依赖", "陪伴", "求助", "现场帮助", "纽带")
_CAUTIOUS_TOKENS = ("谨慎", "保守", "风险回避", "警惕")
_PROACTIVE_TOKENS = ("主动", "探索", "效率", "乐观", "乐观适应", "愿意学习")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def age_bucket(value: Any) -> str:
    age = _safe_int(value, -1)
    if age < 0:
        return "unknown"
    if age < 65:
        return "lt65"
    if age < 75:
        return "65_74"
    return "75plus"


def persona_bucket(persona: Any, background_summary: Any = None) -> str:
    text = f"{persona or ''} {background_summary or ''}".strip()
    if not text:
        return "unknown"
    if any(token in text for token in _SUPPORT_SEEKING_TOKENS):
        return "support_seeking"
    if any(token in text for token in _CAUTIOUS_TOKENS):
        return "cautious"
    if any(token in text for token in _PROACTIVE_TOKENS):
        return "proactive"
    return "neutral"
