#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

MOBILE_INTENTIONS = (
    "check_information",
    "use_payment_or_finance",
    "login_or_verify_account",
    "submit_service_application",
    "upload_or_manage_profile",
    "find_location_or_service",
    "communicate_or_seek_help",
    "browse_entertainment",
    "no_mobile_action",
    "unknown_or_unmapped",
)

TASK_MAPPING = {
    "check_information": "information_search_judgment",
    "use_payment_or_finance": "payment_risk_confirmation",
    "login_or_verify_account": "account_login_verification",
    "submit_service_application": "service_application_submission",
    "upload_or_manage_profile": "profile_form_upload",
    "find_location_or_service": "navigation_service_location",
}


def _age_bucket(value: Any) -> str:
    try:
        age = int(float(value))
    except (TypeError, ValueError):
        return "unknown"
    if age < 65:
        return "lt65"
    if age < 75:
        return "65_74"
    return "75plus"


def _gender_bucket(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"f", "female", "女"}:
        return "female"
    if text in {"m", "male", "男"}:
        return "male"
    return "unknown"


def _category_to_intention(category: str) -> tuple[str, float, str]:
    text = str(category or "").strip().lower()
    if not text:
        return "unknown_or_unmapped", 0.0, "empty_category"
    finance = ("bank", "loan", "wealth", "fund", "stock", "payment", "pay", "finance")
    navigation = ("map", "navigation", "travel", "taxi", "transport", "weather")
    communication = ("social", "chat", "im", "community", "weibo", "wechat", "qq")
    entertainment = ("game", "music", "video", "entertain", "reading", "novel", "news")
    service = ("medical", "health", "service", "government", "utility", "life", "shopping")
    account = ("security", "password", "authentication", "login", "account")
    upload = ("photo", "camera", "album", "cloud", "document", "office")
    information = ("search", "browser", "education", "information", "tool", "dictionary")
    if any(token in text for token in finance):
        return "use_payment_or_finance", 0.80, "keyword_finance"
    if any(token in text for token in navigation):
        return "find_location_or_service", 0.78, "keyword_navigation"
    if any(token in text for token in communication):
        return "communicate_or_seek_help", 0.74, "keyword_communication"
    if any(token in text for token in entertainment):
        return "browse_entertainment", 0.74, "keyword_entertainment"
    if any(token in text for token in service):
        return "submit_service_application", 0.72, "keyword_service"
    if any(token in text for token in account):
        return "login_or_verify_account", 0.72, "keyword_account"
    if any(token in text for token in upload):
        return "upload_or_manage_profile", 0.72, "keyword_upload"
    if any(token in text for token in information):
        return "check_information", 0.70, "keyword_information"
    return "unknown_or_unmapped", 0.0, "unmapped"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _normalize(counter: Counter[str], include_no_mobile: float = 0.0) -> dict[str, float]:
    values = {intent: float(counter.get(intent, 0)) for intent in MOBILE_INTENTIONS}
    values["no_mobile_action"] += float(include_no_mobile)
    total = sum(values.values())
    if total <= 0:
        return {intent: (1.0 if intent == "no_mobile_action" else 0.0) for intent in MOBILE_INTENTIONS}
    return {intent: values[intent] / total for intent in MOBILE_INTENTIONS}


def build_artifacts(
    reference_csv: Path,
    output_dir: Path,
    *,
    source_split: str = "elder_reference_may1_may3",
    uses_validation_data: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    row_count = 0
    users: set[str] = set()
    active_users_by_bucket_hour: defaultdict[tuple[str, int], set[str]] = defaultdict(set)
    all_users_by_bucket: defaultdict[str, set[str]] = defaultdict(set)
    category_counts: Counter[tuple[str, int, str]] = Counter()
    intention_counts: Counter[tuple[str, int, str]] = Counter()
    user_intentions: defaultdict[str, Counter[str]] = defaultdict(Counter)
    category_mapping: dict[str, tuple[str, float, str]] = {}

    with reference_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_count += 1
            device_id = str(row.get("device_id", "")).strip()
            if device_id:
                users.add(device_id)
            gender = _gender_bucket(row.get("gender"))
            age = _age_bucket(row.get("age"))
            bucket = f"{age}|{gender}|digital_mid"
            all_users_by_bucket[bucket].add(device_id)
            timestamp = str(row.get("timestamp", "")).strip()
            try:
                hour = int(timestamp[11:13])
            except (TypeError, ValueError):
                hour = 0
            if str(row.get("is_active", "1")).strip() in {"0", "0.0", "false", "False"}:
                continue
            category = str(row.get("category", "")).strip()
            active_users_by_bucket_hour[(bucket, hour)].add(device_id)
            category_counts[(bucket, hour, category)] += 1
            intention, confidence, basis = category_mapping.get(
                category,
                _category_to_intention(category),
            )
            category_mapping[category] = (intention, confidence, basis)
            intention_counts[(bucket, hour, intention)] += 1
            if device_id:
                user_intentions[device_id][intention] += 1

    calibration: dict[str, Any] = {
        "source_split": source_split,
        "schema_version": "mobile_intention_calibration_v1",
        "source_hash": _hash_file(reference_csv),
        "row_count": row_count,
        "user_count": len(users),
        "uses_validation_data": bool(uses_validation_data),
        "mobile_intention_prior_by_bucket_hour": {},
        "global_hourly_prior": {},
        "global_prior": {},
    }

    total_intentions: Counter[str] = Counter()
    hourly_totals: defaultdict[int, Counter[str]] = defaultdict(Counter)
    for (bucket, hour, intention), count in intention_counts.items():
        total_intentions[intention] += count
        hourly_totals[hour][intention] += count
        key = f"{bucket}|hour={hour}"
        calibration["mobile_intention_prior_by_bucket_hour"].setdefault(
            key,
            {
                "bucket": bucket,
                "hour": hour,
                "p_mobile_intention": {},
                "active_user_count": len(active_users_by_bucket_hour[(bucket, hour)]),
                "bucket_user_count": len(all_users_by_bucket[bucket]),
            },
        )
    for key, row in calibration["mobile_intention_prior_by_bucket_hour"].items():
        bucket = row["bucket"]
        hour = int(row["hour"])
        counter = Counter(
            {
                intention: intention_counts[(bucket, hour, intention)]
                for intention in MOBILE_INTENTIONS
            }
        )
        inactive_mass = max(0, len(all_users_by_bucket[bucket]) - len(active_users_by_bucket_hour[(bucket, hour)]))
        row["p_mobile_intention"] = _normalize(counter, include_no_mobile=inactive_mass)
    for hour, counter in hourly_totals.items():
        calibration["global_hourly_prior"][str(hour)] = {
            "hour": hour,
            "p_mobile_intention": _normalize(counter),
        }
    calibration["global_prior"] = {"p_mobile_intention": _normalize(total_intentions)}

    (output_dir / "mobile_intention_prior_by_bucket_hour.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "calibration_manifest.json").write_text(
        json.dumps(
            {
                "source_split": source_split,
                "source_path": str(reference_csv),
                "source_hash": calibration["source_hash"],
                "row_count": row_count,
                "user_count": len(users),
                "uses_validation_data": bool(uses_validation_data),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (output_dir / "profile_bucket_definitions.json").write_text(
        json.dumps(
            {
                "age_bucket": ["lt65", "65_74", "75plus", "unknown"],
                "gender_bucket": ["female", "male", "unknown"],
                "digital_bucket": ["digital_mid"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with (output_dir / "category_to_mobile_intention_map.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
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
        for category in sorted(category_mapping):
            intention, confidence, basis = category_mapping[category]
            writer.writerow(
                {
                    "category_raw": category,
                    "category_normalized": category.lower(),
                    "mobile_intention": intention,
                    "mapped_task_family": TASK_MAPPING.get(intention, ""),
                    "mapping_confidence": f"{confidence:.3f}",
                    "mapping_basis": basis,
                    "review_status": "auto_keyword_needs_human_review",
                }
            )
    (output_dir / "mobile_intention_mapping.json").write_text(
        json.dumps(
            {
                "source_split": source_split,
                "uses_validation_data": bool(uses_validation_data),
                "mobile_intention_mapping": {
                    intention: {
                        "mapped_task_family": TASK_MAPPING.get(intention),
                        "mapping_confidence": 1.0
                        if intention in TASK_MAPPING
                        else 0.0,
                    }
                    for intention in MOBILE_INTENTIONS
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    task_prior = Counter()
    mapped_mass = 0
    unknown_mass = 0
    for intention, count in total_intentions.items():
        if intention in TASK_MAPPING:
            task_prior[TASK_MAPPING[intention]] += count
            mapped_mass += count
        else:
            unknown_mass += count
    (output_dir / "task_family_opportunity_prior.json").write_text(
        json.dumps(
            {
                "source_split": source_split,
                "uses_validation_data": bool(uses_validation_data),
                "p_task_family": {
                    family: count / max(1, sum(task_prior.values()))
                    for family, count in sorted(task_prior.items())
                },
                "mapped_task_coverage": mapped_mass / max(1, mapped_mass + unknown_mass),
                "unknown_or_context_mass": unknown_mass / max(1, mapped_mass + unknown_mass),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with (output_dir / "user_preference_profiles.jsonl").open("w", encoding="utf-8") as handle:
        for device_id, counter in sorted(user_intentions.items()):
            handle.write(
                json.dumps(
                    {
                        "device_id_hash": hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:16],
                        "mobile_intention_vector": _normalize(counter),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    with (output_dir / "mapping_coverage_report.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "total_category_count",
                "mapped_high_confidence_mass",
                "low_confidence_mass",
                "unknown_or_unmapped_mass",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "total_category_count": len(category_mapping),
                "mapped_high_confidence_mass": mapped_mass,
                "low_confidence_mass": 0,
                "unknown_or_unmapped_mass": unknown_mass,
            }
        )
    with (output_dir / "category_distribution_by_bucket_hour.json").open("w", encoding="utf-8") as handle:
        payload = {
            f"{bucket}|hour={hour}|{category}": count
            for (bucket, hour, category), count in category_counts.items()
        }
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    with (output_dir / "hourly_mobile_activity_profile.json").open("w", encoding="utf-8") as handle:
        payload = {
            f"{bucket}|hour={hour}": {
                "active_user_count": len(active_users_by_bucket_hour[(bucket, hour)]),
                "bucket_user_count": len(all_users_by_bucket[bucket]),
            }
            for bucket in all_users_by_bucket
            for hour in range(24)
        }
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--validation-csv",
        default="",
        help="Optional held-out May4-May7 CSV; outputs validation-only targets.",
    )
    parser.add_argument(
        "--validation-output-dir",
        default="",
        help="Defaults to <output-dir>/heldout_validation when --validation-csv is set.",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    build_artifacts(
        Path(args.reference_csv),
        output_dir,
        source_split="elder_reference_may1_may3",
        uses_validation_data=False,
    )
    if str(args.validation_csv).strip():
        validation_output_dir = (
            Path(args.validation_output_dir)
            if str(args.validation_output_dir).strip()
            else output_dir / "heldout_validation"
        )
        build_artifacts(
            Path(args.validation_csv),
            validation_output_dir,
            source_split="elder_validation_may4_may7",
            uses_validation_data=True,
        )


if __name__ == "__main__":
    main()
