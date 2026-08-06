"""Integration: stale-unready sweep and age alerts against real PostgreSQL (task 4.2 RED, 5.2).

The sweep cron owns compensation markers: stale unready rows (created before
``sweep_age_seconds``) are selected with ``SKIP LOCKED`` so a concurrent
holder is skipped, their objects deleted with bounded retries, and the rows
removed. Fresh unready rows and ready rows (even with a missing object) are
never touched; object-delete exhaustion logs an alert with the document id
correlation and keeps the row as the sweep marker. PR5 adds the bounded
alert surface: a post-sweep remaining count alerts on sweep backlog, and
``alert_stale_pending`` (run by the same cron) alerts on any ``pending`` row
older than ``pending_age_seconds`` with the document-id correlation.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from raguard_api.documents.contracts import FakeObjectStore
from raguard_api.documents.models import Document
from raguard_api.identity.models import Tenant
from raguard_worker.cleanup import (
    SqlAlchemySweepStore,
    alert_stale_pending,
    sweep_stale_unready,
)
from raguard_worker.settings import WorkerSettings
from sqlalchemy import select

pytestmark = pytest.mark.integration

SWEEP_AGE_SECONDS = 300.0


class RecordingLogger:
    """Observability seam: records formatted log lines instead of emitting."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append(message % args)

    def info(self, message: str, *args: object) -> None:
        self.infos.append(message % args)


class FailingDeleteStore(FakeObjectStore):
    """Object store whose delete always fails (provider outage)."""

    def delete(self, key: str) -> None:
        raise RuntimeError("object store down")


async def seed_document(
    db, *, ready: bool = False, age_seconds: float = 400.0, name: str = "sweep.md"
) -> tuple[uuid.UUID, str]:
    """Seed one document row (plus its tenant) with an explicit created_at."""
    async with db.session_factory() as session:
        tenant = Tenant(name="Tenant Sweep")
        session.add(tenant)
        await session.flush()
        document_id = uuid.uuid4()
        storage_key = f"{tenant.id}/{document_id}/{name}"
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant.id,
                name=name,
                status="pending",
                dispatch_ready=ready,
                storage_key=storage_key,
                created_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
            )
        )
        await session.commit()
        return document_id, storage_key


async def row_exists(db, document_id: uuid.UUID) -> bool:
    async with db.session_factory() as session:
        return await session.get(Document, document_id) is not None


def sweep_ctx(db, object_store: FakeObjectStore, logger: RecordingLogger) -> dict:
    return {
        "settings": WorkerSettings(),
        "sweep_store": SqlAlchemySweepStore(db.session_factory),
        "object_store": object_store,
        "logger": logger,
    }


async def test_sweep_deletes_stale_unready_row_and_object(migrated_db) -> None:
    document_id, storage_key = await seed_document(migrated_db)
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# orphaned marker")
    logger = RecordingLogger()

    await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))

    assert not await row_exists(migrated_db, document_id)
    assert storage_key in object_store.deleted_keys
    assert logger.errors == []


async def test_sweep_skips_rows_locked_by_another_transaction(migrated_db) -> None:
    locked_id, locked_key = await seed_document(migrated_db, name="locked.md")
    free_id, free_key = await seed_document(migrated_db, name="free.md")
    object_store = FakeObjectStore()
    object_store.put(locked_key, b"locked marker")
    object_store.put(free_key, b"free marker")
    logger = RecordingLogger()

    async with migrated_db.session_factory() as session:
        locked = (
            await session.execute(
                select(Document).where(Document.id == locked_id).with_for_update()
            )
        ).scalar_one()
        assert locked.id == locked_id
        # the sweep's SKIP LOCKED select must skip the locked row while it is held
        await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))
        await session.commit()

    assert not await row_exists(migrated_db, free_id)  # unlocked stale row swept
    assert await row_exists(migrated_db, locked_id)  # locked row skipped
    assert locked_key not in object_store.deleted_keys

    await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))
    assert not await row_exists(migrated_db, locked_id)  # swept once the lock is gone
    assert locked_key in object_store.deleted_keys


async def test_sweep_leaves_fresh_unready_row_and_object_untouched(migrated_db) -> None:
    document_id, storage_key = await seed_document(migrated_db, age_seconds=10.0, name="fresh.md")
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# still uploading")
    logger = RecordingLogger()

    await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))

    assert await row_exists(migrated_db, document_id)
    assert storage_key not in object_store.deleted_keys
    async with migrated_db.session_factory() as session:
        row = await session.get(Document, document_id)
        assert row.dispatch_ready is False  # not locked, not flipped, not swept
        assert row.status == "pending"


async def test_sweep_never_touches_ready_rows_even_with_missing_object(migrated_db) -> None:
    ready_id, ready_key = await seed_document(
        migrated_db, ready=True, age_seconds=400.0, name="ready.md"
    )
    object_store = FakeObjectStore()  # object deliberately missing
    logger = RecordingLogger()

    await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))

    assert await row_exists(migrated_db, ready_id)  # process-owned, not swept
    async with migrated_db.session_factory() as session:
        row = await session.get(Document, ready_id)
        assert row.status == "pending"  # not failed, not deleted: the worker owns it
        assert row.dispatch_ready is True


async def test_sweep_exhaustion_alerts_and_keeps_marker_row(migrated_db) -> None:
    document_id, storage_key = await seed_document(migrated_db, name="stuck.md")
    object_store = FailingDeleteStore()
    object_store.put(storage_key, b"# cannot clean")
    logger = RecordingLogger()

    await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))

    assert await row_exists(migrated_db, document_id)  # marker row kept
    assert len(logger.errors) == 2
    assert str(document_id) in logger.errors[0]  # alert carries the correlation id
    assert "sweep marker" in logger.errors[0]
    assert "sweep backlog alert" in logger.errors[1]  # the row still remains
    assert "remaining_stale_unready=1" in logger.errors[1]


async def test_pending_age_alert_logs_old_pending_rows_with_correlation(migrated_db) -> None:
    old_id, old_key = await seed_document(
        migrated_db, ready=True, age_seconds=1000.0, name="old.md"
    )
    fresh_id, fresh_key = await seed_document(
        migrated_db, ready=True, age_seconds=10.0, name="fresh.md"
    )
    object_store = FakeObjectStore()
    object_store.put(old_key, b"# old")
    object_store.put(fresh_key, b"# fresh")
    logger = RecordingLogger()

    await alert_stale_pending(sweep_ctx(migrated_db, object_store, logger))

    assert len(logger.errors) == 1  # only the row older than pending_age_seconds
    assert "pending age alert" in logger.errors[0]
    assert str(old_id) in logger.errors[0]
    assert str(fresh_id) not in logger.errors[0]


async def test_pending_age_alert_ignores_non_pending_rows(migrated_db) -> None:
    indexed_id, indexed_key = await seed_document(
        migrated_db, ready=True, age_seconds=1000.0, name="indexed.md"
    )
    object_store = FakeObjectStore()
    object_store.put(indexed_key, b"# indexed")
    logger = RecordingLogger()

    async with migrated_db.session_factory() as session:
        row = await session.get(Document, indexed_id)
        row.status = "indexed"
        await session.commit()

    await alert_stale_pending(sweep_ctx(migrated_db, object_store, logger))

    assert logger.errors == []  # only pending rows age-alert


async def test_sweep_backlog_alert_when_batch_is_saturated(migrated_db) -> None:
    first_id, first_key = await seed_document(migrated_db, name="one.md")
    second_id, second_key = await seed_document(migrated_db, name="two.md")
    object_store = FakeObjectStore()
    object_store.put(first_key, b"# one")
    object_store.put(second_key, b"# two")
    logger = RecordingLogger()
    ctx = sweep_ctx(migrated_db, object_store, logger)
    ctx["settings"] = WorkerSettings(sweep_batch_size=1)

    await sweep_stale_unready(ctx)

    assert not await row_exists(migrated_db, first_id)  # swept
    assert await row_exists(migrated_db, second_id)  # backlog remains
    assert len(logger.errors) == 1
    assert "sweep backlog alert" in logger.errors[0]
    assert "remaining_stale_unready=1" in logger.errors[0]


async def test_sweep_no_backlog_alert_when_fully_drained(migrated_db) -> None:
    document_id, storage_key = await seed_document(migrated_db, name="only.md")
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# only")
    logger = RecordingLogger()
    ctx = sweep_ctx(migrated_db, object_store, logger)
    ctx["settings"] = WorkerSettings(sweep_batch_size=1)

    await sweep_stale_unready(ctx)

    assert not await row_exists(migrated_db, document_id)
    assert logger.errors == []  # nothing remains: no backlog


async def test_pending_age_alert_runs_inside_the_sweep_cron(migrated_db) -> None:
    document_id, storage_key = await seed_document(
        migrated_db, ready=True, age_seconds=1000.0, name="stuck-pending.md"
    )
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# stuck pending")
    logger = RecordingLogger()

    await sweep_stale_unready(sweep_ctx(migrated_db, object_store, logger))

    assert len(logger.errors) == 1
    assert "pending age alert" in logger.errors[0]
    assert str(document_id) in logger.errors[0]
