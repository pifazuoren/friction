#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


APP_CONTEXTS: tuple[str, ...] = (
    "finance_context",
    "finance_candidate_review",
    "public_service_context",
    "health_service_context",
    "shopping_lifestyle_context",
    "navigation_transport_context",
    "communication_social_context",
    "media_entertainment_context",
    "device_tool_context",
    "education_work_context",
    "taxonomy_profile_label",
    "unknown_or_unmapped",
)

TASK_OPPORTUNITY_BY_CONTEXT: dict[str, dict[str, float]] = {
    "finance_context": {
        "account_login_verification": 0.25,
        "information_search_judgment": 0.20,
        "payment_risk_confirmation": 0.40,
        "service_application_submission": 0.15,
    },
    "public_service_context": {
        "navigation_service_location": 0.25,
        "account_login_verification": 0.20,
        "profile_form_upload": 0.25,
        "service_application_submission": 0.30,
    },
    "health_service_context": {
        "navigation_service_location": 0.20,
        "account_login_verification": 0.15,
        "information_search_judgment": 0.20,
        "profile_form_upload": 0.20,
        "service_application_submission": 0.25,
    },
    "shopping_lifestyle_context": {
        "navigation_service_location": 0.15,
        "account_login_verification": 0.15,
        "information_search_judgment": 0.20,
        "payment_risk_confirmation": 0.30,
        "service_application_submission": 0.20,
    },
    "navigation_transport_context": {
        "navigation_service_location": 0.55,
        "information_search_judgment": 0.20,
        "account_login_verification": 0.10,
        "payment_risk_confirmation": 0.15,
    },
    "education_work_context": {
        "navigation_service_location": 0.15,
        "account_login_verification": 0.10,
        "information_search_judgment": 0.50,
        "profile_form_upload": 0.15,
        "service_application_submission": 0.10,
    },
}

TASK_ELIGIBLE_CONTEXTS: frozenset[str] = frozenset(TASK_OPPORTUNITY_BY_CONTEXT)

DEFAULT_REFERENCE_CSV = Path.home() / "Downloads/SeniorApp/TalkingData/elder_reference.csv"
DEFAULT_VALIDATION_CSV = Path.home() / "Downloads/SeniorApp/TalkingData/elder_validation.csv"
DEFAULT_CATEGORY_MAP = Path(
    "examples/digital_friction_mvp/mobile_intention_artifacts/category_to_mobile_intention_map.csv"
)
DEFAULT_OUTPUT_DIR = Path("examples/digital_friction_mvp/analysis")


@dataclass(frozen=True, slots=True)
class AppContextClassification:
    app_context: str
    task_eligible: bool
    candidate_task_families: tuple[str, ...]
    mapping_basis: str
    review_status: str


def normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, phrases: tuple[str, ...]) -> str:
    padded = f" {text} "
    for phrase in phrases:
        normalized = normalize_category(phrase)
        if normalized and f" {normalized} " in padded:
            return normalized
    return ""


def _make_classification(
    app_context: str,
    *,
    mapping_basis: str,
    review_status: str,
    task_eligible: bool | None = None,
) -> AppContextClassification:
    eligible = app_context in TASK_ELIGIBLE_CONTEXTS if task_eligible is None else bool(task_eligible)
    return AppContextClassification(
        app_context=app_context,
        task_eligible=eligible,
        candidate_task_families=tuple(TASK_OPPORTUNITY_BY_CONTEXT.get(app_context, {})),
        mapping_basis=mapping_basis,
        review_status=review_status,
    )


def classify_app_context(category: Any, old_mobile_intention: str = "") -> AppContextClassification:
    text = normalize_category(category)
    old_intention = str(old_mobile_intention or "").strip()
    if not text or text in {"unknown", "other", "others", "unclassified"}:
        return _make_classification(
            "unknown_or_unmapped",
            mapping_basis="empty_or_unknown_category",
            review_status="unknown_needs_review",
            task_eligible=False,
        )

    explicit_finance = (
        "internet banking",
        "mobile bank",
        "bank financing",
        "bank credit card",
        "third party payment",
        "wealth management",
        "financial services",
        "payment",
        "pay",
        "finance",
        "bank",
        "insurance",
        "credit card",
        "fund",
    )
    matched = _contains_any(text, explicit_finance)
    if matched:
        return _make_classification(
            "finance_context",
            mapping_basis=f"keyword_finance_context:{matched}",
            review_status="task_context_auto",
        )

    finance_review = (
        "p2p",
        "net loan",
        "loan",
        "loans",
        "financing",
        "crowdfunding",
        "securities",
        "shares",
        "stock",
        "futures",
        "fixed income",
        "debit and credit",
        "high risk",
        "low risk",
        "risk",
        "liquidity",
        "profitability",
        "financial supermarket",
        "financial",
        "lottery",
        "card management",
    )
    matched = _contains_any(text, finance_review)
    if matched:
        return _make_classification(
            "finance_candidate_review",
            mapping_basis=f"keyword_finance_candidate:{matched}",
            review_status="finance_candidate_needs_review",
            task_eligible=False,
        )

    taxonomy = (
        "industry tag",
        "property industry",
        "custom label",
        "customized",
        "services 1",
        "total cost",
        "personal effectiveness",
        "higher income",
        "low income",
        "income",
        "1 free",
        "1 reputation",
        "1 vitality",
        "nature",
        "cozy",
        "pursue",
        "high flow",
        "high mobility",
        "liquid medium",
        "quality",
        "reputation",
        "vitality",
    )
    matched = _contains_any(text, taxonomy)
    if matched:
        return _make_classification(
            "taxonomy_profile_label",
            mapping_basis=f"keyword_taxonomy_profile:{matched}",
            review_status="taxonomy_profile_label",
            task_eligible=False,
        )

    health = (
        "medical",
        "medicine",
        "health",
        "hospital",
        "doctor",
        "pharmacy",
        "drug",
        "clinic",
    )
    matched = _contains_any(text, health)
    if matched:
        return _make_classification(
            "health_service_context",
            mapping_basis=f"keyword_health_context:{matched}",
            review_status="task_context_auto",
        )

    shopping = (
        "online mall",
        "online malls",
        "online shopping",
        "shopping",
        "price comparing",
        "fashion",
        "beauty",
        "hotel",
        "food",
        "catering",
        "takeout",
        "maternal",
        "baby",
        "home appliance",
        "life shopping",
    )
    matched = _contains_any(text, shopping)
    if matched:
        return _make_classification(
            "shopping_lifestyle_context",
            mapping_basis=f"keyword_shopping_context:{matched}",
            review_status="task_context_auto",
        )

    navigation = (
        "map",
        "navigation",
        "transport",
        "taxi",
        "travel",
        "tourism",
        "flight",
        "airline",
        "aeronautical",
        "train",
        "bus",
        "weather",
        "location",
    )
    matched = _contains_any(text, navigation)
    if matched:
        return _make_classification(
            "navigation_transport_context",
            mapping_basis=f"keyword_navigation_context:{matched}",
            review_status="task_context_auto",
        )

    public_service = (
        "government",
        "public",
        "utility",
        "convenience services",
        "life service",
        "administrative",
        "social security",
        "provident",
        "service application",
    )
    matched = _contains_any(text, public_service)
    if matched:
        return _make_classification(
            "public_service_context",
            mapping_basis=f"keyword_public_service_context:{matched}",
            review_status="task_context_auto",
        )

    communication = (
        "im",
        "wechat",
        "weibo",
        "qq",
        "tencent",
        "community",
        "social",
        "chat",
        "contacts",
        "relatives",
        "church",
        "forum",
    )
    matched = _contains_any(text, communication)
    if matched:
        return _make_classification(
            "communication_social_context",
            mapping_basis=f"keyword_communication_context:{matched}",
            review_status="context_only_auto",
            task_eligible=False,
        )

    media = (
        "game",
        "comic",
        "video",
        "music",
        "radio",
        "news",
        "novel",
        "reading",
        "movie",
        "tv",
        "anime",
        "entertainment",
        "parkour",
        "arpg",
        "rpg",
        "casual game",
    )
    matched = _contains_any(text, media)
    if matched:
        return _make_classification(
            "media_entertainment_context",
            mapping_basis=f"keyword_media_context:{matched}",
            review_status="context_only_auto",
            task_eligible=False,
        )

    device_tool = (
        "calendar",
        "tool",
        "camera",
        "photo",
        "album",
        "cloud",
        "file",
        "document",
        "browser",
        "dictionary",
        "security",
        "system",
        "input",
        "wallpaper",
        "battery",
        "scanner",
    )
    matched = _contains_any(text, device_tool)
    if matched:
        return _make_classification(
            "device_tool_context",
            mapping_basis=f"keyword_device_tool_context:{matched}",
            review_status="context_only_auto",
            task_eligible=False,
        )

    education_work = (
        "education",
        "learning",
        "school",
        "exam",
        "technology information",
        "technology",
        "science",
        "office",
        "work",
        "recruit",
        "job",
        "accounting",
        "business",
        "productivity",
        "information",
        "search",
    )
    matched = _contains_any(text, education_work)
    if matched:
        return _make_classification(
            "education_work_context",
            mapping_basis=f"keyword_education_work_context:{matched}",
            review_status="task_context_auto",
        )

    old_intention_context = {
        "use_payment_or_finance": "finance_context",
        "submit_service_application": "public_service_context",
        "find_location_or_service": "navigation_transport_context",
        "check_information": "education_work_context",
        "communicate_or_seek_help": "communication_social_context",
        "browse_entertainment": "media_entertainment_context",
    }
    if old_intention in old_intention_context:
        app_context = old_intention_context[old_intention]
        return _make_classification(
            app_context,
            mapping_basis=f"old_mobile_intention_fallback:{old_intention}",
            review_status=(
                "task_context_from_old_intention_needs_review"
                if app_context in TASK_ELIGIBLE_CONTEXTS
                else "context_only_from_old_intention_needs_review"
            ),
            task_eligible=app_context in TASK_ELIGIBLE_CONTEXTS,
        )

    return _make_classification(
        "unknown_or_unmapped",
        mapping_basis="unmapped_after_app_context_rules",
        review_status="unknown_needs_review",
        task_eligible=False,
    )


def _read_old_category_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"category map not found: {path}")
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            category = str(row.get("category_raw", "") or "").strip()
            rows[category] = {
                "old_mobile_intention": str(row.get("mobile_intention", "") or "").strip(),
                "old_mapped_task_family": str(row.get("mapped_task_family", "") or "").strip(),
                "old_mapping_basis": str(row.get("mapping_basis", "") or "").strip(),
                "old_review_status": str(row.get("review_status", "") or "").strip(),
            }
    return rows


def _read_active_category_counts(path: Path) -> Counter[str]:
    if not path.exists():
        raise FileNotFoundError(f"TalkingData csv not found: {path}")
    counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if str(row.get("is_active", "1")).strip() in {"0", "0.0", "false", "False"}:
                continue
            category = str(row.get("category", "") or "").strip()
            counts[category] += 1
    return counts


def _mass(count: int, total: int) -> float:
    return float(count) / float(total) if total > 0 else 0.0


def _write_audit_csv(
    *,
    out_csv: Path,
    rows: list[dict[str, Any]],
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "category_raw",
        "category_normalized",
        "old_mobile_intention",
        "old_mapped_task_family",
        "old_mapping_basis",
        "new_app_context",
        "task_eligible",
        "candidate_task_families_json",
        "count_reference",
        "mass_reference",
        "count_validation",
        "mass_validation",
        "mapping_basis",
        "review_status",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_split_summary(
    *,
    out_csv: Path,
    split: str,
    counts_by_context: dict[str, int],
    category_counts_by_context: dict[str, int],
    total_count: int,
) -> None:
    fieldnames = [
        "split",
        "app_context",
        "count",
        "mass",
        "category_count",
        "task_eligible",
        "candidate_task_families_json",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for context in APP_CONTEXTS:
            writer.writerow(
                {
                    "split": split,
                    "app_context": context,
                    "count": int(counts_by_context.get(context, 0)),
                    "mass": f"{_mass(int(counts_by_context.get(context, 0)), total_count):.6f}",
                    "category_count": int(category_counts_by_context.get(context, 0)),
                    "task_eligible": str(context in TASK_ELIGIBLE_CONTEXTS).lower(),
                    "candidate_task_families_json": json.dumps(
                        list(TASK_OPPORTUNITY_BY_CONTEXT.get(context, {})),
                        ensure_ascii=False,
                    ),
                }
            )


def _write_comparison_summary(
    *,
    out_csv: Path,
    reference_counts: dict[str, int],
    validation_counts: dict[str, int],
    reference_total: int,
    validation_total: int,
) -> None:
    fieldnames = [
        "app_context",
        "count_reference",
        "mass_reference",
        "count_validation",
        "mass_validation",
        "delta_validation_minus_reference",
        "task_eligible",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for context in APP_CONTEXTS:
            ref_mass = _mass(int(reference_counts.get(context, 0)), reference_total)
            val_mass = _mass(int(validation_counts.get(context, 0)), validation_total)
            writer.writerow(
                {
                    "app_context": context,
                    "count_reference": int(reference_counts.get(context, 0)),
                    "mass_reference": f"{ref_mass:.6f}",
                    "count_validation": int(validation_counts.get(context, 0)),
                    "mass_validation": f"{val_mass:.6f}",
                    "delta_validation_minus_reference": f"{(val_mass - ref_mass):.6f}",
                    "task_eligible": str(context in TASK_ELIGIBLE_CONTEXTS).lower(),
                }
            )


def write_app_context_audit(
    *,
    reference_csv: Path,
    validation_csv: Path,
    category_map: Path,
    output_dir: Path,
) -> dict[str, Path]:
    old_map = _read_old_category_map(category_map)
    reference_counts = _read_active_category_counts(reference_csv)
    validation_counts = _read_active_category_counts(validation_csv)
    reference_total = sum(reference_counts.values())
    validation_total = sum(validation_counts.values())

    categories = sorted(set(old_map) | set(reference_counts) | set(validation_counts))
    rows: list[dict[str, Any]] = []
    reference_context_counts: defaultdict[str, int] = defaultdict(int)
    validation_context_counts: defaultdict[str, int] = defaultdict(int)
    reference_category_counts_by_context: defaultdict[str, int] = defaultdict(int)
    validation_category_counts_by_context: defaultdict[str, int] = defaultdict(int)

    for category in categories:
        old = old_map.get(category, {})
        old_mobile_intention = old.get("old_mobile_intention", "")
        classification = classify_app_context(category, old_mobile_intention)
        ref_count = int(reference_counts.get(category, 0))
        val_count = int(validation_counts.get(category, 0))
        reference_context_counts[classification.app_context] += ref_count
        validation_context_counts[classification.app_context] += val_count
        if ref_count > 0:
            reference_category_counts_by_context[classification.app_context] += 1
        if val_count > 0:
            validation_category_counts_by_context[classification.app_context] += 1
        rows.append(
            {
                "category_raw": category,
                "category_normalized": normalize_category(category),
                "old_mobile_intention": old_mobile_intention,
                "old_mapped_task_family": old.get("old_mapped_task_family", ""),
                "old_mapping_basis": old.get("old_mapping_basis", ""),
                "new_app_context": classification.app_context,
                "task_eligible": str(classification.task_eligible).lower(),
                "candidate_task_families_json": json.dumps(
                    list(classification.candidate_task_families),
                    ensure_ascii=False,
                ),
                "count_reference": ref_count,
                "mass_reference": f"{_mass(ref_count, reference_total):.6f}",
                "count_validation": val_count,
                "mass_validation": f"{_mass(val_count, validation_total):.6f}",
                "mapping_basis": classification.mapping_basis,
                "review_status": classification.review_status,
            }
        )

    rows.sort(
        key=lambda row: (
            -(int(row["count_reference"]) + int(row["count_validation"])),
            str(row["category_normalized"]),
        )
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    audit_csv = output_dir / "category_to_app_context_audit.csv"
    reference_summary_csv = output_dir / "app_context_summary_reference.csv"
    validation_summary_csv = output_dir / "app_context_summary_validation.csv"
    comparison_csv = output_dir / "app_context_summary_comparison.csv"

    _write_audit_csv(out_csv=audit_csv, rows=rows)
    _write_split_summary(
        out_csv=reference_summary_csv,
        split="elder_reference_may1_may3",
        counts_by_context=reference_context_counts,
        category_counts_by_context=reference_category_counts_by_context,
        total_count=reference_total,
    )
    _write_split_summary(
        out_csv=validation_summary_csv,
        split="elder_validation_may4_may7",
        counts_by_context=validation_context_counts,
        category_counts_by_context=validation_category_counts_by_context,
        total_count=validation_total,
    )
    _write_comparison_summary(
        out_csv=comparison_csv,
        reference_counts=reference_context_counts,
        validation_counts=validation_context_counts,
        reference_total=reference_total,
        validation_total=validation_total,
    )
    return {
        "audit_csv": audit_csv,
        "reference_summary_csv": reference_summary_csv,
        "validation_summary_csv": validation_summary_csv,
        "comparison_csv": comparison_csv,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit TalkingData category -> app-context mapping without changing "
            "the simulation entry layer."
        )
    )
    parser.add_argument("--reference-csv", type=Path, default=DEFAULT_REFERENCE_CSV)
    parser.add_argument("--validation-csv", type=Path, default=DEFAULT_VALIDATION_CSV)
    parser.add_argument("--category-map", type=Path, default=DEFAULT_CATEGORY_MAP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    outputs = write_app_context_audit(
        reference_csv=args.reference_csv,
        validation_csv=args.validation_csv,
        category_map=args.category_map,
        output_dir=args.output_dir,
    )
    for path in outputs.values():
        print(path)


if __name__ == "__main__":
    main()
