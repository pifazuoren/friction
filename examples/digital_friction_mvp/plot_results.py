import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml


SURVEY_FIELDS = [
    "tech_acceptance",
    "trust_in_apps",
    "avoidance_tendency",
]


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
        # Handle double-encoded JSON strings
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


def _fetch_survey_curve(
    conn: sqlite3.Connection, exp_id: str
) -> Dict[str, Dict[int, float]]:
    table = _table_name(exp_id, "agent_survey")
    cursor = conn.execute(f"SELECT day, result FROM {table}")
    day_values: Dict[int, Dict[str, list[float]]] = {}
    for day, result in cursor.fetchall():
        payload = _load_json(result)
        answers = _extract_survey_answers(payload)
        if not answers:
            continue
        for idx, value in enumerate(answers):
            if idx >= len(SURVEY_FIELDS):
                break
            key = SURVEY_FIELDS[idx]
            day_values.setdefault(int(day), {}).setdefault(key, []).append(value)
    curves: Dict[str, Dict[int, float]] = {}
    for key in SURVEY_FIELDS:
        curves[key] = {
            day: sum(values[key]) / len(values[key])
            for day, values in sorted(day_values.items())
            if values.get(key)
        }
    return curves


def _fetch_status_curves(
    conn: sqlite3.Connection, exp_id: str
) -> Dict[str, Dict[int, float]]:
    table = _table_name(exp_id, "agent_status")
    cursor = conn.execute(f"SELECT id, day, t, status FROM {table}")
    latest: Dict[Tuple[int, int], Tuple[float, Dict[str, Any]]] = {}
    for agent_id, day, t, status in cursor.fetchall():
        payload = _load_json(status)
        if not isinstance(payload, dict):
            continue
        key = (int(agent_id), int(day))
        if key not in latest or float(t) > latest[key][0]:
            latest[key] = (float(t), payload)
    metrics = {
        "helplessness_score": {},
        "trust_in_apps": {},
        "avoidance_tendency": {},
    }
    buckets = {k: {} for k in metrics.keys()}
    for (_, day), (_, payload) in latest.items():
        for metric in metrics.keys():
            value = payload.get(metric)
            if value is None:
                continue
            buckets[metric].setdefault(day, []).append(float(value))
    for metric, day_values in buckets.items():
        metrics[metric] = {
            day: sum(values) / len(values)
            for day, values in sorted(day_values.items())
        }
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Plot MVP curves from sqlite")
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
        "--out",
        default="mvp_curves.png",
        help="Output image file (default: mvp_curves.png)",
    )
    args = parser.parse_args()

    home_dir = Path(args.home_dir)
    db_path = Path(args.db) if args.db else home_dir / "sqlite.db"
    if not db_path.exists():
        raise FileNotFoundError(f"sqlite db not found: {db_path}")

    exp_id = args.exp_id or _load_latest_exp_id(home_dir)
    conn = sqlite3.connect(str(db_path))
    try:
        survey_curves = _fetch_survey_curve(conn, exp_id)
        status_curves = _fetch_status_curves(conn, exp_id)
    finally:
        conn.close()

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5))
    if survey_curves:
        for key, curve in survey_curves.items():
            if not curve:
                continue
            days = list(curve.keys())
            values = list(curve.values())
            ax.plot(days, values, marker="o", label=key)
    for metric, curve in status_curves.items():
        if not curve:
            continue
        days = list(curve.keys())
        values = list(curve.values())
        ax.plot(days, values, marker="o", label=metric)

    ax.set_xlabel("day")
    ax.set_ylabel("score (avg)")
    ax.set_title(f"MVP curves (exp_id={exp_id})")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"Saved plot to: {args.out}")


if __name__ == "__main__":
    main()
