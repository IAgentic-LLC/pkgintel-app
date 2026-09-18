"""Chapter 11, orchestration tier: an in-memory Qdrant client
(`location=":memory:"`, the real qdrant-client library, no server, no
docker) standing in for the real one, `ScriptedModelClient` standing in
for the real model, same reasoning as every orchestration test since
chapter 4. Both tenants are seeded with the *identical* vector on
purpose: if isolation still holds with nothing left for similarity
search to tell them apart on, it can only be coming from the
collection boundary itself.
"""

from pkgintel_app.tenant_rag import ask_rag_agent_for_tenant, tenant_collection_name
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from reliable_agents_labs.models import ModelResult

from tests.fakes import FakeEmbeddingClient, ScriptedModelClient

_SHARED_VECTOR = [1.0, 0.0, 0.0, 0.0]


def _text_result(text: str) -> ModelResult:
    return ModelResult(
        text=text, input_tokens=10, output_tokens=5, model_id="scripted", provider="scripted"
    )


async def _seed(qdrant: AsyncQdrantClient, tenant_id: str, name: str, summary: str) -> None:
    collection = tenant_collection_name(tenant_id)
    await qdrant.create_collection(
        collection, vectors_config=VectorParams(size=len(_SHARED_VECTOR), distance=Distance.COSINE)
    )
    point = PointStruct(id=1, vector=_SHARED_VECTOR, payload={"name": name, "summary": summary})
    await qdrant.upsert(collection, points=[point])


async def test_a_tenant_only_ever_retrieves_from_its_own_collection():
    qdrant = AsyncQdrantClient(location=":memory:")
    await _seed(qdrant, "acme", "httpx", "the next generation HTTP client")
    await _seed(qdrant, "globex", "fastapi", "a modern web framework")

    retrieved = {}
    model = ScriptedModelClient([_text_result('{"answer": "n/a", "cited_packages": []}')])
    embedder = FakeEmbeddingClient(_SHARED_VECTOR)

    await ask_rag_agent_for_tenant(
        "acme",
        "anything",
        qdrant=qdrant,
        embedder=embedder,
        model_client=model,
        on_retrieval=lambda results: retrieved.setdefault("results", results),
    )

    names = {r["name"] for r in retrieved["results"]}
    assert names == {"httpx"}
    assert "fastapi" not in names


async def test_a_second_tenant_is_equally_isolated_in_the_other_direction():
    qdrant = AsyncQdrantClient(location=":memory:")
    await _seed(qdrant, "acme", "httpx", "the next generation HTTP client")
    await _seed(qdrant, "globex", "fastapi", "a modern web framework")

    retrieved = {}
    model = ScriptedModelClient([_text_result('{"answer": "n/a", "cited_packages": []}')])
    embedder = FakeEmbeddingClient(_SHARED_VECTOR)

    await ask_rag_agent_for_tenant(
        "globex",
        "anything",
        qdrant=qdrant,
        embedder=embedder,
        model_client=model,
        on_retrieval=lambda results: retrieved.setdefault("results", results),
    )

    names = {r["name"] for r in retrieved["results"]}
    assert names == {"fastapi"}
    assert "httpx" not in names
