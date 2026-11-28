import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_social_memory_week as week
from config_runtime import load_runtime_config


@pytest.mark.parametrize(("days_option", "total_days", "arm"), [
    ([], 5, None), (["--days", "5"], 5, None), (["--days", "7"], 7, "standard"),
])
def test_week_launcher_replaces_stale_overrides_before_agent_configuration(tmp_path, monkeypatch, days_option,
                                                                           total_days, arm):
    # --check stops before credentials, experiment creation or model access.
    data = tmp_path / "data"
    data.mkdir()
    sim = data / "agentsociety-sim-oss"
    sim.touch(mode=0o700)
    for name in ("map.pb", "profiles.json", "prior.json"):
        (data / name).write_text("{}")
    monkeypatch.setattr(week, "DATA", data)
    monkeypatch.setitem(week.SETTINGS, "MAP_FILE_PATH", str(data / "map.pb"))
    monkeypatch.setitem(week.SETTINGS, "DIGITAL_FRICTION_PROFILES_PATH", str(data / "profiles.json"))
    monkeypatch.setitem(week.SETTINGS, "PROTO_TASK_OCCURRENCE_PRIOR_PATH", str(data / "prior.json"))
    monkeypatch.setenv("PROTO_HOURLY_INTENTION_MODE", "stale")
    monkeypatch.setenv("PROTO_LOGIN_DIFFICULTY_ARM", "elevated")
    monkeypatch.setattr(sys, "argv", ["week", "--scheduled-login", "--check", "--hourly-intention-mode",
                                      "opportunity_v1", "--max-defer-hours", "12", "--paired-environment-seed", "0",
                                      *days_option])
    captured = []
    monkeypatch.setattr(week, "checked_replay", lambda config: (captured.append(config), "test-device"))
    # The launcher intentionally mutates its process environment for children; isolate it in this test.
    monkeypatch.setattr(week.os, "environ", week.os.environ.copy())
    monkeypatch.setattr(week.os, "umask", lambda _: None)
    week.main()
    config, = captured
    assert config.proto_hourly_intention_mode == "opportunity_v1"
    assert config.proto_app_entry_plan_prompt_version == "app_entry_plan_v4"
    assert config.proto_app_entry_phone_use_needs_version == "digital_needs_phone_use_v5"
    assert config.proto_hourly_intention_max_defer_hours == 12
    assert config.proto_paired_environment_seed == 0
    assert config.proto_scheduled_login_hour == 9
    assert config.proto_login_difficulty_arm == arm
    assert int(week.os.environ["STAGE_DAYS"]) == total_days
    assert not (data / "runs").exists()


def test_opportunity_plan_default_and_explicit_older_version(monkeypatch):
    monkeypatch.setenv("STAGE_MODE", "single")
    monkeypatch.setenv("STAGE_DAYS", "7")
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "app_context_replay_then_llm_rollout")
    monkeypatch.setenv("PROTO_HOURLY_INTENTION_MODE", "opportunity_v1")
    monkeypatch.delenv("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION", raising=False)
    assert load_runtime_config().proto_app_entry_plan_prompt_version == "app_entry_plan_v4"
    monkeypatch.setenv("PROTO_APP_ENTRY_PLAN_PROMPT_VERSION", "app_entry_plan_v3")
    assert load_runtime_config().proto_app_entry_plan_prompt_version == "app_entry_plan_v3"


def test_free_hour_version_is_independent_of_task_hour_prompt(monkeypatch):
    monkeypatch.setenv("PROTO_APP_ENTRY_NEEDS_PROMPT_VERSION", "digital_needs_compact_v2")
    for version in ("digital_needs_phone_use_v3", "digital_needs_phone_use_v4", "digital_needs_phone_use_v5"):
        monkeypatch.setenv("PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION", version)
        config = load_runtime_config()
        assert config.proto_app_entry_phone_use_needs_version == version
        assert config.proto_app_entry_needs_prompt_version == "digital_needs_compact_v2"
    monkeypatch.setenv("PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION", "unknown")
    with pytest.raises(ValueError, match="PROTO_APP_ENTRY_PHONE_USE_NEEDS_VERSION"):
        load_runtime_config()


def test_preflight_rejects_a_missing_hour_on_the_tenth_device(tmp_path, replay_files):
    rows = Path(replay_files["bundle_path"]).read_text().splitlines()
    incomplete = tmp_path / "incomplete.csv"
    missing = next(row for row in rows if row.startswith("synthetic-10,3,23,"))
    rows.remove(missing)
    incomplete.write_text("\n".join(rows) + "\n")
    config = SimpleNamespace(proto_app_entry_replay_bundle_path=str(incomplete),
                             proto_app_entry_replay_device_path=replay_files["device_mapping_path"],
                             proto_app_entry_replay_days=(1, 2, 3))
    with pytest.raises(ValueError, match="replay bundle missing hourly rows: synthetic-10"):
        week.checked_replay(config)


def test_new_mode_rejects_incompatible_entry_and_nonpositive_interval(monkeypatch):
    monkeypatch.setenv("PROTO_HOURLY_INTENTION_MODE", "opportunity_v1")
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "fixed_assignment")
    with pytest.raises(ValueError, match="requires app_context"):
        load_runtime_config()
    monkeypatch.setenv("PROTO_TASK_ENTRY_MODE", "app_context_replay_then_llm_rollout")
    monkeypatch.setenv("PROTO_HOURLY_INTENTION_MAX_DEFER_HOURS", "0")
    with pytest.raises(ValueError, match="MAX_DEFER_HOURS"):
        load_runtime_config()


def test_ten_resident_inputs_match_engine_ids_and_survive_archiving(tmp_path, replay_files):
    replay = week.get_replay_source(**replay_files, replay_days=(1, 2, 3))
    profiles = tmp_path / "residents.json"
    profiles.write_text(json.dumps([{"id": i} for i in range(10, 0, -1)]))
    settings = {
        "DIGITAL_FRICTION_PROFILES_PATH": str(profiles),
        "PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH": replay_files["bundle_path"],
        "PROTO_APP_ENTRY_REPLAY_DEVICE_PATH": replay_files["device_mapping_path"],
    }
    before = week.matched_cohort(replay, settings["DIGITAL_FRICTION_PROFILES_PATH"], 10)
    assert len({p["device_id"] for p in before}) == len({p["profile_id"] for p in before}) == 10
    assert [p["selected_rank"] for p in before] == list(range(1, 11))
    week.freeze_cohort_inputs(tmp_path, settings)
    archived = week.get_replay_source(
        bundle_path=settings["PROTO_APP_ENTRY_REPLAY_BUNDLE_PATH"],
        device_mapping_path=settings["PROTO_APP_ENTRY_REPLAY_DEVICE_PATH"],
        replay_days=(1, 2, 3),
    )
    path = tmp_path / "inputs" / "profiles.json"
    assert before == week.matched_cohort(archived, path, 10)
    assert [p["profile_id"] for p in before] == list(range(1, 11))
    assert archived.bundle_hash == replay.bundle_hash
    assert archived.device_mapping_hash == replay.device_mapping_hash
    original = json.loads(path.read_text())
    original[1]["id"] = original[0]["id"]
    path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="Duplicate"):
        week.matched_cohort(archived, path, 10)
