"""Worker ingestion job: dispatch state machine and pipeline (task 3.4).

The job follows the DESIGN.md dispatch table over the shared
``raguard_api.documents`` models/contracts:

| Observed state             | Action                                     |
|----------------------------|--------------------------------------------|
| Ready row + object         | Lock, process, atomically replace chunks   |
| Fresh unready row          | Bounded unlocked poll, then defer          |
| Stale unready row          | ACK no-op (sweep-owned)                    |
| Missing row                | ACK no-op                                  |
| Ready row + missing object | failed/source_missing, chunks cleared      |

Terminal ``failed`` rows ACK without adapters or mutation; ``indexed`` rows
reprocess (idempotent redelivery). Parsers/embeddings/chunking are injected
seams; PR4b supplies the real adapters. Provider errors retry
``provider_attempts`` times with jitter and honor a bounded Retry-After
(task 3.2); retry-budget exhaustion ends in an allowlisted failure reason.
Corrective remediation: with Arq retries left, a transient parser/embedder
failure raises ``TransientStageFailure`` (an arq ``Retry``) so the worker
re-enqueues the job within the bounded budget — arq 0.28 terminal-fails plain
exceptions, which would leave the row ``pending`` forever. Only the terminal
``job_try`` commits the allowlisted failure.
PR5 adds the observability contract: every terminal failure and every
unhandled stage failure logs a bounded-cardinality alert carrying the
document-id correlation and ``job_try``, successes log an info line, and
designed deferrals (``DispatchNotReady``/``TransientStageFailure``) never
alert.
"""

import asyncio
import logging
import random
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from arq.worker import Retry
from raguard_api.documents.contracts import FAILURE_REASONS, DocumentStatus
from raguard_api.documents.models import Chunk, Document
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_worker.parsers import parse_failure_reason

logger = logging.getLogger("raguard_worker.jobs")

_MAX_JITTER = 0.05


class DispatchNotReady(Retry):
    """Typed deferral: the row was still unready after the bounded poll window.

    Subclasses arq's ``Retry`` so the worker defers the job (honoring
    ``retry_after``) instead of failing it; deferrals stay outside the
    ingestion/provider retry budget.
    """

    def __init__(self, *, retry_after: float) -> None:
        super().__init__(defer=retry_after)


class TransientStageFailure(Retry):
    """Typed deferral: a transient parser/embedder failure with Arq retries left.

    Subclasses arq's ``Retry`` so the worker re-enqueues the job (honoring
    ``retry_after``) instead of terminal-failing it — arq 0.28 only requeues
    ``Retry`` exceptions; plain exceptions consume the job. The deferral stays
    inside the bounded retry budget: ``_fail_if_exhausted`` commits the
    allowlisted failure once ``job_try`` reaches ``max_tries``.
    """

    def __init__(self, *, retry_after: float) -> None:
        super().__init__(defer=retry_after)


class ProviderRateLimited(Exception):
    """Provider 429: carries the Retry-After the retry loop honors, bounded."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"provider rate limited; retry after {retry_after}s")


@dataclass(frozen=True)
class DocumentState:
    """Immutable row view produced by the dispatch seam (never the ORM object)."""

    document_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    status: str
    failure_reason: str | None
    dispatch_ready: bool
    storage_key: str
    created_at: datetime


@dataclass(frozen=True)
class NewChunk:
    """One chunk awaiting atomic insertion (content + embedding vector)."""

    content: str
    embedding: list[float]


class DocumentClaim(Protocol):
    """Locked document row: one transaction stays open until commit/close."""

    state: DocumentState

    async def commit_indexed(self, chunks: Sequence[NewChunk]) -> None: ...
    async def commit_failed(self, reason: str) -> None: ...
    async def close(self) -> None: ...


class DispatchStore(Protocol):
    """Worker-side persistence seam over the shared ORM models (task 3.5)."""

    async def fetch(self, document_id: uuid.UUID) -> DocumentState | None: ...
    async def lock_for_process(self, document_id: uuid.UUID) -> DocumentClaim | None: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


def is_fresh(created_at: datetime, *, now: datetime, freshness_seconds: float) -> bool:
    """True while the row is inside the dispatch freshness window."""
    return (now - created_at).total_seconds() <= freshness_seconds


def dispatch_action(state: DocumentState | None, *, now: datetime, freshness_seconds: float) -> str:
    """Map the observed row to the DESIGN.md dispatch action: ack | poll | process.

    Missing rows, terminal ``failed`` rows, and stale unready rows ACK without
    touching adapters; fresh unready rows poll; ready rows process (object
    presence is decided under the lock during processing).
    """
    if state is None or state.status == DocumentStatus.failed.value:
        return "ack"
    if not state.dispatch_ready:
        if is_fresh(state.created_at, now=now, freshness_seconds=freshness_seconds):
            return "poll"
        return "ack"
    return "process"


async def poll_until_ready(
    store: DispatchStore,
    document_id: uuid.UUID,
    *,
    wait_seconds: float,
    poll_interval_seconds: float,
    freshness_seconds: float,
) -> DocumentState | None:
    """Bounded unlocked polling for the ready commit (design: fresh unready).

    Returns the ready row once observed, None when the row vanished, failed,
    or turned stale (ACK), and raises DispatchNotReady when the bounded wait
    expires with the row still fresh and unready.
    """
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        state = await store.fetch(document_id)
        action = dispatch_action(state, now=_utcnow(), freshness_seconds=freshness_seconds)
        if action == "process":
            return state
        if action == "ack":
            return None
        if asyncio.get_running_loop().time() >= deadline:
            raise DispatchNotReady(retry_after=wait_seconds)
        await asyncio.sleep(poll_interval_seconds)


def _retry_budget_exhausted(ctx: dict, settings) -> bool:
    """True when this Arq attempt is the last allowed one (ctx job_try)."""
    return ctx.get("job_try", 1) >= settings.max_tries


async def call_with_retries[T](
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    max_jitter: float,
    max_retry_after: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Bounded provider retries: thrice-by-default with growing jitter (task 3.2).

    ``ProviderRateLimited`` (429) sleeps ``min(retry_after, max_retry_after)``;
    any other failure sleeps a jittered backoff. The last failure propagates.
    ``sleep`` is injectable so tests record backoff without waiting.
    """
    for attempt in range(attempts):
        try:
            return await call()
        except ProviderRateLimited as exc:
            if attempt == attempts - 1:
                raise
            await sleep(min(exc.retry_after, max_retry_after))
        except Exception:
            if attempt == attempts - 1:
                raise
            await sleep(random.uniform(0.0, max_jitter * (attempt + 1)))
    raise AssertionError("unreachable")


async def _log_job_failure(log, *, document_id: uuid.UUID, reason: str, ctx: dict) -> None:
    """Bounded-cardinality job-failure alert with the document-id correlation (task 5.2)."""
    log.error(
        "job failure alert document_id=%s reason=%s job_try=%s",
        document_id,
        reason,
        ctx.get("job_try", 1),
    )


def _stage_retry_defer(settings, exc: Exception) -> float:
    """Bounded deferral for a transient stage retry (corrective remediation).

    Provider 429s honor their Retry-After, bounded by
    ``max_retry_after_seconds``; any other transient failure defers a jittered
    backoff within the same bound so a stuck job cannot pin the queue.
    """
    if isinstance(exc, ProviderRateLimited):
        return min(exc.retry_after, settings.max_retry_after_seconds)
    return random.uniform(0.0, settings.max_retry_after_seconds)


async def ingest_document(ctx: dict, document_id: str) -> None:
    """Arq job: dispatch one document through the DESIGN.md state machine.

    Jobs carry only the document id (contracts.JobQueue). Every branch ends in
    an ACK (no-op), a typed DispatchNotReady deferral, an allowlisted terminal
    failure, or an atomic replace of chunks/status. The row is locked before
    processing so the replace is serialized with any concurrent run. Unhandled
    stage failures re-raise for Arq after logging a job-failure alert (the
    correlation id is the raw job payload, which may pre-date id parsing).
    """
    settings = ctx["settings"]
    store = ctx["store"]
    log = ctx.get("logger", logger)
    try:
        parsed_id = uuid.UUID(document_id)

        state = await store.fetch(parsed_id)
        action = dispatch_action(
            state, now=_utcnow(), freshness_seconds=settings.dispatch_freshness_seconds
        )
        if action == "ack":
            return None
        if action == "poll":
            state = await poll_until_ready(
                store,
                parsed_id,
                wait_seconds=settings.dispatch_wait_seconds,
                poll_interval_seconds=settings.dispatch_poll_interval_seconds,
                freshness_seconds=settings.dispatch_freshness_seconds,
            )
            if state is None:
                return None

        claim = await store.lock_for_process(parsed_id)
        if claim is None:
            return None
        try:
            try:
                data = await asyncio.to_thread(ctx["object_store"].get, claim.state.storage_key)
            except Exception:
                await claim.commit_failed("source_missing")
                await _log_job_failure(log, document_id=parsed_id, reason="source_missing", ctx=ctx)
                return None
            try:
                text = await call_with_retries(
                    lambda: asyncio.to_thread(ctx["parser"].parse, data),
                    attempts=settings.provider_attempts,
                    max_jitter=_MAX_JITTER,
                    max_retry_after=settings.max_retry_after_seconds,
                )
            except Exception as exc:
                reason = parse_failure_reason(exc)
                if await _fail_if_exhausted(claim, ctx, settings, reason=reason):
                    await _log_job_failure(log, document_id=parsed_id, reason=reason, ctx=ctx)
                    return None
                # Retries remain: defer via arq's Retry so the worker requeues
                # the job (arq 0.28 terminal-fails plain exceptions, which
                # would leave the row pending forever).
                raise TransientStageFailure(retry_after=_stage_retry_defer(settings, exc)) from exc
            try:
                parts = ctx["chunker"](text)
            except Exception as exc:
                # Chunking is deterministic pure logic: a failure is terminal, so
                # write the allowlisted reason immediately (no retry budget burn).
                reason = parse_failure_reason(exc)
                await claim.commit_failed(reason)
                await _log_job_failure(log, document_id=parsed_id, reason=reason, ctx=ctx)
                return None
            try:
                vectors = await call_with_retries(
                    lambda: asyncio.to_thread(ctx["embedder"].embed, parts),
                    attempts=settings.provider_attempts,
                    max_jitter=_MAX_JITTER,
                    max_retry_after=settings.max_retry_after_seconds,
                )
            except Exception as exc:
                if await _fail_if_exhausted(claim, ctx, settings, reason="limit"):
                    await _log_job_failure(log, document_id=parsed_id, reason="limit", ctx=ctx)
                    return None
                raise TransientStageFailure(retry_after=_stage_retry_defer(settings, exc)) from exc
            await claim.commit_indexed(
                [
                    NewChunk(content=part, embedding=vector)
                    for part, vector in zip(parts, vectors, strict=True)
                ]
            )
            log.info(
                "document indexed document_id=%s chunks=%s",
                parsed_id,
                len(parts),
            )
        finally:
            await claim.close()
    except (DispatchNotReady, TransientStageFailure):
        raise  # designed deferrals: arq re-enqueues, no alert
    except Exception as exc:
        log.error(
            "job failure alert document_id=%s exception=%s job_try=%s",
            document_id,
            type(exc).__name__,
            ctx.get("job_try", 1),
        )
        raise


async def _fail_if_exhausted(claim, ctx: dict, settings, *, reason: str) -> bool:
    """Write the terminal allowlisted failure once the retry budget is spent.

    Returns True when the failure was written (the job ends here); False when
    the job still has Arq retries left and the caller defers via
    ``TransientStageFailure``. ``reason`` is allowlisted per DESIGN.md:
    parse-stage failures are ``malformed``, other bounded failures (embedding
    provider, rate limits) are ``limit``.
    """
    if _retry_budget_exhausted(ctx, settings):
        await claim.commit_failed(reason)
        return True
    return False


class _SqlAlchemyClaim:
    """A locked Document row: one open transaction until commit/close.

    The row lock is held from ``lock_for_process`` until the atomic replace:
    chunks are deleted, new chunks inserted, and the status flipped in a
    single transaction, so a failure mid-commit rolls everything back (zero
    or all chunks, never ``indexed`` with partial chunks).
    """

    def __init__(self, session: AsyncSession, row: Document) -> None:
        self._session = session
        self._row = row
        self.state = _to_state(row)

    async def commit_indexed(self, chunks: Sequence[NewChunk]) -> None:
        await self._session.execute(delete(Chunk).where(Chunk.document_id == self._row.id))
        self._session.add_all(
            [
                Chunk(
                    tenant_id=self._row.tenant_id,
                    document_id=self._row.id,
                    position=index,
                    content=chunk.content,
                    embedding=chunk.embedding,
                )
                for index, chunk in enumerate(chunks)
            ]
        )
        self._row.status = DocumentStatus.indexed.value
        self._row.failure_reason = None
        await self._session.commit()

    async def commit_failed(self, reason: str) -> None:
        if reason not in FAILURE_REASONS:
            raise ValueError(f"failure reason not allowlisted: {reason}")
        await self._session.execute(delete(Chunk).where(Chunk.document_id == self._row.id))
        self._row.status = DocumentStatus.failed.value
        self._row.failure_reason = reason
        await self._session.commit()

    async def close(self) -> None:
        await self._session.close()


class SqlAlchemyDispatchStore:
    """DispatchStore over the shared ORM models: unlocked fetch, locked claim.

    ``fetch`` is a plain read (polling never locks, so sweeps cannot race
    unready rows); ``lock_for_process`` takes the row lock and returns a
    claim that keeps the transaction open through the atomic replace.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def fetch(self, document_id: uuid.UUID) -> DocumentState | None:
        async with self._session_factory() as session:
            row = await session.get(Document, document_id)
            return _to_state(row) if row is not None else None

    async def lock_for_process(self, document_id: uuid.UUID) -> DocumentClaim | None:
        session = self._session_factory()
        try:
            row = (
                await session.execute(
                    select(Document).where(Document.id == document_id).with_for_update()
                )
            ).scalar_one_or_none()
        except Exception:
            await session.close()
            raise
        if row is None:
            await session.close()
            return None
        return _SqlAlchemyClaim(session, row)


def _to_state(row: Document) -> DocumentState:
    return DocumentState(
        document_id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        status=row.status,
        failure_reason=row.failure_reason,
        dispatch_ready=row.dispatch_ready,
        storage_key=row.storage_key,
        created_at=row.created_at,
    )
