"""F7 structured observability: request ids, JSON access logs, health/ready/metrics.

Single access-log line per request is emitted by :class:`ObservabilityMiddleware`
(a ``request`` INFO record on ``raguard_api.access``); the record carries only
``method``/``path`` (no query string)/``status``/``duration_ms`` plus the
propagated request id. Auth headers, cookies, tokens, and bodies are never
attached to records — the formatter below only renders an allowlisted field
set, so there is no channel for secrets to leak through logs.

Uvicorn decision (deliberate, documented here so it is not "fixed" later):
this module never touches the ``uvicorn``/``uvicorn.access`` loggers. Uvicorn
keeps its own access log for process-level concerns; operators wanting a
single access stream run uvicorn with ``--no-access-log`` and rely on ours.
Mutating uvicorn loggers at import would also make test imports side-effect
ful, which the ``create_app`` factory style explicitly avoids.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128

READY_TIMEOUT_SECONDS = 2.0

HISTOGRAM_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "raguard_request_id", default=None
)

access_logger = logging.getLogger("raguard_api.access")
logger = logging.getLogger(__name__)


def get_request_id() -> str | None:
    """Request id for the current task, if inside a request."""
    return request_id_ctx.get()


def _coerce_request_id(raw: str | None) -> str:
    candidate = (raw or "").strip()
    if candidate and len(candidate) <= MAX_REQUEST_ID_LENGTH:
        return candidate
    return uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    """One JSON object per line with a fixed, secret-free field set.

    ``request_id`` falls back to the request contextvar so log calls that do
    not pass an explicit ``extra`` still correlate; ``method``/``path``/
    ``status``/``duration_ms`` come from the access record ``extra`` and are
    ``None`` for non-request logs. Only these keys are ever rendered.
    """

    FIELDS = (
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_ctx.get(),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status", None),
            "duration_ms": getattr(record, "duration_ms", None),
        }
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(*, json_format: bool = True) -> None:
    """Point the API root logger (``raguard_api``) at the F7 formatter.

    Idempotent: previous handlers installed by this function are replaced, so
    repeated ``create_app`` calls (tests, reload) never duplicate lines. The
    stdlib root and uvicorn loggers are left untouched by design (see module
    docstring); only the level of the ``raguard_api`` logger is ensured.
    """
    api_logger = logging.getLogger("raguard_api")
    for handler in list(api_logger.handlers):
        if getattr(handler, "_raguard_observability", False):
            api_logger.removeHandler(handler)
    if json_format:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler._raguard_observability = True  # type: ignore[attr-defined]
    api_logger.addHandler(handler)
    if api_logger.level == logging.NOTSET:
        api_logger.setLevel(logging.INFO)


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsRegistry:
    """Minimal in-process Prometheus registry (no new dependencies).

    Series use the FastAPI route template (``/api/documents/{id}``) as the
    ``path_template`` label — never the raw path — so high-cardinality ids
    cannot explode series count. Unmatched paths (404s) use ``"unknown"``.
    """

    def __init__(self) -> None:
        self._requests: dict[tuple[str, str, str], int] = {}
        self._durations: dict[tuple[str, str], list[float]] = {}
        self._ready = 1
        self._rate_limited = 0

    def observe_request(
        self, *, method: str, path_template: str, status: int, duration_seconds: float
    ) -> None:
        key = (method, path_template, str(status))
        self._requests[key] = self._requests.get(key, 0) + 1
        series = self._durations.setdefault((method, path_template), [])
        series.append(max(0.0, float(duration_seconds)))

    def set_ready(self, ready: bool) -> None:
        self._ready = 1 if ready else 0

    def inc_rate_limited(self) -> None:
        """Count an F4 rejection (called by the rate-limit middleware)."""
        self._rate_limited += 1

    def reset(self) -> None:
        self._requests.clear()
        self._durations.clear()
        self._ready = 1
        self._rate_limited = 0

    def render(self) -> str:
        lines = [
            "# HELP raguard_http_requests_total Total HTTP requests.",
            "# TYPE raguard_http_requests_total counter",
        ]
        for method, template, status in sorted(self._requests):
            count = self._requests[(method, template, status)]
            lines.append(
                f'raguard_http_requests_total{{method="{_escape_label(method)}",'
                f'path_template="{_escape_label(template)}",status="{_escape_label(status)}"}}'
                f" {count}"
            )
        lines += [
            "# HELP raguard_http_request_duration_seconds HTTP request duration in seconds.",
            "# TYPE raguard_http_request_duration_seconds histogram",
        ]
        for method, template in sorted(self._durations):
            observations = self._durations[(method, template)]
            labels = f'method="{_escape_label(method)}",path_template="{_escape_label(template)}"'
            for bucket in HISTOGRAM_BUCKETS:
                cumulative = sum(1 for value in observations if value <= bucket)
                lines.append(
                    f"raguard_http_request_duration_seconds_bucket{{{labels},"
                    f'le="{bucket}"}} {cumulative}'
                )
            lines.append(
                f'raguard_http_request_duration_seconds_bucket{{{labels},le="+Inf"}}'
                f" {len(observations)}"
            )
            lines.append(
                f"raguard_http_request_duration_seconds_sum{{{labels}}} {float(sum(observations))}"
            )
            lines.append(
                f"raguard_http_request_duration_seconds_count{{{labels}}} {len(observations)}"
            )
        lines += [
            "# HELP raguard_ready Readiness gauge (1 ready, 0 degraded).",
            "# TYPE raguard_ready gauge",
            f"raguard_ready {self._ready}",
            "# HELP raguard_http_rate_limited_total Total requests rejected by rate limiting.",
            "# TYPE raguard_http_rate_limited_total counter",
            f"raguard_http_rate_limited_total {self._rate_limited}",
        ]
        return "\n".join(lines) + "\n"


_default_registry = MetricsRegistry()


def get_default_registry() -> MetricsRegistry:
    """Process-wide registry shared by the middleware and /metrics."""
    return _default_registry


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Request-id + access log + metrics in one pass (outermost middleware).

    Must be added after the rate-limit middleware so denials (which never
    reach ``call_next`` of inner layers) are still observed, logged, and
    stamped with the request id on their way out.
    """

    def __init__(self, app: Any, *, registry: MetricsRegistry | None = None) -> None:
        super().__init__(app)
        self._registry = registry or get_default_registry()

    async def dispatch(self, request: Request, call_next):
        request_id = _coerce_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            duration_seconds = time.perf_counter() - start
            route = request.scope.get("route")
            template = getattr(route, "path", None) or "unknown"
            self._registry.observe_request(
                method=request.method,
                path_template=template,
                status=status,
                duration_seconds=duration_seconds,
            )
            # url.path never includes the query string; duration with ms precision.
            access_logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
            )
            request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


async def _default_db_check(session_factory: Any) -> None:
    from sqlalchemy import text

    async with session_factory() as session:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=READY_TIMEOUT_SECONDS)


async def _default_redis_check(redis_url: str) -> None:
    import redis.asyncio as redis_async

    client = redis_async.from_url(redis_url)
    try:
        await asyncio.wait_for(client.ping(), timeout=READY_TIMEOUT_SECONDS)
    finally:
        aclose = getattr(client, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 - close path must not fail readiness
                pass


CheckFn = Callable[[], Awaitable[None]]


def create_observability_router(
    *,
    session_factory: Any = None,
    redis_url: str = "",
    checks: dict[str, CheckFn] | None = None,
    registry: MetricsRegistry | None = None,
) -> APIRouter:
    """Liveness, readiness, and Prometheus exposition (no rate limiting).

    ``checks`` overrides ``{"db": ..., "redis": ...}`` with test doubles; each
    check raises on failure. Responses never carry internal detail — labels
    are ``ok``/``error`` only.
    """
    active_registry = registry or get_default_registry()
    if checks is not None:
        db_check = checks.get("db")
        redis_check = checks.get("redis")
    else:
        db_check = None
        redis_check = None
    if db_check is None:
        if session_factory is None:
            raise ValueError("session_factory or checks['db'] is required")

        async def db_check() -> None:
            await _default_db_check(session_factory)

    if redis_check is None:

        async def redis_check() -> None:
            await _default_redis_check(redis_url)

    router = APIRouter()

    @router.get("/health")
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    async def _ready() -> Response:
        results = await asyncio.gather(
            _run_check("postgres", db_check),
            _run_check("redis", redis_check),
            return_exceptions=False,
        )
        checks_out = {name: state for name, state in results}
        ready = all(state == "ok" for _, state in results)
        active_registry.set_ready(ready)
        if ready:
            return Response(
                content=json.dumps({"status": "ok", "checks": checks_out}, separators=(",", ":")),
                media_type="application/json",
            )
        return Response(
            content=json.dumps({"status": "degraded", "checks": checks_out}, separators=(",", ":")),
            status_code=503,
            media_type="application/json",
        )

    @router.get("/metrics")
    async def _metrics() -> Response:
        return Response(
            content=active_registry.render(),
            media_type="text/plain; version=0.0.4",
        )

    return router


async def _run_check(name: str, check: CheckFn) -> tuple[str, str]:
    try:
        await check()
    except Exception:  # noqa: BLE001 - readiness maps every failure to "error"
        logger.warning("readiness check failed: %s", name)
        return (name, "error")
    return (name, "ok")
