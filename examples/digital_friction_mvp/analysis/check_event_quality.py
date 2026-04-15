import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def _latest_exp_id(home_dir: Path) -> str:
    exp_files = list(home_dir.glob("exps/**/experiment_info.yaml"))
    if not exp_files:
        raise FileNotFoundError(f"No experiment_info.yaml found under {home_dir}/exps")
    exp_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    with exp_files[0].open("r", encoding="utf-8") as f:
        info = yaml.safe_load(f) or {}
    exp_id = info.get("id")
    if not exp_id:
        raise ValueError("exp_id not found in latest experiment_info.yaml")
    return str(exp_id)


def _metric_table(exp_id: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_metric"


def _iter_artifact_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for key, value in payload.items():
        if not key.endswith("_events") or not isinstance(value, dict):
            continue
        for _, event_items in value.items():
            if not isinstance(event_items, list):
                continue
            for item in event_items:
                if isinstance(item, dict):
                    events.append(item)
    return events


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _is_reading_hobby_text(text: str) -> bool:
    lowered = str(text).lower()
    tokens = {
        "read",
        "reading",
        "hobby",
        "meditation",
        "book",
        "阅读",
        "看书",
        "爱好",
        "休闲",
    }
    return any(token in lowered for token in tokens)


def _analyze_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(events)
    scenario_counter: Counter[str] = Counter()
    outcome_counter: Counter[str] = Counter()
    entry_reason_counter: Counter[str] = Counter()
    emit_policy_counter: Counter[str] = Counter()
    status_gate_reason_counter: Counter[str] = Counter()

    matched_non_digital = 0
    reading_hobby_info_ad_click = 0
    status_gate_eligible = 0
    status_gate_attempted = 0
    status_gate_hit = 0
    status_gate_override = 0
    status_gate_blocked_from_status = 0
    status_gate_blocked_anchor = 0
    emit_forced_by_policy = 0

    for item in events:
        scenario_name = str(item.get("scenario", "unknown"))
        outcome = str(item.get("outcome", "unknown"))
        scenario_counter[scenario_name] += 1
        outcome_counter[outcome] += 1
        decision = item.get("decision", {})
        if not isinstance(decision, dict):
            decision = {}

        entry_reason = str(decision.get("scenario_entry_reason", "unknown"))
        entry_reason_counter[entry_reason] += 1
        status_gate_reason = str(decision.get("status_gate_reason", "unknown"))
        status_gate_reason_counter[status_gate_reason] += 1
        emit_policy = str(decision.get("emit_policy", "unknown"))
        emit_policy_counter[emit_policy] += 1

        if (
            entry_reason == "matched"
            and not _is_truthy(decision.get("digital_exposure", False))
        ):
            matched_non_digital += 1

        if scenario_name == "info_ad_click":
            step_intention = str(decision.get("step_intention", ""))
            if _is_reading_hobby_text(step_intention):
                reading_hobby_info_ad_click += 1

        if _is_truthy(decision.get("status_gate_eligible", False)):
            status_gate_eligible += 1
        if _is_truthy(decision.get("status_gate_attempted", False)):
            status_gate_attempted += 1
        if _is_truthy(decision.get("status_gate_matched", False)):
            status_gate_hit += 1
        if _is_truthy(decision.get("status_gate_override_applied", False)):
            status_gate_override += 1
        if status_gate_reason == "from_status_false":
            status_gate_blocked_from_status += 1
        if status_gate_reason == "no_anchor":
            status_gate_blocked_anchor += 1

        if _is_truthy(decision.get("emit_forced_by_policy", False)):
            emit_forced_by_policy += 1

    return {
        "total_events": total,
        "scenario_counts": dict(scenario_counter),
        "outcome_counts": dict(outcome_counter),
        "entry_reason_counts": dict(entry_reason_counter),
        "status_gate_reason_counts": dict(status_gate_reason_counter),
        "emit_policy_counts": dict(emit_policy_counter),
        "matched_non_digital_count": matched_non_digital,
        "matched_non_digital_ratio": (
            float(matched_non_digital) / float(total) if total > 0 else 0.0
        ),
        "reading_hobby_info_ad_click_count": reading_hobby_info_ad_click,
        "status_gate_funnel": {
            "eligible": status_gate_eligible,
            "attempted": status_gate_attempted,
            "hit": status_gate_hit,
            "override": status_gate_override,
            "blocked_by_from_status": status_gate_blocked_from_status,
            "blocked_by_anchor": status_gate_blocked_anchor,
            "attempt_rate": (
                float(status_gate_attempted) / float(status_gate_eligible)
                if status_gate_eligible > 0
                else 0.0
            ),
            "hit_rate": (
                float(status_gate_hit) / float(status_gate_attempted)
                if status_gate_attempted > 0
                else 0.0
            ),
        },
        "emit_forced_by_policy_count": emit_forced_by_policy,
    }


def _read_metric_summary(db_path: Path, exp_id: str) -> dict[str, float]:
    keys = [
        "step.decision_attempt_count",
        "step.event_emitted_count",
        "step.no_event_count",
        "step.scenario_alignment_rate",
        "step.status_gate_eligible_count",
        "step.scenario_status_gate_attempt_count",
        "step.scenario_status_gate_hit_count",
        "step.status_gate_override_count",
        "step.status_gate_blocked_from_status_count",
        "step.status_gate_blocked_anchor_count",
        "step.emit_policy_forced_count",
        "step.emit_policy_soft_skip_count",
    ]

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    table = _metric_table(exp_id)
    table_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not table_exists:
        conn.close()
        return {}

    placeholders = ",".join("?" for _ in keys)
    rows = cur.execute(
        f"SELECT key, SUM(value) FROM {table} WHERE key IN ({placeholders}) GROUP BY key",
        keys,
    ).fetchall()
    conn.close()
    summary: dict[str, float] = {}
    for key, value in rows:
        try:
            summary[str(key)] = float(value)
        except (TypeError, ValueError):
            summary[str(key)] = 0.0
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Event quality checker for digital friction experiments."
    )
    parser.add_argument(
        "--home-dir",
        default="./agentsociety_data",
        help="AgentSociety home dir (default: ./agentsociety_data)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to sqlite.db (default: <home_dir>/sqlite.db)",
    )
    parser.add_argument(
        "--exp-id",
        default=None,
        help="Experiment ID (default: latest experiment in <home_dir>/exps)",
    )
    args = parser.parse_args()

    home_dir = Path(args.home_dir)
    db_path = Path(args.db) if args.db else home_dir / "sqlite.db"
    exp_id = args.exp_id or _latest_exp_id(home_dir)
    artifacts_path = home_dir / "exps" / exp_id / "artifacts.json"
    if not artifacts_path.exists():
        raise FileNotFoundError(f"artifacts.json not found: {artifacts_path}")

    with artifacts_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    events = _iter_artifact_events(payload)

    result = {
        "exp_id": exp_id,
        "artifacts_path": str(artifacts_path),
        "event_quality": _analyze_events(events),
        "metric_summary": _read_metric_summary(db_path, exp_id),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
