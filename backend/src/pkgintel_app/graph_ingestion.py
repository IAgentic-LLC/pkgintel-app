"""Chapter 13: chapter 12's ingestion, once it actually has to fan out
to a second real store. `fetch_package_metadata`'s one real result now
feeds two independent writes, a vector embedding into Qdrant and a set
of `DEPENDS_ON` edges into Neo4j, before a shared prune step needs both
done. That branch-then-merge shape is what a plain scheduled function
can't express cleanly and a DAG can, the actual reason this chapter
reaches for Airflow instead of extending chapter 12's own SAQ cron.

The graph side is deliberately NOT tenant-scoped, unlike chapter 11's
vector collections. "numpy depends on X" is a fact about numpy, not
about which tenant happens to be asking, so every tenant's packages
write into the same shared graph.
"""

from reliable_agents_labs.dependency_graph import _dependency_name
from reliable_agents_labs.graph_etl import _is_core_requirement
from reliable_agents_labs.graph_store import AsyncDriver, create_depends_on
from reliable_agents_labs.ingest import package_point_id, prune_stale
from reliable_agents_labs.models import EmbeddingClient
from reliable_agents_labs.pypi import PackageMetadata, fetch_package_metadata
from reliable_agents_labs.vector_store import AsyncQdrantClient, ensure_collection, upsert_package

from pkgintel_app.tenant_rag import tenant_collection_name


async def fetch_metadata(name: str) -> PackageMetadata:
    """One real PyPI call, the same one chapter 11's `sync_packages`
    already made, pulled out on its own so both branches below can
    reuse its one result instead of each fetching it again.
    """
    return await fetch_package_metadata(name)


async def embed_and_upsert(
    metadata: PackageMetadata, tenant_id: str, qdrant: AsyncQdrantClient, embedder: EmbeddingClient
) -> str:
    """The vector branch: chapter 11's own tenant-scoped collection,
    `upsert_package` reused unchanged, just handed metadata that was
    already fetched instead of fetching it again itself.
    """
    collection_name = tenant_collection_name(tenant_id)
    await ensure_collection(qdrant, collection_name=collection_name)
    vector = await embedder.embed(metadata.summary)
    await upsert_package(
        qdrant,
        package_point_id(metadata.name),
        metadata.name,
        metadata.summary,
        vector,
        collection_name=collection_name,
    )
    return metadata.name


async def write_graph_edges(metadata: PackageMetadata, driver: AsyncDriver) -> list[str]:
    """The graph branch: chapter 19's own `create_depends_on`, called
    directly with metadata already in hand, rather than through
    chapter 19's `load_dependency_graph`, which would fetch it again.
    Only core requirements, chapter 19's own distinction between a
    package's real, always-needed dependencies and ones gated behind
    an optional extra.
    """
    core_requirements = [r for r in metadata.requires_dist if _is_core_requirement(r)]
    deps = sorted({_dependency_name(r) for r in core_requirements})
    for dep in deps:
        await create_depends_on(driver, metadata.name, dep)
    return deps


async def prune_removed(
    tenant_id: str, current_names: list[str], qdrant: AsyncQdrantClient
) -> list[str]:
    """The merge step: chapter 11's own `prune_stale`, run only once
    both branches above have finished, so a package that both got
    embedded and got its edges written is never pruned mid-write.
    """
    return await prune_stale(
        current_names, qdrant, collection_name=tenant_collection_name(tenant_id)
    )
