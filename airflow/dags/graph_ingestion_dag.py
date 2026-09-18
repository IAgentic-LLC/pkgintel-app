"""Chapter 13: the same ingestion chapter 12 already runs on a
schedule, given a second real destination. One real PyPI fetch per
package now feeds two independent writes, a vector embedding into
Qdrant and a set of `DEPENDS_ON` edges into Neo4j, before a shared
prune step waits for both. This shape, fan out, then merge, with
per-task retry and a UI that shows exactly which package failed on
which branch, is what Airflow is actually for, unlike chapter 12's own
single scheduled function, which never needed any of that.

All the real logic lives in `pkgintel_app.graph_ingestion` and
`pkgintel_app.ingestion_schedule`, imported unchanged. This file only
wires it into Airflow's own task graph.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task
from pkgintel_app.graph_ingestion import (
    embed_and_upsert,
    fetch_metadata,
    prune_removed,
    write_graph_edges,
)
from pkgintel_app.tenant_registry import load_tenant_packages

TENANTS_CONFIG_PATH = "/opt/airflow/config/tenants.yaml"


@dag(
    dag_id="graph_ingestion",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["pkgintel-app", "chapter-13"],
)
def graph_ingestion():
    @task
    async def fetch(name: str) -> dict:
        metadata = await fetch_metadata(name)
        return metadata.model_dump()

    @task
    async def to_qdrant(metadata: dict, tenant_id: str) -> str:
        from pkgintel_app.tenant_rag import build_tenant_qdrant_client
        from reliable_agents_labs.models import build_embedding_client
        from reliable_agents_labs.pypi import PackageMetadata

        # Not reliable_agents_labs' own build_qdrant_client: that one
        # defaults to "localhost" with no env var fallback at all,
        # which inside this container means the container itself, not
        # the host. build_tenant_qdrant_client reads QDRANT_URL,
        # confirmed live as the actual difference between this task
        # failing outright and to_neo4j (whose own build_neo4j_driver
        # does read an env var) succeeding on the very same run.
        return await embed_and_upsert(
            PackageMetadata(**metadata),
            tenant_id,
            build_tenant_qdrant_client(),
            build_embedding_client(),
        )

    @task
    async def to_neo4j(metadata: dict) -> list[str]:
        from reliable_agents_labs.graph_store import build_neo4j_driver
        from reliable_agents_labs.pypi import PackageMetadata

        driver = build_neo4j_driver()
        deps = await write_graph_edges(PackageMetadata(**metadata), driver)
        await driver.close()
        return deps

    @task
    async def prune(tenant_id: str, current_names: list[str]) -> list[str]:
        from pkgintel_app.tenant_rag import build_tenant_qdrant_client

        return await prune_removed(tenant_id, current_names, build_tenant_qdrant_client())

    for tenant_id, names in load_tenant_packages(TENANTS_CONFIG_PATH).items():
        fetched = fetch.override(task_id=f"fetch_{tenant_id}").expand(name=names)
        qdrant_done = (
            to_qdrant.override(task_id=f"to_qdrant_{tenant_id}")
            .partial(tenant_id=tenant_id)
            .expand(metadata=fetched)
        )
        neo4j_done = to_neo4j.override(task_id=f"to_neo4j_{tenant_id}").expand(metadata=fetched)
        pruned = prune.override(task_id=f"prune_{tenant_id}")(
            tenant_id=tenant_id, current_names=qdrant_done
        )
        neo4j_done >> pruned


graph_ingestion()
