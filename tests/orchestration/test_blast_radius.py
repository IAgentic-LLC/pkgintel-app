"""Chapter 33, orchestration tier: proves the real bug this chapter
found and fixed. `sync_packages` itself is monkeypatched, not faked
out of a real seam `reliable_agents_labs.ingest` never designed for,
the same disclosed constraint `test_ingestion_schedule.py` already
names: this test is about `sync_all_tenants`'s own per-tenant
isolation logic, not about ingestion itself.
"""

import pkgintel_app.ingestion_schedule as ingestion_schedule


async def test_one_tenants_real_failure_never_stops_the_next_tenants_sync(monkeypatch):
    monkeypatch.setattr(
        ingestion_schedule, "load_tenant_packages", lambda: {"acme": ["x"], "globex": ["y"]}
    )

    async def _flaky_sync_packages(names, client, embedder, collection_name):
        if collection_name == "packages_acme":
            raise RuntimeError("real Qdrant error specific to acme's own collection")
        return {"succeeded": names, "failed": [], "pruned": 0}

    monkeypatch.setattr(ingestion_schedule, "sync_packages", _flaky_sync_packages)

    results = await ingestion_schedule.sync_all_tenants({"qdrant": None, "embedder": None})

    assert "error" in results["acme"]
    # The real point: globex's own sync still ran and still succeeded,
    # acme's own real failure never reached this loop's own caller.
    assert results["globex"] == {"succeeded": ["y"], "failed": [], "pruned": 0}
