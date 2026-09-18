"""Chapter 14: a real API in front of chapters 11 and 13's own logic,
unchanged. `ask_rag_agent_for_tenant` already refuses to look outside a
caller's own collection; this module's only real job is making sure the
`tenant_id` it's handed came from a verified organization claim, never
from a request body a caller could set to anyone else's tenant.

The dependency graph query (`find_dependents`) is deliberately not
tenant-scoped, same reasoning as chapter 13: "numpy depends on X" is a
fact about numpy, not about who's asking, so every authenticated tenant
can ask it, over the one shared graph.
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg

if sys.platform == "win32":
    # Chapter 15's own real finding: this app never touched psycopg
    # directly from the API process before now (chapter 12's cron job
    # runs it from a separate SAQ worker process). The same real
    # incompatibility reorder-app's own chapters 7 and 9 already found,
    # confirmed live again here: psycopg's async mode refuses to run
    # under Windows' default ProactorEventLoop. Has to run before
    # uvicorn builds its own event loop, so it lives here, at module
    # import time.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from reliable_agents_labs.cost import estimate_cost
from reliable_agents_labs.graph_store import build_neo4j_driver, find_dependents
from reliable_agents_labs.models import EmbeddingClient, ModelClient, ModelResult

from pkgintel_app.auth import TenantPrincipal, register_auth_exception_handlers, verify_tenant_token
from pkgintel_app.cost_cache import AnswerCache, PostgresAnswerCache, cache_key
from pkgintel_app.observability import ask_rag_agent_for_tenant_traced

load_dotenv()


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One real Neo4j driver for the app's whole lifetime, same reasoning
    # as reorder-app's Postgres pool: a driver per request would mean a
    # fresh connection negotiation on every single call.
    driver = build_neo4j_driver()
    app.state.neo4j_driver = driver

    # Chapter 17: schema is no longer created here. Migrations are
    # their own explicit deploy step (`scripts/migrate.py`), run once,
    # before this app starts taking traffic, not implicitly, by
    # whichever one of potentially several replicas happens to boot
    # first and race the others to run the identical DDL.
    try:
        yield
    finally:
        await driver.close()


app = FastAPI(title="pkgintel-app", lifespan=lifespan)
register_auth_exception_handlers(app)

# Chapter 14's own frontend runs on a different Vite dev port (5174)
# than reorder-app's (5173), both products' frontends can run at once
# against this Auth0 tenant without colliding.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5174")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    answer: str
    cited_packages: list[str]
    cached: bool = False
    cost_usd: float = 0.0
    model_id: str | None = None


class DependentsResponse(BaseModel):
    target: str
    dependents: list[str]


class UsageResponse(BaseModel):
    tenant_id: str
    total_cost_usd: float
    call_count: int
    cache_hit_count: int


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str


class UpstreamError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


@app.exception_handler(UpstreamError)
async def handle_upstream_error(request: Request, exc: UpstreamError) -> JSONResponse:
    problem = ProblemDetail(
        type="https://pkgintel-app.dev/problems/upstream-error",
        title="Upstream error",
        status=502,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=502,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


async def get_qdrant_client() -> AsyncQdrantClient | None:
    """`None` means "let `ask_rag_agent_for_tenant` build its own real
    client". A test overrides this with an in-memory Qdrant instead,
    same seam chapter 11's own tests already established.
    """
    return None


async def get_embedding_client() -> EmbeddingClient | None:
    return None


async def get_model_client() -> ModelClient | None:
    return None


async def get_answer_cache() -> AsyncIterator[AnswerCache]:
    """The real Postgres implementation, opened and closed once per
    request, same lifetime as chapter 9's own per-job connection. A test
    overrides this with an in-memory dict-backed double instead, no real
    Postgres, proving the caching and cost-accounting logic on its own.
    """
    async with await psycopg.AsyncConnection.connect(_database_url()) as conn:
        yield PostgresAnswerCache(conn)


@app.post("/v1/questions", response_model=AnswerResponse)
async def ask_question(
    payload: QuestionRequest,
    qdrant: AsyncQdrantClient | None = Depends(get_qdrant_client),
    embedder: EmbeddingClient | None = Depends(get_embedding_client),
    model_client: ModelClient | None = Depends(get_model_client),
    cache: AnswerCache = Depends(get_answer_cache),
    principal: TenantPrincipal = Depends(verify_tenant_token),
) -> AnswerResponse:
    question_hash = cache_key(payload.question)

    cached_answer = await cache.get(principal.tenant_id, question_hash)
    if cached_answer is not None:
        await cache.record_usage(principal.tenant_id, cost_usd=0.0, cache_hit=True)
        return AnswerResponse(
            answer=cached_answer.answer,
            cited_packages=cached_answer.cited_packages,
            cached=True,
            cost_usd=0.0,
            model_id=cached_answer.model_id,
        )

    result_holder: dict[str, ModelResult] = {}

    def _capture_result(result: ModelResult) -> None:
        result_holder["result"] = result

    try:
        rag_answer = await ask_rag_agent_for_tenant_traced(
            principal.tenant_id,
            payload.question,
            qdrant=qdrant,
            embedder=embedder,
            model_client=model_client,
            on_model_result=_capture_result,
        )
    except Exception as exc:
        raise UpstreamError(detail=str(exc)) from exc

    model_result = result_holder.get("result")
    cost_usd = estimate_cost(model_result) if model_result else 0.0
    model_id = model_result.model_id if model_result else None
    await cache.put(principal.tenant_id, question_hash, rag_answer, model_id=model_id)
    await cache.record_usage(principal.tenant_id, cost_usd=cost_usd, cache_hit=False)
    return AnswerResponse(
        answer=rag_answer.answer,
        cited_packages=rag_answer.cited_packages,
        cached=False,
        cost_usd=cost_usd,
        model_id=model_id,
    )


@app.get("/v1/packages/{name}/dependents", response_model=DependentsResponse)
async def get_dependents(
    name: str,
    request: Request,
    principal: TenantPrincipal = Depends(verify_tenant_token),
) -> DependentsResponse:
    try:
        dependents = await find_dependents(request.app.state.neo4j_driver, name)
    except Exception as exc:
        raise UpstreamError(detail=str(exc)) from exc
    return DependentsResponse(target=name, dependents=dependents)


@app.get("/v1/usage", response_model=UsageResponse)
async def get_usage(
    cache: AnswerCache = Depends(get_answer_cache),
    principal: TenantPrincipal = Depends(verify_tenant_token),
) -> UsageResponse:
    record = await cache.get_usage(principal.tenant_id)
    return UsageResponse(**record.model_dump())
