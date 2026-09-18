"""Chapter 12, orchestration tier: the SAQ wiring itself, no network,
no real Postgres, no real Qdrant. `sync_all_tenants`'s own body reaches
real PyPI with no seam to fake that call out (`reliable_agents_labs.
ingest` was never designed with a fake data source), so proving *that*
runs correctly belongs to the integration tier instead, a real, named
constraint, not an oversight. What this tier can prove without any of
that: the cron job is actually configured, pointed at the right
function, on the schedule this app's own config says it should be.
"""

from pkgintel_app.ingestion_schedule import settings, sync_all_tenants


def test_settings_wires_a_cron_job_for_sync_all_tenants(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5999/db")
    monkeypatch.setenv("INGESTION_CRON", "*/5 * * * *")

    result = settings()

    assert result["functions"] == [sync_all_tenants]
    assert len(result["cron_jobs"]) == 1
    assert result["cron_jobs"][0].cron == "*/5 * * * *"


def test_settings_falls_back_to_the_real_default_cron(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5999/db")
    monkeypatch.delenv("INGESTION_CRON", raising=False)

    result = settings()

    assert result["cron_jobs"][0].cron == "0 */6 * * *"
