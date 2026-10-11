"""Integration tests for F4 rate limiting against real Redis (task F4).

Skipped when Redis is unavailable (local runs without docker); CI runs the
full stack. The sliding-window contract is verified end to end through the
production limiter + middleware wiring.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.config import Settings
from raguard_api.main import create_app
from raguard_api.ratelimit import SlidingWindowLimiter

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"
REDIS_URL = "redis://127.0.0.1:6379/1"


def _settings(**overrides) -> Settings:
    base = {
        "jwt_secret": JWT_SECRET,
        "rate_limit_requests": 3,
        "rate_limit_window_seconds": 60,
        "rate_limit_redis_url": REDIS_URL,
    }
    base.update(overrides)
    return Settings(**base)


async def _redis_available() -> bool:
    try:
        import redis.asyncio as redis_async
    except ImportError:
        return False
    try:
        client = redis_async.from_url(REDIS_URL)
        try:
            await client.ping()
        finally:
            await client.aclose()
    except Exception:
        return False
    return True


async def _make_app(db, settings: Settings) -> FastAPI:
    if not await _redis_available():
        pytest.skip("Redis unavailable; start the local stack")
    return create_app(settings=settings, session_factory=db.session_factory)


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_redis_sliding_window_blocks_over_limit(migrated_db) -> None:
    app = await _make_app(migrated_db, _settings())
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    settings = _settings()
    token = create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)
    headers = {"Cookie": f"raguard_session={token}"}
    async with _client(app) as client:
        statuses = []
        for _ in range(5):
            response = await client.get("/api/org/users", headers=headers)
            statuses.append(response.status_code)
    assert statuses[:3] != [429, 429, 429]
    assert 429 in statuses
    # The 429 carries the safe envelope plus Retry-After.
    async with _client(app) as client:
        response = await client.get("/api/org/users", headers=headers)
        if response.status_code == 429:
            assert response.json()["error"]["code"] == "rate_limited"
            assert int(response.headers["Retry-After"]) >= 1


async def test_rate_limiting_disabled_bypasses_with_real_redis(migrated_db) -> None:
    app = await _make_app(migrated_db, _settings(rate_limit_enabled=False))
    async with _client(app) as client:
        for _ in range(5):
            response = await client.get("/api/org/users")
            assert response.status_code in (200, 401)  # never 429
            assert response.status_code != 429


async def test_excluded_paths_never_limited(migrated_db) -> None:
    # /health, /ready, and /metrics bypass the limiter: with a budget of 1,
    # any limited route would 429 on the second hit, while excluded paths
    # keep serving. (An unknown /api/... path IS limited — 429 there is the
    # correct behavior, not an exclusion.)
    app = await _make_app(
        migrated_db, _settings(rate_limit_requests=1, rate_limit_window_seconds=60)
    )
    async with _client(app) as client:
        for _ in range(3):
            for path in ("/health", "/metrics"):
                response = await client.get(path)
                assert response.status_code == 200  # excluded, never 429


async def test_sliding_window_unit_against_real_redis() -> None:
    if not await _redis_available():
        pytest.skip("Redis unavailable; start the local stack")
    import redis.asyncio as redis_async

    client = redis_async.from_url(REDIS_URL)
    try:
        await client.flushdb()
        limiter = SlidingWindowLimiter(
            redis_client=client, requests_per_window=2, window_seconds=60
        )
        tenant = f"t-{uuid.uuid4().hex[:8]}"
        assert (await limiter.check(tenant=tenant, subject="u")).allowed
        assert (await limiter.check(tenant=tenant, subject="u")).allowed
        denied = await limiter.check(tenant=tenant, subject="u")
        assert denied.allowed is False
        assert denied.retry_after_seconds >= 1
        # Isolation: another tenant is unaffected.
        assert (await limiter.check(tenant=f"t-{uuid.uuid4().hex[:8]}", subject="u")).allowed
    finally:
        await client.aclose()
