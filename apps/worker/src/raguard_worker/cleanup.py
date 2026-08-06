"""Stale-unready sweep cron and its observability seam (tasks 4.2/4.3, 5.2).

The API compensation leaves a stale unready row as a sweep marker when the
object store refuses cleanup (router._compensate). This cron owns those
markers: it selects stale unready rows with ``SKIP LOCKED`` (so a concurrent
holder is skipped and fresh/ready rows are never locked), deletes each
object with the bounded jittered retry budget, removes the row on success,
and on exhaustion logs an alert carrying the document id correlation and
keeps the row. Ready rows — even with a missing object — are process-owned
and never touched here (the worker writes ``failed/source_missing`` under
the row lock). PR5 adds the bounded alert surface to the same run: a
post-sweep remaining count alerts on sweep backlog, and
``alert_stale_pending`` alerts on any ``pending`` row older than
``pending_age_seconds`` with the document-id correlation (both capped at
``sweep_batch_size`` rows per run).
"""

import asyncio
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from raguard_api.documents.contracts import DocumentStatus
from raguard_api.documents.models import Document
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from raguard_worker.jobs import DocumentState, _to_state, call_with_retries

logger = logging.getLogger("raguard_worker.cleanup")

_MAX_JITTER = 0.05


class SweepStore(Protocol):
    """Persistence seam for the sweep: stale unready rows, pending-age rows, and deletion."""

    async def stale_unready(self, *, cutoff: datetime, limit: int) -> Sequence[DocumentState]: ...
    async def count_stale_unready(self, *, cutoff: datetime) -> int: ...
    async def pending_older_than(
        self, *, cutoff: datetime, limit: int
    ) -> Sequence[DocumentState]: ...
    async def delete(self, document_id: uuid.UUID) -> None: ...


class SqlAlchemySweepStore:
    """SweepStore over the shared ORM models with a ``SKIP LOCKED`` select.

    The select is bounded (``limit``), ordered by age, and uses
    ``with_for_update(skip_locked=True)`` so concurrent sweep runs or any
    other lock holder are skipped instead of blocked; the transaction ends
    when the select session closes, so no unready row stays locked.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def stale_unready(self, *, cutoff: datetime, limit: int) -> Sequence[DocumentState]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Document)
                        .where(Document.dispatch_ready.is_(False), Document.created_at < cutoff)
                        .order_by(Document.created_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            return [_to_state(row) for row in rows]

    async def count_stale_unready(self, *, cutoff: datetime) -> int:
        async with self._session_factory() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.dispatch_ready.is_(False), Document.created_at < cutoff)
                )
            ).scalar_one()

    async def pending_older_than(self, *, cutoff: datetime, limit: int) -> Sequence[DocumentState]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Document)
                        .where(
                            Document.status == DocumentStatus.pending.value,
                            Document.created_at < cutoff,
                        )
                        .order_by(Document.created_at)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [_to_state(row) for row in rows]

    async def delete(self, document_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(Document).where(Document.id == document_id))
            await session.commit()


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def alert_stale_pending(ctx: dict) -> None:
    """Alert on ``pending`` rows older than ``pending_age_seconds`` (task 5.2).

    Runs on the sweep cron's cadence (every minute) and is bounded at
    ``sweep_batch_size`` rows per run. Every alert line carries the
    document-id correlation and the measured age; the status is implied by
    the select (``pending``), so no unbounded dimensions are logged. Rows are
    read without locking — alerts may lag concurrent writes by one run.
    """
    settings = ctx["settings"]
    store: SweepStore = ctx["sweep_store"]
    log = ctx.get("logger", logger)

    cutoff = _utcnow() - timedelta(seconds=settings.pending_age_seconds)
    rows = await store.pending_older_than(cutoff=cutoff, limit=settings.sweep_batch_size)
    for state in rows:
        age = round((_utcnow() - state.created_at).total_seconds())
        log.error(
            "pending age alert document_id=%s age_seconds=%s",
            state.document_id,
            age,
        )


async def sweep_stale_unready(ctx: dict) -> None:
    """Cron job: delete stale unready markers; alert on exhaustion and backlog.

    Reads the ``sweep_store``/``object_store`` seams and the injectable
    ``logger`` observability seam from the job context (defaults to the
    module logger). One run is bounded by ``sweep_batch_size`` rows, then
    alerts on any remaining stale-unready count (sweep backlog) and on
    pending rows older than ``pending_age_seconds``.
    """
    settings = ctx["settings"]
    store: SweepStore = ctx["sweep_store"]
    object_store = ctx["object_store"]
    log = ctx.get("logger", logger)

    cutoff = _utcnow() - timedelta(seconds=settings.sweep_age_seconds)
    rows = await store.stale_unready(cutoff=cutoff, limit=settings.sweep_batch_size)
    for state in rows:
        key = state.storage_key
        try:
            await call_with_retries(
                lambda key=key: asyncio.to_thread(object_store.delete, key),
                attempts=settings.provider_attempts,
                max_jitter=_MAX_JITTER,
                max_retry_after=settings.max_retry_after_seconds,
            )
        except Exception:
            log.error(
                "compensation exhaustion: stale unready row kept as sweep marker "
                "document_id=%s key=%s",
                state.document_id,
                state.storage_key,
            )
            continue
        await store.delete(state.document_id)
        log.info(
            "swept stale unready row document_id=%s key=%s",
            state.document_id,
            state.storage_key,
        )
    remaining = await store.count_stale_unready(cutoff=cutoff)
    if remaining > 0:
        log.error(
            "sweep backlog alert remaining_stale_unready=%s",
            remaining,
        )
    await alert_stale_pending(ctx)
