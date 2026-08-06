"""Integration: transient stage failures defer via arq Retry, then terminal failed.

Corrective remediation for the verified production gap: arq 0.28 does not
re-queue jobs that raise plain exceptions, so a transient parser/embedder
failure re-raised from ``ingest_document`` terminal-failed at the arq level and
the document stayed ``pending`` instead of reaching bounded ``failed``. These
tests prove the corrected contract against the real ``SqlAlchemyDispatchStore``
and Postgres:

- a transient parser/embedder failure at a non-terminal ``job_try`` raises the
  bounded ``TransientStageFailure`` (an ``arq.worker.Retry`` the worker
  requeues) without writing any status or chunks and with the row lock
  released;
- at the terminal ``job_try`` the allowlisted reason is committed (parse ->
  ``failed/malformed``, embed -> ``failed/limit``) with zero chunks;
- fresh-unready dispatch deferrals keep their existing ``DispatchNotReady``
  semantics.
"""

import uuid

import pytest
from arq.worker import Retry
from raguard_api.documents.contracts import FakeEmbedder, FakeObjectStore, FakeParser
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import Tenant
from raguard_worker.jobs import (
    DispatchNotReady,
    SqlAlchemyDispatchStore,
    TransientStageFailure,
    ingest_document,
)
from raguard_worker.settings import WorkerSettings
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


class FailingParser:
    def parse(self, data: bytes) -> str:
        raise RuntimeError("parse failed")


class FailingEmbedder:
    def embed(self, texts) -> list[list[float]]:
        raise RuntimeError("embed failed")


async def _seed_document(db, *, ready: bool = True) -> tuple[uuid.UUID, str]:
    async with db.session_factory() as session:
        tenant = Tenant(name="Tenant Transient Retry")
        session.add(tenant)
        await session.flush()
        document_id = uuid.uuid4()
        storage_key = f"{tenant.id}/{document_id}/transient.md"
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant.id,
                name="transient.md",
                status="pending",
                dispatch_ready=ready,
                storage_key=storage_key,
            )
        )
        await session.commit()
        return document_id, storage_key


async def _row(db, document_id: uuid.UUID) -> tuple[str, str | None]:
    async with db.session_factory() as session:
        row = await session.get(Document, document_id)
        return row.status, row.failure_reason


async def _chunk_count(db, document_id: uuid.UUID) -> int:
    async with db.session_factory() as session:
        return (
            await session.execute(
                select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
            )
        ).scalar_one()


def _ctx(db, **overrides: object) -> dict:
    ctx = {
        "settings": WorkerSettings(dispatch_wait_seconds=0.05, dispatch_poll_interval_seconds=0.01),
        "store": SqlAlchemyDispatchStore(db.session_factory),
        "object_store": FakeObjectStore(),
        "parser": FakeParser(),
        "embedder": FakeEmbedder(),
        "chunker": lambda text: text.splitlines(),
        "job_try": 1,
    }
    ctx.update(overrides)
    return ctx


async def test_transient_parse_failure_defers_then_terminates_failed_malformed(
    migrated_db,
) -> None:
    document_id, storage_key = await _seed_document(migrated_db)
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# transient\n\nbody")
    ctx = _ctx(
        migrated_db,
        object_store=object_store,
        parser=FailingParser(),
        job_try=1,  # non-terminal: the job must requeue, not terminal-fail
    )

    with pytest.raises(TransientStageFailure) as excinfo:
        await ingest_document(ctx, str(document_id))

    assert isinstance(excinfo.value, Retry)  # arq 0.28 requeues Retry exceptions
    assert excinfo.value.defer_score >= 0
    assert await _row(migrated_db, document_id) == ("pending", None)  # no failed write yet
    assert await _chunk_count(migrated_db, document_id) == 0  # no partial chunks

    ctx["job_try"] = 10  # terminal: the allowlisted reason is committed
    assert await ingest_document(ctx, str(document_id)) is None

    assert await _row(migrated_db, document_id) == ("failed", "malformed")
    assert await _chunk_count(migrated_db, document_id) == 0


async def test_transient_embed_failure_defers_then_terminates_failed_limit(migrated_db) -> None:
    document_id, storage_key = await _seed_document(migrated_db)
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# transient\n\nbody")
    ctx = _ctx(
        migrated_db,
        object_store=object_store,
        embedder=FailingEmbedder(),
        job_try=1,
    )

    with pytest.raises(TransientStageFailure) as excinfo:
        await ingest_document(ctx, str(document_id))

    assert isinstance(excinfo.value, Retry)
    assert await _row(migrated_db, document_id) == ("pending", None)
    assert await _chunk_count(migrated_db, document_id) == 0

    ctx["job_try"] = 10
    assert await ingest_document(ctx, str(document_id)) is None

    assert await _row(migrated_db, document_id) == ("failed", "limit")
    assert await _chunk_count(migrated_db, document_id) == 0


async def test_fresh_unready_dispatch_deferral_keeps_existing_semantics(migrated_db) -> None:
    document_id, _storage_key = await _seed_document(migrated_db, ready=False)

    with pytest.raises(DispatchNotReady):
        await ingest_document(_ctx(migrated_db), str(document_id))

    assert await _row(migrated_db, document_id) == ("pending", None)
    assert await _chunk_count(migrated_db, document_id) == 0
