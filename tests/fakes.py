"""Shared test fakes. Copied from `reliable-agents-labs`' own tests/
fakes.py rather than imported, same reasoning as every product repo in
this series: test doubles live under `tests/` there and are not part
of the installed package.
"""

from pkgintel_app.cost_cache import UsageRecord
from reliable_agents_labs.models import ModelResult
from reliable_agents_labs.rag_agent import RagAnswer


class ScriptedModelClient:
    """A deterministic stand-in for any real ModelClient adapter. Feed it a
    list of canned ModelResults; each call to generate() returns the next
    one.
    """

    def __init__(self, scripted_results: list[ModelResult]) -> None:
        self._results = iter(scripted_results)

    async def generate(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
    ) -> ModelResult:
        return next(self._results)


class FakeEmbeddingClient:
    """Returns the same fixed vector regardless of input text. Chapter
    11's own tests need this precisely because it removes semantic
    similarity as a variable: if two tenants' identical vectors still
    never cross into each other's results, isolation comes from the
    collection boundary itself, not from the embedding happening not to
    match.
    """

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, text: str) -> list[float]:
        return self._vector


class InMemoryAnswerCache:
    """Chapter 15's own seam: a plain dict standing in for
    `PostgresAnswerCache`, same reasoning as `AsyncQdrantClient(location=
    ":memory:")` for chapter 11, proving the caching and cost-accounting
    *logic* without a real Postgres connection anywhere in the test run.
    """

    def __init__(self) -> None:
        self._answers: dict[tuple[str, str], RagAnswer] = {}
        self._usage: dict[str, UsageRecord] = {}

    async def get(self, tenant_id: str, question_hash: str) -> RagAnswer | None:
        return self._answers.get((tenant_id, question_hash))

    async def put(self, tenant_id: str, question_hash: str, answer: RagAnswer) -> None:
        self._answers[(tenant_id, question_hash)] = answer

    async def record_usage(self, tenant_id: str, cost_usd: float, cache_hit: bool) -> None:
        existing = self._usage.get(tenant_id) or UsageRecord(
            tenant_id=tenant_id, total_cost_usd=0.0, call_count=0, cache_hit_count=0
        )
        self._usage[tenant_id] = UsageRecord(
            tenant_id=tenant_id,
            total_cost_usd=existing.total_cost_usd + cost_usd,
            call_count=existing.call_count + 1,
            cache_hit_count=existing.cache_hit_count + (1 if cache_hit else 0),
        )

    async def get_usage(self, tenant_id: str) -> UsageRecord:
        return self._usage.get(tenant_id) or UsageRecord(
            tenant_id=tenant_id, total_cost_usd=0.0, call_count=0, cache_hit_count=0
        )
