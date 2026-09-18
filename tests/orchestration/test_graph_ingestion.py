"""Chapter 13, orchestration tier: the vector branch only. Neo4j's own
Python driver has no in-memory mode the way qdrant-client does, a
real, named constraint, not an oversight, so the graph branch's own
correctness is proven at the integration tier instead, against the
real thing.
"""

from pkgintel_app.graph_ingestion import embed_and_upsert
from pkgintel_app.tenant_rag import tenant_collection_name
from qdrant_client import AsyncQdrantClient
from reliable_agents_labs.pypi import PackageMetadata
from reliable_agents_labs.vector_store import VECTOR_SIZE


class _FakeEmbeddingClient:
    async def embed(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (VECTOR_SIZE - 1)


async def test_embed_and_upsert_writes_into_the_tenants_own_collection():
    qdrant = AsyncQdrantClient(location=":memory:")
    metadata = PackageMetadata(name="widget", version="1.0", summary="a real widget")

    name = await embed_and_upsert(metadata, "acme", qdrant, _FakeEmbeddingClient())

    assert name == "widget"
    points = await qdrant.scroll(tenant_collection_name("acme"), with_payload=True)
    assert {p.payload["name"] for p in points[0]} == {"widget"}
