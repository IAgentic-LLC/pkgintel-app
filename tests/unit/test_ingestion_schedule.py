"""Chapter 12, unit tier: no network, no Postgres, no Qdrant."""

from pkgintel_app.ingestion_schedule import load_tenant_packages


def test_loads_the_real_committed_tenant_config():
    tenants = load_tenant_packages("config/tenants.yaml")
    assert tenants["acme"] == ["requests", "httpx", "urllib3"]
    assert tenants["globex"] == ["fastapi"]


def test_missing_config_file_raises_instead_of_silently_scheduling_nothing(tmp_path):
    missing = tmp_path / "does-not-exist.yaml"
    try:
        load_tenant_packages(str(missing))
        raised = False
    except FileNotFoundError:
        raised = True
    assert raised
