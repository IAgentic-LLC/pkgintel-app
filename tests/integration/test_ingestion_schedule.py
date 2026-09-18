"""Chapter 12, integration tier: the real thing, a real Qdrant, a real
Postgres-backed queue, and (unavoidably, see the orchestration tier's
own docstring) a real call to PyPI, `reliable_agents_labs.ingest` has
no seam to fake that out. Proves the scheduled job actually does what
chapter 11's own manual script did, unattended.
"""

import os
from unittest.mock import patch

import pytest
from pkgintel_app.ingestion_schedule import sync_all_tenants
from pkgintel_app.tenant_rag import tenant_collection_name
from qdrant_client import AsyncQdrantClient
from reliable_agents_labs.models import build_embedding_client

pytestmark = pytest.mark.skipif(
    not (os.environ.get("QDRANT_URL") and os.environ.get("GEMINI_API_KEY")),
    reason="No local Qdrant or live embedding credentials configured, see compose.yaml",
)


async def test_sync_all_tenants_ingests_each_tenants_own_real_packages():
    qdrant = AsyncQdrantClient(url=os.environ["QDRANT_URL"])
    ctx = {"qdrant": qdrant, "embedder": build_embedding_client()}
    fake_tenants = {"itest-acme": ["requests"], "itest-globex": ["fastapi"]}

    try:
        with patch(
            "pkgintel_app.ingestion_schedule.load_tenant_packages", return_value=fake_tenants
        ):
            results = await sync_all_tenants(ctx)

        assert results["itest-acme"]["succeeded"] == ["requests"]
        assert results["itest-globex"]["succeeded"] == ["fastapi"]
    finally:
        await qdrant.delete_collection(tenant_collection_name("itest-acme"))
        await qdrant.delete_collection(tenant_collection_name("itest-globex"))
