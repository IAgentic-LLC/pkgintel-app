"""Chapter 16, orchestration tier: `pkgintel-app`'s own first traced
wrapper, proven the same way Book 2's own observability tests prove
reorder-app's: the traced call returns the identical answer an
untraced call would, and the `on_model_result` hook chapter 15 already
depends on still fires, tracing added around chapter 11's own logic,
not inside it. Whether a trace also reaches Langfuse depends on
`LANGFUSE_PUBLIC_KEY` being set; either way this call cannot fail.
"""

from pkgintel_app.observability import ask_rag_agent_for_tenant_traced
from pkgintel_app.tenant_rag import tenant_collection_name
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from reliable_agents_labs.models import ModelResult

from tests.fakes import FakeEmbeddingClient, ScriptedModelClient

_VECTOR = [1.0, 0.0, 0.0, 0.0]


async def _seeded_qdrant() -> AsyncQdrantClient:
    qdrant = AsyncQdrantClient(location=":memory:")
    collection = tenant_collection_name("acme")
    await qdrant.create_collection(
        collection, vectors_config=VectorParams(size=len(_VECTOR), distance=Distance.COSINE)
    )
    await qdrant.upsert(
        collection,
        points=[
            PointStruct(
                id=1, vector=_VECTOR, payload={"name": "httpx", "summary": "an HTTP client"}
            )
        ],
    )
    return qdrant


async def test_the_traced_wrapper_returns_the_same_answer_as_the_untraced_call():
    model = ScriptedModelClient(
        [
            ModelResult(
                text='{"answer": "httpx is an HTTP client.", "cited_packages": ["httpx"]}',
                input_tokens=100,
                output_tokens=20,
                model_id="fake",
                provider="fake",
            )
        ]
    )
    answer = await ask_rag_agent_for_tenant_traced(
        "acme",
        "What does httpx do?",
        qdrant=await _seeded_qdrant(),
        embedder=FakeEmbeddingClient(_VECTOR),
        model_client=model,
    )
    assert answer.answer == "httpx is an HTTP client."
    assert answer.cited_packages == ["httpx"]


async def test_the_on_model_result_hook_still_fires_through_the_traced_wrapper():
    # Chapter 15's own real dependency: the API endpoint's cost capture
    # closure has to keep firing even though a tracing wrapper now sits
    # between it and `ask_rag_agent_for_tenant`.
    model = ScriptedModelClient(
        [
            ModelResult(
                text='{"answer": "n/a", "cited_packages": []}',
                input_tokens=100,
                output_tokens=20,
                model_id="fake",
                provider="fake",
            )
        ]
    )
    captured = {}
    await ask_rag_agent_for_tenant_traced(
        "acme",
        "anything",
        qdrant=await _seeded_qdrant(),
        embedder=FakeEmbeddingClient(_VECTOR),
        model_client=model,
        on_model_result=lambda result: captured.setdefault("result", result),
    )
    assert captured["result"].input_tokens == 100
    assert captured["result"].output_tokens == 20
