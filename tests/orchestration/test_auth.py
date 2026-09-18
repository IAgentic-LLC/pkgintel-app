"""Chapter 14, orchestration tier: deterministic JWT verification tests,
same local-RSA-keypair pattern as reorder-app's chapter 6 (`test_auth.py`
there), extended with the one claim this app's own tokens need: `org_id`.
`tests/contract/test_auth_live.py` is where a real Auth0 tenant issues a
real token, this tier is about the verification and tenant-mapping logic
itself.
"""

import asyncio
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
from qdrant_client.models import Distance, VectorParams
from reliable_agents_labs.models import ModelResult

from tests.fakes import FakeEmbeddingClient, InMemoryAnswerCache, ScriptedModelClient

_TEST_AUDIENCE = "https://pkgintel-app.dev/api"
_TEST_ISSUER = "https://test-tenant.auth0.com/"
_TEST_ACME_ORG_ID = "org_test_acme"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(_private_key.public_key())


def _make_token(*, org_id=_TEST_ACME_ORG_ID, exp_delta=3600, subject="auth0|test-user"):
    now = int(time.time())
    payload = {
        "sub": subject,
        "aud": _TEST_AUDIENCE,
        "iss": _TEST_ISSUER,
        "iat": now,
        "exp": now + exp_delta,
    }
    if org_id is not None:
        payload["org_id"] = org_id
    return jwt.encode(payload, _private_key, algorithm="RS256")


def _override_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_jwks_client", _FakeJWKSClient())
    monkeypatch.setenv("AUTH0_AUDIENCE", _TEST_AUDIENCE)
    monkeypatch.setenv("AUTH0_DOMAIN", "test-tenant.auth0.com")
    monkeypatch.setenv("AUTH0_ACME_ORG_ID", _TEST_ACME_ORG_ID)
    monkeypatch.setenv("AUTH0_GLOBEX_ORG_ID", "org_test_globex")


def _client_with_scripted_answer():
    model = ScriptedModelClient(
        [
            ModelResult(
                text='{"answer": "no packages match.", "cited_packages": []}',
                input_tokens=1,
                output_tokens=1,
                model_id="fake",
                provider="fake",
            )
        ]
    )
    app.dependency_overrides[get_model_client] = lambda: model
    app.dependency_overrides[get_embedding_client] = lambda: FakeEmbeddingClient([1.0, 0.0])

    # A real question has to land on a real (if empty) collection: the
    # underlying `search_packages` call errors on one that was never
    # created, this test's tenant is `acme`, so `acme`'s own collection
    # needs to exist before a request can reach it.
    qdrant = AsyncQdrantClient(location=":memory:")
    asyncio.run(
        qdrant.create_collection(
            tenant_collection_name("acme"),
            vectors_config=VectorParams(size=2, distance=Distance.COSINE),
        )
    )
    app.dependency_overrides[get_qdrant_client] = lambda: qdrant
    app.dependency_overrides[get_answer_cache] = lambda: InMemoryAnswerCache()
    return TestClient(app)


def test_missing_token_is_rejected(monkeypatch):
    _override_jwks(monkeypatch)
    client = _client_with_scripted_answer()
    try:
        response = client.post("/v1/questions", json={"question": "anything"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in (401, 403)


def test_token_with_a_recognized_organization_is_accepted(monkeypatch):
    _override_jwks(monkeypatch)
    client = _client_with_scripted_answer()
    token = _make_token(org_id=_TEST_ACME_ORG_ID)
    try:
        response = client.post(
            "/v1/questions",
            json={"question": "does anyone depend on certifi?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_a_machine_to_machine_token_with_no_org_id_is_rejected(monkeypatch):
    """The real finding this chapter documents: an Auth0 M2M
    (client-credentials) token never carries `org_id` at all, this
    tenant's own dashboard disables the checkbox that would allow it.
    A token shaped exactly like that one, `org_id` simply absent, must
    be rejected here, not treated as some default tenant.
    """
    _override_jwks(monkeypatch)
    client = _client_with_scripted_answer()
    token = _make_token(org_id=None)
    try:
        response = client.post(
            "/v1/questions",
            json={"question": "anything"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    body = response.json()
    assert "machine-to-machine" in body["detail"].lower()


def test_a_token_for_an_unrecognized_organization_is_rejected(monkeypatch):
    _override_jwks(monkeypatch)
    client = _client_with_scripted_answer()
    token = _make_token(org_id="org_some_other_company")
    try:
        response = client.post(
            "/v1/questions",
            json={"question": "anything"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
