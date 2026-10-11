"""Tenant-agnostic chat history retention purge (G3).

Deletes ``conversations`` rows whose ``updated_at`` predates
``now() - retention_days``. Migration ``0004`` declares the messages FKs
without ``ON DELETE CASCADE``, so messages are deleted explicitly first in
the same transaction (no orphan rows, no FK violation). All values are bound
parameters via SQLAlchemy constructs — never interpolated — and logging
carries only the summary count plus the retention window, never message
content. ``retention_days <= 0`` is an explicit no-op returning 0.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from raguard_api.chat.models import Conversation, Message

logger = logging.getLogger(__name__)


def cutoff_for_retention(retention_days: int, *, now: datetime | None = None) -> datetime:
    """Return the expiry cutoff: rows with ``updated_at`` before it are stale."""
    current = now if now is not None else datetime.now(UTC)
    return current - timedelta(days=retention_days)


async def purge_expired_conversations(session_factory, retention_days: int) -> int:
    """Delete stale conversations (and their messages); return the count deleted."""
    if retention_days <= 0:
        logger.info("chat retention purge skipped: retention disabled (days=%s)", retention_days)
        return 0
    cutoff = cutoff_for_retention(retention_days)
    async with session_factory() as session:
        async with session.begin():
            expired_ids = (
                (
                    await session.execute(
                        select(Conversation.id).where(Conversation.updated_at < cutoff)
                    )
                )
                .scalars()
                .all()
            )
            if not expired_ids:
                count = 0
            else:
                await session.execute(
                    delete(Message).where(Message.conversation_id.in_(expired_ids))
                )
                result = await session.execute(
                    delete(Conversation).where(Conversation.id.in_(expired_ids))
                )
                count = result.rowcount or 0
    logger.info(
        "chat retention purge complete: deleted=%s retention_days=%s", count, retention_days
    )
    return count


def main() -> int:
    """Console-script entrypoint (``raguard-purge-chat``): purge per settings.

    Exit codes: 0 success (prints the deleted count), 2 invalid
    environment/settings, 1 runtime failure. Mirrors ``raguard-bootstrap``.
    """
    from raguard_api.config import get_settings
    from raguard_api.db import create_engine, create_session_factory, get_database_url

    try:
        retention_days = get_settings().chat_retention_days
    except Exception as exc:
        print(f"raguard-purge-chat: {exc}", file=sys.stderr)
        return 2
    try:
        engine = create_engine(get_database_url())
    except RuntimeError as exc:
        print(f"raguard-purge-chat: {exc}", file=sys.stderr)
        return 2

    async def _run() -> int:
        try:
            deleted = await purge_expired_conversations(
                create_session_factory(engine), retention_days
            )
        finally:
            await engine.dispose()
        print(f"raguard-purge-chat: deleted={deleted} retention_days={retention_days}")
        return 0

    try:
        return asyncio.run(_run())
    except Exception:
        logger.exception("chat retention purge failed")
        return 1
