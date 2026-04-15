#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import statistics
from pathlib import Path
from typing import Any


DEFAULT_BASELINE_WORLD = "baseline_low_friction"
DEFAULT_COMPARE_WORLDS = (
    "high_friction_low_assist",
    "high_friction_high_assist",
    "low_friction_high_assist",
)
METRIC_FIELDS = (
    "attempt_rate",
    "neg_share",
    "emit_given_attempt",
    "helplessness_delta",
    "trust_delta",
    "avoidance_delta",
)
EXPECTED_DIRECTION_PROFILES = {
    "worse_than_baseline": {
        "attempt_rate": -1,
        "neg_share": 1,
        "emit_given_attempt": None,
        "helplessness_delta": 1,
        "trust_delta": -1,
        "avoidance_delta": 1,
    },
    "better_than_baseline": {
        "attempt_rate": 1,
        "neg_share": -1,
        "emit_given_attempt": None,
        "helplessness_delta": -1,
        "trust_delta": 1,
        "avoidance_delta": -1,
    },
}
DEFAULT_WORLD_DIRECTION_HINTS = {
    "high_friction_low_assist": "worse_than_baseline",
    "low_friction_high_assist": "better_than_baseline",
}


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


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _parse_csv_tokens(raw: str) -> list[str]:
    values: list[str] = []
    for token in str(raw).split(","):
        text = token.strip()
        if text:
            values.append(text)
    return values


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _resolve_compare_worlds(
    *,
    compare_worlds_text: str,
    legacy_high_world: str,
    legacy_low_world: str,
    baseline_world: str,
) -> list[str]:
    compare_worlds = _parse_csv_tokens(compare_worlds_text)
    if not compare_worlds:
        legacy_worlds = _parse_csv_tokens(",".join([legacy_high_world, legacy_low_world]))
        compare_worlds = legacy_worlds or list(DEFAULT_COMPARE_WORLDS)
    filtered = [world for world in compare_worlds if world != baseline_world]
    resolved = _dedupe_preserve_order(filtered)
    if not resolved:
        raise ValueError("No compare worlds remain after excluding the baseline world.")
    return resolved


def _parse_direction_overrides(raw: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for token in _parse_csv_tokens(raw):
        if "=" not in token:
            raise ValueError(
                "direction-overrides must use world=profile format, "
                f"got: {token!r}"
            )
        world_name, profile_name = token.split("=", 1)
        world_name = world_name.strip()
        profile_name = profile_name.strip()
        if not world_name or not profile_name:
            raise ValueError(
                "direction-overrides must use non-empty world=profile entries"
            )
        if profile_name not in EXPECTED_DIRECTION_PROFILES:
            allowed = ", ".join(sorted(EXPECTED_DIRECTION_PROFILES))
            raise ValueError(
                f"Unknown direction profile {profile_name!r}; allowed: {allowed}"
            )
        overrides[world_name] = profile_name
    return overrides


def _resolve_direction_profile(
    world_name: str,
    *,
    direction_overrides: dict[str, str],
) -> str:
    if world_name in direction_overrides:
        return direction_overrides[world_name]
    return DEFAULT_WORLD_DIRECTION_HINTS.get(world_name, "")


def _bootstrap_ci(
    values: list[float],
    *,
    iterations: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260310,
) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = random.Random(seed)
    n = len(values)
    sampled_means: list[float] = []
    rounds = max(200, int(iterations))
    for _ in range(rounds):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        sampled_means.append(float(sum(sample) / n))
    sampled_means.sort()
    low_idx = max(0, int((alpha / 2.0) * rounds))
    high_idx = min(rounds - 1, int((1.0 - alpha / 2.0) * rounds) - 1)
    return float(sampled_means[low_idx]), float(sampled_means[high_idx])


def _wilcoxon_pvalue(values: list[float]) -> float | None:
    if not values:
        return None
    if all(abs(v) < 1e-12 for v in values):
        return 1.0
    try:
        from scipy.stats import wilcoxon  # type: ignore
    except Exception:
        return None
    try:
        result = wilcoxon(values, zero_method="wilcox", alternative="two-sided")
        return float(result.pvalue)
    except Exception:
        return None


def _direction_consistency(values: list[float], expected_sign: int | None) -> float | None:
    if expected_sign is None:
        return None
    if not values:
        return None
    hit = 0
    for value in values:
        if expected_sign > 0 and value > 0:
            hit += 1
        elif expected_sign < 0 and value < 0:
            hit += 1
    return float(hit / len(values))


def _load_summary_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _pair_key(row: dict[str, Any]) -> tuple[str, int, int]:
    group_id = str(row.get("group_id", "")).strip()
    pair_index = _safe_int(row.get("pair_index"), -1)
    pair_seed = _safe_int(row.get("pair_seed"), _safe_int(row.get("seed"), 0))
    return group_id, pair_index, pair_seed


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Paired-difference analysis for Digital Friction parallel worlds."
    )
    parser.add_argument(
        "--summary-csv",
        required=True,
        help="Path to parallel_world_summary_*.csv generated by analysis_parallel_worlds.py",
    )
    parser.add_argument(
        "--out-pair-csv",
        default="examples/digital_friction_mvp/analysis/parallel_world_paired_diffs.csv",
        help="Pair-level diff output csv path",
    )
    parser.add_argument(
        "--out-stats-csv",
        default="examples/digital_friction_mvp/analysis/parallel_world_paired_stats.csv",
        help="Aggregated paired stats output csv path",
    )
    parser.add_argument(
        "--out-qc-csv",
        default="examples/digital_friction_mvp/analysis/parallel_world_paired_qc.csv",
        help="QC inclusion/exclusion output csv path",
    )
    parser.add_argument("--baseline-world", default=DEFAULT_BASELINE_WORLD)
    parser.add_argument(
        "--compare-worlds",
        default="",
        help=(
            "Comma-separated comparison worlds. "
            "Defaults to known non-baseline worlds."
        ),
    )
    parser.add_argument(
        "--high-world",
        default="",
        help="Legacy alias for a worse-than-baseline comparison world",
    )
    parser.add_argument(
        "--low-world",
        default="",
        help="Legacy alias for a better-than-baseline comparison world",
    )
    parser.add_argument(
        "--direction-overrides",
        default="",
        help=(
            "Optional world=profile mapping. Supported profiles: "
            "worse_than_baseline, better_than_baseline"
        ),
    )
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260310)
    args = parser.parse_args()

    summary_path = Path(args.summary_csv)
    if not summary_path.exists():
        raise FileNotFoundError(f"summary csv not found: {summary_path}")

    rows = _load_summary_rows(summary_path)
    grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_pair_key(row), []).append(row)

    qc_rows: list[dict[str, Any]] = []
    paired_rows: list[dict[str, Any]] = []
    baseline_world = str(args.baseline_world).strip()
    compare_worlds = _resolve_compare_worlds(
        compare_worlds_text=str(args.compare_worlds),
        legacy_high_world=str(args.high_world),
        legacy_low_world=str(args.low_world),
        baseline_world=baseline_world,
    )
    direction_overrides = _parse_direction_overrides(str(args.direction_overrides))

    for (group_id, pair_index, pair_seed), bucket in sorted(grouped.items()):
        world_map: dict[str, dict[str, Any]] = {}
        for item in bucket:
            world_name = str(item.get("world_name", "")).strip()
            if world_name not in world_map:
                world_map[world_name] = item
        baseline_pair_index = _safe_int(
            world_map.get(baseline_world, {}).get("pair_index", pair_index), pair_index
        )
        available_worlds = ",".join(sorted(world_map.keys()))
        for compare_world in compare_worlds:
            reasons: list[str] = []
            baseline_row = world_map.get(baseline_world)
            compare_row = world_map.get(compare_world)
            if baseline_row is None:
                reasons.append(f"missing_world:{baseline_world}")
            if compare_row is None:
                reasons.append(f"missing_world:{compare_world}")
            for world_name, row in (
                (baseline_world, baseline_row),
                (compare_world, compare_row),
            ):
                if row is None:
                    continue
                if str(row.get("status", "")).strip().lower() != "ok":
                    reasons.append(f"status_not_ok:{world_name}")
                if not _safe_bool(row.get("qc_config_match", 0)):
                    reasons.append(f"config_mismatch:{world_name}")

            fingerprints = {
                str(row.get("config_fingerprint", "")).strip()
                for row in (baseline_row, compare_row)
                if row is not None
            }
            fingerprints.discard("")
            if len(fingerprints) != 1:
                reasons.append("fingerprint_not_identical")

            direction_profile = _resolve_direction_profile(
                compare_world,
                direction_overrides=direction_overrides,
            )
            qc_pass = len(reasons) == 0
            qc_rows.append(
                {
                    "group_id": group_id,
                    "pair_seed": pair_seed,
                    "pair_index": baseline_pair_index,
                    "baseline_world": baseline_world,
                    "compare_world": compare_world,
                    "contrast_key": f"{compare_world}__vs__{baseline_world}",
                    "direction_profile": direction_profile,
                    "qc_pass": int(qc_pass),
                    "qc_reason": ";".join(reasons),
                    "world_count": len(world_map),
                    "available_worlds": available_worlds,
                }
            )
            if not qc_pass or baseline_row is None or compare_row is None:
                continue

            pair_payload: dict[str, Any] = {
                "group_id": group_id,
                "pair_seed": pair_seed,
                "pair_index": baseline_pair_index,
                "baseline_world": baseline_world,
                "compare_world": compare_world,
                "contrast_key": f"{compare_world}__vs__{baseline_world}",
                "direction_profile": direction_profile,
                "config_fingerprint": str(
                    baseline_row.get("config_fingerprint", "")
                ).strip(),
                "exp_id_baseline": str(baseline_row.get("exp_id", "")).strip(),
                "exp_id_compare": str(compare_row.get("exp_id", "")).strip(),
            }
            for metric in METRIC_FIELDS:
                value_baseline = _safe_float(baseline_row.get(metric), 0.0)
                value_compare = _safe_float(compare_row.get(metric), 0.0)
                pair_payload[f"{metric}_baseline"] = round(value_baseline, 6)
                pair_payload[f"{metric}_compare"] = round(value_compare, 6)
                pair_payload[f"{metric}_diff"] = round(
                    value_compare - value_baseline,
                    6,
                )
            paired_rows.append(pair_payload)

    stats_rows: list[dict[str, Any]] = []
    for compare_world in compare_worlds:
        contrast_key = f"{compare_world}__vs__{baseline_world}"
        direction_profile = _resolve_direction_profile(
            compare_world,
            direction_overrides=direction_overrides,
        )
        expected_profile = EXPECTED_DIRECTION_PROFILES.get(direction_profile, {})
        contrast_rows = [
            row for row in paired_rows if str(row.get("compare_world", "")) == compare_world
        ]
        for metric in METRIC_FIELDS:
            values = [
                _safe_float(row.get(f"{metric}_diff"), 0.0)
                for row in contrast_rows
            ]
            n = len(values)
            mean_diff = float(sum(values) / n) if n > 0 else 0.0
            median_diff = float(statistics.median(values)) if n > 0 else 0.0
            ci_low, ci_high = _bootstrap_ci(
                values,
                iterations=int(args.bootstrap_iterations),
                seed=int(args.bootstrap_seed),
            )
            wilcoxon_p = _wilcoxon_pvalue(values)
            expected_sign = expected_profile.get(metric)
            direction = _direction_consistency(values, expected_sign)
            stats_rows.append(
                {
                    "contrast_key": contrast_key,
                    "baseline_world": baseline_world,
                    "compare_world": compare_world,
                    "direction_profile": direction_profile,
                    "metric": metric,
                    "n_pairs": n,
                    "mean_diff": round(mean_diff, 6),
                    "median_diff": round(median_diff, 6),
                    "ci95_low": round(ci_low, 6),
                    "ci95_high": round(ci_high, 6),
                    "wilcoxon_p": (
                        ""
                        if wilcoxon_p is None
                        else round(float(wilcoxon_p), 6)
                    ),
                    "direction_consistency": (
                        ""
                        if direction is None
                        else round(float(direction), 6)
                    ),
                }
            )

    pair_fieldnames = [
        "group_id",
        "pair_seed",
        "pair_index",
        "baseline_world",
        "compare_world",
        "contrast_key",
        "direction_profile",
        "config_fingerprint",
        "exp_id_baseline",
        "exp_id_compare",
    ]
    for metric in METRIC_FIELDS:
        pair_fieldnames.extend(
            [
                f"{metric}_baseline",
                f"{metric}_compare",
                f"{metric}_diff",
            ]
        )
    stats_fieldnames = [
        "contrast_key",
        "baseline_world",
        "compare_world",
        "direction_profile",
        "metric",
        "n_pairs",
        "mean_diff",
        "median_diff",
        "ci95_low",
        "ci95_high",
        "wilcoxon_p",
        "direction_consistency",
    ]
    qc_fieldnames = [
        "group_id",
        "pair_seed",
        "pair_index",
        "baseline_world",
        "compare_world",
        "contrast_key",
        "direction_profile",
        "qc_pass",
        "qc_reason",
        "world_count",
        "available_worlds",
    ]

    out_pair = Path(args.out_pair_csv)
    out_stats = Path(args.out_stats_csv)
    out_qc = Path(args.out_qc_csv)
    _write_csv(out_pair, paired_rows, pair_fieldnames)
    _write_csv(out_stats, stats_rows, stats_fieldnames)
    _write_csv(out_qc, qc_rows, qc_fieldnames)

    print(str(out_pair))
    print(str(out_stats))
    print(str(out_qc))


if __name__ == "__main__":
    main()
