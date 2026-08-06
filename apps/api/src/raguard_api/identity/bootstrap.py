"""Env-driven first-tenant bootstrap (task 4.4).

Reads bootstrap settings exclusively from the environment, validates them
before any write, and under a transaction advisory lock creates the first
tenant, the default roles, and the admin membership in one atomic transaction —
or exits successfully without altering existing identity data when identity
data already exists. Re-running is idempotent. Secrets come only from
environment variables, never argv, and are never echoed in validation errors,
logs, or output (emails are existence hints and are excluded from logs too).
"""

import asyncio
import logging
import os
import sys
import zlib
from collections.abc import Mapping

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.auth.passwords import hash_password
from raguard_api.authorization.capabilities import DEFAULT_ROLE_CAPABILITIES
from raguard_api.db import create_engine, create_session_factory, get_database_url
from raguard_api.identity.models import Membership, Role, Tenant, User

logger = logging.getLogger(__name__)

BOOTSTRAP_TENANT_NAME = "BOOTSTRAP_TENANT_NAME"
BOOTSTRAP_ADMIN_EMAIL = "BOOTSTRAP_ADMIN_EMAIL"
BOOTSTRAP_ADMIN_PASSWORD = "BOOTSTRAP_ADMIN_PASSWORD"
MIN_ADMIN_PASSWORD_LENGTH = 12

# Stable advisory-lock key serializing concurrent bootstrap runs per database.
_BOOTSTRAP_LOCK_KEY = zlib.crc32(b"raguard-bootstrap")


class BootstrapConfigError(Exception):
    """Bootstrap environment is invalid; nothing was written."""


def read_bootstrap_env(env: Mapping[str, str] | None = None) -> tuple[str, str, str]:
    """Validate the bootstrap environment and return (tenant, email, password).

    Messages are generic so rejected values (including secrets) are never
    echoed to callers, logs, or stderr.
    """
    values = os.environ if env is None else env
    tenant_name = (values.get(BOOTSTRAP_TENANT_NAME) or "").strip()
    email = (values.get(BOOTSTRAP_ADMIN_EMAIL) or "").strip().lower()
    password = values.get(BOOTSTRAP_ADMIN_PASSWORD) or ""
    if not tenant_name:
        raise BootstrapConfigError(f"{BOOTSTRAP_TENANT_NAME} must not be empty")
    if "@" not in email or " " in email:
        raise BootstrapConfigError(f"{BOOTSTRAP_ADMIN_EMAIL} must be a valid email address")
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise BootstrapConfigError(
            f"{BOOTSTRAP_ADMIN_PASSWORD} must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters"
        )
    return tenant_name, email, password


async def run_bootstrap(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    tenant_name: str,
    admin_email: str,
    admin_password: str,
) -> bool:
    """Create the first tenant, default roles, and admin; return True when created.

    Runs in one transaction under ``pg_advisory_xact_lock``: concurrent runs
    serialize, the existence check happens inside the lock, and any failure
    rolls back the whole transaction. Returns False (no writes) when identity
    data already exists.
    """
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _BOOTSTRAP_LOCK_KEY}
            )
            if (await session.execute(select(Tenant.id).limit(1))).first() is not None:
                logger.info("bootstrap complete: identity data already exists, no changes made")
                return False
            tenant = Tenant(name=tenant_name)
            session.add(tenant)
            await session.flush()
            roles = {}
            for name, capabilities in DEFAULT_ROLE_CAPABILITIES.items():
                role = Role(
                    tenant_id=tenant.id,
                    name=name,
                    capabilities=sorted(capabilities),
                )
                session.add(role)
                roles[name] = role
            await session.flush()
            user = User(email=admin_email, password_hash=hash_password(admin_password))
            session.add(user)
            await session.flush()
            session.add(
                Membership(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    role_id=roles["admin"].id,
                )
            )
    logger.info("bootstrap complete: first tenant, default roles, and admin created")
    return True


def main() -> int:
    """CLI entrypoint: read the environment, run the bootstrap, return an exit code.

    Exit codes: 0 success or no-op, 2 invalid environment (nothing written),
    1 runtime failure. Secrets only ever come from environment variables.
    """
    try:
        tenant_name, admin_email, admin_password = read_bootstrap_env()
    except BootstrapConfigError as exc:
        print(f"raguard-bootstrap: {exc}", file=sys.stderr)
        return 2
    try:
        engine = create_engine(get_database_url())
    except RuntimeError as exc:
        print(f"raguard-bootstrap: {exc}", file=sys.stderr)
        return 2

    async def _run() -> None:
        try:
            await run_bootstrap(
                session_factory=create_session_factory(engine),
                tenant_name=tenant_name,
                admin_email=admin_email,
                admin_password=admin_password,
            )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("bootstrap failed")
        return 1
    return 0
