from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from analysis_bayesian_policy_shadow import run_analysis


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _payload(
    *,
    pi_avoid: float,
    top_action: str,
    c_hat_before: float,
    c_hat_after: float,
) -> str:
    if top_action == "attempt_self":
        pi = {
            "attempt_self": 0.6,
            "seek_help_then_attempt": 0.2,
            "avoid": pi_avoid,
        }
    else:
        pi = {
            "attempt_self": 0.2,
            "seek_help_then_attempt": 0.2,
            "avoid": pi_avoid,
        }
    return json.dumps(
        {
            "auxiliary_audit": {
                "bayesian_policy_lite": {
                    "version": "policy_lite_shadow_v1",
                    "mode": "shadow",
                    "status": "updated",
                    "utility_profile": "theory_v2",
                    "uses_post_outcome_information_for_policy": False,
                    "strategy_unchanged": True,
                    "pi_bayes_shadow": pi,
                    "confidence_by_action": {
                        "attempt_self": 0.25,
                        "seek_help_then_attempt": 0.50,
                        "avoid": 0.75,
                    },
                    "posterior_entropy_by_action": {
                        "attempt_self": 0.80,
                        "seek_help_then_attempt": 0.70,
                        "avoid": 0.60,
                    },
                },
                "bayesian_control": {
                    "belief_before": c_hat_before,
                    "belief_after": c_hat_after,
                },
            }
        },
        ensure_ascii=False,
    )


def _semantic_payload() -> str:
    return json.dumps(
        {
            "auxiliary_audit": {
                "bayesian_policy_lite": {
                    "version": "policy_lite_shadow_v1",
                    "mode": "gated_lite",
                    "status": "updated",
                    "utility_profile": "theory_v2",
                    "reference_mode": "semantic_v2",
                    "lambda_llm": 0.25,
                    "min_llm_confidence": 0.50,
                    "uses_post_outcome_information_for_policy": False,
                    "strategy_unchanged": False,
                    "semantic_fallback_used": False,
                    "semantic_fallback_reason": "",
                    "rule_fallback_used": False,
                    "rule_fallback_reason": "",
                    "safety_guard_status": "ok",
                    "intervention_applied": True,
                    "total_variation_distance": 0.02,
                    "pi_prior": {
                        "attempt_self": 0.34,
                        "seek_help_then_attempt": 0.33,
                        "avoid": 0.33,
                    },
                    "pi_llm": {
                        "attempt_self": 0.20,
                        "seek_help_then_attempt": 0.60,
                        "avoid": 0.20,
                    },
                    "pi_semantic": {
                        "attempt_self": 0.305,
                        "seek_help_then_attempt": 0.3975,
                        "avoid": 0.2975,
                    },
                    "pi_ref": {
                        "attempt_self": 0.305,
                        "seek_help_then_attempt": 0.3975,
                        "avoid": 0.2975,
                    },
                    "pi_bayes": {
                        "attempt_self": 0.25,
                        "seek_help_then_attempt": 0.55,
                        "avoid": 0.20,
                    },
                    "pi_bayes_shadow": {
                        "attempt_self": 0.25,
                        "seek_help_then_attempt": 0.55,
                        "avoid": 0.20,
                    },
                    "pi_final": {
                        "attempt_self": 0.29,
                        "seek_help_then_attempt": 0.42,
                        "avoid": 0.29,
                    },
                    "semantic_delta_from_prior": {
                        "attempt_self": -0.035,
                        "seek_help_then_attempt": 0.0675,
                        "avoid": -0.0325,
                    },
                    "delta_applied": {
                        "attempt_self": -0.015,
                        "seek_help_then_attempt": 0.0225,
                        "avoid": -0.0075,
                    },
                    "bayesian_shift_before_floor": {
                        "attempt_self": -0.015,
                        "seek_help_then_attempt": 0.0225,
                        "avoid": -0.0075,
                    },
                    "final_delta_after_floor": {
                        "attempt_self": -0.015,
                        "seek_help_then_attempt": 0.0225,
                        "avoid": -0.0075,
                    },
                    "confidence_by_action": {
                        "attempt_self": 0.25,
                        "seek_help_then_attempt": 0.50,
                        "avoid": 0.75,
                    },
                    "posterior_entropy_by_action": {
                        "attempt_self": 0.80,
                        "seek_help_then_attempt": 0.70,
                        "avoid": 0.60,
                    },
                },
                "bayesian_control": {
                    "belief_before": 0.7,
                    "belief_after": 0.8,
                },
            }
        },
        ensure_ascii=False,
    )


def test_shadow_analysis_writes_reproducible_csvs(tmp_path: Path) -> None:
    db_path = tmp_path / "sqlite.db"
    manifest_path = tmp_path / "exp_group_manifest_shadow_test.json"
    out_dir = tmp_path / "analysis"
    exp_id = "abc-def"
    table_name = "as_abc_def_proto_attempt_rows"

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
                "attempt_self",
                _payload(
                    pi_avoid=0.2,
                    top_action="attempt_self",
                    c_hat_before=0.8,
                    c_hat_after=0.9,
                ),
            ),
            (
                2,
                0,
                1.0,
                "payment_risk_confirmation",
                "avoid",
                _payload(
                    pi_avoid=0.6,
                    top_action="avoid",
                    c_hat_before=0.2,
                    c_hat_after=0.1,
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
                    "group_id": "shadow_test",
                    "pair_index": 0,
                    "pair_seed": 101,
                    "world_order": 0,
                    "world_name": "baseline_low_friction",
                    "exp_id": exp_id,
                    "seed": 101,
                    "status": "ok",
                    "config_fingerprint": "fingerprint123",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "config_snapshot_shadow_test.json").write_text(
        json.dumps(
            {
                "group_id": "shadow_test",
                "config_fingerprint": "fingerprint123",
                "config_payload": {
                    "PROTO_BAYESIAN_POLICY_LITE_UTILITY_PROFILE": "theory_v2"
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output_paths = run_analysis(
        manifest_json=manifest_path,
        db_path=db_path,
        out_dir=out_dir,
    )

    assert len(output_paths) == 5
    summary = _read_csv(out_dir / "bayesian_policy_shadow_summary_shadow_test.csv")[0]
    by_world = _read_csv(out_dir / "bayesian_policy_shadow_by_world_shadow_test.csv")[0]
    qc = _read_csv(out_dir / "bayesian_policy_shadow_qc_shadow_test.csv")[0]

    assert summary["utility_profile"] == "theory_v2"
    assert summary["row_count"] == "2"
    assert summary["policy_payload_coverage"] == "1.0"
    assert summary["control_payload_coverage"] == "1.0"
    assert summary["all_uses_post_outcome_information_false"] == "1"
    assert summary["all_strategy_unchanged"] == "1"
    assert summary["c_hat_before_pi_avoid_corr"] == "-1.0"
    assert summary["c_hat_after_pi_avoid_corr_post_update_audit"] == "-1.0"
    assert by_world["shadow_top_attempt_share"] == "0.5"
    assert by_world["shadow_top_avoid_share"] == "0.5"


def test_shadow_analysis_extracts_semantic_v2_policy_chain(tmp_path: Path) -> None:
    db_path = tmp_path / "sqlite.db"
    manifest_path = tmp_path / "exp_group_manifest_semantic_test.json"
    out_dir = tmp_path / "analysis"
    exp_id = "semantic-exp"
    table_name = "as_semantic_exp_proto_attempt_rows"

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
    cur.execute(
        f"""
        INSERT INTO {table_name} (
            agent_id, day, t, task_family, strategy_type, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            0,
            0.0,
            "payment_risk_confirmation",
            "seek_help_then_attempt",
            _semantic_payload(),
        ),
    )
    conn.commit()
    conn.close()

    manifest_path.write_text(
        json.dumps(
            [
                {
                    "group_id": "semantic_test",
                    "pair_index": 0,
                    "pair_seed": 101,
                    "world_order": 0,
                    "world_name": "baseline_low_friction",
                    "exp_id": exp_id,
                    "seed": 101,
                    "status": "ok",
                    "config_fingerprint": "fingerprint456",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    run_analysis(manifest_json=manifest_path, db_path=db_path, out_dir=out_dir)

    summary = _read_csv(out_dir / "bayesian_policy_shadow_summary_semantic_test.csv")[0]
    by_world = _read_csv(out_dir / "bayesian_policy_shadow_by_world_semantic_test.csv")[0]
    qc = _read_csv(out_dir / "bayesian_policy_shadow_qc_semantic_test.csv")[0]

    assert summary["row_count"] == "1"
    assert summary["semantic_fallback_rate"] == "0.0"
    assert summary["rule_fallback_rate"] == "0.0"
    assert summary["safety_guard_fallback_rate"] == "0.0"
    assert summary["intervention_applied_rate"] == "1.0"
    assert summary["mean_total_variation_distance"] == "0.02"
    assert by_world["mean_pi_prior_attempt"] == "0.34"
    assert by_world["mean_pi_llm_help"] == "0.6"
    assert by_world["mean_pi_semantic_help"] == "0.3975"
    assert by_world["mean_pi_bayes_help"] == "0.55"
    assert by_world["mean_pi_final_help"] == "0.42"
    assert by_world["mean_delta_applied_help"] == "0.0225"
    assert by_world["mean_bayesian_shift_before_floor_help"] == "0.0225"
    assert by_world["mean_final_delta_after_floor_help"] == "0.0225"
    assert by_world["actual_shadow_top_match_rate"] == "1.0"
    assert qc["pair_seed"] == "101"
    assert qc["table_found"] == "1"
