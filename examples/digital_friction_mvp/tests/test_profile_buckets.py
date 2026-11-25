from proto.profile_buckets import age_bucket, persona_bucket


def test_age_bucket_uses_shared_thresholds() -> None:
    assert age_bucket(None) == "unknown"
    assert age_bucket(62) == "lt65"
    assert age_bucket(70) == "65_74"
    assert age_bucket(81) == "75plus"


def test_persona_bucket_support_seeking_can_come_from_background() -> None:
    assert persona_bucket("", "遇到复杂步骤时总想找现场帮助") == "support_seeking"


def test_persona_bucket_keeps_existing_persona_labels() -> None:
    assert persona_bucket("风险回避者") == "cautious"
    assert persona_bucket("主动探索型") == "proactive"
    assert persona_bucket("普通退休用户") == "neutral"
