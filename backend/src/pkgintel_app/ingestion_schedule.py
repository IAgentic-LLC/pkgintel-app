"""Chapter 12: chapter 11's `sync_packages` call, run by a human, once,
by hand. This module is the same call, turned into a real, unattended,
scheduled job, SAQ's own `CronJob`, the same queue technology chapter 9
already introduced for reorder-app, reused rather than reaching for a
second orchestration tool (Airflow, say) for what is really one
scheduled function, not a multi-step DAG with cross-task dependencies.

Chapter 33: a real, previously-unexamined blast-radius bug lived here
since chapter 12. `sync_packages` already returns a summary instead of
raising for a bad *package* name (`ingest_all`'s own per-package try),
but nothing ever caught a failure at the *tenant* level, a real Qdrant
error specific to one tenant's own collection, say. One tenant's own
failure would propagate straight out of this function's own `for`
loop, skipping every tenant listed after it in that same run. Fixed by
scoping the try/except to each tenant, the same real "blast radius"
principle chapter 33's own diagram names directly.
"""

import logging
import os

from reliable_agents_labs.ingest import sync_packages
from reliable_agents_labs.models import build_embedding_client
from saq import CronJob
from saq.queue.postgres import PostgresQueue

from pkgintel_app.tenant_rag import build_tenant_qdrant_client, tenant_collection_name
from pkgintel_app.tenant_registry import load_tenant_packages

logger = logging.getLogger(__name__)


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def get_ingestion_queue() -> PostgresQueue:
    return PostgresQueue.from_url(_database_url(), name="ingestion")


# Every 6 hours: real package metadata doesn't change minute to minute,
# and `sync_packages` is a real network call per package, per tenant,
# not free to run more often than the data actually justifies.
# Overridable via INGESTION_CRON for local verification without
# touching this default.
DEFAULT_CRON = "0 */6 * * *"


async def startup(ctx: dict) -> None:
    """Real resources, built once per worker, not once per run. Chapter
    9's own `startup`/`ctx` pattern: a test calls `sync_all_tenants`
    directly with a fake `qdrant`/`embedder` already in `ctx`, no real
    worker process, no real network, ever required to test this.
    """
    ctx["qdrant"] = build_tenant_qdrant_client()
    ctx["embedder"] = build_embedding_client()


async def sync_all_tenants(ctx: dict) -> dict:
    """The scheduled job itself. Each tenant's sync is chapter 11's own
    `ask_rag_agent_for_tenant`'s sibling on the write side: the exact
    same `sync_packages` a human called by hand in chapter 11, now
    called by SAQ's own cron, once per tenant, every run.

    Chapter 33: each tenant's own real failure is caught and recorded
    here, never allowed to reach this function's own caller and cancel
    every tenant still left in `load_tenant_packages()`'s own
    iteration order. A `{"error": ...}` entry in the returned dict is
    this run's own real, honest record of which tenant failed and why,
    not a silently skipped tenant with no trace left behind.
    """
    qdrant = ctx["qdrant"]
    embedder = ctx["embedder"]
    results = {}
    for tenant_id, names in load_tenant_packages().items():
        try:
            results[tenant_id] = await sync_packages(
                names, qdrant, embedder, collection_name=tenant_collection_name(tenant_id)
            )
        except Exception as exc:
            logger.exception("Sync failed for tenant %r, continuing to the next one", tenant_id)
            results[tenant_id] = {"error": str(exc)}
    return results


def settings() -> dict:
    """A callable, not a module-level dict, same reason chapter 9's
    `reorder_app.jobs.settings` already is: a value that depends on the
    environment (`DATABASE_URL`) shouldn't be computed at import time.
    """
    cron = os.environ.get("INGESTION_CRON", DEFAULT_CRON)
    return {
        "queue": get_ingestion_queue(),
        "functions": [sync_all_tenants],
        "cron_jobs": [CronJob(sync_all_tenants, cron=cron)],
        "startup": startup,
    }
