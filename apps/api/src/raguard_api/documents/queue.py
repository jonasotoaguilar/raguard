"""Job-queue adapter: Arq/Redis behind the JobQueue protocol (task 2.2).

Jobs carry only the document id (contracts.JobQueue) with a deterministic Arq
job id ``ingest:{document_id}`` so Redis deduplicates replays of the same
upload. The protocol is synchronous, so the adapter bridges to Arq's coroutine
API with ``asyncio.run``; the API route executes adapter calls inside
``asyncio.to_thread``, where no event loop is running. A pool is created
lazily from ``redis_url`` on first enqueue unless a ``redis`` object is
injected (tests).
"""

import asyncio
import uuid
from typing import Any

from arq.connections import RedisSettings, create_pool

INGEST_FUNCTION_NAME = "ingest_document"


def _job_id(document_id: uuid.UUID) -> str:
    """Deterministic Arq job id for one upload: ``ingest:{document_id}``."""
    return f"ingest:{document_id}"


class ArqJobQueue:
    """JobQueue adapter over an ArqRedis pool; ``redis`` may be injected for tests."""

    def __init__(
        self,
        *,
        redis_url: str,
        function_name: str = INGEST_FUNCTION_NAME,
        redis: Any | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._function_name = function_name
        self._redis = redis
        self._pool: Any | None = None

    def enqueue(self, job_id: str, document_id: uuid.UUID) -> None:
        asyncio.run(self._enqueue(job_id, document_id))

    async def _enqueue(self, job_id: str, document_id: uuid.UUID) -> None:
        redis = self._redis or await self._ensure_pool()
        await redis.enqueue_job(self._function_name, str(document_id), _job_id=job_id)

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        return self._pool
