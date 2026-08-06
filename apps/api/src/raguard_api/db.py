"""Async SQLAlchemy engine, session factory, and declarative base (task 1.3).

The module exposes factories instead of module-level singletons so tests can
build engines per disposable database; request-scoped wiring arrives with the
config slice (PR 2).
"""

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_database_url() -> str:
    """Return the PostgreSQL URL from the DATABASE_URL environment variable."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    return url


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async engine for the given PostgreSQL URL."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
