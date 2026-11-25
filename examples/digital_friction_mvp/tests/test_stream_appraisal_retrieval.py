from __future__ import annotations

import asyncio
import sys
import types

from config_runtime import load_runtime_config
from proto.llm_psychology import (
    _build_task_appraisal_cache_key,
    _build_task_appraisal_user_payload,
    normalize_digital_emotion_state,
)
from proto.models import DigitalTask


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
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    async def search(self, *, query: str, topic: str, top_k: int):
        self.calls.append({"query": query, "topic": topic, "top_k": top_k})
        response = self.responses.get(topic, "Nothing")
        if isinstance(response, Exception):
            raise response
        return response


class _FakeMemory:
    def __init__(self, stream: _FakeStream):
        self.stream = stream


class _FakeAgent:
    def __init__(self, stream: _FakeStream):
        self.memory = _FakeMemory(stream)


def _make_task() -> DigitalTask:
    return DigitalTask(
        task_id="payment-task",
        task_family="payment_risk_confirmation",
        friction_type="payment_risk_popup",
        difficulty=0.67,
        need_type="daily_task",
        support_sensitivity=0.7,
        assigned_tick=1,
    )


def test_stream_task_appraisal_retrieval_config_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", raising=False)

    config = load_runtime_config()

    assert config.proto_stream_task_appraisal_retrieval_enabled is True


def test_stream_task_appraisal_retrieval_config_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", "0")

    config = load_runtime_config()

    assert config.proto_stream_task_appraisal_retrieval_enabled is False


def test_retrieval_disabled_reports_stream_record_only(monkeypatch):
    monkeypatch.setenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", "1")
    monkeypatch.setenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", "0")
    stream = _FakeStream()
    agent = _FakeAgent(stream)

    packet = asyncio.run(
        DigitalHelplessnessAgent._retrieve_task_episodic_memory(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
        )
    )

    assert packet["condition"] == "stream-record-only"
    assert packet["status"] == "disabled"
    assert packet["count"] == 0
    assert stream.calls == []


def test_retrieval_disabled_reports_structured_only(monkeypatch):
    monkeypatch.setenv("PROTO_STREAM_EPISODE_RECORDING_ENABLED", "0")
    monkeypatch.setenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", "0")
    stream = _FakeStream()
    agent = _FakeAgent(stream)

    packet = asyncio.run(
        DigitalHelplessnessAgent._retrieve_task_episodic_memory(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
        )
    )

    assert packet["condition"] == "structured-only"
    assert packet["status"] == "disabled"
    assert stream.calls == []


def test_retrieval_enabled_searches_only_raw_episode_topics(monkeypatch):
    monkeypatch.setenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", "1")
    stream = _FakeStream(
        {
            "digital_task_episode": "- [digital_task_episode]: payment failed",
            "digital_help_episode": "- [digital_help_episode]: help worked",
            "digital_recovery_episode": "Nothing",
        }
    )
    agent = _FakeAgent(stream)

    packet = asyncio.run(
        DigitalHelplessnessAgent._retrieve_task_episodic_memory(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
        )
    )

    assert packet["condition"] == "stream-appraisal"
    assert packet["status"] == "ok"
    assert packet["count"] == 2
    assert packet["ids"] == []
    assert packet["topics"] == [
        "digital_task_episode",
        "digital_help_episode",
        "digital_recovery_episode",
    ]
    assert [call["topic"] for call in stream.calls] == packet["topics"]
    assert [call["top_k"] for call in stream.calls] == [3, 1, 1]
    assert "digital_daily_reflection" not in [call["topic"] for call in stream.calls]
    assert "digital_friction_stage_summary" not in [
        call["topic"] for call in stream.calls
    ]


def test_retrieval_enabled_empty_result(monkeypatch):
    monkeypatch.setenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", "1")
    stream = _FakeStream()
    agent = _FakeAgent(stream)

    packet = asyncio.run(
        DigitalHelplessnessAgent._retrieve_task_episodic_memory(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
        )
    )

    assert packet["status"] == "empty"
    assert packet["text"] == "Nothing"
    assert packet["count"] == 0


def test_retrieval_enabled_search_error_returns_error_packet(monkeypatch):
    monkeypatch.setenv("PROTO_STREAM_TASK_APPRAISAL_RETRIEVAL_ENABLED", "1")
    stream = _FakeStream({"digital_task_episode": RuntimeError("search boom")})
    agent = _FakeAgent(stream)

    packet = asyncio.run(
        DigitalHelplessnessAgent._retrieve_task_episodic_memory(
            agent,
            runtime_config=load_runtime_config(),
            task=_make_task(),
        )
    )

    assert packet["status"] == "error"
    assert packet["text"] == "Nothing"
    assert packet["count"] == 0
    assert "search boom" in packet["error"]


def test_task_appraisal_payload_includes_retrieved_text_only():
    task = _make_task()
    emotion = normalize_digital_emotion_state({})
    packet = {
        "text": "- [digital_task_episode]: payment failed",
        "hash": "abc123",
        "count": 1,
        "condition": "stream-appraisal",
        "status": "ok",
    }

    payload = _build_task_appraisal_user_payload(
        task=task,
        stage_key="steady",
        world_context={},
        profile_summary={},
        helplessness_now=40.0,
        task_self_efficacy=55.0,
        help_success_rate_smoothed=0.5,
        recent_episode_summary={},
        digital_emotion_state=emotion,
        task_relevant_memory={},
        retrieved_episodic_memory=packet,
    )

    assert payload["Retrieved Episodic Memory"] == packet["text"]
    assert "abc123" not in str(payload["Retrieved Episodic Memory"])


def test_task_appraisal_cache_key_changes_with_retrieval_hash_and_count():
    task = _make_task()
    emotion = normalize_digital_emotion_state({})
    common = {
        "task": task,
        "stage_key": "steady",
        "world_context": {},
        "profile_summary": {},
        "helplessness_now": 40.0,
        "task_self_efficacy": 55.0,
        "help_success_rate_smoothed": 0.5,
        "recent_episode_summary": {},
        "digital_emotion_state": emotion,
        "task_relevant_memory": {},
    }

    key_a = _build_task_appraisal_cache_key(
        **common,
        retrieved_episodic_memory={
            "condition": "stream-appraisal",
            "status": "ok",
            "count": 1,
            "hash": "hash-a",
        },
    )
    key_b = _build_task_appraisal_cache_key(
        **common,
        retrieved_episodic_memory={
            "condition": "stream-appraisal",
            "status": "ok",
            "count": 2,
            "hash": "hash-b",
        },
    )
    key_disabled = _build_task_appraisal_cache_key(
        **common,
        retrieved_episodic_memory={
            "condition": "stream-record-only",
            "status": "disabled",
            "count": 0,
            "hash": "",
        },
    )

    assert key_a != key_b
    assert key_a != key_disabled
