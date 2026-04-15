import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import yaml


def _load_latest_exp_id(home_dir: Path) -> str:
    exp_files = list(home_dir.glob("exps/**/experiment_info.yaml"))
    if not exp_files:
        raise FileNotFoundError(
            f"No experiment_info.yaml found under {home_dir}/exps"
        )
    exp_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    with exp_files[0].open("r", encoding="utf-8") as f:
        info = yaml.safe_load(f)
    exp_id = info.get("id")
    if not exp_id:
        raise ValueError("exp_id not found in experiment_info.yaml")
    return exp_id


def _table_name(exp_id: str, suffix: str) -> str:
    return f"as_{exp_id.replace('-', '_')}_{suffix}"


def _load_json(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            parsed: Any = json.loads(value)
        except json.JSONDecodeError:
            return {}
        for _ in range(2):
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except json.JSONDecodeError:
                    break
        if isinstance(parsed, (dict, list)):
            return parsed
        return {}
    return {}


SURVEY_FIELDS = [
    "tech_acceptance",
    "trust_in_apps",
    "avoidance_tendency",
]


def _extract_survey_answers(payload: Any) -> list[float]:
    answers: list[float] = []

    def _parse_entry(entry: Any) -> Any:
        if isinstance(entry, dict):
            for key in SURVEY_FIELDS:
                if key in entry:
                    return entry[key]
            for key in ("answer", "rating", "value"):
                if key in entry:
                    return entry[key]
            return None
        if isinstance(entry, str):
            try:
                parsed = json.loads(entry)
            except json.JSONDecodeError:
                return None
            return _parse_entry(parsed)
        return None

    if isinstance(payload, list):
        for entry in payload:
            value = _parse_entry(entry)
            if value is None:
                continue
            try:
                answers.append(float(value))
            except (TypeError, ValueError):
                continue
    else:
        value = _parse_entry(payload)
        if value is not None:
            try:
                answers.append(float(value))
            except (TypeError, ValueError):
                pass
    return answers


def _latest_status_per_day(
    rows: Iterable[Tuple[int, int, float, Any]]
) -> Dict[Tuple[int, int], Dict[str, Any]]:
    latest: Dict[Tuple[int, int], Tuple[float, Dict[str, Any]]] = {}
    for agent_id, day, t, status in rows:
        payload = _load_json(status)
        if not isinstance(payload, dict):
            continue
        key = (int(agent_id), int(day))
        if key not in latest or float(t) > latest[key][0]:
            latest[key] = (float(t), payload)
    return {k: v[1] for k, v in latest.items()}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MVP results to CSV")
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
        help="Experiment ID (default: latest in <home_dir>/exps)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: <home_dir>/exports/<exp_id>)",
    )
    args = parser.parse_args()

    home_dir = Path(args.home_dir)
    db_path = Path(args.db) if args.db else home_dir / "sqlite.db"
    if not db_path.exists():
        raise FileNotFoundError(f"sqlite db not found: {db_path}")

    exp_id = args.exp_id or _load_latest_exp_id(home_dir)
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else home_dir / "exports" / exp_id
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = {
        "agent_status": _table_name(exp_id, "agent_status"),
        "agent_survey": _table_name(exp_id, "agent_survey"),
        "agent_profile": _table_name(exp_id, "agent_profile"),
        "agent_dialog": _table_name(exp_id, "agent_dialog"),
        "global_prompt": _table_name(exp_id, "global_prompt"),
        "mvp_status": _table_name(exp_id, "mvp_status"),
        "mvp_decision_attempt": _table_name(exp_id, "mvp_decision_attempt"),
    }

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Export survey daily averages
    day_values: Dict[int, Dict[str, list[float]]] = {}
    for day, result in cur.execute(
        f"SELECT day, result FROM {tables['agent_survey']}"
    ).fetchall():
        payload = _load_json(result)
        answers = _extract_survey_answers(payload)
        if not answers:
            continue
        for idx, value in enumerate(answers):
            if idx >= len(SURVEY_FIELDS):
                break
            key = SURVEY_FIELDS[idx]
            day_values.setdefault(int(day), {}).setdefault(key, []).append(value)

    survey_csv = out_dir / "survey_daily_avg.csv"
    with survey_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day"] + [f"{key}_avg" for key in SURVEY_FIELDS])
        for day in sorted(day_values):
            row = [day]
            for key in SURVEY_FIELDS:
                row.append(round(_mean(day_values[day].get(key, [])), 4))
            writer.writerow(row)

    # Export latest status per day metrics
    status_rows = cur.execute(
        f"SELECT id, day, t, status FROM {tables['agent_status']}"
    ).fetchall()
    latest = _latest_status_per_day(status_rows)

    metrics = [
        "helplessness_score",
        "trust_in_apps",
        "avoidance_tendency",
    ]
    process_metrics = [
        "negative_event_count",
        "intercept_count",
        "help_request_count",
        "success_count",
        "failure_count",
    ]
    by_day: Dict[int, Dict[str, list[float]]] = {}
    for (agent_id, day), payload in latest.items():
        day_bucket = by_day.setdefault(int(day), {})
        for key in metrics + process_metrics:
            value = payload.get(key)
            if value is None:
                continue
            day_bucket.setdefault(key, []).append(float(value))

    status_csv = out_dir / "status_daily_avg.csv"
    with status_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day"] + metrics)
        for day in sorted(by_day):
            row = [day] + [round(_mean(by_day[day].get(k, [])), 4) for k in metrics]
            writer.writerow(row)

    process_csv = out_dir / "process_daily_avg.csv"
    with process_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day"] + process_metrics)
        for day in sorted(by_day):
            row = [day] + [
                round(_mean(by_day[day].get(k, [])), 4) for k in process_metrics
            ]
            writer.writerow(row)

    # Export profiles
    profile_csv = out_dir / "profiles.csv"
    rows = cur.execute(
        f"SELECT id, name, profile FROM {tables['agent_profile']}"
    ).fetchall()
    with profile_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "profile"])
        for row in rows:
            writer.writerow(row)

    # Export global prompts (raw)
    prompt_csv = out_dir / "global_prompt.csv"
    rows = cur.execute(
        f"SELECT day, t, prompt FROM {tables['global_prompt']}"
    ).fetchall()
    with prompt_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "t", "prompt"])
        for row in rows:
            writer.writerow(row)

    # Export dialogs (raw)
    dialog_csv = out_dir / "agent_dialog.csv"
    rows = cur.execute(
        f"SELECT id, day, t, type, speaker, content FROM {tables['agent_dialog']}"
    ).fetchall()
    with dialog_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "day", "t", "type", "speaker", "content"])
        for row in rows:
            writer.writerow(row)

    # Export MVP step-level status if available
    table_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tables["mvp_status"],),
    ).fetchone()
    if table_exists:
        mvp_csv = out_dir / "mvp_status_step.csv"
        rows = cur.execute(
            f"""
            SELECT agent_id, day, t, intention,
                   helplessness_score, trust_in_apps, avoidance_tendency,
                   negative_event_count, intercept_count, help_request_count,
                   success_count, failure_count, status_json
            FROM {tables['mvp_status']}
            """
        ).fetchall()
        with mvp_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "agent_id",
                    "day",
                    "t",
                    "intention",
                    "helplessness_score",
                    "trust_in_apps",
                    "avoidance_tendency",
                    "negative_event_count",
                    "intercept_count",
                    "help_request_count",
                    "success_count",
                    "failure_count",
                    "status_json",
                ]
            )
            for row in rows:
                writer.writerow(row)

    # Export decision attempts if available (one row per decision try)
    attempt_table_exists = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (tables["mvp_decision_attempt"],),
    ).fetchone()
    if attempt_table_exists:
        attempt_csv = out_dir / "mvp_decision_attempt_step.csv"
        rows = cur.execute(
            f"""
            SELECT attempt_uid, agent_id, day, t, step,
                   stage_name, stage_index, intention, need,
                   step_type, step_intention, status_text, step_eval_text, step_outcome,
                   scenario, scenario_entry_reason,
                   digital_exposure, digital_from_action, digital_from_status,
                   digital_from_intention, digital_from_signal,
                   emitted, outcome, roll,
                   p_negative_interval, p_positive_interval, total_event_prob,
                   hazard_p_total, llm_status, decision_json
            FROM {tables['mvp_decision_attempt']}
            """
        ).fetchall()
        with attempt_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "attempt_uid",
                    "agent_id",
                    "day",
                    "t",
                    "step",
                    "stage_name",
                    "stage_index",
                    "intention",
                    "need",
                    "step_type",
                    "step_intention",
                    "status_text",
                    "step_eval_text",
                    "step_outcome",
                    "scenario",
                    "scenario_entry_reason",
                    "digital_exposure",
                    "digital_from_action",
                    "digital_from_status",
                    "digital_from_intention",
                    "digital_from_signal",
                    "emitted",
                    "outcome",
                    "roll",
                    "p_negative_interval",
                    "p_positive_interval",
                    "total_event_prob",
                    "hazard_p_total",
                    "llm_status",
                    "decision_json",
                ]
            )
            for row in rows:
                writer.writerow(row)

    conn.close()

    print("export_dir", str(out_dir))
    print("files", [p.name for p in out_dir.iterdir() if p.is_file()])


if __name__ == "__main__":
    main()
