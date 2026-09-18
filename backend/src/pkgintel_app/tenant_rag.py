"""Chapter 11: `reliable_agents_labs.vector_store` and `.ingest` already
accept a `collection_name` (Book 2's own extensibility point, built for
a reason neither of those chapters needed yet). `ask_rag_agent` is the
one place that doesn't expose it, every question it answers reads from
one single, global collection, no tenant concept anywhere in it. This
module closes exactly that one gap: everything underneath it (the
prompt, the response shape, the actual retrieval call) is reused
unchanged, not rewritten.
"""

import os

from reliable_agents_labs.json_parsing import parse_json_object
from reliable_agents_labs.models import (
    EmbeddingClient,
    ModelClient,
    build_embedding_client,
    build_model_client,
)
from reliable_agents_labs.rag_agent import RAG_SYSTEM_PROMPT, RagAnswer
from reliable_agents_labs.vector_store import (
    AsyncQdrantClient,
    build_qdrant_client,
    search_packages,
)


def tenant_collection_name(tenant_id: str) -> str:
    """One Qdrant collection per tenant. Chapter 16 revisits whether this
    scales to hundreds of tenants; for this book's own two-or-three-
    tenant demonstrations, strong isolation by construction (a tenant
    can only ever query its own collection, there is no shared filter
    to get wrong) is worth more than the efficiency a single collection
    with a payload filter would buy.
    """
    return f"packages_{tenant_id}"


def _qdrant_url() -> str:
    return os.environ.get("QDRANT_URL", "http://localhost:6333")


def build_tenant_qdrant_client() -> AsyncQdrantClient:
    return build_qdrant_client(url=_qdrant_url())


async def ask_rag_agent_for_tenant(
    tenant_id: str,
    question: str,
    qdrant: AsyncQdrantClient | None = None,
    embedder: EmbeddingClient | None = None,
    model_client: ModelClient | None = None,
    limit: int = 3,
    on_retrieval=None,
) -> RagAnswer:
    """`ask_rag_agent`'s own shape, aimed at one tenant's own collection
    instead of the global default. The prompt, the response model, and
    the JSON parsing are the exact same ones `rag_agent.py` uses, only
    the collection a question can ever retrieve from changes.

    `on_retrieval`, the same hook `ask_rag_agent` exposes and for the
    same reason: proving a tenant only ever retrieves its own data
    needs to see what retrieval actually returned, not just what the
    model chose to mention.
    """
    qdrant = qdrant or build_tenant_qdrant_client()
    embedder = embedder or build_embedding_client()
    model_client = model_client or build_model_client("answer_model")
    collection_name = tenant_collection_name(tenant_id)

    query_vector = await embedder.embed(question)
    results = await search_packages(
        qdrant, query_vector, limit=limit, collection_name=collection_name
    )
    if on_retrieval is not None:
        on_retrieval(results)
    context = "\n".join(f"- {r['name']}: {r['summary']}" for r in results)
    user_prompt = f"Package information:\n{context}\n\nQuestion: {question}"
    result = await model_client.generate(system=RAG_SYSTEM_PROMPT, user=user_prompt)
    payload = parse_json_object(result.text)
    return RagAnswer.model_validate(payload)
