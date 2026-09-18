"""Chapter 12's `load_tenant_packages`, pulled out on its own. Chapter
13's Airflow DAG needs this exact function and nothing else chapter
12's own `ingestion_schedule` module carries, SAQ included; importing
it from there dragged a queue library into a container that never
uses one, a real, live-found reason this lives here instead.
"""

import yaml


def load_tenant_packages(config_path: str = "config/tenants.yaml") -> dict[str, list[str]]:
    """Real tenant->package lists, read from config, not hardcoded.
    Adding a tenant or a package here is what "runs on a schedule"
    actually has to notice on its very next run, with no code change.
    """
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
