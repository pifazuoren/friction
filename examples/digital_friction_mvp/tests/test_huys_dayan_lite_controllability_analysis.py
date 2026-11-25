from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from analysis_huys_dayan_lite_controllability import run_analysis


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _payload(
    *,
    c_before: float,
    c_after: float,
    intervention: bool,
    modulation_family: str | None = None,
) -> str:
    family = modulation_family or ("reduce_avoid_high_c" if intervention else "none")
    reference_low_c = family == "shrink_to_reference_low_c"
    reference_mix_gamma = 0.06 if reference_low_c else 0.0
    reference_policy = (
        {
            "attempt_self": 0.20,
            "seek_help_then_attempt": 0.65,
            "avoid": 0.15,
        }
        if reference_low_c
        else {}
    )
    tvd = 0.015 if reference_low_c else (0.04 if intervention else 0.0)
    final_policy = (
        {
            "attempt_self": 0.294,
            "seek_help_then_attempt": 0.415,
            "avoid": 0.291,
        }
        if reference_low_c
        else {
            "attempt_self": 0.30,
            "seek_help_then_attempt": 0.44 if intervention else 0.40,
            "avoid": 0.26 if intervention else 0.30,
        }
    )
    final_delta = (
        {
            "attempt_self": -0.006,
            "seek_help_then_attempt": 0.015,
            "avoid": -0.009,
        }
        if reference_low_c
        else {
            "attempt_self": 0.0,
            "seek_help_then_attempt": 0.04 if intervention else 0.0,
            "avoid": -0.04 if intervention else 0.0,
        }
    )
    return json.dumps(
        {
            "auxiliary_audit": {
                "bayesian_policy_lite": {
                    "reference_mode": "semantic_v2",
                    "lambda_llm": 0.50,
                    "utility_profile": "theory_v2",
                },
                "huys_dayan_lite_controllability": {
                    "mode": (
                        "control_centered_modulate"
                        if reference_low_c
                        else "gated_modulate"
                    ),
                    "status": "computed",
                    "intervention_applied": intervention,
                    "modulation_family": family,
                    "modulation_status": (
                        "modulated" if intervention else "within_neutral_band"
                    ),
                    "controllability_gate_open": intervention,
                    "best_nonavoid_action": "seek_help_then_attempt",
                    "best_nonavoid_source": "phase4_pi_final",
                    "uniform_mix_gamma": 0.0,
                    "reference_mix_gamma": reference_mix_gamma,
                    "control_centered_low_c_target": (
                        "pi_ref" if reference_low_c else ""
                    ),
                    "removed_avoid_mass": (
                        0.0 if reference_low_c else (0.04 if intervention else 0.0)
                    ),
                    "total_variation_distance_from_phase4_pi_final": tvd,
                    "max_abs_controllability_delta": tvd,
                    "uses_post_outcome_information_for_controllability_policy": False,
                    "low_c_directional_help_shift_enabled": False,
                    "extreme_low_c_avoid_shift_enabled": False,
                    "pi_base_before_controllability": {
                        "attempt_self": 0.30,
                        "seek_help_then_attempt": 0.40,
                        "avoid": 0.30,
                    },
                    "pi_reference_for_control_centered": reference_policy,
                    "pi_final_controllability": final_policy,
                    "final_delta_after_controllability_floor": final_delta,
                    "before_event": {
                        "shrunk_c_family": c_before,
                        "raw_c_family": c_before,
                        "family_confidence": 0.80,
                        "entropy_control": 0.70,
                        "action_contrast_control": 0.60,
                        "reward_control_chi_lite": 0.65,
                        "global_controllability_trace": 0.50,
                    },
                    "after_event": {
                        "shrunk_c_family": c_after,
                        "raw_c_family": c_after,
                        "global_controllability_trace_after": 0.52,
                        "would_update_global": True,
                    },
                },
            }
        },
        ensure_ascii=False,
    )


def test_huys_dayan_lite_analysis_writes_phase5b_csvs(tmp_path: Path) -> None:
    db_path = tmp_path / "sqlite.db"
    manifest_path = tmp_path / "exp_group_manifest_huys_test.json"
    out_dir = tmp_path / "analysis"
    exp_id = "huys-exp"
    table_name = "as_huys_exp_proto_attempt_rows"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            day INTEGER,
            t REAL,
            task_family TEXT,
            strategy_type TEXT,
            payload_json TEXT
        )
        """
    )
    cur.executemany(
        f"""
        INSERT INTO {table_name} (
            agent_id, day, t, task_family, strategy_type, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                0,
                0.0,
                "payment_risk_confirmation",
                "seek_help_then_attempt",
                _payload(c_before=0.70, c_after=0.72, intervention=True),
            ),
            (
                1,
                1,
                0.0,
                "payment_risk_confirmation",
                "avoid",
                _payload(c_before=0.50, c_after=0.48, intervention=False),
            ),
            (
                1,
                2,
                0.0,
                "payment_risk_confirmation",
                "seek_help_then_attempt",
                _payload(
                    c_before=0.25,
                    c_after=0.40,
                    intervention=True,
                    modulation_family="shrink_to_reference_low_c",
                ),
            ),
        ],
    )
    conn.commit()
    conn.close()

    manifest_path.write_text(
        json.dumps(
            [
                {
                    "group_id": "huys_test",
                    "pair_index": 0,
                    "pair_seed": 101,
                    "world_order": 0,
                    "world_name": "baseline_low_friction",
                    "exp_id": exp_id,
                    "seed": 101,
                    "config_fingerprint": "fingerprint789",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "config_snapshot_huys_test.json").write_text(
        json.dumps(
            {
                "group_id": "huys_test",
                "config_payload": {
                    "PROTO_BAYESIAN_POLICY_LITE_MAX_DELTA": "0.10",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    outputs = run_analysis(
        manifest_json=manifest_path,
        db_path=db_path,
        out_dir=out_dir,
    )

    assert len(outputs) == 6
    summary = _read_csv(out_dir / "huys_dayan_lite_summary_huys_test.csv")[0]
    by_world = _read_csv(out_dir / "huys_dayan_lite_by_world_huys_test.csv")[0]
    lagged = _read_csv(out_dir / "huys_dayan_lite_lagged_prediction_huys_test.csv")
    by_day = _read_csv(out_dir / "huys_dayan_lite_by_world_day_huys_test.csv")
    qc = _read_csv(out_dir / "huys_dayan_lite_qc_huys_test.csv")[0]
    shrink_day = next(row for row in by_day if row["day"] == "2")

    assert summary["row_count"] == "3"
    assert summary["huys_payload_coverage"] == "1.0"
    assert summary["uses_post_outcome_information_true_count"] == "0"
    assert summary["intervention_applied_rate"] == "0.6666666667"
    assert summary["mean_total_variation_distance_from_phase4_pi_final"] == "0.0183333333"
    assert by_world["reference_modes"] == "semantic_v2"
    assert (
        by_world["modulation_families"]
        == "none|reduce_avoid_high_c|shrink_to_reference_low_c"
    )
    assert shrink_day["mean_reference_mix_gamma"] == "0.06"
    assert shrink_day["control_centered_low_c_targets"] == "pi_ref"
    assert shrink_day["mean_pi_reference_for_control_centered_attempt"] == "0.2"
    assert shrink_day["mean_pi_reference_for_control_centered_help"] == "0.65"
    assert shrink_day["mean_pi_reference_for_control_centered_avoid"] == "0.15"
    assert lagged[0]["c_family_after_event_day_t_minus_1"] == "0.72"
    assert qc["table_found"] == "1"
    assert qc["huys_payload_count"] == "3"
