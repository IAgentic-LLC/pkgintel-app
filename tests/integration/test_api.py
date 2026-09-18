"""Chapter 14, integration tier: the real HTTP surface, a real Qdrant
server, and the real Neo4j graph chapter 13's own DAG already populated,
JWKS verification still doubled (a live Auth0 login is chapter 14's
contract tier, `tests/contract/test_auth_live.py`), everything behind
it real.
"""

import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pkgintel_app import auth
from pkgintel_app.api import app

pytestmark = pytest.mark.skipif(
    not (os.environ.get("QDRANT_URL") and os.environ.get("NEO4J_URI")),
    reason="No local Qdrant or Neo4j configured, see compose.yaml",
)

_AUDIENCE = "https://pkgintel-app.dev/api"
_ISSUER = "https://test-tenant.auth0.com/"
_ACME_ORG_ID = "org_test_acme"

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


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "_jwks_client", _FakeJWKSClient())
    monkeypatch.setenv("AUTH0_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("AUTH0_DOMAIN", "test-tenant.auth0.com")
    monkeypatch.setenv("AUTH0_ACME_ORG_ID", _ACME_ORG_ID)
    monkeypatch.setenv("AUTH0_GLOBEX_ORG_ID", "org_test_globex")
    return TestClient(app)


def test_the_dependents_endpoint_answers_from_the_real_shared_graph(monkeypatch):
    """Chapter 13's own DAG run already wrote real `DEPENDS_ON` edges into
    Neo4j, `certifi` included. This endpoint should surface exactly what
    that graph actually holds, not a value asserted into a test fixture.
    """
    # `with`, not a bare `TestClient(app)`: this endpoint reads
    # `app.state.neo4j_driver`, which only exists once the app's own
    # lifespan has actually run, entering the context manager is what
    # triggers that startup.
    with _client(monkeypatch) as client:
        response = client.get(
            "/v1/packages/certifi/dependents",
            headers={"Authorization": f"Bearer {_acme_token()}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "certifi"
    assert "httpx" in body["dependents"]


def test_dependents_still_requires_a_real_organization_token(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/v1/packages/certifi/dependents")

    assert response.status_code in (401, 403)
