"""Chapter 15, integration tier: `PostgresAnswerCache` against the real
Postgres chapter 12 already runs (`compose.yaml`, port 5434), not a
fake standing in for it. A dedicated `itest-cost-cache` tenant id keeps
this test's own rows out of Acme's and Globex's real usage figures,
cleaned up in `finally` the same way chapter 13's own integration test
deletes the Qdrant collection it creates.

Chapter 17: schema setup is `run_migrations` now, not the old
`ensure_tables`, real migrations applied against the same real
database, not a fixture pretending they already happened.
"""

import os
from pathlib import Path

import psycopg
import pytest
from pkgintel_app.cost_cache import PostgresAnswerCache, cache_key, purge_stale_entries
from pkgintel_app.migrations import run_migrations
from reliable_agents_labs.rag_agent import RagAnswer

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="No local Postgres configured, see compose.yaml"
)

_TENANT_ID = "itest-cost-cache"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


async def test_a_cached_answer_round_trips_through_real_postgres():
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"]) as conn:
        await run_migrations(conn, _MIGRATIONS_DIR)
        cache = PostgresAnswerCache(conn)
        question_hash = cache_key("does anything real ever get asked twice")
        try:
            assert await cache.get(_TENANT_ID, question_hash) is None

            answer = RagAnswer(answer="a real, stored answer", cited_packages=["httpx"])
            await cache.put(_TENANT_ID, question_hash, answer, model_id="gemini-3.6-flash")

            cached = await cache.get(_TENANT_ID, question_hash)
            assert cached is not None
            assert cached.answer == "a real, stored answer"
            assert cached.cited_packages == ["httpx"]
            assert cached.model_id == "gemini-3.6-flash"

            await cache.record_usage(_TENANT_ID, cost_usd=0.001234, cache_hit=False)
            await cache.record_usage(_TENANT_ID, cost_usd=0.0, cache_hit=True)

            usage = await cache.get_usage(_TENANT_ID)
            assert usage.call_count == 2
            assert usage.cache_hit_count == 1
            assert usage.total_cost_usd == pytest.approx(0.001234)
        finally:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM answer_cache WHERE tenant_id = %s", (_TENANT_ID,))
                await cur.execute("DELETE FROM tenant_usage WHERE tenant_id = %s", (_TENANT_ID,))
            await conn.commit()


async def test_purge_deletes_only_entries_older_than_the_ttl():
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"]) as conn:
        await run_migrations(conn, _MIGRATIONS_DIR)
        cache = PostgresAnswerCache(conn)
        fresh_hash = cache_key("a fresh question purge must not touch")
        stale_hash = cache_key("a stale question purge must delete")
        try:
            await cache.put(_TENANT_ID, fresh_hash, RagAnswer(answer="fresh", cited_packages=[]))
            await cache.put(_TENANT_ID, stale_hash, RagAnswer(answer="stale", cited_packages=[]))
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE answer_cache SET created_at = now() - interval '2 hours' "
                    "WHERE tenant_id = %s AND question_hash = %s",
                    (_TENANT_ID, stale_hash),
                )
            await conn.commit()

            await purge_stale_entries(conn, older_than_seconds=3600)

            assert await cache.get(_TENANT_ID, stale_hash) is None
            assert await cache.get(_TENANT_ID, fresh_hash) is not None
        finally:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM answer_cache WHERE tenant_id = %s", (_TENANT_ID,))
                await cur.execute("DELETE FROM tenant_usage WHERE tenant_id = %s", (_TENANT_ID,))
            await conn.commit()
