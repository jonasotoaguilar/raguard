"""Per-tenant sliding-window rate limiting with safe degradation (task F4).

The production backend is Redis: each ``window_seconds`` bucket owns a sorted
set key ``ratelimit:{tenant}:{subject}:{bucket}`` holding request timestamps
as scores. A check trims entries older than the window (ZREMRANGEBYSCORE),
records the current request (ZADD), counts the survivors in this bucket plus
the previous one (ZCARD) for a true sliding window, and refreshes key expiry
(EXPIRE) — all in one pipeline. Counting the previous bucket is what makes
the window slide instead of resetting on bucket boundaries.

When Redis is unreachable (or no client is configured) the limiter degrades
to an in-process per-worker counter enforcing the same limit — never
unlimited — and logs a warning at most once per window to avoid log spam.
"""

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    limit: int
    remaining: int


class RateLimiter(Protocol):
    """Injectable async contract; middleware and tests program to this."""

    async def check(self, *, tenant: str, subject: str) -> RateLimitDecision: ...


def _bucket(now: float, window_seconds: int) -> int:
    return int(now // window_seconds)


def _key(tenant: str, subject: str, bucket: int) -> str:
    return f"ratelimit:{tenant}:{subject}:{bucket}"


def _retry_after(*, now: float, window_seconds: int) -> int:
    """Seconds remaining in the current window bucket (at least 1).

    The client may still be denied on retry while sliding pressure from the
    previous bucket persists — the limiter re-reports the remaining seconds
    then — so this stays a truthful, bounded hint rather than a promise."""
    bucket = _bucket(now, window_seconds)
    remaining = (bucket + 1) * window_seconds - now
    return max(1, int(remaining) + (1 if remaining % 1 > 0 else 0))


class SlidingWindowLimiter:
    """Sliding-window limiter over Redis with in-process fallback.

    ``redis_client`` is a redis-py asyncio client (or a test double speaking
    ``pipeline().zremrangebyscore/zadd/zcard/expire/execute``); ``None``
    forces the fallback path. ``clock`` defaults to wall time and is
    injectable for deterministic tests.
    """

    def __init__(
        self,
        *,
        redis_client: Any | None,
        requests_per_window: int,
        window_seconds: int,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._redis = redis_client
        self._limit = requests_per_window
        self._window = window_seconds
        self._clock: Callable[[], float] = clock or time.time
        self._fallback: dict[str, list[float]] = {}
        self._fallback_warned_at: float | None = None

    async def check(self, *, tenant: str, subject: str) -> RateLimitDecision:
        now = self._clock()
        if self._redis is not None:
            try:
                return await self._check_redis(tenant=tenant, subject=subject, now=now)
            except Exception as exc:
                self._warn_once(now, f"Redis backend failed ({exc!r}); using in-process fallback")
                return self._check_fallback(tenant=tenant, subject=subject, now=now)
        self._warn_once(now, "no Redis rate-limit backend configured; using in-process fallback")
        return self._check_fallback(tenant=tenant, subject=subject, now=now)

    async def _check_redis(self, *, tenant: str, subject: str, now: float) -> RateLimitDecision:
        bucket = _bucket(now, self._window)
        current_key = _key(tenant, subject, bucket)
        previous_key = _key(tenant, subject, bucket - 1)
        cutoff = now - self._window
        member = f"{now}:{uuid.uuid4().hex}"
        ttl = self._window * 2
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(current_key, 0, cutoff)
        pipe.zadd(current_key, {member: now})
        pipe.zcard(current_key)
        pipe.expire(current_key, ttl)
        pipe.zremrangebyscore(previous_key, 0, cutoff)
        pipe.zcard(previous_key)
        pipe.expire(previous_key, ttl)
        results = await pipe.execute()
        current_count = int(results[2])
        previous_count = int(results[5])
        total = current_count + previous_count
        allowed = total <= self._limit
        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=(
                0 if allowed else _retry_after(now=now, window_seconds=self._window)
            ),
            limit=self._limit,
            remaining=max(0, self._limit - total),
        )

    def _check_fallback(self, *, tenant: str, subject: str, now: float) -> RateLimitDecision:
        bucket = _bucket(now, self._window)
        cutoff = now - self._window
        # Drop buckets fully outside the sliding horizon to bound memory.
        stale = [
            key
            for key in self._fallback
            if not key.endswith(f":{bucket}") and not key.endswith(f":{bucket - 1}")
        ]
        for key in stale:
            del self._fallback[key]
        current = self._prune(_key(tenant, subject, bucket), cutoff)
        previous = self._prune(_key(tenant, subject, bucket - 1), cutoff)
        current.append(now)
        total = len(current) + len(previous)
        allowed = total <= self._limit
        return RateLimitDecision(
            allowed=allowed,
            retry_after_seconds=(
                0 if allowed else _retry_after(now=now, window_seconds=self._window)
            ),
            limit=self._limit,
            remaining=max(0, self._limit - total),
        )

    def _prune(self, key: str, cutoff: float) -> list[float]:
        hits = [ts for ts in self._fallback.get(key, []) if ts > cutoff]
        self._fallback[key] = hits
        return hits

    def _warn_once(self, now: float, message: str) -> None:
        if self._fallback_warned_at is None or now - self._fallback_warned_at >= self._window:
            logger.warning(message)
            self._fallback_warned_at = now


def build_rate_limiter(settings, *, redis_client: Any | None = None) -> SlidingWindowLimiter:
    """Compose the production limiter: explicit client wins, otherwise lazily
    connect to ``rate_limit_redis_url`` (falling back to the job-queue URL);
    import/connection failures degrade to the in-process fallback at check
    time rather than at startup."""
    client = redis_client
    if client is None:
        url = settings.rate_limit_redis_url or settings.job_queue_redis_url
        try:
            import redis.asyncio as redis_async

            client = redis_async.from_url(url)
        except Exception as exc:  # pragma: no cover - import-time only
            logger.warning("Redis client unavailable (%r); rate limiting will use fallback", exc)
            client = None
    return SlidingWindowLimiter(
        redis_client=client,
        requests_per_window=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
