"""Chapter 15, orchestration tier: the same real HTTP surface chapter
14's own tests already exercise, an in-memory answer cache standing in
for `PostgresAnswerCache` (chapter 11's own seam reasoning, applied to
Postgres instead of Qdrant), proving the caching and cost-accounting
logic without a real database anywhere in this test run.
"""

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pkgintel_app import auth
from pkgintel_app.api import (
    app,
    get_answer_cache,
    get_embedding_client,
    get_model_client,
    get_qdrant_client,
)
from pkgintel_app.tenant_rag import tenant_collection_name
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from reliable_agents_labs.models import ModelResult

from tests.fakes import FakeEmbeddingClient, InMemoryAnswerCache

_AUDIENCE = "https://pkgintel-app.dev/api"
_ISSUER = "https://test-tenant.auth0.com/"
_ACME_ORG_ID = "org_test_acme"
_SHARED_VECTOR = [1.0, 0.0, 0.0, 0.0]

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(_private_key.public_key())


def _acme_token() -> str:
    now = int(time.time())
    payload = {
        "sub": "auth0|test-user",
        "aud": _AUDIENCE,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + 3600,
        "org_id": _ACME_ORG_ID,
    }
    return jwt.encode(payload, _private_key, algorithm="RS256")


class _CountingModelClient:
    """A `ScriptedModelClient` that fails loudly, via a plain `IndexError`,
    if it's ever called a second time. A cache hit that quietly still
    called the model would otherwise be invisible to this test.
    """

    def __init__(self, result: ModelResult) -> None:
        self._result = result
        self._called = False

    async def generate(self, *, system, user, tools=None, history=None) -> ModelResult:
        if self._called:
            raise AssertionError("model called twice; the cache should have caught the second call")
        self._called = True
        return self._result


async def test_a_repeated_question_is_served_from_cache_at_zero_cost(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client", _FakeJWKSClient())
    monkeypatch.setenv("AUTH0_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("AUTH0_DOMAIN", "test-tenant.auth0.com")
    monkeypatch.setenv("AUTH0_ACME_ORG_ID", _ACME_ORG_ID)
    monkeypatch.setenv("AUTH0_GLOBEX_ORG_ID", "org_test_globex")

    qdrant = AsyncQdrantClient(location=":memory:")
    collection = tenant_collection_name("acme")
    await qdrant.create_collection(
        collection, vectors_config=VectorParams(size=len(_SHARED_VECTOR), distance=Distance.COSINE)
    )
    await qdrant.upsert(
        collection,
        points=[
            PointStruct(
                id=1,
                vector=_SHARED_VECTOR,
                payload={"name": "httpx", "summary": "the next generation HTTP client"},
            )
        ],
    )

    model = _CountingModelClient(
        ModelResult(
            text='{"answer": "httpx is an HTTP client.", "cited_packages": ["httpx"]}',
            input_tokens=1000,
            output_tokens=200,
            model_id="fake",
            provider="fake",
        )
    )
    cache = InMemoryAnswerCache()

    app.dependency_overrides[get_qdrant_client] = lambda: qdrant
    app.dependency_overrides[get_embedding_client] = lambda: FakeEmbeddingClient(_SHARED_VECTOR)
    app.dependency_overrides[get_model_client] = lambda: model
    app.dependency_overrides[get_answer_cache] = lambda: cache
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_acme_token()}"}
    try:
        first = client.post(
            "/v1/questions", json={"question": "What does httpx do?"}, headers=headers
        )
        second = client.post(
            "/v1/questions", json={"question": "  WHAT DOES HTTPX DO?  "}, headers=headers
        )
        usage = client.get("/v1/usage", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["cached"] is False
    assert first.json()["cost_usd"] > 0.0

    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert second.json()["cost_usd"] == 0.0
    assert second.json()["answer"] == first.json()["answer"]

    assert usage.status_code == 200
    body = usage.json()
    assert body["call_count"] == 2
    assert body["cache_hit_count"] == 1
    assert body["total_cost_usd"] == first.json()["cost_usd"]
