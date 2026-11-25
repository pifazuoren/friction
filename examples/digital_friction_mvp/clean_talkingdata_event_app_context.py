#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from audit_talkingdata_app_context import normalize_category
except ModuleNotFoundError:
    from .audit_talkingdata_app_context import normalize_category


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
    "taxonomy_profile_only",
    "unknown_or_unmapped",
)

TASK_ELIGIBLE_CONTEXTS: frozenset[str] = frozenset(
    {
        "finance_context",
        "public_service_context",
        "health_service_context",
        "shopping_lifestyle_context",
        "navigation_transport_context",
        "education_work_context",
    }
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

CONTEXT_PRIORITY: tuple[str, ...] = (
    "finance_context",
    "health_service_context",
    "public_service_context",
    "navigation_transport_context",
    "shopping_lifestyle_context",
    "education_work_context",
    "communication_social_context",
    "media_entertainment_context",
    "device_tool_context",
)

CONTEXT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "finance_context": (
        "finance",
        "internet banking",
        "mobile bank",
        "bank financing",
        "bank credit card",
        "direct bank",
        "third party payment",
        "wealth management",
        "financial services",
        "payment",
        "pay",
        "insurance",
        "credit card",
        "fund",
    ),
    "health_service_context": (
        "medical",
        "medicine",
        "health",
        "hospital",
        "doctor",
        "pharmacy",
        "drug",
        "clinic",
    ),
    "public_service_context": (
        "government",
        "public",
        "utility",
        "administrative",
        "social security",
        "provident",
        "service application",
    ),
    "navigation_transport_context": (
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
        "location",
    ),
    "shopping_lifestyle_context": (
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
    ),
    "education_work_context": (
        "education",
        "learning",
        "school",
        "exam",
        "office",
        "work",
        "recruit",
        "job",
        "jobs",
        "professional skills",
        "accounting",
        "business",
    ),
    "communication_social_context": (
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
    ),
    "media_entertainment_context": (
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
        "sports",
        "literature",
    ),
    "device_tool_context": (
        "calendar",
        "tool",
        "camera",
        "photo",
        "picture",
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
        "notes",
        "network disk",
        "scheduling",
    ),
}

FINANCE_REVIEW_KEYWORDS: tuple[str, ...] = (
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

TAXONOMY_PROFILE_KEYWORDS: tuple[str, ...] = (
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
    "relatives 1",
    "irritation fun",
    "simple",
    "enthusiasm",
    "noble",
    "classical",
    "comfortable",
    "and the church",
    "church",
)

WEAK_CONTEXT_ONLY_KEYWORDS: tuple[str, ...] = (
    "technology information",
    "science and technology",
    "science and technology 1",
    "financial information",
    "information",
    "technology",
    "science",
    "search",
    "weather",
    "convenience services",
    "life service",
)

DEFAULT_RAW_DIR = Path.home() / "Downloads" / "talkingdata-mobile-user-demographics"
DEFAULT_OUTPUT_DIR = Path(
    "examples/digital_friction_mvp/analysis/talkingdata_v3_event_app_context"
)
REFERENCE_START = "2016-05-01"
VALIDATION_START = "2016-05-04"


@dataclass(frozen=True, slots=True)
class EventInfo:
    event_id: str
    device_id: str
    gender: str
    age: str
    timestamp: str
    date: str
    hour: int
    longitude: str
    latitude: str
    phone_brand: str
    device_model: str
    split: str
    profile_bucket: str


@dataclass(frozen=True, slots=True)
class AppContextResult:
    app_context: str
    task_eligible: bool
    matched_contexts: tuple[str, ...]
    mapping_basis: str
    review_status: str


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _age_bucket(value: Any) -> str:
    age = _safe_int(value, -1)
    if age < 0:
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


def _profile_bucket(gender: Any, age: Any) -> str:
    return f"{_age_bucket(age)}|{_gender_bucket(gender)}|digital_mid"


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = normalize_category(phrase)
    if not normalized:
        return False
    return f" {normalized} " in f" {text} "


def _matches_any(text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(keyword for keyword in keywords if _contains_phrase(text, keyword))


def _review_status_for_strong_match(
    *,
    selected: str,
    matched_contexts: list[str],
    weak_matches: tuple[str, ...],
) -> str:
    if selected in TASK_ELIGIBLE_CONTEXTS:
        if len(matched_contexts) > 1 or weak_matches:
            return "mixed_evidence_task_context"
        return "task_context_auto"
    if len(matched_contexts) > 1 or weak_matches:
        return "mixed_evidence_context_only"
    return "context_only_auto"


def _load_profiles(path: Path) -> dict[str, tuple[str, str]]:
    profiles: dict[str, tuple[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            age = _safe_int(row.get("age"), -1)
            if age <= 45:
                continue
            device_id = str(row.get("device_id", "") or "").strip()
            if not device_id:
                continue
            profiles[device_id] = (
                str(row.get("gender", "") or "").strip(),
                str(row.get("age", "") or "").strip(),
            )
    return profiles


def _load_phone_models(path: Path) -> dict[str, tuple[str, str]]:
    values: dict[str, tuple[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            device_id = str(row.get("device_id", "") or "").strip()
            if device_id and device_id not in values:
                values[device_id] = (
                    str(row.get("phone_brand", "") or "").strip(),
                    str(row.get("device_model", "") or "").strip(),
                )
    return values


def _find_eligible_devices(events_csv: Path, profiles: dict[str, tuple[str, str]]) -> set[str]:
    days_by_device: defaultdict[str, set[str]] = defaultdict(set)
    with events_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            device_id = str(row.get("device_id", "") or "").strip()
            if device_id not in profiles:
                continue
            timestamp = str(row.get("timestamp", "") or "").strip()
            date = timestamp[:10]
            if date < REFERENCE_START:
                continue
            days_by_device[device_id].add(date)
    eligible: set[str] = set()
    for device_id, days in days_by_device.items():
        reference_days = {day for day in days if REFERENCE_START <= day < VALIDATION_START}
        validation_days = {day for day in days if day >= VALIDATION_START}
        if len(days) >= 5 and len(reference_days) >= 2 and len(validation_days) >= 2:
            eligible.add(device_id)
    return eligible


def _load_events(
    events_csv: Path,
    *,
    profiles: dict[str, tuple[str, str]],
    phone_models: dict[str, tuple[str, str]],
    eligible_devices: set[str],
) -> dict[str, EventInfo]:
    events: dict[str, EventInfo] = {}
    with events_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            device_id = str(row.get("device_id", "") or "").strip()
            if device_id not in eligible_devices:
                continue
            timestamp = str(row.get("timestamp", "") or "").strip()
            date = timestamp[:10]
            if date < REFERENCE_START:
                continue
            split = "reference" if date < VALIDATION_START else "validation"
            gender, age = profiles[device_id]
            brand, model = phone_models.get(device_id, ("", ""))
            hour = _safe_int(timestamp[11:13], 0) if len(timestamp) >= 13 else 0
            event_id = str(row.get("event_id", "") or "").strip()
            if not event_id:
                continue
            events[event_id] = EventInfo(
                event_id=event_id,
                device_id=device_id,
                gender=gender,
                age=age,
                timestamp=timestamp,
                date=date,
                hour=hour,
                longitude=str(row.get("longitude", "") or "").strip(),
                latitude=str(row.get("latitude", "") or "").strip(),
                phone_brand=brand,
                device_model=model,
                split=split,
                profile_bucket=_profile_bucket(gender, age),
            )
    return events


def _load_app_labels(raw_dir: Path) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    label_to_category: dict[str, str] = {}
    with (raw_dir / "label_categories.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            label_id = str(row.get("label_id", "") or "").strip()
            if label_id:
                label_to_category[label_id] = str(row.get("category", "") or "").strip()
    labels_by_app: defaultdict[str, list[str]] = defaultdict(list)
    categories_by_app: defaultdict[str, list[str]] = defaultdict(list)
    with (raw_dir / "app_labels.csv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            app_id = str(row.get("app_id", "") or "").strip()
            label_id = str(row.get("label_id", "") or "").strip()
            if not app_id or not label_id:
                continue
            labels_by_app[app_id].append(label_id)
            categories_by_app[app_id].append(label_to_category.get(label_id, ""))
    return (
        {app_id: tuple(values) for app_id, values in labels_by_app.items()},
        {app_id: tuple(values) for app_id, values in categories_by_app.items()},
    )


def classify_categories(categories: tuple[str, ...] | list[str]) -> AppContextResult:
    normalized_categories = [normalize_category(category) for category in categories]
    normalized_categories = [value for value in normalized_categories if value]
    if not normalized_categories or all(value in {"unknown", "other", "unclassified"} for value in normalized_categories):
        return AppContextResult(
            app_context="unknown_or_unmapped",
            task_eligible=False,
            matched_contexts=(),
            mapping_basis="empty_or_unknown_labels",
            review_status="unknown_needs_review",
        )

    joined = " ".join(normalized_categories)
    weak_matches = _matches_any(joined, WEAK_CONTEXT_ONLY_KEYWORDS)
    if _contains_phrase(joined, "online shopping navigation"):
        return AppContextResult(
            app_context="shopping_lifestyle_context",
            task_eligible=True,
            matched_contexts=("shopping_lifestyle_context",),
            mapping_basis="strict_special_case:online_shopping_navigation",
            review_status="task_context_auto",
        )

    matched_contexts: list[str] = []
    matched_terms: dict[str, tuple[str, ...]] = {}
    for context, keywords in CONTEXT_KEYWORDS.items():
        matches = _matches_any(joined, keywords)
        if matches:
            matched_contexts.append(context)
            matched_terms[context] = matches

    if matched_contexts:
        for context in CONTEXT_PRIORITY:
            if context in matched_contexts:
                selected = context
                break
        else:
            selected = matched_contexts[0]
        return AppContextResult(
            app_context=selected,
            task_eligible=selected in TASK_ELIGIBLE_CONTEXTS,
            matched_contexts=tuple(matched_contexts),
            mapping_basis=f"strong_context_keywords:{selected}:{','.join(matched_terms[selected])}",
            review_status=_review_status_for_strong_match(
                selected=selected,
                matched_contexts=matched_contexts,
                weak_matches=weak_matches,
            ),
        )

    finance_matches = _matches_any(joined, FINANCE_REVIEW_KEYWORDS)
    if finance_matches:
        return AppContextResult(
            app_context="finance_candidate_review",
            task_eligible=False,
            matched_contexts=("finance_candidate_review",),
            mapping_basis=f"finance_candidate_keywords:{','.join(finance_matches)}",
            review_status="finance_candidate_needs_review",
        )

    taxonomy_matches = _matches_any(joined, TAXONOMY_PROFILE_KEYWORDS)
    if taxonomy_matches:
        return AppContextResult(
            app_context="taxonomy_profile_only",
            task_eligible=False,
            matched_contexts=("taxonomy_profile_only",),
            mapping_basis=f"taxonomy_profile_only:{','.join(taxonomy_matches)}",
            review_status="taxonomy_profile_only",
        )

    if weak_matches:
        return AppContextResult(
            app_context="unknown_or_unmapped",
            task_eligible=False,
            matched_contexts=("unknown_or_unmapped",),
            mapping_basis=f"weak_context_only_keywords:{','.join(weak_matches)}",
            review_status="ambiguous_context_only",
        )

    return AppContextResult(
        app_context="unknown_or_unmapped",
        task_eligible=False,
        matched_contexts=(),
        mapping_basis="unmapped_after_event_app_rules",
        review_status="unknown_needs_review",
    )


def _normalize_counter(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, float]:
    total = sum(max(0, int(counter.get(key, 0))) for key in keys)
    if total <= 0:
        return {key: 0.0 for key in keys}
    return {key: max(0, int(counter.get(key, 0))) / total for key in keys}


def _write_context_prior(
    *,
    out_path: Path,
    split: str,
    raw_hashes: dict[str, str],
    context_counts: Counter[tuple[str, int, str]],
    active_users_by_bucket_hour: dict[tuple[str, int], set[str]],
    bucket_users: dict[str, set[str]],
    total_context_counts: Counter[str],
    row_count: int,
    uses_validation_data: bool,
) -> None:
    prior: dict[str, Any] = {
        "schema_version": "talkingdata_app_context_prior_v3",
        "source_split": split,
        "uses_validation_data": bool(uses_validation_data),
        "raw_hashes": raw_hashes,
        "row_count": row_count,
        "app_contexts": list(APP_CONTEXTS),
        "task_eligible_contexts": sorted(TASK_ELIGIBLE_CONTEXTS),
        "app_context_prior_by_bucket_hour": {},
        "global_hourly_prior": {},
        "global_prior": {
            "p_app_context": _normalize_counter(total_context_counts, APP_CONTEXTS),
        },
    }

    hourly_counts: defaultdict[int, Counter[str]] = defaultdict(Counter)
    for (bucket, hour, context), count in context_counts.items():
        hourly_counts[hour][context] += count
        key = f"{bucket}|hour={hour}"
        row_counts = Counter(
            {
                item: context_counts.get((bucket, hour, item), 0)
                for item in APP_CONTEXTS
            }
        )
        prior["app_context_prior_by_bucket_hour"][key] = {
            "bucket": bucket,
            "hour": hour,
            "p_app_context": _normalize_counter(row_counts, APP_CONTEXTS),
            "context_count": sum(row_counts.values()),
            "active_user_count": len(active_users_by_bucket_hour.get((bucket, hour), set())),
            "bucket_user_count": len(bucket_users.get(bucket, set())),
        }
    for hour, counts in hourly_counts.items():
        prior["global_hourly_prior"][str(hour)] = {
            "hour": hour,
            "p_app_context": _normalize_counter(counts, APP_CONTEXTS),
            "context_count": sum(counts.values()),
        }
    out_path.write_text(
        json.dumps(prior, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_task_opportunity_prior(
    *,
    out_path: Path,
    raw_hashes: dict[str, str],
) -> None:
    payload = {
        "schema_version": "talkingdata_task_opportunity_by_context_v1",
        "source": "manual_prototype_bridge_from_app_context",
        "uses_validation_data": False,
        "raw_hashes": raw_hashes,
        "task_eligible_contexts": sorted(TASK_ELIGIBLE_CONTEXTS),
        "context_only_contexts": sorted(
            context for context in APP_CONTEXTS if context not in TASK_ELIGIBLE_CONTEXTS
        ),
        "task_opportunity_by_context": TASK_OPPORTUNITY_BY_CONTEXT,
        "notes": [
            "TalkingData provides app-level context, not app-internal task labels.",
            "This artifact is a conservative prototype bridge from app context to possible digital friction task family.",
            "v3 strict cleaning does not promote ambiguous taxonomy/profile/content labels to task-eligible contexts.",
            "finance_candidate_review is audit-only and not task-eligible in this version.",
        ],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_summary_csv(
    *,
    out_path: Path,
    split: str,
    context_counts: Counter[str],
    context_app_counts: Counter[str],
    total_rows: int,
) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "split",
                "app_context",
                "count",
                "mass",
                "unique_app_count",
                "task_eligible",
            ],
        )
        writer.writeheader()
        for context in APP_CONTEXTS:
            count = int(context_counts.get(context, 0))
            writer.writerow(
                {
                    "split": split,
                    "app_context": context,
                    "count": count,
                    "mass": f"{(count / total_rows if total_rows else 0.0):.6f}",
                    "unique_app_count": int(context_app_counts.get(context, 0)),
                    "task_eligible": str(context in TASK_ELIGIBLE_CONTEXTS).lower(),
                }
            )


def _write_comparison_csv(
    *,
    out_path: Path,
    reference_counts: Counter[str],
    validation_counts: Counter[str],
    reference_total: int,
    validation_total: int,
) -> None:
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "app_context",
                "count_reference",
                "mass_reference",
                "count_validation",
                "mass_validation",
                "delta_validation_minus_reference",
                "task_eligible",
            ],
        )
        writer.writeheader()
        for context in APP_CONTEXTS:
            ref_count = int(reference_counts.get(context, 0))
            val_count = int(validation_counts.get(context, 0))
            ref_mass = ref_count / reference_total if reference_total else 0.0
            val_mass = val_count / validation_total if validation_total else 0.0
            writer.writerow(
                {
                    "app_context": context,
                    "count_reference": ref_count,
                    "mass_reference": f"{ref_mass:.6f}",
                    "count_validation": val_count,
                    "mass_validation": f"{val_mass:.6f}",
                    "delta_validation_minus_reference": f"{(val_mass - ref_mass):.6f}",
                    "task_eligible": str(context in TASK_ELIGIBLE_CONTEXTS).lower(),
                }
            )


def clean_talkingdata_event_app_context(raw_dir: Path, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_paths = {
        name: raw_dir / name
        for name in (
            "gender_age_train.csv",
            "events.csv",
            "app_events.csv",
            "app_labels.csv",
            "label_categories.csv",
            "phone_brand_device_model.csv",
        )
    }
    for path in raw_paths.values():
        if not path.exists():
            raise FileNotFoundError(f"raw TalkingData file not found: {path}")

    raw_hashes = {name: _hash_file(path) for name, path in raw_paths.items()}
    profiles = _load_profiles(raw_paths["gender_age_train.csv"])
    phone_models = _load_phone_models(raw_paths["phone_brand_device_model.csv"])
    eligible_devices = _find_eligible_devices(raw_paths["events.csv"], profiles)
    events = _load_events(
        raw_paths["events.csv"],
        profiles=profiles,
        phone_models=phone_models,
        eligible_devices=eligible_devices,
    )
    label_ids_by_app, categories_by_app = _load_app_labels(raw_dir)

    reference_out = output_dir / "elder_reference_event_app_context.csv"
    validation_out = output_dir / "elder_validation_event_app_context.csv"
    category_label_audit = output_dir / "category_label_audit.csv"

    fieldnames = [
        "event_id",
        "device_id",
        "gender",
        "age",
        "timestamp",
        "date",
        "hour",
        "longitude",
        "latitude",
        "app_id",
        "is_installed",
        "is_active",
        "label_ids_json",
        "categories_json",
        "app_context",
        "task_eligible",
        "matched_contexts_json",
        "context_mapping_basis",
        "context_review_status",
        "profile_bucket",
        "phone_brand",
        "device_model",
    ]

    context_counts_by_split: dict[str, Counter[str]] = {
        "reference": Counter(),
        "validation": Counter(),
    }
    context_app_sets_by_split: dict[str, defaultdict[str, set[str]]] = {
        "reference": defaultdict(set),
        "validation": defaultdict(set),
    }
    context_counts_by_bucket_hour: dict[str, Counter[tuple[str, int, str]]] = {
        "reference": Counter(),
        "validation": Counter(),
    }
    active_users_by_bucket_hour: dict[str, defaultdict[tuple[str, int], set[str]]] = {
        "reference": defaultdict(set),
        "validation": defaultdict(set),
    }
    bucket_users: dict[str, defaultdict[str, set[str]]] = {
        "reference": defaultdict(set),
        "validation": defaultdict(set),
    }
    category_audit_counts: Counter[tuple[str, str, str, str]] = Counter()
    rows_by_split = {"reference": 0, "validation": 0}

    with reference_out.open("w", encoding="utf-8", newline="") as ref_handle, validation_out.open(
        "w", encoding="utf-8", newline=""
    ) as val_handle:
        writers = {
            "reference": csv.DictWriter(ref_handle, fieldnames=fieldnames),
            "validation": csv.DictWriter(val_handle, fieldnames=fieldnames),
        }
        writers["reference"].writeheader()
        writers["validation"].writeheader()

        with raw_paths["app_events.csv"].open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if str(row.get("is_active", "")).strip() not in {"1", "1.0", "true", "True"}:
                    continue
                event_id = str(row.get("event_id", "") or "").strip()
                event = events.get(event_id)
                if event is None:
                    continue
                app_id = str(row.get("app_id", "") or "").strip()
                label_ids = label_ids_by_app.get(app_id, ())
                categories = categories_by_app.get(app_id, ())
                result = classify_categories(categories)
                split = event.split
                rows_by_split[split] += 1
                context_counts_by_split[split][result.app_context] += 1
                context_app_sets_by_split[split][result.app_context].add(app_id)
                context_counts_by_bucket_hour[split][
                    (event.profile_bucket, event.hour, result.app_context)
                ] += 1
                active_users_by_bucket_hour[split][(event.profile_bucket, event.hour)].add(
                    event.device_id
                )
                bucket_users[split][event.profile_bucket].add(event.device_id)
                for category in categories:
                    category_audit_counts[
                        (
                            str(category),
                            result.app_context,
                            result.mapping_basis,
                            result.review_status,
                        )
                    ] += 1
                writers[split].writerow(
                    {
                        "event_id": event.event_id,
                        "device_id": event.device_id,
                        "gender": event.gender,
                        "age": event.age,
                        "timestamp": event.timestamp,
                        "date": event.date,
                        "hour": event.hour,
                        "longitude": event.longitude,
                        "latitude": event.latitude,
                        "app_id": app_id,
                        "is_installed": str(row.get("is_installed", "") or "").strip(),
                        "is_active": str(row.get("is_active", "") or "").strip(),
                        "label_ids_json": json.dumps(list(label_ids), ensure_ascii=False),
                        "categories_json": json.dumps(list(categories), ensure_ascii=False),
                        "app_context": result.app_context,
                        "task_eligible": str(result.task_eligible).lower(),
                        "matched_contexts_json": json.dumps(
                            list(result.matched_contexts),
                            ensure_ascii=False,
                        ),
                        "context_mapping_basis": result.mapping_basis,
                        "context_review_status": result.review_status,
                        "profile_bucket": event.profile_bucket,
                        "phone_brand": event.phone_brand,
                        "device_model": event.device_model,
                    }
                )

    with category_label_audit.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category_raw",
                "category_normalized",
                "app_context",
                "context_mapping_basis",
                "context_review_status",
                "event_app_label_count",
            ],
        )
        writer.writeheader()
        for (category, context, basis, status), count in sorted(
            category_audit_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            writer.writerow(
                {
                    "category_raw": category,
                    "category_normalized": normalize_category(category),
                    "app_context": context,
                    "context_mapping_basis": basis,
                    "context_review_status": status,
                    "event_app_label_count": int(count),
                }
            )

    reference_context_app_counts = Counter(
        {
            context: len(apps)
            for context, apps in context_app_sets_by_split["reference"].items()
        }
    )
    validation_context_app_counts = Counter(
        {
            context: len(apps)
            for context, apps in context_app_sets_by_split["validation"].items()
        }
    )
    reference_summary = output_dir / "app_context_summary_reference.csv"
    validation_summary = output_dir / "app_context_summary_validation.csv"
    comparison_summary = output_dir / "app_context_summary_comparison.csv"
    _write_summary_csv(
        out_path=reference_summary,
        split="elder_reference_may1_may3_event_app",
        context_counts=context_counts_by_split["reference"],
        context_app_counts=reference_context_app_counts,
        total_rows=rows_by_split["reference"],
    )
    _write_summary_csv(
        out_path=validation_summary,
        split="elder_validation_may4_may7_event_app",
        context_counts=context_counts_by_split["validation"],
        context_app_counts=validation_context_app_counts,
        total_rows=rows_by_split["validation"],
    )
    _write_comparison_csv(
        out_path=comparison_summary,
        reference_counts=context_counts_by_split["reference"],
        validation_counts=context_counts_by_split["validation"],
        reference_total=rows_by_split["reference"],
        validation_total=rows_by_split["validation"],
    )

    reference_prior = output_dir / "app_context_prior_by_bucket_hour_reference.json"
    validation_prior = output_dir / "app_context_prior_by_bucket_hour_validation.json"
    task_opportunity_prior = output_dir / "task_opportunity_prior_by_context.json"
    _write_context_prior(
        out_path=reference_prior,
        split="elder_reference_may1_may3_event_app",
        raw_hashes=raw_hashes,
        context_counts=context_counts_by_bucket_hour["reference"],
        active_users_by_bucket_hour=active_users_by_bucket_hour["reference"],
        bucket_users=bucket_users["reference"],
        total_context_counts=context_counts_by_split["reference"],
        row_count=rows_by_split["reference"],
        uses_validation_data=False,
    )
    _write_context_prior(
        out_path=validation_prior,
        split="elder_validation_may4_may7_event_app",
        raw_hashes=raw_hashes,
        context_counts=context_counts_by_bucket_hour["validation"],
        active_users_by_bucket_hour=active_users_by_bucket_hour["validation"],
        bucket_users=bucket_users["validation"],
        total_context_counts=context_counts_by_split["validation"],
        row_count=rows_by_split["validation"],
        uses_validation_data=True,
    )
    _write_task_opportunity_prior(
        out_path=task_opportunity_prior,
        raw_hashes=raw_hashes,
    )

    manifest = output_dir / "cleaning_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "talkingdata_event_app_context_cleaning_v3",
                "raw_dir": str(raw_dir),
                "raw_hashes": raw_hashes,
                "eligible_device_count": len(eligible_devices),
                "event_count": len(events),
                "reference_event_app_rows": rows_by_split["reference"],
                "validation_event_app_rows": rows_by_split["validation"],
                "reference_start": REFERENCE_START,
                "validation_start": VALIDATION_START,
                "age_filter": "age > 45",
                "active_filter": "app_events.is_active == 1",
                "unit_of_analysis": "event_id + app_id active app exposure",
                "notes": [
                    "Labels are aggregated at event-app granularity before app_context classification.",
                    "taxonomy/profile labels alone do not generate task-eligible context.",
                    "v3 strict cleaning downgrades broad content labels such as technology/information/science/weather/convenience services to context-only unless stronger scene evidence exists.",
                    "online shopping navigation is treated as shopping/lifestyle, not transport navigation.",
                    "Relatives 1 and church labels do not independently create communication/social context.",
                    "validation prior is marked uses_validation_data=true and must not be used at runtime.",
                    "task_opportunity_prior_by_context is a prototype bridge, not a TalkingData ground-truth label.",
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return {
        "reference_event_app_context_csv": reference_out,
        "validation_event_app_context_csv": validation_out,
        "reference_prior_json": reference_prior,
        "validation_prior_json": validation_prior,
        "task_opportunity_prior_json": task_opportunity_prior,
        "reference_summary_csv": reference_summary,
        "validation_summary_csv": validation_summary,
        "comparison_summary_csv": comparison_summary,
        "category_label_audit_csv": category_label_audit,
        "cleaning_manifest_json": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean TalkingData into event-app app_context artifacts."
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    outputs = clean_talkingdata_event_app_context(args.raw_dir, args.output_dir)
    for path in outputs.values():
        print(path)


if __name__ == "__main__":
    main()
