from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle import HourlyAppEntryBundle


@dataclass(frozen=True, slots=True)
class ReplayDeviceAssignment:
    agent_id: int
    selected_rank: int
    device_id: str
    mapping_source: str
    bundle_hash: str
    device_mapping_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": int(self.agent_id),
            "selected_rank": int(self.selected_rank),
            "device_id": self.device_id,
            "mapping_source": self.mapping_source,
            "bundle_hash": self.bundle_hash,
            "device_mapping_hash": self.device_mapping_hash,
            "device_mapping_allowed_columns": ["selected_rank", "device_id"],
            "ignored_validation_columns": True,
        }


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _normalize_path(path: str) -> Path:
    normalized = str(path or "").strip()
    if not normalized:
        raise ValueError("replay path is required")
    if "validation" in normalized.lower():
        raise ValueError("replay runtime path must not point to validation data")
    resolved = Path(normalized).expanduser()
    return resolved


def _parse_replay_days(value: str | tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if isinstance(value, (list, tuple)):
        days = tuple(int(day) for day in value)
    else:
        days = tuple(
            int(token.strip())
            for token in str(value or "").split(",")
            if token.strip()
        )
    if not days:
        raise ValueError("PROTO_APP_ENTRY_REPLAY_DAYS must not be empty")
    for day in days:
        if day < 1 or day > 7:
            raise ValueError("replay days must be in TalkingData day range 1..7")
    return days


class HourlyBundleReplaySource:
    def __init__(
        self,
        *,
        bundle_path: str,
        device_mapping_path: str,
        replay_days: str | tuple[int, ...] | list[int],
    ) -> None:
        self.bundle_path = _normalize_path(bundle_path)
        self.device_mapping_path = _normalize_path(device_mapping_path)
        self.replay_days = _parse_replay_days(replay_days)
        if not self.bundle_path.exists():
            raise FileNotFoundError(f"replay bundle not found: {self.bundle_path}")
        if not self.device_mapping_path.exists():
            raise FileNotFoundError(
                f"replay device mapping not found: {self.device_mapping_path}"
            )
        self.bundle_hash = _file_hash(self.bundle_path)
        self.device_mapping_hash = _file_hash(self.device_mapping_path)
        self.selected_devices = self._load_selected_devices()
        self._bundle_index = self._load_bundles()
        self._validate_completeness()

    def _load_selected_devices(self) -> list[tuple[int, str]]:
        with self.device_mapping_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        devices: list[tuple[int, str]] = []
        seen_ranks: set[int] = set()
        seen_devices: set[str] = set()
        for row in rows:
            rank = int(float(row.get("selected_rank", "")))
            device_id = str(row.get("device_id", "")).strip()
            if not device_id:
                raise ValueError("selected_devices row missing device_id")
            if rank in seen_ranks:
                raise ValueError(f"duplicate selected_rank in device mapping: {rank}")
            if device_id in seen_devices:
                raise ValueError(f"duplicate device_id in device mapping: {device_id}")
            seen_ranks.add(rank)
            seen_devices.add(device_id)
            devices.append((rank, device_id))
        devices.sort(key=lambda item: item[0])
        if not devices:
            raise ValueError("selected_devices mapping is empty")
        return devices

    def _load_bundles(self) -> dict[tuple[str, int, int], HourlyAppEntryBundle]:
        index: dict[tuple[str, int, int], HourlyAppEntryBundle] = {}
        with self.bundle_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                bundle = HourlyAppEntryBundle.from_row(row)
                if int(bundle.day) not in self.replay_days:
                    continue
                key = (bundle.device_id, int(bundle.day), int(bundle.hour))
                if key in index:
                    raise ValueError(f"duplicate replay bundle row: {key}")
                index[key] = bundle
        if not index:
            raise ValueError("replay bundle contains no rows for replay days")
        return index

    def _validate_completeness(self) -> None:
        missing: list[str] = []
        for _, device_id in self.selected_devices:
            for day in self.replay_days:
                for hour in range(24):
                    if (device_id, int(day), int(hour)) not in self._bundle_index:
                        missing.append(f"{device_id}:day{day}:hour{hour}")
        if missing:
            preview = ", ".join(missing[:10])
            raise ValueError(f"replay bundle missing hourly rows: {preview}")

    def assignments_for_agent_ids(
        self,
        agent_ids: list[int] | tuple[int, ...],
    ) -> dict[int, ReplayDeviceAssignment]:
        ordered_agent_ids = sorted(int(agent_id) for agent_id in agent_ids)
        if len(ordered_agent_ids) > len(self.selected_devices):
            raise ValueError(
                "AGENT_COUNT exceeds selected devices in replay mapping: "
                f"{len(ordered_agent_ids)} > {len(self.selected_devices)}"
            )
        assignments: dict[int, ReplayDeviceAssignment] = {}
        for agent_id, (selected_rank, device_id) in zip(
            ordered_agent_ids,
            self.selected_devices,
        ):
            assignments[int(agent_id)] = ReplayDeviceAssignment(
                agent_id=int(agent_id),
                selected_rank=int(selected_rank),
                device_id=device_id,
                mapping_source="selected_rank_order",
                bundle_hash=self.bundle_hash,
                device_mapping_hash=self.device_mapping_hash,
            )
        return assignments

    def bundle_for_device(
        self,
        *,
        device_id: str,
        talkingdata_day: int,
        hour: int,
    ) -> HourlyAppEntryBundle:
        key = (str(device_id), int(talkingdata_day), int(hour))
        try:
            return self._bundle_index[key]
        except KeyError as exc:
            raise KeyError(f"replay bundle not found for {key}") from exc


_REPLAY_SOURCE_CACHE: dict[
    tuple[str, str, tuple[int, ...]],
    tuple[str, str, HourlyBundleReplaySource],
] = {}


def get_replay_source(
    *,
    bundle_path: str,
    device_mapping_path: str,
    replay_days: str | tuple[int, ...] | list[int],
) -> HourlyBundleReplaySource:
    normalized_bundle = str(_normalize_path(bundle_path))
    normalized_device = str(_normalize_path(device_mapping_path))
    days = _parse_replay_days(replay_days)
    bundle_hash = _file_hash(Path(normalized_bundle))
    device_hash = _file_hash(Path(normalized_device))
    key = (normalized_bundle, normalized_device, days)
    cached = _REPLAY_SOURCE_CACHE.get(key)
    if cached is not None and cached[0] == bundle_hash and cached[1] == device_hash:
        return cached[2]
    source = HourlyBundleReplaySource(
        bundle_path=normalized_bundle,
        device_mapping_path=normalized_device,
        replay_days=days,
    )
    _REPLAY_SOURCE_CACHE[key] = (bundle_hash, device_hash, source)
    return source


def simulation_day_to_talkingdata_day(simulation_day: int) -> int:
    return int(simulation_day) + 1


def talkingdata_day_to_simulation_day(talkingdata_day: int) -> int:
    return int(talkingdata_day) - 1
