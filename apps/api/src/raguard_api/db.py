"""Async SQLAlchemy engine, session factory, and declarative base (task 1.3).

F5 adds opt-in RLS defense-in-depth wiring: an ``after_begin`` listener sets
``SET LOCAL app.tenant_id`` when the session carries a tenant, plus the
``tenant_scoped_session`` helper. The default path (plain
``session_factory()`` with no tenant in ``session.info``) is a no-op, so the
existing routers and the owner-based behavior are unchanged.
"""

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


#: Postgres GUC carrying the request tenant for RLS policies. Empty/unset
#: means "no tenant context" (policies match nothing for the app role; the
#: table owner still bypasses RLS, preserving the current default behavior).
TENANT_GUC = "app.tenant_id"

#: ``AsyncSession.info`` key holding the tenant UUID string for this session.
TENANT_INFO_KEY = "tenant_id"


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


def _coerce_tenant_id(tenant_id: uuid.UUID | str) -> str:
    """Validate the tenant as a UUID and return its canonical string form."""
    try:
        return str(uuid.UUID(str(tenant_id)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"invalid tenant_id for RLS session scope: {tenant_id!r}") from exc


def set_session_tenant(session: Any, tenant_id: uuid.UUID | str) -> None:
    """Attach a tenant UUID to a session's ``info`` (opt-in RLS scope)."""
    session.info[TENANT_INFO_KEY] = _coerce_tenant_id(tenant_id)


def get_session_tenant(session: Any) -> str | None:
    """Return the tenant UUID string attached to a session, if any."""
    return session.info.get(TENANT_INFO_KEY)


def clear_session_tenant(session: Any) -> None:
    """Remove any tenant scope from a session, restoring the default no-op."""
    session.info.pop(TENANT_INFO_KEY, None)


def _after_begin_set_tenant(session: Any, transaction: Any, connection: Any) -> None:
    """``after_begin`` hook: ``SET LOCAL app.tenant_id`` when scoped.

    No-op when the session carries no tenant, so plain ``session_factory()``
    usage (all existing routers) behaves exactly as before. The value is a
    validated UUID string, safe to interpolate into the ``SET LOCAL`` literal.
    """
    tenant_id = get_session_tenant(session)
    if tenant_id is None:
        return
    connection.execute(text(f"SET LOCAL {TENANT_GUC} = '{tenant_id}'"))


# Registered on the sync Session class backing AsyncSession, so the hook fires
# for async sessions too. It stays a no-op unless the session carries a tenant.
event.listens_for(AsyncSession.sync_session_class, "after_begin")(_after_begin_set_tenant)


@asynccontextmanager
async def tenant_scoped_session(
    session_factory: Any, tenant_id: uuid.UUID | str
) -> AsyncIterator[Any]:
    """Yield one session scoped to ``tenant_id`` for RLS (opt-in).

    The tenant is stored in ``session.info`` before any statement runs, so the
    ``after_begin`` listener applies ``SET LOCAL`` when the first transaction
    begins. Callers that never use this helper keep the current behavior.
    """
    async with session_factory() as session:
        set_session_tenant(session, tenant_id)
        yield session
