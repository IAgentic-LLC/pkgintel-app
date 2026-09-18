"""Chapter 11's live demonstration: chapter 12 turns this into a real,
scheduled pipeline. For now, a direct call proves tenant isolation
against real PyPI data, not a synthetic fixture.

Usage: uv run python scripts/ingest_tenant.py <tenant_id> <package> [<package> ...]
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from pkgintel_app.tenant_rag import build_tenant_qdrant_client, tenant_collection_name  # noqa: E402
from reliable_agents_labs.ingest import sync_packages  # noqa: E402
from reliable_agents_labs.models import build_embedding_client  # noqa: E402


async def main(tenant_id: str, names: list[str]) -> None:
    qdrant = build_tenant_qdrant_client()
    embedder = build_embedding_client()
    result = await sync_packages(
        names, qdrant, embedder, collection_name=tenant_collection_name(tenant_id)
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
