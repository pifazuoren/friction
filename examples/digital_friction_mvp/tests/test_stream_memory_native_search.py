from __future__ import annotations

import asyncio
import importlib
import sys

from fastembed import SparseTextEmbedding


if "grpc" in sys.modules:
    del sys.modules["grpc"]
importlib.import_module("grpc")

from agentsociety.vectorstore import VectorStore


def test_native_stream_memory_search_returns_topic_filtered_episode():
    async def _run():
        vectorstore = VectorStore(
            SparseTextEmbedding(model_name="Qdrant/bm25"),
        )
        doc_ids = await vectorstore.add_documents(
            documents=[
                "[digital_task_episode][family=payment_risk_confirmation] "
                "I tried payment and risk confirmation but failed."
            ],
            extra_tags={
                "type": "stream",
                "memory_id": 0,
                "topic": "digital_task_episode",
                "day": 0,
                "time": 9 * 60 * 60,
                "location": "unknown",
            },
        )

        matched = await vectorstore.similarity_search(
            query="payment risk confirmation failure help",
            k=3,
            filter={"type": "stream", "topic": "digital_task_episode"},
        )
        wrong_topic = await vectorstore.similarity_search(
            query="payment risk confirmation failure help",
            k=3,
            filter={"type": "stream", "topic": "digital_recovery_episode"},
        )

        assert len(doc_ids) == 1
        assert len(matched) == 1
        content, score, metadata = matched[0]
        assert score > 0.0
        assert "[family=payment_risk_confirmation]" in content
        assert metadata["type"] == "stream"
        assert metadata["topic"] == "digital_task_episode"
        assert metadata["memory_id"] == 0
        assert wrong_topic == []

    asyncio.run(_run())
