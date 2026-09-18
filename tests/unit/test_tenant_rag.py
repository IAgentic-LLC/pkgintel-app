"""Chapter 11, unit tier: no network, no Qdrant, no model call."""

from pkgintel_app.tenant_rag import tenant_collection_name


def test_each_tenant_gets_its_own_collection_name():
    assert tenant_collection_name("acme") == "packages_acme"
    assert tenant_collection_name("globex") == "packages_globex"


def test_different_tenants_never_collide():
    assert tenant_collection_name("acme") != tenant_collection_name("globex")
