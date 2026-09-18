"""Chapter 14, orchestration tier: the same tenant-isolation claim
chapter 11 proved directly against `ask_rag_agent_for_tenant`, now
proved through the actual HTTP surface a browser would call, real
FastAPI routing and real JWT verification included, only the Qdrant
server and the model call are doubles.
"""

import json
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
_GLOBEX_ORG_ID = "org_test_globex"
_SHARED_VECTOR = [1.0, 0.0, 0.0, 0.0]

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(_private_key.public_key())


def _token_for(org_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": "auth0|test-user",
        "aud": _AUDIENCE,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + 3600,
        "org_id": org_id,
    }
    return jwt.encode(payload, _private_key, algorithm="RS256")


async def _seed(qdrant: AsyncQdrantClient, tenant_id: str, name: str, summary: str) -> None:
    collection = tenant_collection_name(tenant_id)
    await qdrant.create_collection(
        collection, vectors_config=VectorParams(size=len(_SHARED_VECTOR), distance=Distance.COSINE)
    )
    point = PointStruct(id=1, vector=_SHARED_VECTOR, payload={"name": name, "summary": summary})
    await qdrant.upsert(collection, points=[point])


async def test_a_tenants_bearer_token_only_ever_reaches_its_own_collection(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client", _FakeJWKSClient())
    monkeypatch.setenv("AUTH0_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("AUTH0_DOMAIN", "test-tenant.auth0.com")
    monkeypatch.setenv("AUTH0_ACME_ORG_ID", _ACME_ORG_ID)
    monkeypatch.setenv("AUTH0_GLOBEX_ORG_ID", _GLOBEX_ORG_ID)

    qdrant = AsyncQdrantClient(location=":memory:")
    await _seed(qdrant, "acme", "httpx", "the next generation HTTP client")
    await _seed(qdrant, "globex", "fastapi", "a modern web framework")

    class _EchoingModelClient:
        """Reflects whatever package context it was actually handed back
        as the "answer", rather than a fixed, scripted string. This is
        what makes the test meaningful: it fails if `to_qdrant`'s tenant
        boundary ever leaks the other tenant's package into the prompt
        this model receives, not just if the route wires differently.
        """

        async def generate(self, *, system, user, tools=None, history=None):
            return ModelResult(
                text=json.dumps({"answer": user, "cited_packages": []}),
                input_tokens=1,
                output_tokens=1,
                model_id="fake",
                provider="fake",
            )

    app.dependency_overrides[get_qdrant_client] = lambda: qdrant
    app.dependency_overrides[get_embedding_client] = lambda: FakeEmbeddingClient(_SHARED_VECTOR)
    app.dependency_overrides[get_model_client] = lambda: _EchoingModelClient()
    app.dependency_overrides[get_answer_cache] = lambda: InMemoryAnswerCache()
    client = TestClient(app)
    try:
        acme_response = client.post(
            "/v1/questions",
            json={"question": "anything"},
            headers={"Authorization": f"Bearer {_token_for(_ACME_ORG_ID)}"},
        )
        globex_response = client.post(
            "/v1/questions",
            json={"question": "anything"},
            headers={"Authorization": f"Bearer {_token_for(_GLOBEX_ORG_ID)}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert acme_response.status_code == 200
    assert globex_response.status_code == 200
    assert "httpx" in acme_response.json()["answer"]
    assert "fastapi" not in acme_response.json()["answer"]
    assert "fastapi" in globex_response.json()["answer"]
    assert "httpx" not in globex_response.json()["answer"]
