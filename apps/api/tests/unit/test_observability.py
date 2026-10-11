"""Unit tests for F7 observability (test-first).

Covers the in-process Prometheus registry, request-id propagation, the JSON
access formatter (fixed fields, no secrets), and the /health-/ready-/metrics
surface wired without real PostgreSQL/Redis (faked checks).
"""

import json
import logging
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.config import Settings
from raguard_api.main import _EXCLUDED_PATHS
from raguard_api.ratelimit import RateLimitDecision

JWT_SECRET = "test-secret-0123456789abcdef1234"


def _settings(**overrides) -> Settings:
    base = {"jwt_secret": JWT_SECRET}
    base.update(overrides)
    return Settings(**base)


def _fake_session_factory() -> Any:
    """Offline stand-in: routers only keep it for request-time use."""
    return MagicMock()


class DenyAll:
    async def check(self, *, tenant: str, subject: str) -> RateLimitDecision:
        return RateLimitDecision(allowed=False, retry_after_seconds=1, limit=60, remaining=0)


def test_excluded_paths_cover_observability() -> None:
    assert {"/health", "/ready", "/metrics"} <= set(_EXCLUDED_PATHS)


def test_registry_renders_valid_prometheus_exposition() -> None:
    from raguard_api.observability import MetricsRegistry

    registry = MetricsRegistry()
    registry.observe_request(
        method="GET", path_template="/api/documents/{id}", status=200, duration_seconds=0.06
    )
    registry.observe_request(
        method="GET", path_template="/api/documents/{id}", status=200, duration_seconds=2.0
    )
    registry.set_ready(True)
    body = registry.render()
    assert "# HELP raguard_http_requests_total" in body
    assert "# TYPE raguard_http_requests_total counter" in body
    assert (
        'raguard_http_requests_total{method="GET",'
        'path_template="/api/documents/{id}",status="200"} 2' in body
    )
    assert "# TYPE raguard_http_request_duration_seconds histogram" in body
    assert "raguard_http_request_duration_seconds_bucket{method=" in body
    assert 'le="+Inf"} 2' in body
    assert "raguard_http_request_duration_seconds_count{method=" in body
    assert "raguard_http_request_duration_seconds_sum{method=" in body
    assert "# TYPE raguard_ready gauge" in body
    assert "raguard_ready 1" in body
    # Buckets are cumulative: the small bucket holds 1, +Inf holds 2.
    small = next(
        line
        for line in body.splitlines()
        if "duration_seconds_bucket" in line and 'le="0.1"' in line
    )
    assert small.rsplit(" ", 1)[-1] == "1"


def test_registry_ready_gauge_zero_when_not_ready() -> None:
    from raguard_api.observability import MetricsRegistry

    registry = MetricsRegistry()
    registry.set_ready(False)
    assert "\nraguard_ready 0" in registry.render()


def test_json_formatter_has_expected_fields_and_no_secrets() -> None:
    from raguard_api.observability import JsonFormatter, request_id_ctx

    token = request_id_ctx.set("req-123")
    try:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="raguard_api.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request",
            args=(),
            exc_info=None,
        )
        record.method = "GET"  # type: ignore[attr-defined]
        record.path = "/api/documents"  # type: ignore[attr-defined]
        record.status = 200  # type: ignore[attr-defined]
        record.duration_ms = 12.5  # type: ignore[attr-defined]
        payload = json.loads(formatter.format(record))
    finally:
        request_id_ctx.reset(token)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "raguard_api.access"
    assert payload["message"] == "request"
    assert payload["request_id"] == "req-123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/documents"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 12.5
    assert "timestamp" in payload
    assert set(payload) == {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
    }


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_request_id_propagated_when_sent() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()
    app = create_app(settings=_settings(), session_factory=_fake_session_factory())
    async with _client(app) as client:
        response = await client.get("/health", headers={"X-Request-ID": "caller-id-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "caller-id-1"


async def test_request_id_generated_when_missing() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()
    app = create_app(settings=_settings(), session_factory=_fake_session_factory())
    async with _client(app) as client:
        first = await client.get("/health")
        second = await client.get("/health")
    assert first.headers["X-Request-ID"]
    assert second.headers["X-Request-ID"]
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_health_is_liveness_without_dependencies() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()
    app = create_app(settings=_settings(), session_factory=_fake_session_factory())
    async with _client(app) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_200_when_all_checks_pass() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()

    async def _ok() -> None:
        return None

    app = create_app(
        settings=_settings(),
        session_factory=_fake_session_factory(),
        observability_checks={"db": _ok, "redis": _ok},
    )
    async with _client(app) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


async def test_ready_503_without_internal_detail_when_dependency_fails() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()

    async def _ok() -> None:
        return None

    async def _boom() -> None:
        raise ConnectionError("pg host db.internal:5432 refused (super secret)")

    app = create_app(
        settings=_settings(),
        session_factory=_fake_session_factory(),
        observability_checks={"db": _boom, "redis": _ok},
    )
    async with _client(app) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"postgres": "error", "redis": "ok"}
    assert "db.internal" not in response.text
    assert "secret" not in response.text.lower()


async def test_metrics_endpoint_exposes_prometheus_format() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()
    app = create_app(settings=_settings(), session_factory=_fake_session_factory())
    async with _client(app) as client:
        await client.get("/health")
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "raguard_http_requests_total" in response.text


async def test_metrics_use_route_template_not_raw_path() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()
    app = create_app(settings=_settings(), session_factory=_fake_session_factory())

    @app.get("/api/widgets/{widget_id}")
    async def _doc(widget_id: str):
        return {"id": widget_id}

    async with _client(app) as client:
        first = await client.get("/api/widgets/11111111-1111-1111-1111-111111111111")
        assert first.status_code == 200
        response = await client.get("/metrics")
    assert 'path_template="/api/widgets/{widget_id}"' in response.text
    assert "11111111-1111-1111-1111-111111111111" not in response.text


async def test_observability_paths_bypass_rate_limiting() -> None:
    from raguard_api.main import create_app
    from raguard_api.observability import get_default_registry

    get_default_registry().reset()
    app = create_app(
        settings=_settings(),
        session_factory=_fake_session_factory(),
        limiter=DenyAll(),
    )
    async with _client(app) as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/ready")).status_code in (200, 503)
        assert (await client.get("/metrics")).status_code == 200


async def test_arbitrary_method_normalizes_to_other_without_new_series() -> None:
    """Unbounded methods must not explode Prometheus cardinality.

    ``/health``/``/ready``/``/metrics`` bypass the rate limiter, so any
    client can send arbitrary method tokens; only the fixed allowlist may
    appear as a label, everything else collapses to ``OTHER``.
    """
    from raguard_api.observability import ALLOWED_METHODS, MetricsRegistry

    registry = MetricsRegistry()
    registry.observe_request(
        method="FROBNICATE", path_template="unknown", status=200, duration_seconds=0.01
    )
    registry.observe_request(
        method="WHATEVER", path_template="unknown", status=200, duration_seconds=0.01
    )
    body = registry.render()
    assert 'method="OTHER"' in body
    assert "FROBNICATE" not in body
    assert "WHATEVER" not in body
    # Both requests share one series — no per-value growth.
    assert len(registry._requests) == 1
    assert len(registry._durations) == 1
    assert set(ALLOWED_METHODS) == {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    }


async def test_metrics_memory_is_bounded_across_many_requests() -> None:
    """Regression (audit finding): raw samples must never accumulate.

    The pre-fix registry appended every duration to a list that was never
    pruned, so a long-running process grew without bound. The histogram now
    keeps fixed buckets, so storage is O(series) regardless of request count.
    """
    from raguard_api.observability import HISTOGRAM_BUCKETS, MetricsRegistry

    registry = MetricsRegistry()
    for index in range(10_000):
        registry.observe_request(
            method="GET",
            path_template="/api/documents/{id}",
            status=200,
            duration_seconds=(index % 50) / 100.0,
        )

    series = registry._durations[("GET", "/api/documents/{id}")]
    # Exactly one counter per finite bucket — no per-request growth.
    assert len(series._counts) == len(HISTOGRAM_BUCKETS)
    assert series.count == 10_000
    assert registry.render().count("_bucket{") == len(HISTOGRAM_BUCKETS) + 1
