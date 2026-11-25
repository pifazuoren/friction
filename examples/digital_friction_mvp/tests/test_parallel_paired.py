from __future__ import annotations

import csv
import json
import subprocess
import sys
import textwrap
from pathlib import Path


def _write_world_summary(path: Path) -> None:
    fieldnames = [
        "group_id",
        "pair_index",
        "pair_seed",
        "world_name",
        "status",
        "qc_config_match",
        "config_fingerprint",
        "exp_id",
        "attempt_rate",
        "neg_share",
        "emit_given_attempt",
        "helplessness_delta",
        "trust_delta",
        "avoidance_delta",
    ]
    rows = [
        {
            "group_id": "g1",
            "pair_index": 0,
            "pair_seed": 101,
            "world_name": "baseline_low_friction",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-a-101",
            "attempt_rate": 0.50,
            "neg_share": 0.20,
            "emit_given_attempt": 0.90,
            "helplessness_delta": 10.0,
            "trust_delta": -5.0,
            "avoidance_delta": 8.0,
        },
        {
            "group_id": "g1",
            "pair_index": 0,
            "pair_seed": 101,
            "world_name": "high_friction_low_assist",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-b-101",
            "attempt_rate": 0.30,
            "neg_share": 0.45,
            "emit_given_attempt": 0.92,
            "helplessness_delta": 18.0,
            "trust_delta": -11.0,
            "avoidance_delta": 17.0,
        },
        {
            "group_id": "g1",
            "pair_index": 0,
            "pair_seed": 101,
            "world_name": "high_friction_high_assist",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-c-101",
            "attempt_rate": 0.44,
            "neg_share": 0.28,
            "emit_given_attempt": 0.93,
            "helplessness_delta": 12.0,
            "trust_delta": -7.0,
            "avoidance_delta": 11.0,
        },
        {
            "group_id": "g1",
            "pair_index": 0,
            "pair_seed": 101,
            "world_name": "low_friction_high_assist",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-d-101",
            "attempt_rate": 0.72,
            "neg_share": 0.11,
            "emit_given_attempt": 0.95,
            "helplessness_delta": 6.0,
            "trust_delta": 2.0,
            "avoidance_delta": 3.0,
        },
        {
            "group_id": "g1",
            "pair_index": 1,
            "pair_seed": 102,
            "world_name": "baseline_low_friction",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-a-102",
            "attempt_rate": 0.55,
            "neg_share": 0.18,
            "emit_given_attempt": 0.88,
            "helplessness_delta": 9.0,
            "trust_delta": -4.0,
            "avoidance_delta": 7.0,
        },
        {
            "group_id": "g1",
            "pair_index": 1,
            "pair_seed": 102,
            "world_name": "high_friction_low_assist",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-b-102",
            "attempt_rate": 0.31,
            "neg_share": 0.42,
            "emit_given_attempt": 0.90,
            "helplessness_delta": 17.5,
            "trust_delta": -10.0,
            "avoidance_delta": 15.0,
        },
        {
            "group_id": "g1",
            "pair_index": 1,
            "pair_seed": 102,
            "world_name": "high_friction_high_assist",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-c-102",
            "attempt_rate": 0.47,
            "neg_share": 0.23,
            "emit_given_attempt": 0.91,
            "helplessness_delta": 11.0,
            "trust_delta": -6.5,
            "avoidance_delta": 9.0,
        },
        {
            "group_id": "g1",
            "pair_index": 1,
            "pair_seed": 102,
            "world_name": "low_friction_high_assist",
            "status": "ok",
            "qc_config_match": 1,
            "config_fingerprint": "fp1",
            "exp_id": "exp-d-102",
            "attempt_rate": 0.74,
            "neg_share": 0.09,
            "emit_given_attempt": 0.94,
            "helplessness_delta": 5.5,
            "trust_delta": 3.0,
            "avoidance_delta": 2.0,
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_parallel_paired_supports_multiple_compare_worlds(tmp_path: Path) -> None:
    summary_csv = tmp_path / "parallel_world_summary_test.csv"
    out_pair_csv = tmp_path / "parallel_world_paired_diffs_test.csv"
    out_stats_csv = tmp_path / "parallel_world_paired_stats_test.csv"
    out_qc_csv = tmp_path / "parallel_world_paired_qc_test.csv"
    _write_world_summary(summary_csv)

    script_path = Path(__file__).resolve().parents[1] / "analysis_parallel_paired.py"
    subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--summary-csv",
            str(summary_csv),
            "--out-pair-csv",
            str(out_pair_csv),
            "--out-stats-csv",
            str(out_stats_csv),
            "--out-qc-csv",
            str(out_qc_csv),
        ],
        check=True,
    )

    pair_rows = list(csv.DictReader(out_pair_csv.open("r", encoding="utf-8")))
    stats_rows = list(csv.DictReader(out_stats_csv.open("r", encoding="utf-8")))
    qc_rows = list(csv.DictReader(out_qc_csv.open("r", encoding="utf-8")))

    assert len(pair_rows) == 6
    assert len(stats_rows) == 18
    assert len(qc_rows) == 6
    assert {row["compare_world"] for row in pair_rows} == {
        "high_friction_low_assist",
        "high_friction_high_assist",
        "low_friction_high_assist",
    }
    assert all(row["qc_pass"] == "1" for row in qc_rows)

    worse_attempt = next(
        row
        for row in stats_rows
        if row["compare_world"] == "high_friction_low_assist"
        and row["metric"] == "attempt_rate"
    )
    assert worse_attempt["direction_profile"] == "worse_than_baseline"
    assert worse_attempt["direction_consistency"] == "1.0"

    high_assist_attempt = next(
        row
        for row in stats_rows
        if row["compare_world"] == "high_friction_high_assist"
        and row["metric"] == "attempt_rate"
    )
    assert high_assist_attempt["direction_profile"] == ""
    assert high_assist_attempt["direction_consistency"] == ""


def test_world_runner_generates_paired_outputs_with_summary_bundle(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "analysis"
    fake_main = tmp_path / "fake_main.py"
    fake_summary = tmp_path / "fake_summary.py"

    fake_main.write_text(
        textwrap.dedent(
            """
            import json
            import os
            from pathlib import Path

            metadata_path = Path(os.environ["RUN_METADATA_PATH"])
            payload = {
                "exp_id": os.environ["EXP_NAME"],
                "config_fingerprint": os.environ["PARALLEL_CONFIG_FINGERPRINT"],
                "agent_count": 10,
                "stage_mode": os.environ.get("STAGE_MODE", "single"),
                "stage_days": int(os.environ.get("STAGE_DAYS", "2")),
                "stage_count": 1,
                "decision_interval_minutes": int(
                    os.environ.get("EVENT_DECISION_INTERVAL_MINUTES", "30")
                ),
                "decision_intervals_per_day": 48,
                "total_days": int(os.environ.get("STAGE_DAYS", "2")),
                "opportunities_per_agent": 96,
                "opportunities_total": 960,
            }
            metadata_path.write_text(json.dumps(payload), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    fake_summary.write_text(
        textwrap.dedent(
            """
            import argparse
            import csv
            import json
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--manifest", required=True)
            parser.add_argument("--out-csv", required=True)
            parser.add_argument("--out-stage-csv", required=True)
            parser.add_argument("--plot-dir", required=True)
            args = parser.parse_args()

            manifest_rows = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            metrics = {
                "baseline_low_friction": (0.50, 0.20, 0.90, 10.0, -5.0, 8.0),
                "high_friction_low_assist": (0.30, 0.45, 0.92, 18.0, -11.0, 17.0),
                "high_friction_high_assist": (0.44, 0.28, 0.93, 12.0, -7.0, 11.0),
                "low_friction_high_assist": (0.72, 0.11, 0.95, 6.0, 2.0, 3.0),
            }
            fieldnames = [
                "group_id",
                "pair_index",
                "pair_seed",
                "world_name",
                "status",
                "qc_config_match",
                "config_fingerprint",
                "exp_id",
                "attempt_rate",
                "neg_share",
                "emit_given_attempt",
                "helplessness_delta",
                "trust_delta",
                "avoidance_delta",
            ]
            out_csv = Path(args.out_csv)
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            with out_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in manifest_rows:
                    values = metrics[row["world_name"]]
                    writer.writerow(
                        {
                            "group_id": row["group_id"],
                            "pair_index": row["pair_index"],
                            "pair_seed": row["pair_seed"],
                            "world_name": row["world_name"],
                            "status": row["status"],
                            "qc_config_match": row["qc_config_match"],
                            "config_fingerprint": row["config_fingerprint"],
                            "exp_id": row["exp_id"],
                            "attempt_rate": values[0],
                            "neg_share": values[1],
                            "emit_given_attempt": values[2],
                            "helplessness_delta": values[3],
                            "trust_delta": values[4],
                            "avoidance_delta": values[5],
                        }
                    )

            out_stage_csv = Path(args.out_stage_csv)
            with out_stage_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["group_id", "world_name", "stage_name", "helplessness_delta"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "group_id": manifest_rows[0]["group_id"],
                        "world_name": manifest_rows[0]["world_name"],
                        "stage_name": "steady",
                        "helplessness_delta": 10.0,
                    }
                )

            Path(args.plot_dir).mkdir(parents=True, exist_ok=True)
            """
        ),
        encoding="utf-8",
    )

    world_runner = Path(__file__).resolve().parents[1] / "world_runner.py"
    paired_script = Path(__file__).resolve().parents[1] / "analysis_parallel_paired.py"
    subprocess.run(
        [
            sys.executable,
            str(world_runner),
            "--group-id",
            "paired_bundle_test",
            "--base-seed",
            "101",
            "--n-seeds",
            "2",
            "--analysis-dir",
            str(analysis_dir),
            "--script-path",
            str(fake_main),
            "--summary-script-path",
            str(fake_summary),
            "--paired-script-path",
            str(paired_script),
            "--summarize-paired",
        ],
        check=True,
    )

    assert (analysis_dir / "exp_group_manifest_paired_bundle_test.json").exists()
    assert (analysis_dir / "exp_group_manifest_paired_bundle_test.csv").exists()
    assert (analysis_dir / "config_snapshot_paired_bundle_test.json").exists()
    assert (analysis_dir / "parallel_world_summary_paired_bundle_test.csv").exists()
    assert (analysis_dir / "parallel_stage_summary_paired_bundle_test.csv").exists()
    assert (analysis_dir / "parallel_world_paired_diffs_paired_bundle_test.csv").exists()
    assert (analysis_dir / "parallel_world_paired_stats_paired_bundle_test.csv").exists()
    assert (analysis_dir / "parallel_world_paired_qc_paired_bundle_test.csv").exists()

    paired_rows = list(
        csv.DictReader(
            (analysis_dir / "parallel_world_paired_diffs_paired_bundle_test.csv").open(
                "r",
                encoding="utf-8",
            )
        )
    )
    assert len(paired_rows) == 6
    assert {row["compare_world"] for row in paired_rows} == {
        "high_friction_low_assist",
        "high_friction_high_assist",
        "low_friction_high_assist",
    }
