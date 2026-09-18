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

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from reliable_agents_labs.graph_store import build_neo4j_driver, find_dependents
from reliable_agents_labs.models import EmbeddingClient, ModelClient

from pkgintel_app.auth import TenantPrincipal, register_auth_exception_handlers, verify_tenant_token
from pkgintel_app.tenant_rag import ask_rag_agent_for_tenant

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One real Neo4j driver for the app's whole lifetime, same reasoning
    # as reorder-app's Postgres pool: a driver per request would mean a
    # fresh connection negotiation on every single call.
    driver = build_neo4j_driver()
    app.state.neo4j_driver = driver
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


class DependentsResponse(BaseModel):
    target: str
    dependents: list[str]


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


@app.post("/v1/questions", response_model=AnswerResponse)
async def ask_question(
    payload: QuestionRequest,
    qdrant: AsyncQdrantClient | None = Depends(get_qdrant_client),
    embedder: EmbeddingClient | None = Depends(get_embedding_client),
    model_client: ModelClient | None = Depends(get_model_client),
    principal: TenantPrincipal = Depends(verify_tenant_token),
) -> AnswerResponse:
    try:
        rag_answer = await ask_rag_agent_for_tenant(
            principal.tenant_id,
            payload.question,
            qdrant=qdrant,
            embedder=embedder,
            model_client=model_client,
        )
    except Exception as exc:
        raise UpstreamError(detail=str(exc)) from exc
    return AnswerResponse(answer=rag_answer.answer, cited_packages=rag_answer.cited_packages)


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
