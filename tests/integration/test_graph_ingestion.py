"""Chapter 13, integration tier: the real thing, both branches, a real
PyPI fetch feeding a real Qdrant upsert and real Neo4j edges, then a
real prune. `httpx`'s own core dependencies (`anyio`, `certifi`,
`httpcore`, `idna`), confirmed live against PyPI while writing this
test, not assumed from memory.
"""

import os

import pytest
from pkgintel_app.graph_ingestion import (
    embed_and_upsert,
    fetch_metadata,
    prune_removed,
    write_graph_edges,
)
from pkgintel_app.tenant_rag import tenant_collection_name
from qdrant_client import AsyncQdrantClient
from reliable_agents_labs.graph_store import build_neo4j_driver, find_dependents
from reliable_agents_labs.models import build_embedding_client

pytestmark = pytest.mark.skipif(
    not (os.environ.get("QDRANT_URL") and os.environ.get("GEMINI_API_KEY")),
    reason="No local Qdrant or live embedding credentials configured, see compose.yaml",
)


async def test_one_real_fetch_feeds_both_a_vector_upsert_and_real_graph_edges():
    tenant_id = "itest-graph"
    qdrant = AsyncQdrantClient(url=os.environ["QDRANT_URL"])
    driver = build_neo4j_driver()
    try:
        metadata = await fetch_metadata("httpx")

        upserted_name = await embed_and_upsert(
            metadata, tenant_id, qdrant, build_embedding_client()
        )
        deps = await write_graph_edges(metadata, driver)

        assert upserted_name == "httpx"
        assert set(deps) == {"anyio", "certifi", "httpcore", "idna"}

        dependents = await find_dependents(driver, "certifi")
        assert "httpx" in dependents

        pruned = await prune_removed(tenant_id, [], qdrant)
        assert pruned == ["httpx"]
    finally:
        await qdrant.delete_collection(tenant_collection_name(tenant_id))
        await driver.close()
