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


def _read_artifacts_summary(artifacts_path: Path) -> dict[str, Any]:
    if not artifacts_path.exists():
        return {
            "artifacts_found": False,
            "decision_count": 0,
            "source_counts": {},
            "fallback_reason_counts": {},
            "alpha_stats": {},
        }

    with artifacts_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    source_counts: Counter[str] = Counter()
    fallback_counts: Counter[str] = Counter()
    alphas: list[float] = []

    for key, value in payload.items():
        if not key.endswith("_events"):
            continue
        if not isinstance(value, dict):
            continue
        for _, events in value.items():
            if not isinstance(events, list):
                continue
            for item in events:
                if not isinstance(item, dict):
                    continue
                decision = item.get("decision")
                if not isinstance(decision, dict):
                    continue
                source = str(decision.get("source", "unknown"))
                source_counts[source] += 1
                if source == "rule_fallback":
                    reason = str(decision.get("fallback_reason", "unknown"))
                    fallback_counts[reason] += 1
                try:
                    alphas.append(float(decision.get("alpha", 0.0)))
                except (TypeError, ValueError):
                    pass

    alpha_stats: dict[str, float] = {}
    if alphas:
        positive = [a for a in alphas if a > 0]
        alpha_stats = {
            "min": min(alphas),
            "max": max(alphas),
            "mean": sum(alphas) / len(alphas),
            "positive_count": float(len(positive)),
            "positive_ratio": float(len(positive) / len(alphas)),
        }

    return {
        "artifacts_found": True,
        "decision_count": int(sum(source_counts.values())),
        "source_counts": dict(source_counts),
        "fallback_reason_counts": dict(fallback_counts),
        "alpha_stats": alpha_stats,
    }


def _read_metric_summary(db_path: Path, exp_id: str) -> dict[str, float]:
    keys = [
        "step.decision_attempt_count",
        "step.event_emitted_count",
        "step.no_event_count",
        "step.hybrid_applied_count",
        "step.rule_applied_count",
        "step.rule_fallback_count",
        "step.scenario_skip_count",
        "step.llm_cache_hit_count",
        "step.llm_query_success_count",
        "step.smoke_forced_event",
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

    result: dict[str, float] = {}
    for key, value in rows:
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            result[str(key)] = 0.0
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quick checker for hybrid decision branch coverage."
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

    summary = {
        "exp_id": exp_id,
        "artifacts_path": str(artifacts_path),
        "artifacts_summary": _read_artifacts_summary(artifacts_path),
        "metric_summary": _read_metric_summary(db_path, exp_id),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
