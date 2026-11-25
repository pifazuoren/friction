from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_memory_module(monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    memory_path = repo_root / "packages" / "agentsociety" / "agentsociety" / "memory" / "memory.py"

    for module_name in (
        "agentsociety",
        "agentsociety.memory",
        "agentsociety.memory.memory",
        "agentsociety.environment",
        "agentsociety.logger",
        "agentsociety.utils",
        "agentsociety.utils.decorators",
        "agentsociety.vectorstore",
        "agentsociety.agent",
        "agentsociety.agent.memory_config_generator",
    ):
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    agentsociety_module = types.ModuleType("agentsociety")
    agentsociety_module.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agentsociety", agentsociety_module)

    memory_pkg = types.ModuleType("agentsociety.memory")
    memory_pkg.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agentsociety.memory", memory_pkg)

    fastembed_module = types.ModuleType("fastembed")
    fastembed_module.SparseTextEmbedding = type("SparseTextEmbedding", (), {})
    monkeypatch.setitem(sys.modules, "fastembed", fastembed_module)

    environment_module = types.ModuleType("agentsociety.environment")
    environment_module.Environment = type("Environment", (), {})
    monkeypatch.setitem(sys.modules, "agentsociety.environment", environment_module)

    logger_module = types.ModuleType("agentsociety.logger")
    logger_module.get_logger = lambda: types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "agentsociety.logger", logger_module)

    utils_module = types.ModuleType("agentsociety.utils")
    utils_module.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agentsociety.utils", utils_module)

    decorators_module = types.ModuleType("agentsociety.utils.decorators")

    def lock_decorator(fn):
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)

        return wrapper

    decorators_module.lock_decorator = lock_decorator
    monkeypatch.setitem(sys.modules, "agentsociety.utils.decorators", decorators_module)

    vectorstore_module = types.ModuleType("agentsociety.vectorstore")
    vectorstore_module.VectorStore = _FakeVectorStore
    monkeypatch.setitem(sys.modules, "agentsociety.vectorstore", vectorstore_module)

    agent_module = types.ModuleType("agentsociety.agent")
    agent_module.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agentsociety.agent", agent_module)

    memory_config_module = types.ModuleType("agentsociety.agent.memory_config_generator")
    memory_config_module.MemoryConfig = type("MemoryConfig", (), {})
    monkeypatch.setitem(
        sys.modules,
        "agentsociety.agent.memory_config_generator",
        memory_config_module,
    )

    spec = importlib.util.spec_from_file_location(
        "agentsociety.memory.memory",
        memory_path,
    )
    assert spec is not None
    assert spec.loader is not None
    memory_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "agentsociety.memory.memory", memory_module)
    spec.loader.exec_module(memory_module)
    return memory_module


class _FakeVectorStore:
    def __init__(self, embedding):
        self.docs = []

    async def add_documents(self, documents, extra_tags=None):
        doc_ids = []
        for document in documents:
            payload = {"content": document}
            if extra_tags:
                payload.update(extra_tags)
            self.docs.append(payload)
            doc_ids.append(f"doc-{len(self.docs) - 1}")
        return doc_ids

    async def similarity_search(self, query, k=4, filter=None):
        filter = filter or {}
        query_tokens = {
            token.lower()
            for token in str(query or "").replace("[", " ").replace("]", " ").split()
            if token
        }
        results = []
        for payload in self.docs:
            if not _matches_filter(payload, filter):
                continue
            content = str(payload.get("content", ""))
            content_lower = content.lower()
            if query_tokens and not any(token in content_lower for token in query_tokens):
                continue
            metadata = {key: value for key, value in payload.items() if key != "content"}
            results.append((content, 1.0, metadata))
        return results[:k]


def _matches_filter(payload, filter_dict):
    for key, expected in filter_dict.items():
        actual = payload.get(key)
        if isinstance(expected, dict):
            gte = expected.get("gte")
            lte = expected.get("lte")
            if gte is not None and not (actual >= gte):
                return False
            if lte is not None and not (actual <= lte):
                return False
        elif actual != expected:
            return False
    return True


class _FakeEnvironment:
    def get_datetime(self):
        return 3, 4567


class _FakeStatusMemory:
    async def get(self, key, default_value=None):
        if key == "position":
            return {"aoi_position": {"aoi_id": "home-aoi"}}
        return default_value


def test_stream_add_writes_metadata_used_by_search(monkeypatch):
    asyncio.run(_run_stream_add_writes_metadata_used_by_search(monkeypatch))


async def _run_stream_add_writes_metadata_used_by_search(monkeypatch):
    memory_module = _load_memory_module(monkeypatch)

    stream = memory_module.StreamMemory(
        environment=_FakeEnvironment(),
        status_memory=_FakeStatusMemory(),
        embedding=object(),
    )

    description = (
        "[digital_task_episode][family=payment_risk_confirmation] "
        "payment failed after risk popup"
    )
    memory_id = await stream.add(
        topic="digital_task_episode",
        description=description,
    )

    assert memory_id == 0
    assert stream._vectorstore.docs == [
        {
            "content": description,
            "type": "stream",
            "memory_id": 0,
            "topic": "digital_task_episode",
            "day": 3,
            "time": 4567,
            "location": "home-aoi",
        }
    ]

    search_result = await stream.search(
        "payment",
        topic="digital_task_episode",
        top_k=3,
    )
    assert "Nothing" not in search_result
    assert "[digital_task_episode]" in search_result
    assert "location: home-aoi" in search_result

    today_result = await stream.search_today(
        "payment",
        topic="digital_task_episode",
        top_k=3,
    )
    assert "Nothing" not in today_result
    assert "[digital_task_episode]" in today_result


def test_stream_search_respects_topic_filter(monkeypatch):
    asyncio.run(_run_stream_search_respects_topic_filter(monkeypatch))


async def _run_stream_search_respects_topic_filter(monkeypatch):
    memory_module = _load_memory_module(monkeypatch)

    stream = memory_module.StreamMemory(
        environment=_FakeEnvironment(),
        status_memory=_FakeStatusMemory(),
        embedding=object(),
    )

    await stream.add(
        topic="digital_task_episode",
        description="[digital_task_episode] payment failed",
    )
    await stream.add(
        topic="digital_daily_reflection",
        description="[digital_daily_reflection] payment felt stressful today",
    )

    result = await stream.search(
        "payment",
        topic="digital_task_episode",
        top_k=5,
    )

    assert "[digital_task_episode]" in result
    assert "[digital_daily_reflection]" not in result
