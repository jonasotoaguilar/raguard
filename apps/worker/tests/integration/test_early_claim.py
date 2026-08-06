"""Integration: early claim before the ready commit waits and then indexes (task 3.3 RED).

The API enqueues the deterministic ``ingest:{document_id}`` job, then commits
``dispatch_ready`` right before responding, so a worker may claim the job in
that window. The job must poll (bounded, unlocked), observe the ready commit,
and then index on its first attempt — no ingestion/provider retry consumption
(single job_try, single parser/embedder calls) — against the real
SqlAlchemyDispatchStore and Postgres.
"""

import asyncio
import uuid

import pytest
from raguard_api.documents.contracts import FakeEmbedder, FakeObjectStore, FakeParser
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import Tenant
from raguard_worker.jobs import SqlAlchemyDispatchStore, ingest_document
from raguard_worker.settings import WorkerSettings
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def _seed_unready_document(db) -> tuple[uuid.UUID, str]:
    async with db.session_factory() as session:
        tenant = Tenant(name="Tenant Early Claim")
        session.add(tenant)
        await session.flush()
        document_id = uuid.uuid4()
        storage_key = f"{tenant.id}/{document_id}/early.md"
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant.id,
                name="early.md",
                status="pending",
                storage_key=storage_key,
            )
        )
        await session.commit()
        return document_id, storage_key


async def _commit_ready(db, document_id: uuid.UUID) -> None:
    async with db.session_factory() as session:
        row = await session.get(Document, document_id)
        row.dispatch_ready = True
        await session.commit()


async def test_early_claim_waits_for_ready_commit_then_indexes_without_retries(
    migrated_db,
) -> None:
    document_id, storage_key = await _seed_unready_document(migrated_db)
    object_store = FakeObjectStore()
    object_store.put(storage_key, b"# early claim\n\nsecond line")
    calls = {"parse": 0, "embed": 0}

    class CountingParser(FakeParser):
        def parse(self, data: bytes) -> str:
            calls["parse"] += 1
            return super().parse(data)

    class CountingEmbedder(FakeEmbedder):
        def embed(self, texts):
            calls["embed"] += 1
            return super().embed(texts)

    ctx = {
        "settings": WorkerSettings(dispatch_wait_seconds=2.0, dispatch_poll_interval_seconds=0.02),
        "store": SqlAlchemyDispatchStore(migrated_db.session_factory),
        "object_store": object_store,
        "parser": CountingParser(),
        "embedder": CountingEmbedder(),
        "chunker": lambda text: [line for line in text.splitlines() if line.strip()],
        "job_try": 1,
    }
    task = asyncio.create_task(ingest_document(ctx, str(document_id)))

    await asyncio.sleep(0.4)  # the job claimed the row and is polling while unready
    async with migrated_db.session_factory() as session:
        row = await session.get(Document, document_id)
        assert row.status == "pending"  # nothing processed before the ready commit

    await _commit_ready(migrated_db, document_id)
    await asyncio.wait_for(task, timeout=10)
    assert task.exception() is None

    async with migrated_db.session_factory() as session:
        row = await session.get(Document, document_id)
        assert row.status == "indexed"
        assert row.failure_reason is None
        chunks = (
            (await session.execute(select(Chunk).where(Chunk.document_id == document_id)))
            .scalars()
            .all()
        )
        assert [(chunk.position, chunk.content) for chunk in chunks] == [
            (0, "# early claim"),
            (1, "second line"),
        ]
    assert calls == {"parse": 1, "embed": 1}  # no retry consumption
