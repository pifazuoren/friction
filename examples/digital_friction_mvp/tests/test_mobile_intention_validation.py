from __future__ import annotations

import csv
import json

import pytest

from validate_mobile_intention_exposure import write_validation_report


def test_mobile_intention_validation_report_uses_heldout_targets(tmp_path) -> None:
    status_csv = tmp_path / "mvp_status_step.csv"
    with status_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["agent_id", "day", "t", "status_json"])
        writer.writeheader()
        writer.writerow(
            {
                "agent_id": 1,
                "day": 4,
                "t": 3600.0,
                "status_json": json.dumps(
                    {
                        "proto_mobile_entry_decision": {
                            "entry_evaluated": True,
                            "selected_mobile_intention": "check_information",
                            "mapped_task_family": "information_search_judgment",
                            "task_generated": True,
                            "audit": {"task_generated": True},
                        }
                    }
                ),
            }
        )
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    (validation_dir / "mobile_intention_prior_by_bucket_hour.json").write_text(
        json.dumps(
            {
                "uses_validation_data": True,
                "global_prior": {
                    "p_mobile_intention": {
                        "check_information": 1.0,
                    }
                },
                "global_hourly_prior": {
                    "1": {
                        "p_mobile_intention": {
                            "no_mobile_action": 0.0,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (validation_dir / "task_family_opportunity_prior.json").write_text(
        json.dumps(
            {
                "uses_validation_data": True,
                "p_task_family": {"information_search_judgment": 1.0},
            }
        ),
        encoding="utf-8",
    )
    out_csv = tmp_path / "report.csv"

    write_validation_report(status_csv, validation_dir, out_csv)

    rows = list(csv.DictReader(out_csv.open("r", encoding="utf-8")))
    metrics = {row["metric"]: row["value"] for row in rows}
    assert metrics["mobile_intention_tvd"] == "0.000000"
    assert metrics["task_family_opportunity_tvd"] == "0.000000"
    assert metrics["sim_task_generated_per_evaluated_entry"] == "1.000000"


def test_validation_report_includes_app_context_metrics_when_targets_exist(tmp_path) -> None:
    status_csv = tmp_path / "mvp_status_step.csv"
    with status_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["agent_id", "day", "t", "status_json"])
        writer.writeheader()
        writer.writerow(
            {
                "agent_id": 1,
                "day": 4,
                "t": 3600.0,
                "status_json": json.dumps(
                    {
                        "proto_mobile_entry_decision": {
                            "entry_evaluated": True,
                            "selected_app_context": "finance_context",
                            "mapped_task_family": "payment_risk_confirmation",
                            "task_generated": True,
                            "audit": {
                                "final_selected_app_context": "finance_context",
                                "task_generated": True,
                            },
                        }
                    }
                ),
            }
        )
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    (validation_dir / "mobile_intention_prior_by_bucket_hour.json").write_text(
        json.dumps(
            {
                "uses_validation_data": True,
                "global_prior": {"p_mobile_intention": {"unknown_or_unmapped": 1.0}},
                "global_hourly_prior": {"1": {"p_mobile_intention": {"no_mobile_action": 0.0}}},
            }
        ),
        encoding="utf-8",
    )
    (validation_dir / "task_family_opportunity_prior.json").write_text(
        json.dumps(
            {
                "uses_validation_data": True,
                "p_task_family": {"payment_risk_confirmation": 1.0},
            }
        ),
        encoding="utf-8",
    )
    (validation_dir / "app_context_prior_by_bucket_hour_validation.json").write_text(
        json.dumps(
            {
                "uses_validation_data": True,
                "global_prior": {"p_app_context": {"finance_context": 1.0}},
                "global_hourly_prior": {
                    "1": {
                        "p_app_context": {"finance_context": 1.0},
                        "context_count": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    out_csv = tmp_path / "report.csv"

    write_validation_report(status_csv, validation_dir, out_csv)

    rows = list(csv.DictReader(out_csv.open("r", encoding="utf-8")))
    metrics = {row["metric"]: row["value"] for row in rows}
    assert metrics["app_context_tvd"] == "0.000000"
    assert metrics["task_eligible_context_mass_gap"] == "0.000000"
    assert metrics["context_only_mass_gap"] == "0.000000"


def test_mobile_intention_validation_requires_validation_marker(tmp_path) -> None:
    status_csv = tmp_path / "mvp_status_step.csv"
    status_csv.write_text("agent_id,day,t,status_json\n", encoding="utf-8")
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    (validation_dir / "mobile_intention_prior_by_bucket_hour.json").write_text(
        '{"uses_validation_data":false}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="uses_validation_data"):
        write_validation_report(status_csv, validation_dir, tmp_path / "report.csv")
