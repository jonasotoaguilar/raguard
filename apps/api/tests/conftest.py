"""Shared integration-test fixtures: disposable migrated PostgreSQL databases (task 1.6).

Every test that needs a real database gets a fresh, function-scoped database
created by this fixture, migrated to head via Alembic, and dropped afterwards —
isolation is per test, never shared.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

API_DIR = Path(__file__).resolve().parents[1]


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
        """Run an Alembic upgrade/downgrade against this database."""
        cfg = Config(str(API_DIR / "alembic.ini"))
        # str(engine.url) masks the password; render explicitly for the option.
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
