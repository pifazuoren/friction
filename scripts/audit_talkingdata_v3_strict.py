#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V2_ELDERLY_DIR = REPO_ROOT / "agentsociety_data" / "elderly"
DEFAULT_V3_ELDERLY_DIR = REPO_ROOT / "agentsociety_data" / "elderly_v3"
DEFAULT_V2_10_DIR = DEFAULT_V2_ELDERLY_DIR / "10person"
DEFAULT_V3_10_DIR = DEFAULT_V2_ELDERLY_DIR / "10person_v3"
DEFAULT_OUTPUT_DIR = DEFAULT_V3_ELDERLY_DIR / "audit"

TASK_ELIGIBLE_CONTEXTS = {
    "finance_context",
    "public_service_context",
    "health_service_context",
    "shopping_lifestyle_context",
    "navigation_transport_context",
    "education_work_context",
}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        encoding="utf-8-sig",
        dtype={"device_id": "string", "event_id": "string", "app_id": "string"},
    )


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _event_path(base_dir: Path, prefix: str) -> Path:
    return base_dir / f"talkingdata_elderly_{prefix}_event_app_context.csv"


def _bundle_path(base_dir: Path) -> Path:
    return base_dir / "talkingdata_elderly_10_hourly_app_entry_bundle.csv"


def _context_distribution(v2: pd.DataFrame, v3: pd.DataFrame) -> pd.DataFrame:
    contexts = sorted(set(v2["app_context"]).union(set(v3["app_context"])))
    rows: list[dict[str, Any]] = []
    for context in contexts:
        v2_count = int((v2["app_context"] == context).sum())
        v3_count = int((v3["app_context"] == context).sum())
        rows.append(
            {
                "app_context": context,
                "v2_count": v2_count,
                "v2_share": v2_count / len(v2) if len(v2) else 0.0,
                "v3_count": v3_count,
                "v3_share": v3_count / len(v3) if len(v3) else 0.0,
                "delta_count": v3_count - v2_count,
                "delta_share": (v3_count / len(v3) if len(v3) else 0.0)
                - (v2_count / len(v2) if len(v2) else 0.0),
            }
        )
    return pd.DataFrame(rows).sort_values("delta_count")


def _task_eligible_share(df: pd.DataFrame) -> float:
    return df["task_eligible"].astype(str).str.lower().eq("true").mean()


def _parse_categories_column(df: pd.DataFrame) -> pd.Series:
    return df["categories_json"].map(
        lambda value: [str(item).strip().lower() for item in _json_loads(value, [])]
    )


def _targeted_checks(v2: pd.DataFrame, v3: pd.DataFrame) -> pd.DataFrame:
    definitions = {
        "relatives_only": lambda values: "relatives 1" in values
        and not any(
            marker in values
            for marker in [
                "im",
                "wechat",
                "weibo",
                "qq",
                "tencent",
                "community",
                "social",
                "chat",
                "contacts",
                "forum",
            ]
        ),
        "online_shopping_navigation": lambda values: "online shopping navigation" in values,
        "weak_education_information": lambda values: any(
            marker in values
            for marker in [
                "technology information",
                "science and technology 1",
                "science and technology",
                "financial information",
                "information",
                "technology",
                "science",
            ]
        ),
        "convenience_or_life_service": lambda values: any(
            marker in values for marker in ["convenience services", "life service"]
        ),
        "weather_only": lambda values: "weather" in values and len(values) == 1,
    }

    rows: list[dict[str, Any]] = []
    parsed_by_version = {
        "v2": (v2, _parse_categories_column(v2)),
        "v3": (v3, _parse_categories_column(v3)),
    }
    for check_name, predicate in definitions.items():
        for version, (df, parsed) in parsed_by_version.items():
            mask = parsed.map(predicate)
            sub = df[mask]
            counts = sub["app_context"].value_counts().to_dict()
            rows.append(
                {
                    "check": check_name,
                    "version": version,
                    "row_count": int(len(sub)),
                    "app_context_counts_json": json.dumps(
                        {str(key): int(value) for key, value in counts.items()},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
    return pd.DataFrame(rows)


def _bundle_check(base_dir: Path, version: str) -> tuple[dict[str, Any], pd.DataFrame]:
    bundle = _read_csv(_bundle_path(base_dir))
    bad_sum = 0
    bad_primary = 0
    bad_task_flag = 0
    for row in bundle.itertuples(index=False):
        counts = _json_loads(row.app_context_counts_json, {})
        exposure_sum = sum(int(value) for value in counts.values())
        exposures = int(row.active_event_app_exposures)
        if exposure_sum != exposures:
            bad_sum += 1

        primary_context = str(row.primary_context)
        if exposures == 0:
            if primary_context != "no_app_context":
                bad_primary += 1
        elif primary_context not in counts:
            bad_primary += 1

        expected_task_flag = primary_context in TASK_ELIGIBLE_CONTEXTS
        actual_task_flag = str(row.primary_context_task_eligible).lower() == "true"
        if expected_task_flag != actual_task_flag:
            bad_task_flag += 1

    active_mask = bundle["active"].astype(str).str.lower().eq("true")
    primary_distribution = (
        bundle[active_mask]["primary_context"]
        .value_counts()
        .rename_axis("primary_context")
        .reset_index(name="active_hour_count")
    )
    primary_distribution.insert(0, "version", version)
    return (
        {
            "version": version,
            "row_count": int(len(bundle)),
            "active_hour_count": int(active_mask.sum()),
            "bad_app_context_sum_rows": int(bad_sum),
            "bad_primary_context_rows": int(bad_primary),
            "bad_primary_task_flag_rows": int(bad_task_flag),
            "primary_task_eligible_hour_share": float(
                bundle["primary_context_task_eligible"].astype(str).str.lower().eq("true").mean()
            ),
        },
        primary_distribution,
    )


def _write_markdown_summary(
    path: Path,
    *,
    rows: dict[str, int],
    shares: dict[str, float],
    context_10: pd.DataFrame,
    bundle_checks: pd.DataFrame,
) -> None:
    def count(context: str, version: str) -> int:
        col = f"{version}_count"
        match = context_10[context_10["app_context"] == context]
        return int(match.iloc[0][col]) if not match.empty else 0

    lines = [
        "# TalkingData v3 Strict Cleaning Audit",
        "",
        "This audit compares the existing v2 artifacts with the v3 strict app-context cleaning artifacts.",
        "",
        "## Row Counts",
        "",
        f"- 59-person event-app rows: v2={rows['v2_59']}, v3={rows['v3_59']}",
        f"- 10-person event-app rows: v2={rows['v2_10']}, v3={rows['v3_10']}",
        "",
        "The row counts stay unchanged, so v3 changes classification only; it does not change the event-app unit of analysis.",
        "",
        "## Task-Eligible Exposure Share",
        "",
        f"- 59-person task-eligible share: v2={shares['v2_59']:.6f}, v3={shares['v3_59']:.6f}",
        f"- 10-person task-eligible share: v2={shares['v2_10']:.6f}, v3={shares['v3_10']:.6f}",
        "",
        "## Key 10-Person Context Changes",
        "",
        f"- `education_work_context`: {count('education_work_context', 'v2')} -> {count('education_work_context', 'v3')}",
        f"- `navigation_transport_context`: {count('navigation_transport_context', 'v2')} -> {count('navigation_transport_context', 'v3')}",
        f"- `shopping_lifestyle_context`: {count('shopping_lifestyle_context', 'v2')} -> {count('shopping_lifestyle_context', 'v3')}",
        f"- `communication_social_context`: {count('communication_social_context', 'v2')} -> {count('communication_social_context', 'v3')}",
        f"- `taxonomy_profile_only`: {count('taxonomy_profile_only', 'v2')} -> {count('taxonomy_profile_only', 'v3')}",
        "",
        "## Hourly Bundle Checks",
        "",
        bundle_checks.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "v3 strict cleaning lowers task-eligible mass mainly by preventing broad information/technology/science labels from becoming `education_work_context`, by moving `online shopping navigation` to shopping/lifestyle, and by stopping `Relatives 1` from independently creating social context.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(
    *,
    v2_elderly_dir: Path,
    v3_elderly_dir: Path,
    v2_10_dir: Path,
    v3_10_dir: Path,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    v2_59 = _read_csv(_event_path(v2_elderly_dir, "59"))
    v3_59 = _read_csv(_event_path(v3_elderly_dir, "59"))
    v2_10 = _read_csv(_event_path(v2_10_dir, "10"))
    v3_10 = _read_csv(_event_path(v3_10_dir, "10"))

    context_59 = _context_distribution(v2_59, v3_59)
    context_10 = _context_distribution(v2_10, v3_10)
    targeted = _targeted_checks(v2_10, v3_10)

    v2_bundle_check, v2_primary = _bundle_check(v2_10_dir, "v2")
    v3_bundle_check, v3_primary = _bundle_check(v3_10_dir, "v3")
    bundle_checks = pd.DataFrame([v2_bundle_check, v3_bundle_check])
    primary_contexts = pd.concat([v2_primary, v3_primary], ignore_index=True)

    paths = {
        "context_distribution_59": output_dir / "v2_vs_v3_59_context_distribution.csv",
        "context_distribution_10": output_dir / "v2_vs_v3_10_context_distribution.csv",
        "targeted_checks": output_dir / "v2_vs_v3_10_targeted_checks.csv",
        "bundle_checks": output_dir / "v2_vs_v3_10_hourly_bundle_checks.csv",
        "primary_contexts": output_dir / "v2_vs_v3_10_primary_context_distribution.csv",
        "summary": output_dir / "v3_strict_audit_summary.md",
    }

    context_59.to_csv(paths["context_distribution_59"], index=False, encoding="utf-8-sig")
    context_10.to_csv(paths["context_distribution_10"], index=False, encoding="utf-8-sig")
    targeted.to_csv(paths["targeted_checks"], index=False, encoding="utf-8-sig")
    bundle_checks.to_csv(paths["bundle_checks"], index=False, encoding="utf-8-sig")
    primary_contexts.to_csv(paths["primary_contexts"], index=False, encoding="utf-8-sig")

    _write_markdown_summary(
        paths["summary"],
        rows={
            "v2_59": len(v2_59),
            "v3_59": len(v3_59),
            "v2_10": len(v2_10),
            "v3_10": len(v3_10),
        },
        shares={
            "v2_59": _task_eligible_share(v2_59),
            "v3_59": _task_eligible_share(v3_59),
            "v2_10": _task_eligible_share(v2_10),
            "v3_10": _task_eligible_share(v3_10),
        },
        context_10=context_10,
        bundle_checks=bundle_checks,
    )

    return {key: str(value) for key, value in paths.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-elderly-dir", type=Path, default=DEFAULT_V2_ELDERLY_DIR)
    parser.add_argument("--v3-elderly-dir", type=Path, default=DEFAULT_V3_ELDERLY_DIR)
    parser.add_argument("--v2-10-dir", type=Path, default=DEFAULT_V2_10_DIR)
    parser.add_argument("--v3-10-dir", type=Path, default=DEFAULT_V3_10_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = run_audit(
        v2_elderly_dir=args.v2_elderly_dir,
        v3_elderly_dir=args.v3_elderly_dir,
        v2_10_dir=args.v2_10_dir,
        v3_10_dir=args.v3_10_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(outputs, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
