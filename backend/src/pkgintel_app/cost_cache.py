"""Chapter 15: two real problems a two-tenant demo never surfaces but a
product at scale can't avoid. First, the same question gets asked more
than once, an identical model call for an identical answer is a real
cost paid for nothing new. Second, that cost is invisible unless
something adds it up. Chapter 9's own idempotency ledger is the model
for both: the same Postgres this app already runs (chapter 12), no new
datastore introduced just to back either one.

Caching is exact-match, not semantic: the question text, trimmed and
case-folded, is the whole key. Two different phrasings of the same
question still miss the cache, a real and disclosed limitation, not a
gap this chapter pretends isn't there, semantic caching is a real
technique but adds a similarity threshold to tune, out of scope for a
two-tenant demonstration.

Cost is tracked for generation only, via `reliable_agents_labs.cost`'s
`estimate_cost`, reused unchanged. Embedding calls have a real dollar
cost too, but `EmbeddingClient.embed()` returns a bare vector, no
token usage at all, so there is nothing here to measure it with. The
dollar figures below are real, just not the whole bill.

Chapter 17: the table and column shapes below are no longer defined
here at all. `migrations/` is the one real source of truth for this
app's schema now; this module only ever reads and writes rows within
whatever shape the applied migrations have actually left behind.
"""

import hashlib
from typing import Protocol

import psycopg
from pydantic import BaseModel
from reliable_agents_labs.rag_agent import RagAnswer

# Shorter than chapter 12's own 6-hour ingestion cadence, on purpose: a
# cached answer can never outlive more than one ingestion cycle's worth
# of drift between what this app once said and what the graph now holds.
CACHE_TTL_SECONDS = 3600


def cache_key(question: str) -> str:
    normalized = question.strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CachedAnswer(BaseModel):
    answer: str
    cited_packages: list[str]
    model_id: str | None = None


async def get_cached_answer(
    conn: psycopg.AsyncConnection, tenant_id: str, question_hash: str
) -> CachedAnswer | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT answer, cited_packages, model_id FROM answer_cache "
            "WHERE tenant_id = %s AND question_hash = %s "
            "AND created_at > now() - make_interval(secs => %s)",
            (tenant_id, question_hash, CACHE_TTL_SECONDS),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return CachedAnswer(answer=row[0], cited_packages=row[1], model_id=row[2])


async def store_answer(
    conn: psycopg.AsyncConnection,
    tenant_id: str,
    question_hash: str,
    answer: RagAnswer,
    model_id: str | None = None,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO answer_cache (tenant_id, question_hash, answer, cited_packages, model_id) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, question_hash) "
            "DO UPDATE SET answer = EXCLUDED.answer, "
            "cited_packages = EXCLUDED.cited_packages, model_id = EXCLUDED.model_id, "
            "created_at = now()",
            (tenant_id, question_hash, answer.answer, answer.cited_packages, model_id),
        )
    await conn.commit()


async def purge_stale_entries(
    conn: psycopg.AsyncConnection, older_than_seconds: int = CACHE_TTL_SECONDS
) -> int:
    """Chapter 17's own real reason `idx_answer_cache_created_at` exists:
    a cache that only ever grows is not actually a cache, it's a leak.
    This is the query the new index is for, real `EXPLAIN` output
    proving it (chapter 17's own migration 0003) rather than assumed.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM answer_cache WHERE created_at < now() - make_interval(secs => %s)",
            (older_than_seconds,),
        )
        deleted = cur.rowcount
    await conn.commit()
    return deleted


async def record_usage(
    conn: psycopg.AsyncConnection, tenant_id: str, cost_usd: float, cache_hit: bool
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO tenant_usage (tenant_id, total_cost_usd, call_count, cache_hit_count) "
            "VALUES (%s, %s, 1, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "total_cost_usd = tenant_usage.total_cost_usd + EXCLUDED.total_cost_usd, "
            "call_count = tenant_usage.call_count + 1, "
            "cache_hit_count = tenant_usage.cache_hit_count + EXCLUDED.cache_hit_count",
            (tenant_id, cost_usd, 1 if cache_hit else 0),
        )
    await conn.commit()


class UsageRecord(BaseModel):
    tenant_id: str
    total_cost_usd: float
    call_count: int
    cache_hit_count: int


async def get_usage(conn: psycopg.AsyncConnection, tenant_id: str) -> UsageRecord:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT total_cost_usd, call_count, cache_hit_count "
            "FROM tenant_usage WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return UsageRecord(tenant_id=tenant_id, total_cost_usd=0.0, call_count=0, cache_hit_count=0)
    return UsageRecord(
        tenant_id=tenant_id, total_cost_usd=row[0], call_count=row[1], cache_hit_count=row[2]
    )


class AnswerCache(Protocol):
    """The real seam this chapter's tests depend on, same reasoning as
    chapter 5's `ModelClient`: a swappable interface, not a hardcoded
    `psycopg.AsyncConnection` inside `api.py` itself. A test overrides
    this with an in-memory dict instead of a real Postgres connection,
    no server, no docker, for the caching and cost-accounting *logic*;
    `PostgresAnswerCache` below is what actually backs it in production,
    proven against a real database at integration tier.
    """

    async def get(self, tenant_id: str, question_hash: str) -> CachedAnswer | None: ...
    async def put(
        self, tenant_id: str, question_hash: str, answer: RagAnswer, model_id: str | None = None
    ) -> None: ...
    async def record_usage(self, tenant_id: str, cost_usd: float, cache_hit: bool) -> None: ...
    async def get_usage(self, tenant_id: str) -> UsageRecord: ...


class PostgresAnswerCache:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self._conn = conn

    async def get(self, tenant_id: str, question_hash: str) -> CachedAnswer | None:
        return await get_cached_answer(self._conn, tenant_id, question_hash)

    async def put(
        self, tenant_id: str, question_hash: str, answer: RagAnswer, model_id: str | None = None
    ) -> None:
        await store_answer(self._conn, tenant_id, question_hash, answer, model_id=model_id)

    async def record_usage(self, tenant_id: str, cost_usd: float, cache_hit: bool) -> None:
        await record_usage(self._conn, tenant_id, cost_usd, cache_hit)

    async def get_usage(self, tenant_id: str) -> UsageRecord:
        return await get_usage(self._conn, tenant_id)
