from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

from config_runtime import load_runtime_config
from proto.models import AttemptOutcome, AttemptStrategy, DigitalTask


def _install_agent_dependency_stubs() -> None:
    if "openai.types.chat" not in sys.modules:
        openai_module = types.ModuleType("openai")
        openai_types_module = types.ModuleType("openai.types")
        openai_chat_module = types.ModuleType("openai.types.chat")

        class _AsyncOpenAI:
            def __init__(self, *args, **kwargs):
                pass

        class _OpenAIError(Exception):
            pass

        class _APIConnectionError(_OpenAIError):
            pass

        class _NotGiven:
            pass

        class _CompletionParams:
            class ResponseFormat:
                pass

        openai_module.NOT_GIVEN = object()
        openai_module.APIConnectionError = _APIConnectionError
        openai_module.AsyncOpenAI = _AsyncOpenAI
        openai_module.NotGiven = _NotGiven
        openai_module.OpenAIError = _OpenAIError
        openai_chat_module.ChatCompletionMessageParam = dict
        openai_chat_module.ChatCompletionToolChoiceOptionParam = dict
        openai_chat_module.ChatCompletionToolParam = dict
        openai_chat_module.completion_create_params = _CompletionParams
        openai_types_module.chat = openai_chat_module
        openai_module.types = openai_types_module
        sys.modules["openai"] = openai_module
        sys.modules["openai.types"] = openai_types_module
        sys.modules["openai.types.chat"] = openai_chat_module

    if "ray" not in sys.modules:
        ray_module = types.ModuleType("ray")
        actor_module = types.ModuleType("ray.actor")
        actor_module.ActorHandle = object
        ray_module.actor = actor_module
        ray_module.ObjectRef = type("ObjectRef", (), {})
        ray_module.remote = lambda obj=None, **kwargs: obj if obj is not None else (
            lambda inner: inner
        )
        sys.modules["ray"] = ray_module
        sys.modules["ray.actor"] = actor_module

    if "qdrant_client.http.models" not in sys.modules:
        qdrant_client_module = types.ModuleType("qdrant_client")
        http_module = types.ModuleType("qdrant_client.http")
        models_module = types.ModuleType("qdrant_client.http.models")

        class _QdrantClient:
            def __init__(self, *args, **kwargs):
                pass

        class _Distance:
            COSINE = "cosine"

        class _Placeholder:
            def __init__(self, *args, **kwargs):
                pass

        models_module.Distance = _Distance
        for name in (
            "VectorParams",
            "SparseVectorParams",
            "SparseIndexParams",
            "PointStruct",
            "SparseVector",
            "PointIdsList",
            "NamedSparseVector",
            "FieldCondition",
            "Filter",
        ):
            setattr(models_module, name, _Placeholder)
        qdrant_client_module.QdrantClient = _QdrantClient
        qdrant_client_module.http = http_module
        http_module.models = models_module
        sys.modules["qdrant_client"] = qdrant_client_module
        sys.modules["qdrant_client.http"] = http_module
        sys.modules["qdrant_client.http.models"] = models_module

    if "fastembed" not in sys.modules:
        fastembed_module = types.ModuleType("fastembed")
        fastembed_module.SparseTextEmbedding = type("SparseTextEmbedding", (), {})
        sys.modules["fastembed"] = fastembed_module

    if "grpc.aio" not in sys.modules:
        grpc_module = sys.modules.get("grpc")
        if grpc_module is None:
            grpc_module = types.ModuleType("grpc")
            sys.modules["grpc"] = grpc_module
        aio_module = types.ModuleType("grpc.aio")
        aio_module.Channel = type("Channel", (), {})
        aio_module.Server = type("Server", (), {})
        aio_module.ServicerContext = type("ServicerContext", (), {})
        aio_module.secure_channel = lambda *args, **kwargs: aio_module.Channel()
        aio_module.insecure_channel = lambda *args, **kwargs: aio_module.Channel()
        grpc_module.aio = aio_module
        sys.modules["grpc.aio"] = aio_module

    if "boto3" not in sys.modules:
        boto3_module = types.ModuleType("boto3")
        boto3_module.client = lambda *args, **kwargs: object()
        sys.modules["boto3"] = boto3_module

    if "botocore.exceptions" not in sys.modules:
        botocore_module = types.ModuleType("botocore")
        exceptions_module = types.ModuleType("botocore.exceptions")

        class ClientError(Exception):
            pass

        exceptions_module.ClientError = ClientError
        botocore_module.exceptions = exceptions_module
        sys.modules["botocore"] = botocore_module
        sys.modules["botocore.exceptions"] = exceptions_module

    if "pyproj" not in sys.modules:
        pyproj_module = types.ModuleType("pyproj")

        class _Proj:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, *args, **kwargs):
                return 0.0, 0.0

        pyproj_module.Proj = _Proj
        sys.modules["pyproj"] = pyproj_module

    if "shapely" not in sys.modules:
        shapely_module = types.ModuleType("shapely")
        geometry_module = types.ModuleType("shapely.geometry")
        geometry_module.Point = type("Point", (), {})
        geometry_module.Polygon = type("Polygon", (), {})
        shapely_module.geometry = geometry_module
        sys.modules["shapely"] = shapely_module
        sys.modules["shapely.geometry"] = geometry_module


_install_agent_dependency_stubs()

for _module_name, _module in list(sys.modules.items()):
    if not _module_name.startswith("pycityproto"):
        continue
    module_file = getattr(_module, "__file__", None)
    if not isinstance(module_file, str):
        setattr(_module, "__file__", f"<stub:{_module_name}>")

from proto.agent import DigitalHelplessnessAgent


class _FakeStream:
    def __init__(self):
        self.records = []

    async def add(self, *, topic: str, description: str):
        memory_id = len(self.records)
        self.records.append(
            {
                "topic": topic,
                "description": description,
                "memory_id": memory_id,
            }
        )
        return memory_id


class _FakeMemory:
    def __init__(self):
        self.stream = _FakeStream()


class _FakeAgent:
    def __init__(self):
        self.memory = _FakeMemory()

    async def _record_task_episode_stream(self, **kwargs):
        return await DigitalHelplessnessAgent._record_task_episode_stream(
            self,
            **kwargs,
        )

    async def _record_help_episode_stream(self, **kwargs):
        return await DigitalHelplessnessAgent._record_help_episode_stream(
            self,
            **kwargs,
        )

    async def _record_recovery_episode_stream(self, **kwargs):
        return await DigitalHelplessnessAgent._record_recovery_episode_stream(
            self,
            **kwargs,
        )


def _make_task(task_family: str = "payment_risk_confirmation") -> DigitalTask:
    return DigitalTask(
        task_id=f"{task_family}-task",
        task_family=task_family,  # type: ignore[arg-type]
        friction_type="payment_risk_popup",
        difficulty=0.67,
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=1,
    )


def _make_strategy(strategy_type: str = "attempt_self") -> AttemptStrategy:
    return AttemptStrategy(
        strategy_type=strategy_type,  # type: ignore[arg-type]
        support_requested=strategy_type == "seek_help_then_attempt",
        rationale="test strategy",
        weights={
            "attempt_self": 0.7,
            "seek_help_then_attempt": 0.2,
            "avoid": 0.1,
        },
    )


def _make_outcome(
    outcome_type: str = "failure_after_attempt",
    *,
    help_used: bool = False,
    negative_feedback: bool = True,
    support_quality: int = 1,
    support_mode: str = "not_applicable",
) -> AttemptOutcome:
    return AttemptOutcome(
        outcome_type=outcome_type,  # type: ignore[arg-type]
        success=outcome_type in {"success_self", "success_with_help"},
        help_used=help_used,
        negative_feedback=negative_feedback,
        support_quality=support_quality,
        event_level_uncontrollability=1 if negative_feedback else 0,
        friction_tier=1,
        success_probability=0.5,
        abandon_probability=0.1,
        note="test outcome",
        rule_event_level_uncontrollability=1 if negative_feedback else 0,
        support_mode=support_mode,
    )


def _make_memory_features(recent_same_task_failure_count: int = 0):
    return SimpleNamespace(
        recent_same_task_failure_count=recent_same_task_failure_count,
    )


def test_stream_episode_recording_config_defaults_to_enabled(monkeypatch) -> None:
    monkeypatch.delenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", raising=False)

    config = load_runtime_config()

    assert config.proto_stream_episode_recording_enabled is True


def test_stream_episode_recording_config_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", "0")

    config = load_runtime_config()

    assert config.proto_stream_episode_recording_enabled is False


def test_phase0_recording_writes_task_episode_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", raising=False)
    agent = _FakeAgent()

    audit = asyncio.run(
        DigitalHelplessnessAgent._record_phase0_stream_episodes(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_outcome(),
            memory_features=_make_memory_features(),
        )
    )

    assert audit["enabled"] is True
    assert audit["condition"] == "stream-record-only"
    assert audit["records"] == [
        {"topic": "digital_task_episode", "memory_id": 0, "status": "ok"}
    ]
    assert agent.memory.stream.records[0]["topic"] == "digital_task_episode"
    description = agent.memory.stream.records[0]["description"]
    assert description.startswith("[digital_task_episode]")
    assert "[family=payment_risk_confirmation]" in description
    assert "[outcome=failure_after_attempt]" in description
    assert "I tried payment and risk confirmation" in description


def test_phase0_recording_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", "0")
    agent = _FakeAgent()

    audit = asyncio.run(
        DigitalHelplessnessAgent._record_phase0_stream_episodes(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_outcome(),
            memory_features=_make_memory_features(),
        )
    )

    assert audit == {
        "enabled": False,
        "condition": "structured-only",
        "records": [],
        "error_count": 0,
    }
    assert agent.memory.stream.records == []


def test_phase0_recording_writes_help_episode_for_help_strategy(monkeypatch) -> None:
    monkeypatch.delenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", raising=False)
    agent = _FakeAgent()

    audit = asyncio.run(
        DigitalHelplessnessAgent._record_phase0_stream_episodes(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
            strategy=_make_strategy("seek_help_then_attempt"),
            outcome=_make_outcome(
                "success_with_help",
                help_used=True,
                negative_feedback=False,
                support_quality=2,
                support_mode="enabling_support",
            ),
            memory_features=_make_memory_features(),
        )
    )

    topics = [record["topic"] for record in audit["records"]]
    assert topics == ["digital_task_episode", "digital_help_episode"]
    assert [record["topic"] for record in agent.memory.stream.records] == topics
    help_description = agent.memory.stream.records[1]["description"]
    assert help_description.startswith("[digital_help_episode]")
    assert "[support_mode=enabling_support]" in help_description
    assert "I sought help for payment and risk confirmation" in help_description


def test_phase0_recording_writes_recovery_after_repeated_failures(monkeypatch) -> None:
    monkeypatch.delenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", raising=False)
    agent = _FakeAgent()

    audit = asyncio.run(
        DigitalHelplessnessAgent._record_phase0_stream_episodes(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_outcome(
                "success_self",
                negative_feedback=False,
            ),
            memory_features=_make_memory_features(recent_same_task_failure_count=2),
        )
    )

    topics = [record["topic"] for record in audit["records"]]
    assert topics == ["digital_task_episode", "digital_recovery_episode"]
    recovery_description = agent.memory.stream.records[1]["description"]
    assert recovery_description.startswith("[digital_recovery_episode]")
    assert "[outcome=success_self]" in recovery_description
    assert "I recovered in payment and risk confirmation" in recovery_description


def test_phase0_recording_does_not_write_recovery_for_ordinary_success(monkeypatch) -> None:
    monkeypatch.delenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", raising=False)
    agent = _FakeAgent()

    audit = asyncio.run(
        DigitalHelplessnessAgent._record_phase0_stream_episodes(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
            strategy=_make_strategy(),
            outcome=_make_outcome(
                "success_self",
                negative_feedback=False,
            ),
            memory_features=_make_memory_features(recent_same_task_failure_count=0),
        )
    )

    assert audit["records"] == [
        {"topic": "digital_task_episode", "memory_id": 0, "status": "ok"}
    ]
    assert [record["topic"] for record in agent.memory.stream.records] == [
        "digital_task_episode"
    ]
