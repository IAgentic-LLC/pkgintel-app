"""Chapter 15, integration tier: `PostgresAnswerCache` against the real
Postgres chapter 12 already runs (`compose.yaml`, port 5434), not a
fake standing in for it. A dedicated `itest-cost-cache` tenant id keeps
this test's own rows out of Acme's and Globex's real usage figures,
cleaned up in `finally` the same way chapter 13's own integration test
deletes the Qdrant collection it creates.
"""

import os

import psycopg
import pytest
from pkgintel_app.cost_cache import (
    PostgresAnswerCache,
    cache_key,
    ensure_tables,
)
from reliable_agents_labs.rag_agent import RagAnswer

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="No local Postgres configured, see compose.yaml"
)

_TENANT_ID = "itest-cost-cache"


async def test_a_cached_answer_round_trips_through_real_postgres():
    async with await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"]) as conn:
        await ensure_tables(conn)
        cache = PostgresAnswerCache(conn)
        question_hash = cache_key("does anything real ever get asked twice")
        try:
            assert await cache.get(_TENANT_ID, question_hash) is None

            answer = RagAnswer(answer="a real, stored answer", cited_packages=["httpx"])
            await cache.put(_TENANT_ID, question_hash, answer)

            cached = await cache.get(_TENANT_ID, question_hash)
            assert cached is not None
            assert cached.answer == "a real, stored answer"
            assert cached.cited_packages == ["httpx"]

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
