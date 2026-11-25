from proto.compat import apply_compatibility_updates


def test_negative_outcome_updates_legacy_fields() -> None:
    update = apply_compatibility_updates(
        trust_now=60,
        avoidance_now=30,
        outcome_type="failure_after_attempt",
        help_used=False,
    )
    assert update.trust_in_apps == 52
    assert update.avoidance_tendency == 35
    assert update.failure_increment == 1
    assert update.negative_event_increment == 1


def test_helped_success_updates_help_and_intercept() -> None:
    update = apply_compatibility_updates(
        trust_now=60,
        avoidance_now=30,
        outcome_type="success_with_help",
        help_used=True,
    )
    assert update.help_request_increment == 1
    assert update.intercept_increment == 1
    assert update.success_increment == 1


def test_avoid_reason_splits_compatibility_updates() -> None:
    helpless = apply_compatibility_updates(
        trust_now=60,
        avoidance_now=30,
        outcome_type="avoid_without_attempt",
        help_used=False,
        avoid_reason="helpless_avoid",
    )
    risk = apply_compatibility_updates(
        trust_now=60,
        avoidance_now=30,
        outcome_type="avoid_without_attempt",
        help_used=False,
        avoid_reason="risk_avoid",
    )
    low_value = apply_compatibility_updates(
        trust_now=60,
        avoidance_now=30,
        outcome_type="avoid_without_attempt",
        help_used=False,
        avoid_reason="low_value_avoid",
    )
    assert helpless.trust_delta < risk.trust_delta <= low_value.trust_delta
    assert helpless.avoidance_delta > risk.avoidance_delta > low_value.avoidance_delta
    assert helpless.trust_in_apps < risk.trust_in_apps <= low_value.trust_in_apps
    assert helpless.avoidance_tendency > risk.avoidance_tendency > low_value.avoidance_tendency
