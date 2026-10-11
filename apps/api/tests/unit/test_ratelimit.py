"""Unit tests for the F4 sliding-window rate limiter (task F4, test-first).

The limiter is exercised against an in-memory fake Redis speaking the same
pipeline calls as the production backend (ZREMRANGEBYSCORE + ZADD + ZCARD +
EXPIRE), plus failure-injection fakes for the in-process fallback path.
"""

import logging
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.config import Settings
from raguard_api.main import attach_rate_limiting
from raguard_api.ratelimit import RateLimitDecision, SlidingWindowLimiter

JWT_SECRET = "test-secret-0123456789abcdef1234"


def _settings(**overrides) -> Settings:
    base = {"jwt_secret": JWT_SECRET}
    base.update(overrides)
    return Settings(**base)


class FakePipeline:
    """Minimal redis-py pipeline double: queues ops, applies them on execute."""

    def __init__(self, store: dict) -> None:
        self._store = store
        self._ops: list = []

    def zremrangebyscore(self, key: str, _min, _max):
        self._ops.append(lambda: self._trim(key, float(_max)))
        return self

    def zadd(self, key: str, mapping: dict):
        def _add():
            zset = self._store.setdefault(key, {})
            zset.update(mapping)
            return len(mapping)

        self._ops.append(_add)
        return self

    def zcard(self, key: str):
        self._ops.append(lambda: len(self._store.get(key, {})))
        return self

    def expire(self, _key: str, _ttl: int):
        self._ops.append(lambda: True)
        return self

    async def execute(self):
        return [op() for op in self._ops]

    @staticmethod
    def _trim_key(store: dict, key: str, cutoff: float) -> int:
        zset = store.get(key, {})
        expired = [m for m, score in zset.items() if score <= cutoff]
        for m in expired:
            del zset[m]
        return len(expired)

    def _trim(self, key: str, cutoff: float) -> int:
        return self._trim_key(self._store, key, cutoff)


class FakeRedis:
    """Async fake speaking the subset of redis-py used by SlidingWindowLimiter."""

    def __init__(self, store: dict | None = None) -> None:
        self.store: dict = store if store is not None else {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self.store)


class FailingRedis:
    """Backend double whose pipeline always fails, forcing the fallback path."""

    def pipeline(self):
        raise ConnectionError("redis down")

    def __getattr__(self, _name):
        raise ConnectionError("redis down")


@pytest.fixture()
def clock():
    now = [1_000_000.0]
    return now, lambda: now[0]


def _limiter(redis_client, clock, *, limit=3, window=60) -> SlidingWindowLimiter:
    now, tick = clock
    limiter = SlidingWindowLimiter(
        redis_client=redis_client,
        requests_per_window=limit,
        window_seconds=window,
        clock=tick,
    )
    return limiter, now


async def test_allows_up_to_limit_then_blocks(clock) -> None:
    limiter, _ = _limiter(FakeRedis(), clock)
    for _ in range(3):
        decision = await limiter.check(tenant="t1", subject="user:u1")
        assert decision.allowed is True
    denied = await limiter.check(tenant="t1", subject="user:u1")
    assert denied.allowed is False
    assert denied.retry_after_seconds >= 1


async def test_window_reset_allows_again(clock) -> None:
    limiter, now = _limiter(FakeRedis(), clock, limit=2)
    assert (await limiter.check(tenant="t", subject="s")).allowed
    assert (await limiter.check(tenant="t", subject="s")).allowed
    assert not (await limiter.check(tenant="t", subject="s")).allowed
    now[0] += 2 * 60 + 1  # slide fully past both buckets
    assert (await limiter.check(tenant="t", subject="s")).allowed


async def test_distinct_tenants_and_subjects_are_isolated(clock) -> None:
    limiter, _ = _limiter(FakeRedis(), clock, limit=1)
    assert (await limiter.check(tenant="t1", subject="user:u1")).allowed
    assert not (await limiter.check(tenant="t1", subject="user:u1")).allowed
    # Same user, other tenant: unaffected.
    assert (await limiter.check(tenant="t2", subject="user:u1")).allowed
    # Same tenant, other user: unaffected.
    assert (await limiter.check(tenant="t1", subject="user:u2")).allowed


async def test_backend_failure_falls_back_to_in_process_limit(clock) -> None:
    limiter, _ = _limiter(FailingRedis(), clock, limit=2)
    assert (await limiter.check(tenant="t", subject="s")).allowed
    assert (await limiter.check(tenant="t", subject="s")).allowed
    denied = await limiter.check(tenant="t", subject="s")
    assert denied.allowed is False  # never unlimited on fallback
    assert denied.retry_after_seconds >= 1


async def test_fallback_logs_warning_only_once_per_window(clock, caplog) -> None:
    limiter, now = _limiter(FailingRedis(), clock, limit=100)
    with caplog.at_level(logging.WARNING, logger="raguard_api.ratelimit"):
        for _ in range(5):
            assert (await limiter.check(tenant="t", subject="s")).allowed
    warnings = [r for r in caplog.records if "fallback" in r.getMessage().lower()]
    assert len(warnings) == 1
    # Next window: one fresh warning is acceptable again.
    now[0] += 61
    with caplog.at_level(logging.WARNING, logger="raguard_api.ratelimit"):
        assert (await limiter.check(tenant="t", subject="other")).allowed
    warnings = [r for r in caplog.records if "fallback" in r.getMessage().lower()]
    assert len(warnings) == 2


async def test_direct_calls_without_backend_use_fallback(clock) -> None:
    limiter, _ = _limiter(None, clock, limit=1)
    assert (await limiter.check(tenant="t", subject="s")).allowed
    assert not (await limiter.check(tenant="t", subject="s")).allowed


# --- Middleware unit tests (no Redis, injected limiter doubles) ---


class AllowAll:
    async def check(self, *, tenant: str, subject: str) -> RateLimitDecision:
        return RateLimitDecision(allowed=True, retry_after_seconds=0, limit=60, remaining=59)


class DenyAll:
    def __init__(self, retry_after: int = 42) -> None:
        self.retry_after = retry_after

    async def check(self, *, tenant: str, subject: str) -> RateLimitDecision:
        return RateLimitDecision(
            allowed=False, retry_after_seconds=self.retry_after, limit=60, remaining=0
        )


class RecordingLimiter(AllowAll):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def check(self, *, tenant: str, subject: str) -> RateLimitDecision:
        self.calls.append((tenant, subject))
        return await super().check(tenant=tenant, subject=subject)


def _build_app(settings: Settings, limiter) -> FastAPI:
    app = FastAPI()
    attach_rate_limiting(app, settings, limiter=limiter)

    @app.get("/api/items")
    async def _items():
        return {"ok": True}

    @app.get("/health")
    async def _health():
        return {"ok": True}

    @app.get("/metrics")
    async def _metrics():
        return {"ok": True}

    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_middleware_passes_under_limit() -> None:
    app = _build_app(_settings(), AllowAll())
    async with _client(app) as client:
        response = await client.get("/api/items")
    assert response.status_code == 200
    assert "Retry-After" not in response.headers


async def test_middleware_returns_429_with_retry_after() -> None:
    app = _build_app(_settings(), DenyAll(retry_after=17))
    async with _client(app) as client:
        response = await client.get("/api/items")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert "error" in body


async def test_middleware_skips_excluded_paths() -> None:
    app = _build_app(_settings(), DenyAll())
    async with _client(app) as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/metrics")).status_code == 200


async def test_middleware_disabled_bypasses() -> None:
    app = _build_app(_settings(rate_limit_enabled=False), DenyAll())
    async with _client(app) as client:
        response = await client.get("/api/items")
    assert response.status_code == 200


async def test_middleware_derives_identity_from_jwt() -> None:

    settings = _settings()
    recorder = RecordingLimiter()
    app = _build_app(settings, recorder)
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)
    async with _client(app) as client:
        response = await client.get("/api/items", headers={"Cookie": f"raguard_session={token}"})
    assert response.status_code == 200
    assert recorder.calls == [(str(tenant_id), f"user:{user_id}")]


async def test_middleware_accepts_bearer_header() -> None:

    settings = _settings()
    recorder = RecordingLimiter()
    app = _build_app(settings, recorder)
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)
    async with _client(app) as client:
        response = await client.get("/api/items", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert recorder.calls == [(str(tenant_id), f"user:{user_id}")]


async def test_middleware_falls_back_to_ip_without_identity() -> None:
    recorder = RecordingLimiter()
    app = _build_app(_settings(), recorder)
    async with _client(app) as client:
        response = await client.get("/api/items")
    assert response.status_code == 200
    assert recorder.calls == [("anonymous", "ip:127.0.0.1")]


async def test_middleware_ignores_forwarded_for_unless_trusted() -> None:
    recorder = RecordingLimiter()
    app = _build_app(_settings(), recorder)
    async with _client(app) as client:
        await client.get("/api/items", headers={"X-Forwarded-For": "9.9.9.9"})
    assert recorder.calls == [("anonymous", "ip:127.0.0.1")]

    trusted_recorder = RecordingLimiter()
    trusted_app = _build_app(_settings(trust_proxy_headers=True), trusted_recorder)
    async with _client(trusted_app) as client:
        await client.get("/api/items", headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.1"})
    # Rightmost hop wins: with one trusted proxy (Caddy) the proxy appends
    # the observed TCP peer last, so 10.0.0.1 — not the spoofable 9.9.9.9 —
    # owns the bucket.
    assert trusted_recorder.calls == [("anonymous", "ip:10.0.0.1")]


async def test_middleware_trusted_proxy_ignores_spoofed_left_hop() -> None:
    """A client-forged left hop must not move the bucket off the real peer."""
    recorder = RecordingLimiter()
    app = _build_app(_settings(trust_proxy_headers=True), recorder)
    async with _client(app) as client:
        # "9.9.9.9" is attacker-controlled; "10.0.0.5" is the peer our
        # trusted proxy appended rightmost — the bucket must be the latter.
        await client.get("/api/items", headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.5"})
    assert recorder.calls == [("anonymous", "ip:10.0.0.5")]


async def test_middleware_invalid_token_falls_back_to_ip() -> None:
    recorder = RecordingLimiter()
    app = _build_app(_settings(), recorder)
    async with _client(app) as client:
        response = await client.get("/api/items", headers={"Cookie": "raguard_session=forged"})
    assert response.status_code == 200
    assert recorder.calls == [("anonymous", "ip:127.0.0.1")]


def test_rate_limit_settings_defaults_and_bounds() -> None:
    settings = _settings()
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_requests == 60
    assert settings.rate_limit_window_seconds == 60
    assert settings.rate_limit_redis_url == ""
    assert settings.trust_proxy_headers is False
    with pytest.raises(ValueError):
        _settings(rate_limit_requests=0)
    with pytest.raises(ValueError):
        _settings(rate_limit_window_seconds=0)
    with pytest.raises(ValueError):
        _settings(rate_limit_requests=10_001)


async def test_rate_limit_error_handler_sets_retry_after() -> None:
    from raguard_api.errors import RateLimitError, register_error_handlers

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def _boom():
        raise RateLimitError(retry_after_seconds=33)

    async with _client(app) as client:
        response = await client.get("/boom")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "33"
    assert response.json()["error"]["code"] == "rate_limited"
