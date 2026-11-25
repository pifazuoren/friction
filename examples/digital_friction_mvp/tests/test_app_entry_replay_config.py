from __future__ import annotations

from pathlib import Path

import pytest

from config_runtime import (
    DEFAULT_APP_ENTRY_REPLAY_BUNDLE_PATH,
    DEFAULT_APP_ENTRY_REPLAY_DEVICE_PATH,
    load_runtime_config,
)
from proto.app_entry.bundle_loader import get_replay_source


def test_runtime_config_defaults_to_replay_bundle(monkeypatch, synthetic_replay_root) -> None:
    monkeypatch.chdir(synthetic_replay_root)
    for key in (
        "PROTO_TASK_ENTRY_MODE",
        "PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH",
        "PROTO_APP_ENTRY_REPLAY_DEVICE_PATH",
        "PROTO_APP_ENTRY_REPLAY_DAYS",
        "PROTO_APP_ENTRY_NEEDS_PROMPT_VERSION",
        "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION",
        "PROTO_APP_ENTRY_ROLLOUT_JSON_ATTEMPTS",
        "PROTO_APP_ENTRY_ROLLOUT_MIN_CONFIDENCE",
        "PROTO_APP_ENTRY_ROLLOUT_TOP_K",
        "PROTO_APP_ENTRY_ROLLOUT_MAX_EXPOSURES",
    ):
        monkeypatch.delenv(key, raising=False)

    config = load_runtime_config()

    assert config.proto_task_entry_mode == "app_context_replay_bundle"
    assert config.proto_app_entry_replay_bundle_path == DEFAULT_APP_ENTRY_REPLAY_BUNDLE_PATH
    assert config.proto_app_entry_replay_device_path == DEFAULT_APP_ENTRY_REPLAY_DEVICE_PATH
    assert config.proto_app_entry_replay_days == (1, 2, 3)
    assert config.proto_app_entry_needs_prompt_version == "digital_needs_v1"
    assert config.proto_app_entry_plan_prompt_version == "app_entry_plan_v3"
    assert config.proto_app_entry_rollout_json_attempts == 5
    assert config.proto_app_entry_rollout_min_confidence == pytest.approx(0.50)
    assert config.proto_app_entry_rollout_top_k == 5
    assert config.proto_app_entry_rollout_max_exposures == 12
    assert Path(config.proto_app_entry_replay_bundle_path).exists()
    assert Path(config.proto_app_entry_replay_device_path).exists()


def test_runtime_config_default_replay_paths_are_loader_compatible(monkeypatch, synthetic_replay_root) -> None:
    monkeypatch.chdir(synthetic_replay_root)
    for key in ("PROTO_TASK_ENTRY_MODE", "PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH", "PROTO_APP_ENTRY_REPLAY_DEVICE_PATH", "PROTO_APP_ENTRY_REPLAY_DAYS"):
        monkeypatch.delenv(key, raising=False)
    config = load_runtime_config()

    source = get_replay_source(
        bundle_path=config.proto_app_entry_replay_bundle_path,
        device_mapping_path=config.proto_app_entry_replay_device_path,
        replay_days=config.proto_app_entry_replay_days,
    )

    assert len(source.selected_devices) == 10


def test_runtime_config_old_modes_remain_explicitly_available(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "fixed_assignment")
    config = load_runtime_config()
    assert config.proto_task_entry_mode == "fixed_assignment"

    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "app_context_rule")
    config = load_runtime_config()
    assert config.proto_task_entry_mode == "app_context_rule"


def test_runtime_config_rejects_replay_validation_path(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "app_context_replay_bundle")
    monkeypatch.setenv("PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH", "/tmp/validation.csv")

    with pytest.raises(ValueError, match="validation"):
        load_runtime_config()


def test_runtime_config_bounds_rollout_json_attempts(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_APP_ENTRY_ROLLOUT_JSON_ATTEMPTS", "99")
    monkeypatch.setenv("PROTO_APP_ENTRY_ROLLOUT_MIN_CONFIDENCE", "0.75")

    config = load_runtime_config()

    assert config.proto_app_entry_rollout_json_attempts == 5
    assert config.proto_app_entry_rollout_min_confidence == pytest.approx(0.75)


def test_runtime_config_accepts_combined_mode_with_required_boundaries(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PROTO_TASK_ENTRY_MODE",
        "app_context_replay_then_llm_rollout",
    )
    monkeypatch.setenv("STAGE_MODE", "single")
    monkeypatch.setenv("PROTO_APP_ENTRY_REPLAY_DAYS", "1,2,3")

    config = load_runtime_config()

    assert config.proto_task_entry_mode == "app_context_replay_then_llm_rollout"
    assert config.proto_app_entry_replay_days == (1, 2, 3)


def test_runtime_config_rejects_combined_mode_with_full_stage(monkeypatch) -> None:
    monkeypatch.setenv(
        "PROTO_TASK_ENTRY_MODE",
        "app_context_replay_then_llm_rollout",
    )
    monkeypatch.setenv("STAGE_MODE", "full")

    with pytest.raises(ValueError, match="requires STAGE_MODE=single"):
        load_runtime_config()


def test_runtime_config_rejects_combined_mode_with_wrong_replay_days(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PROTO_TASK_ENTRY_MODE",
        "app_context_replay_then_llm_rollout",
    )
    monkeypatch.setenv("STAGE_MODE", "single")
    monkeypatch.setenv("PROTO_APP_ENTRY_REPLAY_DAYS", "1,2")

    with pytest.raises(ValueError, match="REPLAY_DAYS=1,2,3"):
        load_runtime_config()


@pytest.mark.parametrize(
    "name",
    [
        "PROTO_APP_ENTRY_NEEDS_PROMPT_VERSION",
        "PROTO_APP_ENTRY_PLAN_PROMPT_VERSION",
    ],
)
def test_runtime_config_rejects_empty_app_entry_prompt_versions(monkeypatch, name) -> None:
    monkeypatch.setenv(name, " ")

    with pytest.raises(ValueError, match="must not be empty"):
        load_runtime_config()
