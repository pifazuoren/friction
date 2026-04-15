#!/usr/bin/env python3
import argparse
import csv
import json
import sqlite3
from pathlib import Path


def parse_status(raw):
    if raw is None:
        return ""
    value = raw
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    for _ in range(2):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                break
    return value if isinstance(value, str) else str(value)


def table_exists(cur, name: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def main():
    parser = argparse.ArgumentParser(
        description="导出进入决策尝试样本：intention + action + agent_status.status + emitted/outcome"
    )
    parser.add_argument("exp_id", help="实验编号，例如 6031fbbc-f5c6-4054-8f76-f88f06c81b03")
    parser.add_argument("--db-path", default="agentsociety_data/sqlite.db", help="sqlite 路径")
    parser.add_argument(
        "--out-csv",
        default=None,
        help="输出 CSV 路径（默认自动命名到 examples/digital_friction_mvp/analysis）",
    )
    args = parser.parse_args()

    exp_id = args.exp_id.strip()
    prefix = exp_id.replace("-", "_")

    attempt_table = f"as_{prefix}_mvp_decision_attempt"
    status_table = f"as_{prefix}_agent_status"

    if args.out_csv:
        out_csv = Path(args.out_csv)
    else:
        out_csv = Path(
            f"examples/digital_friction_mvp/analysis/attempt_intention_action_status_outcome_{exp_id[:8]}.csv"
        )

    conn = sqlite3.connect(str(args.db_path))
    cur = conn.cursor()

    if not table_exists(cur, attempt_table):
        raise SystemExit(f"找不到表: {attempt_table}")
    if not table_exists(cur, status_table):
        raise SystemExit(f"找不到表: {status_table}")

    rows = cur.execute(
        f"""
        SELECT
          a.intention,
          s.action,
          s.status,
          a.emitted,
          a.outcome
        FROM {attempt_table} a
        LEFT JOIN {status_table} s
          ON s.id = a.agent_id
         AND s.day = a.day
         AND ABS(s.t - a.t) < 1e-6
        ORDER BY a.day, a.t, a.agent_id
        """
    ).fetchall()

    conn.close()

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["intention", "action", "agent_status_status", "emitted", "outcome"])
        for intention, action, status, emitted, outcome in rows:
            w.writerow([
                intention or "",
                action or "",
                parse_status(status),
                int(emitted) if emitted is not None else 0,
                outcome or "",
            ])

    print(out_csv)


if __name__ == "__main__":
    main()
