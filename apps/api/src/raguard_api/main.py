"""FastAPI app factory wiring the auth, org, documents, retrieval, and chat routers (task 4.4).

Builds the application from a settings object and a session factory: standard
error handlers plus the auth (login), org administration, documents
ingestion, retrieval search, and grounded chat routers. The documents router
receives real adapters (boto3 S3 and Arq/Redis) constructed from settings,
the retrieval router receives a lazily-connecting provider embedder, and the
chat router a lazy provider-selected completer (OpenAI default, Ollama opt-in);
connections are lazy, so factory tests stay offline. F4 rate limiting guards
every ``/api/`` route (health/metrics and non-API paths excluded) per
tenant+user — or client IP without a verified identity — degrading to an
in-process bound when Redis is unreachable.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from raguard_api.auth.jwt import InvalidToken, decode_access_token
from raguard_api.auth.router import create_auth_router
from raguard_api.chat.providers import create_completer
from raguard_api.chat.router import create_chat_router, create_conversations_router
from raguard_api.config import Settings, get_settings
from raguard_api.db import create_engine, create_session_factory, get_database_url
from raguard_api.documents.queue import ArqJobQueue
from raguard_api.documents.router import create_documents_router
from raguard_api.documents.storage import S3ObjectStore, create_s3_client
from raguard_api.errors import RateLimitError, register_error_handlers
from raguard_api.org.router import create_org_router
from raguard_api.ratelimit import RateLimiter, build_rate_limiter
from raguard_api.retrieval.embeddings import create_embedder
from raguard_api.retrieval.router import create_retrieval_router

_EXCLUDED_PATHS = frozenset({"/health", "/metrics"})


def _resolve_identity(request: Request, settings: Settings) -> tuple[str, str]:
    """(tenant, subject) from the verified JWT or, without one, the client IP.

    The token is read from the session cookie first, then the Authorization
    Bearer header; an invalid token falls back to IP instead of failing, so
    unauthenticated abuse still shares one bounded bucket. X-Forwarded-For is
    honored only when ``trust_proxy_headers`` is explicitly enabled —
    otherwise the direct peer address is used, never client-controlled input.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if token is None:
        authorization = request.headers.get("authorization", "")
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            token = credentials.strip()
    if token is not None:
        try:
            claims = decode_access_token(token, settings)
            return str(claims.tid), f"user:{claims.sub}"
        except InvalidToken:
            pass
    ip = request.client.host if request.client is not None else "unknown"
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip() if forwarded else ""
        if first:
            ip = first
    return "anonymous", f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """F4 enforcement: bounded requests per window on ``/api/`` routes only.

    The limiter is read from ``app.state`` per request so tests can inject a
    double after factory composition; ``limiter_override`` covers bare-app
    wiring without state setup.
    """

    def __init__(
        self, app: Any, *, settings: Settings, limiter_override: RateLimiter | None = None
    ) -> None:
        super().__init__(app)
        self._settings = settings
        self._limiter_override = limiter_override

    async def dispatch(self, request: Request, call_next):
        settings = self._settings
        path = request.url.path
        if not settings.rate_limit_enabled:
            return await call_next(request)
        if not path.startswith("/api/") or path in _EXCLUDED_PATHS:
            return await call_next(request)
        limiter: RateLimiter | None = self._limiter_override or getattr(
            request.app.state, "rate_limiter", None
        )
        if limiter is None:  # miswired app: fail open is forbidden, fail safe
            exc = RateLimitError()
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": exc.code, "message": exc.message}},
                headers={"Retry-After": str(exc.retry_after_seconds)},
            )
        tenant, subject = _resolve_identity(request, settings)
        decision = await limiter.check(tenant=tenant, subject=subject)
        if not decision.allowed:
            exc = RateLimitError(retry_after_seconds=decision.retry_after_seconds)
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": exc.code, "message": exc.message}},
                headers={"Retry-After": str(exc.retry_after_seconds)},
            )
        return await call_next(request)


def attach_rate_limiting(
    app: FastAPI, settings: Settings, *, limiter: RateLimiter | None = None
) -> RateLimiter:
    """Mount the F4 middleware; returns the active limiter for overrides."""
    active = limiter if limiter is not None else build_rate_limiter(settings)
    app.state.rate_limiter = active
    app.add_middleware(RateLimitMiddleware, settings=settings, limiter_override=active)
    return active


def create_app(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the raguard API application with the standard error envelope."""
    app = FastAPI(title="raguard API", version="0.1.0")
    register_error_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    attach_rate_limiting(app, settings, limiter=limiter)
    app.include_router(create_auth_router(settings=settings, session_factory=session_factory))
    app.include_router(create_org_router(session_factory=session_factory))
    store = S3ObjectStore(create_s3_client(settings), bucket=settings.object_store_bucket)
    queue = ArqJobQueue(
        redis_url=settings.job_queue_redis_url,
        function_name=settings.job_queue_function_name,
    )
    app.include_router(
        create_documents_router(
            session_factory=session_factory, settings=settings, store=store, queue=queue
        )
    )
    embedder = create_embedder(settings=settings)
    app.include_router(
        create_retrieval_router(
            session_factory=session_factory, settings=settings, embedder=embedder
        )
    )
    completer = create_completer(settings=settings)
    app.include_router(
        create_chat_router(
            session_factory=session_factory,
            settings=settings,
            embedder=embedder,
            completer=completer,
        )
    )
    app.include_router(create_conversations_router(session_factory=session_factory))
    return app


def create_default_app() -> FastAPI:
    """Compose/uvicorn entrypoint: build the app from the process environment.

    Reads ``Settings`` from the environment (``JWT_SECRET`` and friends) and
    ``DATABASE_URL`` for the async engine, then delegates to :func:`create_app`.
    Served as ``uvicorn --factory raguard_api.main:create_default_app`` (see
    ``apps/api/Dockerfile``). A factory — rather than a module-level ``app`` —
    keeps the import side-effect free, so tests keep composing the app via
    ``create_app`` with explicit settings and a missing/invalid environment
    fails fast only when the server actually starts.
    """
    settings = Settings()
    engine = create_engine(get_database_url())
    return create_app(settings=settings, session_factory=create_session_factory(engine))
