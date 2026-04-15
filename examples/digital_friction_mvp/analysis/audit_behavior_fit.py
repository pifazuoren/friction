#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "sleep_rest": (r"\bsleep\b", r"\bbed\b", r"\brest\b", r"\brelax\b", r"\bnap\b", r"\bpajamas?\b"),
    "meal_cooking": (
        r"\bcook\b",
        r"\bcooking\b",
        r"\bmeal\b",
        r"\bbreakfast\b",
        r"\blunch\b",
        r"\bdinner\b",
        r"\bingredients?\b",
        r"\bkitchen\b",
        r"\btea\b",
        r"\bdishes\b",
    ),
    "home_chores": (
        r"\bclean\b",
        r"\blaundry\b",
        r"\borgani[sz]e\b",
        r"\btemperature\b",
        r"\blights?\b",
        r"\broom\b",
        r"\btable\b",
    ),
    "mobility": (
        r"\btravel\b",
        r"\bcommute\b",
        r"\bwalk\b",
        r"\bbus\b",
        r"\bsubway\b",
        r"\btaxi\b",
        r"\bride\b",
        r"\bshopping\b",
        r"\bgo out\b",
        r"\broute\b",
    ),
    "digital": (
        r"\bapp\b",
        r"\bpayment\b",
        r"\blogin\b",
        r"\bcaptcha\b",
        r"\bonline\b",
        r"\bphone\b",
        r"\bmessage\b",
        r"\bverify\b",
        r"\bwechat\b",
        r"\balipay\b",
    ),
    "health": (r"\bexercise\b", r"\bstretch\b", r"\bmedicine\b", r"\bhospital\b", r"\bclinic\b", r"\bhealth\b"),
}


@dataclass
class AuditResult:
    total_rows: int
    unique_steps: int
    expected_agents: int
    rows_per_step_min: int
    rows_per_step_max: int
    core_agent_ids: list[int]
    extra_agent_counts: dict[int, int]
    swapped_step_count: int
    bucket_counts: dict[str, int]
    digital_step_count: int
    mobility_step_count: int
    digital_action_count: int
    mobility_action_count: int
    unique_action_count: int
    adjacent_repeat_ratio_avg: float
    task_fit_score: float
    task_fit_level: str
    event_count: int | None
    event_scenario_counts: dict[str, int]


def _compile_patterns() -> dict[str, list[re.Pattern[str]]]:
    return {
        name: [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]
        for name, patterns in CATEGORY_PATTERNS.items()
    }


COMPILED_PATTERNS = _compile_patterns()


def bucket_action(action: str) -> str:
    lowered = action.lower()
    for bucket_name, patterns in COMPILED_PATTERNS.items():
        if any(pattern.search(lowered) for pattern in patterns):
            return bucket_name
    return "other"


def load_long_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(
                {
                    "day": int(float(row["day"])),
                    "t": float(row["t"]),
                    "parent_id": int(row["parent_id"]),
                    "action": (row.get("action") or "").strip(),
                    "status": (row.get("status") or "").strip(),
                }
            )
    rows.sort(key=lambda item: (item["day"], item["t"], item["parent_id"]))
    return rows


def load_event_summary(artifacts_path: Path | None) -> tuple[int | None, dict[str, int]]:
    if artifacts_path is None or not artifacts_path.exists():
        return None, {}
    obj = json.loads(artifacts_path.read_text(encoding="utf-8"))
    stage_keys = ("stage_1_events", "stage_2_events", "stage_3_events")
    total_count = 0
    scenario_counter: Counter[str] = Counter()
    for stage_key in stage_keys:
        stage_payload = obj.get(stage_key, {})
        if not isinstance(stage_payload, dict):
            continue
        for event_list in stage_payload.values():
            if not isinstance(event_list, list):
                continue
            total_count += len(event_list)
            for event in event_list:
                scenario_name = str(event.get("scenario", "unknown"))
                scenario_counter[scenario_name] += 1
    return total_count, dict(scenario_counter)


def compute_task_fit_score(
    rows_per_step_min: int,
    rows_per_step_max: int,
    expected_agents: int,
    digital_step_rate: float,
    mobility_step_rate: float,
    swapped_step_count: int,
    total_steps: int,
) -> tuple[float, str]:
    score = 0.0
    if rows_per_step_min == expected_agents and rows_per_step_max == expected_agents:
        score += 2.0
    if digital_step_rate >= 0.25:
        score += 4.0
    elif digital_step_rate >= 0.15:
        score += 3.0
    elif digital_step_rate >= 0.08:
        score += 2.0
    elif digital_step_rate >= 0.03:
        score += 1.0
    if mobility_step_rate >= 0.15:
        score += 2.0
    elif mobility_step_rate >= 0.06:
        score += 1.0
    if total_steps <= 0:
        continuity = 0.0
    else:
        swap_rate = swapped_step_count / total_steps
        if swap_rate <= 0.01:
            continuity = 2.0
        elif swap_rate <= 0.10:
            continuity = 1.0
        else:
            continuity = 0.0
    score += continuity
    if score >= 8:
        level = "high"
    elif score >= 5:
        level = "medium"
    else:
        level = "low"
    return round(score, 2), level


def audit(rows: list[dict[str, Any]], artifacts_path: Path | None = None) -> AuditResult:
    row_count = len(rows)
    step_counts: Counter[tuple[int, float]] = Counter((row["day"], row["t"]) for row in rows)
    unique_steps = len(step_counts)
    rows_per_step_min = min(step_counts.values()) if step_counts else 0
    rows_per_step_max = max(step_counts.values()) if step_counts else 0
    parent_counts = Counter(row["parent_id"] for row in rows)
    core_agent_ids = [parent_id for parent_id, _ in parent_counts.most_common(6)]
    expected_agents = len(core_agent_ids)
    extra_agent_counts = {
        parent_id: count for parent_id, count in parent_counts.items() if parent_id not in core_agent_ids
    }
    swapped_step_count = 0
    core_set = set(core_agent_ids)
    for day, t in step_counts:
        step_parent_ids = {row["parent_id"] for row in rows if row["day"] == day and row["t"] == t}
        missing_core = bool(core_set - step_parent_ids)
        contains_extra = bool(step_parent_ids - core_set)
        if missing_core and contains_extra:
            swapped_step_count += 1
    bucket_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    step_has_digital: set[tuple[int, float]] = set()
    step_has_mobility: set[tuple[int, float]] = set()
    repeat_ratios: list[float] = []
    grouped_by_core: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        action = row["action"]
        bucket_name = bucket_action(action)
        bucket_counter[bucket_name] += 1
        action_counter[action] += 1
        step_key = (row["day"], row["t"])
        if bucket_name == "digital":
            step_has_digital.add(step_key)
        if bucket_name == "mobility":
            step_has_mobility.add(step_key)
        if row["parent_id"] in core_set:
            grouped_by_core[row["parent_id"]].append(row)
    for parent_id in core_agent_ids:
        sequence = sorted(grouped_by_core.get(parent_id, []), key=lambda item: (item["day"], item["t"]))
        if len(sequence) <= 1:
            repeat_ratios.append(0.0)
            continue
        repeat_count = 0
        for idx in range(len(sequence) - 1):
            if sequence[idx]["action"] == sequence[idx + 1]["action"]:
                repeat_count += 1
        repeat_ratios.append(repeat_count / (len(sequence) - 1))
    event_count, event_scenario_counts = load_event_summary(artifacts_path)
    digital_step_rate = len(step_has_digital) / unique_steps if unique_steps else 0.0
    mobility_step_rate = len(step_has_mobility) / unique_steps if unique_steps else 0.0
    score, level = compute_task_fit_score(
        rows_per_step_min=rows_per_step_min,
        rows_per_step_max=rows_per_step_max,
        expected_agents=expected_agents,
        digital_step_rate=digital_step_rate,
        mobility_step_rate=mobility_step_rate,
        swapped_step_count=swapped_step_count,
        total_steps=unique_steps,
    )
    return AuditResult(
        total_rows=row_count,
        unique_steps=unique_steps,
        expected_agents=expected_agents,
        rows_per_step_min=rows_per_step_min,
        rows_per_step_max=rows_per_step_max,
        core_agent_ids=sorted(core_agent_ids),
        extra_agent_counts=dict(sorted(extra_agent_counts.items())),
        swapped_step_count=swapped_step_count,
        bucket_counts=dict(bucket_counter),
        digital_step_count=len(step_has_digital),
        mobility_step_count=len(step_has_mobility),
        digital_action_count=bucket_counter.get("digital", 0),
        mobility_action_count=bucket_counter.get("mobility", 0),
        unique_action_count=len(action_counter),
        adjacent_repeat_ratio_avg=sum(repeat_ratios) / len(repeat_ratios) if repeat_ratios else 0.0,
        task_fit_score=score,
        task_fit_level=level,
        event_count=event_count,
        event_scenario_counts=event_scenario_counts,
    )


def render_markdown(result: AuditResult) -> str:
    bucket_total = sum(result.bucket_counts.values()) or 1
    digital_step_rate = result.digital_step_count / max(1, result.unique_steps)
    mobility_step_rate = result.mobility_step_count / max(1, result.unique_steps)
    lines = [
        "# 行为合理性与任务匹配审计",
        "",
        "## 1) 结构完整性",
        f"- 行为记录总数：`{result.total_rows}`",
        f"- step 数：`{result.unique_steps}`",
        f"- 每 step 记录数：`min={result.rows_per_step_min}, max={result.rows_per_step_max}`（目标 `{result.expected_agents}`）",
        f"- 核心 agent IDs：`{result.core_agent_ids}`",
        f"- 额外 ID 及次数：`{result.extra_agent_counts}`",
        f"- 核心/额外替换步数：`{result.swapped_step_count}`",
        "",
        "## 2) 行为主题分布",
    ]
    for key, value in sorted(result.bucket_counts.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- `{key}`: `{value}` ({value / bucket_total:.2%})")
    lines.extend(
        [
            "",
            "## 3) 数字任务暴露",
            f"- 数字动作条数：`{result.digital_action_count}`",
            f"- mobility 动作条数：`{result.mobility_action_count}`",
            f"- 含数字动作的 step：`{result.digital_step_count}/{result.unique_steps}` ({digital_step_rate:.2%})",
            f"- 含 mobility 动作的 step：`{result.mobility_step_count}/{result.unique_steps}` ({mobility_step_rate:.2%})",
            "",
            "## 4) 行为稳定性",
            f"- 唯一动作文本数：`{result.unique_action_count}`",
            f"- 邻接动作重复率（核心 agent 平均）：`{result.adjacent_repeat_ratio_avg:.2%}`",
            "",
            "## 5) 任务匹配评分",
            f"- 评分：`{result.task_fit_score}/10`",
            f"- 等级：`{result.task_fit_level}`",
        ]
    )
    if result.event_count is not None:
        lines.extend(
            [
                "",
                "## 6) 事件触发概况（来自 artifacts）",
                f"- 事件总数：`{result.event_count}`",
                f"- 场景分布：`{result.event_scenario_counts}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 7) 建议",
            "- 如果数字 step 占比 < 10%，优先提高数字任务生成占比（在日程/意图层注入线上任务）。",
            "- 如果 mobility step 占比 < 10%，增加“出行刚需”窗口（买药、就医、政务办理）。",
            "- 如果存在核心/额外 ID 替换，做 ID 映射稳定化，避免纵向追踪误差。",
            "- 对事件触发，优先提高 `pre_match` 命中与 fallback 触发率，再调命中概率。",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit long-view step actions for behavior rationality and task fit.")
    parser.add_argument("--long-csv", required=True, type=Path, help="Path to step_actions_*_long.csv")
    parser.add_argument("--artifacts", type=Path, default=None, help="Optional artifacts.json path")
    parser.add_argument("--out", type=Path, default=None, help="Optional markdown output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_long_csv(args.long_csv)
    result = audit(rows, args.artifacts)
    report = render_markdown(result)
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
        print(f"saved report -> {args.out}")
    print(report)


if __name__ == "__main__":
    main()
