"""Disposable migrated evaluation database lifecycle (ODD-2).

Each evaluation run gets a uniquely named PostgreSQL database created from an
AUTOCOMMIT admin engine, migrated to Alembic head through
``apps/api/alembic.ini`` (resolved from this file's location, never from the
caller's working directory), and dropped with ``WITH (FORCE)`` from a
``finally`` path so cleanup survives seeding and assertion failures.

Production API models and migrations are read-only seams here: this module
only creates/drops the database and runs the existing migrations. Connection
state is kept out of ``repr`` and is never logged or serialized.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

EVAL_DATABASE_NAME_RE = re.compile(r"raguard_eval_[0-9a-f]{12}")
ALEMBIC_INI_PATH = Path(__file__).resolve().parents[4] / "apps" / "api" / "alembic.ini"


@dataclass
class EvaluationDatabase:
    """An open, migrated, disposable evaluation database."""

    engine: AsyncEngine = field(repr=False)
    session_factory: async_sessionmaker = field(repr=False)
    database_name: str


def generate_eval_database_name() -> str:
    """Return a unique ``raguard_eval_<12 lowercase hex chars>`` database name."""
    return f"raguard_eval_{secrets.token_hex(6)}"


def eval_admin_url() -> str:
    """Admin URL from TEST_DATABASE_URL or the local compose POSTGRES_* defaults."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "raguard")
    secret = os.environ.get("POSTGRES_PASSWORD", "change-me")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "raguard")
    return f"postgresql+psycopg://{user}:{secret}@{host}:{port}/{database}"


def _with_database(admin_url: str, database_name: str) -> str:
    """Swap the database while preserving driver, userinfo, host, port, and query."""
    url = make_url(admin_url).set(database=database_name)
    return url.render_as_string(hide_password=False)


async def _upgrade_to_head(database_url: str) -> None:
    """Run the production Alembic migrations to head against ``database_url``."""
    cfg = Config(str(ALEMBIC_INI_PATH))
    # Alembic options pass through configparser interpolation, where a bare
    # ``%`` (including percent-encoded userinfo) is a syntax error; ``%%``
    # reads back as the identical value.
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    await asyncio.to_thread(command.upgrade, cfg, "head")


@asynccontextmanager
async def evaluation_database(*, admin_url: str | None = None) -> AsyncIterator[EvaluationDatabase]:
    """Yield a fresh migrated evaluation database; always force-drop it on exit."""
    admin = admin_url or eval_admin_url()
    database_name = generate_eval_database_name()

    setup_engine = create_async_engine(admin, isolation_level="AUTOCOMMIT")
    try:
        async with setup_engine.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await setup_engine.dispose()

    engine = create_async_engine(_with_database(admin, database_name))
    try:
        await _upgrade_to_head(engine.url.render_as_string(hide_password=False))
        yield EvaluationDatabase(
            engine=engine,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            database_name=database_name,
        )
    finally:
        await engine.dispose()
        drop_engine = create_async_engine(admin, isolation_level="AUTOCOMMIT")
        try:
            async with drop_engine.connect() as conn:
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)'))
        finally:
            await drop_engine.dispose()
