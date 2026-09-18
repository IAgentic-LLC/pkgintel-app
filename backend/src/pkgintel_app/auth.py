"""Chapter 14: chapter 6's own JWT verification, extended with one more
claim check. `sub` alone answers "who is this token for"; multi-tenant
retrieval needs "which tenant is this token allowed to see", and that
is exactly what Auth0 Organizations puts on a token when a user logs in
through one: `org_id`.

Machine-to-machine tokens never carry that claim at all, confirmed
against this book's own Auth0 tenant while building this chapter: the
client-access grant screen for an M2M application shows "Machine to
machine access cannot be scoped to an organization", with the checkbox
that would allow it disabled. Real tenant identity for this API can
only ever come from a real, logged-in user, not a service credential,
which is a stronger design anyway, Organizations models which person
belongs to which company, not which script is allowed to call an API.
"""

import os

import jwt
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


def _auth0_domain() -> str:
    return os.environ.get("AUTH0_DOMAIN", "")


def _auth0_audience() -> str:
    return os.environ.get("AUTH0_AUDIENCE", "")


def _org_tenant_map() -> dict[str, str]:
    """Real Auth0 organization IDs, not tenant names, are what actually
    lands in a token's `org_id` claim. This is the one place that name
    gets attached to a `tenant_id` this app's own code already knows
    about, `acme` and `globex` throughout chapters 11 through 13.
    """
    return {
        os.environ.get("AUTH0_ACME_ORG_ID", ""): "acme",
        os.environ.get("AUTH0_GLOBEX_ORG_ID", ""): "globex",
    }


_bearer_scheme = HTTPBearer()
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(f"https://{_auth0_domain()}/.well-known/jwks.json")
    return _jwks_client


class TenantPrincipal(BaseModel):
    subject: str
    tenant_id: str


class UnauthorizedError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail


async def verify_tenant_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> TenantPrincipal:
    """`_get_jwks_client` and `_org_tenant_map` are the seams a test
    overrides, same reasoning as chapter 6: a monkeypatched signing key
    and a fake org map instead of a real Auth0 tenant on every run.
    """
    token = credentials.credentials
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_auth0_audience(),
            issuer=f"https://{_auth0_domain()}/",
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(detail=str(exc)) from exc

    org_id = payload.get("org_id")
    tenant_id = _org_tenant_map().get(org_id) if org_id else None
    if tenant_id is None:
        raise UnauthorizedError(
            detail="Token carries no recognized organization. Machine-to-machine "
            "tokens cannot be scoped to a tenant; sign in as a real user instead."
        )
    return TenantPrincipal(subject=payload["sub"], tenant_id=tenant_id)


def register_auth_exception_handlers(app) -> None:
    @app.exception_handler(UnauthorizedError)
    async def handle_unauthorized(request: Request, exc: UnauthorizedError) -> JSONResponse:
        from pkgintel_app.api import ProblemDetail

        problem = ProblemDetail(
            type="https://pkgintel-app.dev/problems/unauthorized",
            title="Unauthorized",
            status=401,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=401,
            content=problem.model_dump(),
            media_type="application/problem+json",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        from pkgintel_app.api import ProblemDetail

        problem = ProblemDetail(
            type="https://pkgintel-app.dev/problems/unauthorized",
            title="Unauthorized",
            status=exc.status_code,
            detail=str(exc.detail),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=problem.model_dump(),
            media_type="application/problem+json",
        )
