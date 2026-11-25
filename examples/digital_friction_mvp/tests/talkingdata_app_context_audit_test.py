from __future__ import annotations

"""Tests for the TalkingData app-context audit script."""

import csv

from audit_talkingdata_app_context import (
    classify_app_context,
    write_app_context_audit,
)


def test_finance_candidate_review_is_audit_only() -> None:
    result = classify_app_context("P2P", "unknown_or_unmapped")

    assert result.app_context == "finance_candidate_review"
    assert result.task_eligible is False
    assert result.candidate_task_families == ()
    assert result.review_status == "finance_candidate_needs_review"

    loans = classify_app_context("Consumer loans", "use_payment_or_finance")
    assert loans.app_context == "finance_candidate_review"
    assert loans.task_eligible is False


def test_taxonomy_profile_label_stays_context_only() -> None:
    result = classify_app_context("Industry tag", "unknown_or_unmapped")

    assert result.app_context == "taxonomy_profile_label"
    assert result.task_eligible is False
    assert result.review_status == "taxonomy_profile_label"


def test_context_only_examples_are_not_task_eligible() -> None:
    assert classify_app_context("Calendar", "unknown_or_unmapped").app_context == "device_tool_context"
    assert classify_app_context("Calendar", "unknown_or_unmapped").task_eligible is False
    assert classify_app_context("80s Japanese comic", "unknown_or_unmapped").app_context == (
        "media_entertainment_context"
    )
    assert classify_app_context("80s Japanese comic", "unknown_or_unmapped").task_eligible is False


def test_explicit_finance_context_has_task_opportunities() -> None:
    result = classify_app_context("Internet banking", "use_payment_or_finance")

    assert result.app_context == "finance_context"
    assert result.task_eligible is True
    assert "payment_risk_confirmation" in result.candidate_task_families


def test_write_app_context_audit_outputs_split_summaries(tmp_path) -> None:
    category_map = tmp_path / "category_to_mobile_intention_map.csv"
    with category_map.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category_raw",
                "category_normalized",
                "mobile_intention",
                "mapped_task_family",
                "mapping_confidence",
                "mapping_basis",
                "review_status",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "category_raw": "P2P",
                "category_normalized": "p2p",
                "mobile_intention": "unknown_or_unmapped",
                "mapped_task_family": "",
                "mapping_confidence": "0.000",
                "mapping_basis": "unmapped",
                "review_status": "auto_keyword_needs_human_review",
            }
        )
        writer.writerow(
            {
                "category_raw": "Internet banking",
                "category_normalized": "internet banking",
                "mobile_intention": "use_payment_or_finance",
                "mapped_task_family": "payment_risk_confirmation",
                "mapping_confidence": "0.800",
                "mapping_basis": "keyword_finance",
                "review_status": "auto_keyword_needs_human_review",
            }
        )
        writer.writerow(
            {
                "category_raw": "Industry tag",
                "category_normalized": "industry tag",
                "mobile_intention": "unknown_or_unmapped",
                "mapped_task_family": "",
                "mapping_confidence": "0.000",
                "mapping_basis": "unmapped",
                "review_status": "auto_keyword_needs_human_review",
            }
        )

    reference_csv = tmp_path / "elder_reference.csv"
    validation_csv = tmp_path / "elder_validation.csv"
    for path, categories in [
        (reference_csv, ["P2P", "P2P", "Internet banking", "Industry tag"]),
        (validation_csv, ["P2P", "Internet banking", "Internet banking"]),
    ]:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["is_active", "category"])
            writer.writeheader()
            for category in categories:
                writer.writerow({"is_active": "1.0", "category": category})
            writer.writerow({"is_active": "0.0", "category": "Internet banking"})

    outputs = write_app_context_audit(
        reference_csv=reference_csv,
        validation_csv=validation_csv,
        category_map=category_map,
        output_dir=tmp_path / "analysis",
    )

    audit_rows = list(csv.DictReader(outputs["audit_csv"].open("r", encoding="utf-8")))
    rows_by_category = {row["category_raw"]: row for row in audit_rows}
    assert rows_by_category["P2P"]["new_app_context"] == "finance_candidate_review"
    assert rows_by_category["P2P"]["task_eligible"] == "false"
    assert rows_by_category["Internet banking"]["new_app_context"] == "finance_context"
    assert rows_by_category["Internet banking"]["task_eligible"] == "true"

    comparison_rows = list(csv.DictReader(outputs["comparison_csv"].open("r", encoding="utf-8")))
    comparison_by_context = {row["app_context"]: row for row in comparison_rows}
    assert comparison_by_context["finance_candidate_review"]["mass_reference"] == "0.500000"
    assert comparison_by_context["finance_context"]["mass_validation"] == "0.666667"
