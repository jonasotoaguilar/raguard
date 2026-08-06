"""Shared worker-test fixtures: unit dispatch fakes and migrated PostgreSQL.

The in-memory DispatchStore/Claim fakes drive the job's state machine without
a database; the ``migrated_db`` fixture (same pattern as the API suite)
exercises the real SqlAlchemyDispatchStore against a disposable database
migrated to head and dropped afterwards.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from raguard_api.documents.contracts import FakeEmbedder, FakeObjectStore, FakeParser
from raguard_worker.jobs import DocumentState, NewChunk
from raguard_worker.settings import WorkerSettings
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

API_DIR = Path(__file__).resolve().parents[2] / "api"


def _test_admin_url() -> str:
    """Admin URL from TEST_DATABASE_URL or the local compose POSTGRES_* defaults."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "raguard")
    password = os.environ.get("POSTGRES_PASSWORD", "change-me")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "raguard")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


def _with_database(admin_url: str, database_name: str) -> str:
    base, _slash, _db = admin_url.rpartition("/")
    return f"{base}/{database_name}"


@dataclass
class MigratedDatabase:
    """A disposable database migrated to head, with an Alembic runner bound to it."""

    engine: AsyncEngine
    session_factory: async_sessionmaker
    database_name: str

    async def alembic(self, direction: str, revision: str) -> None:
        cfg = Config(str(API_DIR / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", self.engine.url.render_as_string(hide_password=False))
        fn = command.upgrade if direction == "up" else command.downgrade
        await asyncio.to_thread(fn, cfg, revision)


@pytest.fixture
async def migrated_db() -> AsyncIterator[MigratedDatabase]:
    """Yield a fresh migrated database per test and drop it afterwards."""
    admin_url = _test_admin_url()
    database_name = f"raguard_test_{uuid.uuid4().hex[:12]}"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL unavailable ({exc.__class__.__name__}); start the local stack")
    finally:
        await admin_engine.dispose()

    engine = create_async_engine(_with_database(admin_url, database_name))
    database = MigratedDatabase(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        database_name=database_name,
    )
    try:
        await database.alembic("up", "head")
        yield database
    finally:
        await engine.dispose()
        admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with admin_engine.connect() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        finally:
            await admin_engine.dispose()


def state(
    *,
    ready: bool = True,
    status: str = "pending",
    created_at: datetime | None = None,
    failed_reason: str | None = None,
) -> DocumentState:
    return DocumentState(
        document_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="notes.md",
        status=status,
        failure_reason=failed_reason,
        dispatch_ready=ready,
        storage_key=f"{uuid.uuid4()}/notes.md",
        # Call-time now: module-level constants age past the 30s freshness
        # window when the full suite runs long, flipping fresh rows to stale.
        created_at=created_at or datetime.now(UTC),
    )


def stale_state(**kwargs) -> DocumentState:
    return state(created_at=datetime.now(UTC) - timedelta(seconds=400), **kwargs)


class FakeClaim:
    """In-memory DocumentClaim recording every commit for behavioral asserts."""

    def __init__(self, document_state: DocumentState | None) -> None:
        self.state = document_state
        self.indexed_calls: list[list[NewChunk]] = []
        self.failed_calls: list[str] = []
        self.closed = False

    async def commit_indexed(self, chunks) -> None:
        self.indexed_calls.append(list(chunks))

    async def commit_failed(self, reason: str) -> None:
        self.failed_calls.append(reason)

    async def close(self) -> None:
        self.closed = True


class FakeDispatchStore:
    """In-memory DispatchStore; fetch returns states[i] (last repeats)."""

    def __init__(self, states: list[DocumentState | None] | None, claim: FakeClaim | None) -> None:
        self._states = states
        self.claim = claim
        self.fetch_count = 0
        self.lock_calls: list[uuid.UUID] = []

    async def fetch(self, document_id: uuid.UUID) -> DocumentState | None:
        if self._states is None:
            return self.claim.state if self.claim else None
        index = min(self.fetch_count, len(self._states) - 1)
        self.fetch_count += 1
        return self._states[index]

    async def lock_for_process(self, document_id: uuid.UUID) -> FakeClaim | None:
        self.lock_calls.append(document_id)
        return self.claim


def ctx(*, claim: FakeClaim | None = None, states: list[DocumentState | None] | None = None):
    store = FakeDispatchStore(states, claim)
    return {
        "settings": WorkerSettings(dispatch_wait_seconds=0.05, dispatch_poll_interval_seconds=0.01),
        "store": store,
        "object_store": FakeObjectStore(),
        "parser": FakeParser(),
        "embedder": FakeEmbedder(),
        "chunker": lambda text: text.splitlines(),
        "job_try": 1,
    }


class RecordingLogger:
    """Observability seam (PR5): records formatted log lines instead of emitting."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.infos: list[str] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append(message % args)

    def info(self, message: str, *args: object) -> None:
        self.infos.append(message % args)


@pytest.fixture
def claim() -> FakeClaim:
    return FakeClaim(state())


@pytest.fixture
def recording_logger() -> RecordingLogger:
    return RecordingLogger()


@pytest.fixture
def env(claim: FakeClaim) -> dict:
    return ctx(claim=claim)


@pytest.fixture
def object_store() -> FakeObjectStore:
    return FakeObjectStore()
