from __future__ import annotations

import csv
import sys
import types
from pathlib import Path

import pytest


EXAMPLE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXAMPLE_DIR.parents[1]
AGENTSOCIETY_PACKAGE_DIR = REPO_ROOT / "packages" / "agentsociety"
if str(EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(AGENTSOCIETY_PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTSOCIETY_PACKAGE_DIR))


def _install_pycityproto_stub() -> None:
    if "pycityproto" in sys.modules:
        return

    class _ProtoMessage:
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _PersonType:
        PERSON_TYPE_NORMAL = 0

    class _VehicleEngineType:
        VEHICLE_ENGINE_TYPE_FUEL = 0

    class _TripMode:
        TRIP_MODE_DRIVE_ONLY = 0

    class _Status:
        STATUS_UNSPECIFIED = 0

    def _make_module(name: str, attrs: dict[str, object] | None = None) -> types.ModuleType:
        module = types.ModuleType(name)
        attrs = attrs or {}
        for key, value in attrs.items():
            setattr(module, key, value)

        def __getattr__(attr_name: str):
            placeholder = type(attr_name, (_ProtoMessage,), {})
            setattr(module, attr_name, placeholder)
            return placeholder

        module.__getattr__ = __getattr__  # type: ignore[attr-defined]
        return module

    sys.modules["pycityproto"] = _make_module("pycityproto")
    sys.modules["pycityproto.city"] = _make_module("pycityproto.city")
    sys.modules["pycityproto.city.person"] = _make_module("pycityproto.city.person")
    sys.modules["pycityproto.city.person.v2"] = _make_module("pycityproto.city.person.v2")
    person_pb2_module = _make_module(
        "pycityproto.city.person.v2.person_pb2",
        {
            "BikeAttribute": type("BikeAttribute", (_ProtoMessage,), {}),
            "EmissionAttribute": type("EmissionAttribute", (_ProtoMessage,), {}),
            "PedestrianAttribute": type("PedestrianAttribute", (_ProtoMessage,), {}),
            "Person": type("Person", (_ProtoMessage,), {}),
            "PersonAttribute": type("PersonAttribute", (_ProtoMessage,), {}),
            "PersonType": _PersonType,
            "VehicleAttribute": type("VehicleAttribute", (_ProtoMessage,), {}),
            "VehicleEngineEfficiency": type(
                "VehicleEngineEfficiency", (_ProtoMessage,), {}
            ),
            "VehicleEngineType": _VehicleEngineType,
        },
    )
    sys.modules["pycityproto.city.person.v2.person_pb2"] = person_pb2_module
    person_service_pb2_module = _make_module(
        "pycityproto.city.person.v2.person_service_pb2"
    )
    sys.modules["pycityproto.city.person.v2.person_service_pb2"] = person_service_pb2_module
    person_service_grpc_module = _make_module(
        "pycityproto.city.person.v2.person_service_pb2_grpc",
        {"PersonServiceStub": type("PersonServiceStub", (), {})},
    )
    sys.modules["pycityproto.city.person.v2.person_service_pb2_grpc"] = person_service_grpc_module
    sys.modules["pycityproto.city.map"] = _make_module("pycityproto.city.map")
    sys.modules["pycityproto.city.map.v2"] = _make_module("pycityproto.city.map.v2")
    map_pb2_module = _make_module(
        "pycityproto.city.map.v2.map_pb2"
    )
    sys.modules["pycityproto.city.map.v2.map_pb2"] = map_pb2_module
    sys.modules["pycityproto.city.sync"] = _make_module("pycityproto.city.sync")
    sys.modules["pycityproto.city.sync.v2"] = _make_module("pycityproto.city.sync.v2")
    sync_pb2_module = _make_module(
        "pycityproto.city.sync.v2.sync_service_pb2"
    )
    sys.modules["pycityproto.city.sync.v2.sync_service_pb2"] = sync_pb2_module
    sync_grpc_module = _make_module(
        "pycityproto.city.sync.v2.sync_service_pb2_grpc"
    )
    sys.modules["pycityproto.city.sync.v2.sync_service_pb2_grpc"] = sync_grpc_module
    sys.modules["pycityproto.city.economy"] = _make_module("pycityproto.city.economy")
    sys.modules["pycityproto.city.economy.v2"] = _make_module(
        "pycityproto.city.economy.v2"
    )
    economy_pb2_module = _make_module(
        "pycityproto.city.economy.v2.economy_pb2"
    )
    sys.modules["pycityproto.city.economy.v2.economy_pb2"] = economy_pb2_module
    org_service_pb2_module = _make_module(
        "pycityproto.city.economy.v2.org_service_pb2"
    )
    sys.modules["pycityproto.city.economy.v2.org_service_pb2"] = org_service_pb2_module
    org_service_grpc_module = _make_module(
        "pycityproto.city.economy.v2.org_service_pb2_grpc"
    )
    sys.modules["pycityproto.city.economy.v2.org_service_pb2_grpc"] = org_service_grpc_module
    sys.modules["pycityproto.city.trip"] = _make_module("pycityproto.city.trip")
    sys.modules["pycityproto.city.trip.v2"] = _make_module("pycityproto.city.trip.v2")
    trip_pb2_module = _make_module(
        "pycityproto.city.trip.v2.trip_pb2",
        {"TripMode": _TripMode},
    )
    sys.modules["pycityproto.city.trip.v2.trip_pb2"] = trip_pb2_module
    motion_pb2_module = _make_module(
        "pycityproto.city.person.v2.motion_pb2",
        {"Status": _Status},
    )
    sys.modules["pycityproto.city.person.v2.motion_pb2"] = motion_pb2_module

    sys.modules["pycityproto"].city = sys.modules["pycityproto.city"]
    sys.modules["pycityproto.city"].person = sys.modules["pycityproto.city.person"]
    sys.modules["pycityproto.city"].map = sys.modules["pycityproto.city.map"]
    sys.modules["pycityproto.city"].sync = sys.modules["pycityproto.city.sync"]
    sys.modules["pycityproto.city"].economy = sys.modules["pycityproto.city.economy"]
    sys.modules["pycityproto.city"].trip = sys.modules["pycityproto.city.trip"]
    sys.modules["pycityproto.city.person"].v2 = sys.modules["pycityproto.city.person.v2"]
    sys.modules["pycityproto.city.person.v2"].person_pb2 = person_pb2_module
    sys.modules["pycityproto.city.person.v2"].person_service_pb2 = person_service_pb2_module
    sys.modules["pycityproto.city.person.v2"].person_service_pb2_grpc = person_service_grpc_module
    sys.modules["pycityproto.city.person.v2"].motion_pb2 = motion_pb2_module
    sys.modules["pycityproto.city.map"].v2 = sys.modules["pycityproto.city.map.v2"]
    sys.modules["pycityproto.city.map.v2"].map_pb2 = map_pb2_module
    sys.modules["pycityproto.city.sync"].v2 = sys.modules["pycityproto.city.sync.v2"]
    sys.modules["pycityproto.city.sync.v2"].sync_service_pb2 = sync_pb2_module
    sys.modules["pycityproto.city.sync.v2"].sync_service_pb2_grpc = sync_grpc_module
    sys.modules["pycityproto.city.economy"].v2 = sys.modules["pycityproto.city.economy.v2"]
    sys.modules["pycityproto.city.economy.v2"].economy_pb2 = economy_pb2_module
    sys.modules["pycityproto.city.economy.v2"].org_service_pb2 = org_service_pb2_module
    sys.modules["pycityproto.city.economy.v2"].org_service_pb2_grpc = org_service_grpc_module
    sys.modules["pycityproto.city.trip"].v2 = sys.modules["pycityproto.city.trip.v2"]
    sys.modules["pycityproto.city.trip.v2"].trip_pb2 = trip_pb2_module


_install_pycityproto_stub()


def _install_grpc_stub() -> None:
    if "grpc" in sys.modules:
        return

    class _Channel:
        pass

    class _AioModule:
        Channel = _Channel

        @staticmethod
        def secure_channel(*args, **kwargs):
            return _Channel()

        @staticmethod
        def insecure_channel(*args, **kwargs):
            return _Channel()

    grpc_module = types.ModuleType("grpc")
    grpc_module.Channel = _Channel
    grpc_module.aio = _AioModule()
    grpc_module.secure_channel = lambda *args, **kwargs: _Channel()
    grpc_module.insecure_channel = lambda *args, **kwargs: _Channel()
    grpc_module.ssl_channel_credentials = lambda *args, **kwargs: object()
    sys.modules["grpc"] = grpc_module


_install_grpc_stub()


def _install_json_repair_stub() -> None:
    if "json_repair" in sys.modules:
        return

    import json

    module = types.ModuleType("json_repair")

    def loads(payload):
        text = str(payload or "").strip()
        if not text:
            raise json.JSONDecodeError("empty payload", text, 0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            while start >= 0:
                depth = 0
                in_string = False
                escaped = False
                for index in range(start, len(text)):
                    char = text[index]
                    if in_string:
                        if escaped:
                            escaped = False
                        elif char == "\\":
                            escaped = True
                        elif char == '"':
                            in_string = False
                        continue
                    if char == '"':
                        in_string = True
                    elif char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = text[start : index + 1]
                            return json.loads(candidate)
                start = text.find("{", start + 1)
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    module.loads = loads  # type: ignore[attr-defined]
    sys.modules["json_repair"] = module


_install_json_repair_stub()


@pytest.fixture(scope="session")
def synthetic_replay_root(tmp_path_factory):
    from config_runtime import DEFAULT_APP_ENTRY_REPLAY_BUNDLE_PATH, DEFAULT_APP_ENTRY_REPLAY_DEVICE_PATH

    root = tmp_path_factory.mktemp("synthetic-replay")
    bundle = root / DEFAULT_APP_ENTRY_REPLAY_BUNDLE_PATH
    mapping = root / DEFAULT_APP_ENTRY_REPLAY_DEVICE_PATH
    bundle.parent.mkdir(parents=True)
    with mapping.open("w", newline="") as dm, bundle.open("w", newline="") as ref:
        devices = csv.writer(dm)
        devices.writerow(("selected_rank", "device_id"))
        records = csv.writer(ref)
        records.writerow(("device_id", "day_index", "hour", "active", "active_event_app_exposures",
                          "app_context_counts_json", "primary_context", "source"))
        for rank in range(10, 0, -1):
            device = f"synthetic-{rank}"
            devices.writerow((rank, device))
            for day in (1, 2, 3):
                for hour in range(24):
                    records.writerow((device, day, hour, False, 0, "{}", "no_app_context", "synthetic"))
    return root


@pytest.fixture
def replay_files(synthetic_replay_root):
    from config_runtime import DEFAULT_APP_ENTRY_REPLAY_BUNDLE_PATH, DEFAULT_APP_ENTRY_REPLAY_DEVICE_PATH

    return {
        "bundle_path": str(synthetic_replay_root / DEFAULT_APP_ENTRY_REPLAY_BUNDLE_PATH),
        "device_mapping_path": str(synthetic_replay_root / DEFAULT_APP_ENTRY_REPLAY_DEVICE_PATH),
    }
