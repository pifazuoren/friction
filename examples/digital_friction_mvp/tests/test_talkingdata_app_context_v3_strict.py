from __future__ import annotations

from clean_talkingdata_event_app_context import classify_categories


def test_relatives_only_is_taxonomy_profile_not_social() -> None:
    result = classify_categories(["Relatives 1"])

    assert result.app_context == "taxonomy_profile_only"
    assert result.task_eligible is False
    assert result.review_status == "taxonomy_profile_only"


def test_im_with_relatives_still_counts_as_social_context_only() -> None:
    result = classify_categories(["IM", "Relatives 1"])

    assert result.app_context == "communication_social_context"
    assert result.task_eligible is False


def test_weak_information_labels_do_not_become_education_work() -> None:
    for category in ["Technology Information", "Science and Technology 1", "Information"]:
        result = classify_categories([category])

        assert result.app_context == "unknown_or_unmapped"
        assert result.task_eligible is False
        assert result.review_status == "ambiguous_context_only"


def test_online_shopping_navigation_is_shopping_not_transport() -> None:
    result = classify_categories(["online shopping navigation"])

    assert result.app_context == "shopping_lifestyle_context"
    assert result.task_eligible is True


def test_weather_and_life_service_are_context_only_when_alone() -> None:
    for category in ["Weather", "convenience services", "life service"]:
        result = classify_categories([category])

        assert result.app_context == "unknown_or_unmapped"
        assert result.task_eligible is False
        assert result.review_status == "ambiguous_context_only"


def test_mixed_health_evidence_keeps_health_but_marks_mixed() -> None:
    result = classify_categories(["Medical", "health", "IM", "convenience services", "sports and gym"])

    assert result.app_context == "health_service_context"
    assert result.task_eligible is True
    assert result.review_status == "mixed_evidence_task_context"
