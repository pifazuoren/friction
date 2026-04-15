import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


KEYWORDS = {
    "negative": [
        "anxious",
        "frustrated",
        "failed",
        "stuck",
        "worried",
        "helpless",
        "scam",
        "fraud",
        "mistake",
        "confused",
    ],
    "positive": [
        "success",
        "successful",
        "completed",
        "resolved",
        "smooth",
        "easy",
        "clear",
        "relief",
    ],
    "help_request": [
        "help",
        "support",
        "ask",
        "asked",
        "family",
        "community",
        "customer service",
        "call",
    ],
    "fraud_risk": [
        "scam",
        "fraud",
        "risk",
        "misled",
        "tricked",
        "charged",
        "payment",
    ],
    "failure": [
        "failed",
        "failure",
        "didn't work",
        "couldn't",
        "unable",
        "repeat",
    ],
    "success": ["success", "successful", "completed", "done"],
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(word in text for word in keywords)


def analyze_dialogs(db_path: Path, exp_id: str, out_dir: Path) -> None:
    prefix = f"as_{exp_id.replace('-', '_')}_"
    table = f"{prefix}agent_dialog"

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    rows = cur.execute(f"SELECT day, content FROM {table}").fetchall()
    conn.close()

    day_counts = defaultdict(lambda: Counter())
    keyword_freq = Counter()

    for day, content in rows:
        text = str(content)
        for category, words in KEYWORDS.items():
            if _contains_any(text, words):
                day_counts[int(day)][category] += 1
        for words in KEYWORDS.values():
            for word in words:
                if word in text:
                    keyword_freq[word] += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    day_csv = out_dir / "dialog_keyword_counts_by_day.csv"
    top_csv = out_dir / "dialog_keyword_top.csv"

    categories = list(KEYWORDS.keys())
    with day_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day", *categories])
        for day in sorted(day_counts.keys()):
            row = [day] + [day_counts[day].get(c, 0) for c in categories]
            writer.writerow(row)

    with top_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["keyword", "count"])
        for word, count in keyword_freq.most_common():
            writer.writerow([word, count])


def analyze_artifacts_events(artifacts_path: Path, out_dir: Path) -> None:
    if not artifacts_path.exists():
        return
    with artifacts_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    stage_rows = []
    agent_rows = []
    for stage_idx in (1, 2, 3):
        key = f"stage_{stage_idx}_events"
        events = data.get(key, {})
        stage_counts = Counter()
        for agent_id, logs in events.items():
            for item in logs:
                outcome = item.get("outcome", "unknown")
                stage_counts[outcome] += 1
                agent_rows.append(
                    [
                        stage_idx,
                        agent_id,
                        item.get("day", ""),
                        item.get("t", ""),
                        item.get("scenario", ""),
                        outcome,
                        item.get("message", ""),
                    ]
                )
        stage_rows.append(
            [
                stage_idx,
                stage_counts.get("negative", 0),
                stage_counts.get("positive", 0),
                stage_counts.get("unknown", 0),
            ]
        )

    stage_csv = out_dir / "event_log_stage_counts.csv"
    detail_csv = out_dir / "event_log_detail.csv"

    with stage_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stage", "negative_count", "positive_count", "unknown_count"])
        writer.writerows(stage_rows)

    with detail_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["stage", "agent_id", "day", "t", "scenario", "outcome", "message"]
        )
        writer.writerows(agent_rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keyword-based dialog analysis for process indicators."
    )
    parser.add_argument("--exp-id", required=True, help="Experiment ID")
    parser.add_argument(
        "--db-path",
        default="/Users/pifazuoren/Downloads/AgentSociety-main/agentsociety_data/sqlite.db",
        help="Path to sqlite.db",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (defaults to experiment folder)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = (
            Path("/Users/pifazuoren/Downloads/AgentSociety-main/agentsociety_data/exps")
            / args.exp_id
        )

    analyze_dialogs(db_path, args.exp_id, out_dir)
    artifacts_path = (
        Path("/Users/pifazuoren/Downloads/AgentSociety-main/agentsociety_data/exps")
        / args.exp_id
        / "artifacts.json"
    )
    analyze_artifacts_events(artifacts_path, out_dir)
    print("exported", str(out_dir / "dialog_keyword_counts_by_day.csv"))
    print("exported", str(out_dir / "dialog_keyword_top.csv"))
    print("exported", str(out_dir / "event_log_stage_counts.csv"))
    print("exported", str(out_dir / "event_log_detail.csv"))


if __name__ == "__main__":
    main()
