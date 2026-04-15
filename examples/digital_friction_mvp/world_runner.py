#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_WORLDS = [
    "baseline_low_friction",
    "high_friction_low_assist",
    "high_friction_high_assist",
    "low_friction_high_assist",
]

FINGERPRINT_ENV_KEYS = (
    "AGENT_COUNT",
    "AGENT_PLAN_PROMPT_PROFILE",
    "STAGE_MODE",
    "STAGE_SINGLE_NAME",
    "STAGE_DAYS",
    "EVENT_DECISION_INTERVAL_MINUTES",
    "EVENT_DECIDER_MODE",
    "EVENT_PROB_MODEL",
    "EVENT_EMIT_POLICY",
    "EVENT_MIN_STAGE_EVENT_EMITS",
    "EVENT_MESSAGE_MODE",
    "PROTO_LLM_PSYCHOLOGY_MODE",
    "PROTO_LLM_TASK_APPRAISAL_ENABLED",
    "PROTO_LLM_EVENT_APPRAISAL_ENABLED",
    "PROTO_LLM_DAILY_REFLECTION_ENABLED",
    "PROTO_LLM_STRATEGY_DELIBERATION_ENABLED",
    "PROTO_LLM_STRATEGY_BIAS_ENABLED",
    "PROTO_LLM_STAGE_INTERVIEW_ENABLED",
    "PROTO_LLM_FINAL_INTERVIEW_ENABLED",
    "PROTO_LLM_PSYCHOLOGY_MIN_CONFIDENCE",
    "PROTO_LLM_PSYCHOLOGY_TIMEOUT",
    "PROTO_LLM_PSYCHOLOGY_RETRIES",
    "PROTO_LLM_PSYCHOLOGY_CACHE_ENABLED",
    "PROTO_LLM_STRATEGY_BIAS_MAX_SHIFT",
    "PROTO_LLM_UNCONTROLLABILITY_MODE",
    "PROTO_LLM_UNCONTROLLABILITY_MIN_CONFIDENCE",
    "PROTO_LLM_UNCONTROLLABILITY_MAX_SHIFT",
    "PROTO_LLM_UNCONTROLLABILITY_TIMEOUT",
    "PROTO_LLM_UNCONTROLLABILITY_RETRIES",
    "PROTO_LLM_UNCONTROLLABILITY_CACHE_ENABLED",
    "PROTO_LOGICAL_CLOCK_ENABLED",
    "FIRST_GATE_MIN_SCORE",
    "FIRST_GATE_TOP_GAP",
    "FIRST_GATE_REQUIRE_DIGITAL_FOR_WEAK_MATCH",
    "STATUS_GATE_ENABLED",
    "STATUS_GATE_MIN_SCORE",
    "STATUS_GATE_TOP_GAP",
    "STATUS_GATE_REQUIRE_ANCHOR",
    "STATUS_GATE_STEP_TYPE_RELAX",
    "STATUS_GATE_ALLOW_OVERRIDE",
    "STATUS_GATE_OVERRIDE_MIN_SCORE",
    "ATTEMPT_HAZARD_CALIBRATE_ENABLED",
    "ATTEMPT_HAZARD_REQUIRE_DIGITAL",
    "ATTEMPT_HAZARD_REFRACTORY_DECAY",
    "ATTEMPT_HAZARD_HISTORY_WINDOW",
    "ATTEMPT_HAZARD_MIN_P",
    "ATTEMPT_HAZARD_MAX_P",
    "DIGITAL_SUPPLY_ENABLED",
    "DIGITAL_SUPPLY_DAILY_TASKS_PER_AGENT",
    "DIGITAL_SUPPLY_MAX_QUEUE",
    "DIGITAL_SUPPLY_SURFACE_PROB",
    "DIGITAL_SUPPLY_SURFACE_IDLE_ONLY",
    "DIGITAL_SUPPLY_CARRYOVER_ENABLED",
    "DIGITAL_SUPPLY_PENDING_MAX_HOURS",
    "DIGITAL_SUPPLY_LOG_ENABLED",
    "NON_DIGITAL_EXPLORATORY_DAILY_PROB",
    "RANDOM_SCENARIO_FALLBACK_DAILY_PROB",
    "ECONOMY_BLOCK_ENABLED",
    "ECONOMY_BINDING_AUDIT_STRICT",
)


def _run_command(command: list[str], env: dict[str, str], cwd: Path) -> int:
    proc = subprocess.run(command, cwd=str(cwd), env=env)
    return int(proc.returncode)


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_seed_values(*, base_seed: int, n_seeds: int, seed_list: str) -> list[int]:
    seed_text = seed_list.strip()
    if seed_text:
        values: list[int] = []
        for token in seed_text.split(","):
            token = token.strip()
            if not token:
                continue
            values.append(int(token))
        if not values:
            raise ValueError("seed-list is provided but no valid integer seeds were found")
        return values
    count = max(1, int(n_seeds))
    return [int(base_seed) + idx for idx in range(count)]


def _build_config_payload(env: dict[str, str], worlds: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"world_batch": list(worlds)}
    for key in sorted(FINGERPRINT_ENV_KEYS):
        if key in env:
            payload[key] = str(env[key])
    return payload


def _build_config_fingerprint(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return digest[:16]


def _resolve_compare_worlds(
    *,
    worlds: list[str],
    baseline_world: str,
    requested_compare_worlds: str,
) -> list[str]:
    if baseline_world not in worlds:
        raise ValueError(
            f"paired baseline world {baseline_world!r} is not in world-batch"
        )
    if str(requested_compare_worlds).strip():
        candidates = [
            token.strip()
            for token in str(requested_compare_worlds).split(",")
            if token.strip()
        ]
    else:
        candidates = [world for world in worlds if world != baseline_world]

    resolved: list[str] = []
    seen: set[str] = set()
    for world_name in candidates:
        if world_name not in worlds:
            raise ValueError(
                f"paired compare world {world_name!r} is not in world-batch"
            )
        if world_name == baseline_world or world_name in seen:
            continue
        seen.add(world_name)
        resolved.append(world_name)
    if not resolved:
        raise ValueError("No compare worlds available for paired analysis.")
    return resolved


def _write_manifest_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "group_id",
        "pair_index",
        "pair_seed",
        "world_order",
        "world_name",
        "exp_name",
        "exp_id",
        "seed",
        "status",
        "return_code",
        "qc_config_match",
        "config_fingerprint",
        "run_meta_path",
        "agent_count",
        "stage_mode",
        "stage_days",
        "stage_count",
        "decision_interval_minutes",
        "decision_intervals_per_day",
        "total_days",
        "opportunities_per_agent",
        "opportunities_total",
        "started_at",
        "finished_at",
        "command",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Digital Friction MVP across parallel worlds.")
    parser.add_argument("--group-id", default="", help="Experiment group id (default: timestamp)")
    parser.add_argument("--base-seed", type=int, default=101, help="Base seed for world runs")
    parser.add_argument(
        "--n-seeds",
        type=int,
        default=1,
        help="Number of paired seed groups to run (ignored when --seed-list is set)",
    )
    parser.add_argument(
        "--seed-list",
        default="",
        help="Comma-separated explicit seeds for paired groups (e.g. 101,202,303)",
    )
    parser.add_argument(
        "--world-batch",
        default=",".join(DEFAULT_WORLDS),
        help="Comma-separated world names",
    )
    parser.add_argument(
        "--script-path",
        default="examples/digital_friction_mvp/main.py",
        help="Main experiment script path",
    )
    parser.add_argument(
        "--analysis-dir",
        default="examples/digital_friction_mvp/analysis",
        help="Output directory for manifest files",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable for running child experiments",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Run analysis_parallel_worlds.py after finishing all worlds",
    )
    parser.add_argument(
        "--summarize-paired",
        action="store_true",
        help="Run paired comparison analysis after generating world summaries",
    )
    parser.add_argument(
        "--paired-baseline-world",
        default="baseline_low_friction",
        help="Baseline world for paired comparison outputs",
    )
    parser.add_argument(
        "--paired-compare-worlds",
        default="",
        help=(
            "Comma-separated paired comparison worlds. "
            "Defaults to all non-baseline worlds in world-batch."
        ),
    )
    parser.add_argument(
        "--paired-direction-overrides",
        default="",
        help=(
            "Optional world=profile mapping forwarded to analysis_parallel_paired.py. "
            "Profiles: worse_than_baseline, better_than_baseline."
        ),
    )
    parser.add_argument(
        "--summary-script-path",
        default="examples/digital_friction_mvp/analysis_parallel_worlds.py",
        help="Summary analysis script path",
    )
    parser.add_argument(
        "--paired-script-path",
        default="examples/digital_friction_mvp/analysis_parallel_paired.py",
        help="Paired comparison analysis script path",
    )
    args = parser.parse_args()

    cwd = Path(__file__).resolve().parent.parent.parent
    analysis_dir = Path(args.analysis_dir)
    if not analysis_dir.is_absolute():
        analysis_dir = cwd / analysis_dir
    analysis_dir.mkdir(parents=True, exist_ok=True)

    group_id = args.group_id.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    worlds = [
        token.strip()
        for token in str(args.world_batch).split(",")
        if token.strip()
    ] or DEFAULT_WORLDS
    seed_values = _parse_seed_values(
        base_seed=int(args.base_seed),
        n_seeds=int(args.n_seeds),
        seed_list=str(args.seed_list),
    )

    rows: list[dict[str, Any]] = []
    script_path = Path(args.script_path)
    if not script_path.is_absolute():
        script_path = cwd / script_path
    if not script_path.exists():
        raise FileNotFoundError(f"script_path not found: {script_path}")

    base_env = os.environ.copy()
    base_env.setdefault("STAGE_MODE", "single")
    base_env.setdefault("STAGE_SINGLE_NAME", "steady")
    config_payload = _build_config_payload(base_env, worlds)
    config_fingerprint = _build_config_fingerprint(config_payload)
    config_snapshot_path = analysis_dir / f"config_snapshot_{group_id}.json"
    config_snapshot_path.write_text(
        json.dumps(
            {
                "group_id": group_id,
                "config_fingerprint": config_fingerprint,
                "config_payload": config_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    qc_failures = 0
    for pair_index, pair_seed in enumerate(seed_values):
        for world_order, world_name in enumerate(worlds):
            now_token = datetime.now().strftime("%Y%m%d_%H%M%S")
            exp_name = (
                f"digital_friction_parallel_{group_id}_p{pair_index:03d}_"
                f"{world_name}_{now_token}"
            )
            metadata_path = (
                analysis_dir
                / f"run_meta_{group_id}_p{pair_index:03d}_w{world_order:02d}.json"
            )

            env = base_env.copy()
            env["WORLD_NAME"] = world_name
            env["EXP_SEED"] = str(pair_seed)
            env["EXP_NAME"] = exp_name
            env["PARALLEL_GROUP_NAME"] = group_id
            env["EXPERIMENT_MODE"] = "parallel_worlds"
            env["WORLD_BATCH"] = ",".join(worlds)
            env["PARALLEL_PAIR_INDEX"] = str(pair_index)
            env["PARALLEL_PAIR_SEED"] = str(pair_seed)
            env["PARALLEL_WORLD_ORDER"] = str(world_order)
            env["PARALLEL_CONFIG_FINGERPRINT"] = config_fingerprint
            env["RUN_METADATA_PATH"] = str(metadata_path)

            if metadata_path.exists():
                try:
                    metadata_path.unlink()
                except Exception:
                    pass
            cmd = [args.python_bin, str(script_path)]
            started_at = datetime.now().isoformat(timespec="seconds")
            return_code = _run_command(cmd, env=env, cwd=cwd)
            finished_at = datetime.now().isoformat(timespec="seconds")

            metadata = _load_metadata(metadata_path)
            exp_id = str(metadata.get("exp_id", "")).strip()
            metadata_fingerprint = str(metadata.get("config_fingerprint", "")).strip()
            qc_config_match = int(metadata_fingerprint == config_fingerprint and bool(metadata_fingerprint))
            if return_code == 0 and qc_config_match != 1:
                qc_failures += 1
            if return_code == 0 and qc_config_match == 1:
                status = "ok"
            else:
                status = "failed"
            rows.append(
                {
                    "group_id": group_id,
                    "pair_index": int(pair_index),
                    "pair_seed": int(pair_seed),
                    "world_order": int(world_order),
                    "world_name": world_name,
                    "exp_name": exp_name,
                    "exp_id": exp_id,
                    "seed": int(pair_seed),
                    "status": status,
                    "return_code": return_code,
                    "qc_config_match": int(qc_config_match),
                    "config_fingerprint": config_fingerprint,
                    "run_meta_path": str(metadata_path),
                    "agent_count": _safe_int(metadata.get("agent_count"), 0),
                    "stage_mode": str(metadata.get("stage_mode", "")),
                    "stage_days": _safe_int(metadata.get("stage_days"), 0),
                    "stage_count": _safe_int(metadata.get("stage_count"), 0),
                    "decision_interval_minutes": _safe_int(
                        metadata.get("decision_interval_minutes"), 0
                    ),
                    "decision_intervals_per_day": _safe_int(
                        metadata.get("decision_intervals_per_day"), 0
                    ),
                    "total_days": _safe_int(metadata.get("total_days"), 0),
                    "opportunities_per_agent": _safe_int(
                        metadata.get("opportunities_per_agent"), 0
                    ),
                    "opportunities_total": _safe_int(
                        metadata.get("opportunities_total"), 0
                    ),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "command": " ".join(cmd),
                }
            )

    manifest_json = analysis_dir / f"exp_group_manifest_{group_id}.json"
    manifest_csv = analysis_dir / f"exp_group_manifest_{group_id}.csv"
    manifest_json.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_manifest_csv(rows, manifest_csv)

    should_summarize = bool(args.summarize or args.summarize_paired)
    if should_summarize:
        summary_script = Path(args.summary_script_path)
        if not summary_script.is_absolute():
            summary_script = cwd / summary_script
        if not summary_script.exists():
            raise FileNotFoundError(f"summary_script_path not found: {summary_script}")
        world_summary_csv = analysis_dir / f"parallel_world_summary_{group_id}.csv"
        stage_summary_csv = analysis_dir / f"parallel_stage_summary_{group_id}.csv"
        plot_dir = analysis_dir / f"parallel_world_plots_{group_id}"
        summary_cmd = [
            args.python_bin,
            str(summary_script),
            "--manifest",
            str(manifest_json),
            "--out-csv",
            str(world_summary_csv),
            "--out-stage-csv",
            str(stage_summary_csv),
            "--plot-dir",
            str(plot_dir),
        ]
        summary_proc = subprocess.run(
            summary_cmd,
            cwd=str(cwd),
            env=os.environ.copy(),
            check=False,
        )
        if summary_proc.returncode != 0:
            raise RuntimeError(
                "analysis_parallel_worlds.py failed with return code "
                f"{summary_proc.returncode}"
            )
        print(str(world_summary_csv))
        print(str(stage_summary_csv))
        print(str(plot_dir))

        if args.summarize_paired:
            paired_script = Path(args.paired_script_path)
            if not paired_script.is_absolute():
                paired_script = cwd / paired_script
            if not paired_script.exists():
                raise FileNotFoundError(f"paired_script_path not found: {paired_script}")
            compare_worlds = _resolve_compare_worlds(
                worlds=worlds,
                baseline_world=str(args.paired_baseline_world).strip(),
                requested_compare_worlds=str(args.paired_compare_worlds),
            )
            pair_csv = analysis_dir / f"parallel_world_paired_diffs_{group_id}.csv"
            pair_stats_csv = analysis_dir / f"parallel_world_paired_stats_{group_id}.csv"
            pair_qc_csv = analysis_dir / f"parallel_world_paired_qc_{group_id}.csv"
            paired_cmd = [
                args.python_bin,
                str(paired_script),
                "--summary-csv",
                str(world_summary_csv),
                "--out-pair-csv",
                str(pair_csv),
                "--out-stats-csv",
                str(pair_stats_csv),
                "--out-qc-csv",
                str(pair_qc_csv),
                "--baseline-world",
                str(args.paired_baseline_world).strip(),
                "--compare-worlds",
                ",".join(compare_worlds),
            ]
            direction_overrides = str(args.paired_direction_overrides).strip()
            if direction_overrides:
                paired_cmd.extend(
                    [
                        "--direction-overrides",
                        direction_overrides,
                    ]
                )
            paired_proc = subprocess.run(
                paired_cmd,
                cwd=str(cwd),
                env=os.environ.copy(),
                check=False,
            )
            if paired_proc.returncode != 0:
                raise RuntimeError(
                    "analysis_parallel_paired.py failed with return code "
                    f"{paired_proc.returncode}"
                )
            print(str(pair_csv))
            print(str(pair_stats_csv))
            print(str(pair_qc_csv))

    print(str(manifest_json))
    print(str(manifest_csv))
    print(str(config_snapshot_path))

    if qc_failures > 0:
        raise RuntimeError(
            f"Config fingerprint mismatch detected in {qc_failures} successful runs; "
            "check run metadata and env consistency."
        )


if __name__ == "__main__":
    main()
