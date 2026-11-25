from __future__ import annotations

import pytest

from proto.app_entry.bundle_loader import get_replay_source


def test_replay_loader_validates_complete_reference_bundle(replay_files) -> None:
    source = get_replay_source(
        **replay_files,
        replay_days=(1, 2, 3),
    )

    assert len(source.selected_devices) == 10
    assert len(source._bundle_index) == 720
    rank, device_id = source.selected_devices[0]
    assert rank == 1
    first_bundle = source.bundle_for_device(
        device_id=device_id,
        talkingdata_day=1,
        hour=0,
    )
    assert first_bundle.device_id == device_id
    assert first_bundle.hour == 0


def test_replay_loader_maps_agent_ids_by_selected_rank_order(replay_files) -> None:
    source = get_replay_source(
        **replay_files,
        replay_days="1,2,3",
    )

    assignments = source.assignments_for_agent_ids([42, 7, 13])

    assert list(sorted(assignments)) == [7, 13, 42]
    assert assignments[7].selected_rank == 1
    assert assignments[13].selected_rank == 2
    assert assignments[42].selected_rank == 3
    assert assignments[7].to_dict()["device_mapping_allowed_columns"] == [
        "selected_rank",
        "device_id",
    ]


def test_replay_loader_rejects_agent_count_over_selected_devices(replay_files) -> None:
    source = get_replay_source(
        **replay_files,
        replay_days=(1, 2, 3),
    )

    with pytest.raises(ValueError, match="AGENT_COUNT exceeds selected devices"):
        source.assignments_for_agent_ids(list(range(11)))


def test_replay_loader_rejects_validation_paths() -> None:
    with pytest.raises(ValueError, match="validation"):
        get_replay_source(
            bundle_path="validation_bundle.csv",
            device_mapping_path="unused_mapping.csv",
            replay_days=(1, 2, 3),
        )


def test_replay_loader_cache_uses_hash_key(replay_files) -> None:
    first = get_replay_source(
        **replay_files,
        replay_days=(1, 2, 3),
    )
    second = get_replay_source(
        **replay_files,
        replay_days=(1, 2, 3),
    )

    assert second is first
    assert first.bundle_hash
    assert first.device_mapping_hash
