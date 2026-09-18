"""Chapter 11, integration tier: the same isolation guarantee the
orchestration tier already proved against an in-memory Qdrant, proven
again against the real one (see compose.yaml). A scripted model and a
constant-vector embedder keep this free and fast; the real thing under
test is Qdrant's own collection boundary, not the model or the
embedding.
"""

import os
import uuid

import pytest
from pkgintel_app.tenant_rag import ask_rag_agent_for_tenant, tenant_collection_name
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from reliable_agents_labs.models import ModelResult

from tests.fakes import FakeEmbeddingClient, ScriptedModelClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("QDRANT_URL"),
    reason="No local Qdrant configured for this environment, see compose.yaml",
)

_SHARED_VECTOR = [1.0, 0.0, 0.0, 0.0]


def _text_result(text: str) -> ModelResult:
    return ModelResult(
        text=text, input_tokens=10, output_tokens=5, model_id="scripted", provider="scripted"
    )


async def test_a_tenant_only_ever_retrieves_from_its_own_real_collection():
    suffix = uuid.uuid4().hex[:8]
    tenant_a, tenant_b = f"itest-a-{suffix}", f"itest-b-{suffix}"
    qdrant = AsyncQdrantClient(url=os.environ["QDRANT_URL"])
    try:
        for tenant_id, name, summary in [
            (tenant_a, "httpx", "the next generation HTTP client"),
            (tenant_b, "fastapi", "a modern web framework"),
        ]:
            collection = tenant_collection_name(tenant_id)
            await qdrant.create_collection(
                collection,
                vectors_config=VectorParams(size=len(_SHARED_VECTOR), distance=Distance.COSINE),
            )
            point = PointStruct(
                id=1, vector=_SHARED_VECTOR, payload={"name": name, "summary": summary}
            )
            await qdrant.upsert(collection, points=[point])

        retrieved = {}
        model = ScriptedModelClient([_text_result('{"answer": "n/a", "cited_packages": []}')])
        await ask_rag_agent_for_tenant(
            tenant_a,
            "anything",
            qdrant=qdrant,
            embedder=FakeEmbeddingClient(_SHARED_VECTOR),
            model_client=model,
            on_retrieval=lambda results: retrieved.setdefault("results", results),
        )

        names = {r["name"] for r in retrieved["results"]}
        assert names == {"httpx"}
        assert "fastapi" not in names
    finally:
        await qdrant.delete_collection(tenant_collection_name(tenant_a))
        await qdrant.delete_collection(tenant_collection_name(tenant_b))
