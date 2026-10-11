"""Integration tests: chat history retention purge (G3).

On real migrated PostgreSQL: conversations older than the retention window
are deleted together with their messages (the 0004 FKs carry no
``ON DELETE CASCADE``, so the purge deletes messages explicitly in the same
transaction); fresh conversations and their messages survive. Tenant-agnostic:
rows from every tenant are eligible.
"""

from datetime import UTC, datetime, timedelta

import pytest
from raguard_api.chat.models import Conversation, Message
from raguard_api.chat.retention import purge_expired_conversations
from raguard_api.identity.models import Tenant, User
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def _seed_conversation(db, *, age_days: int, title: str = "thread"):
    now = datetime.now(UTC)
    async with db.session_factory() as session:
        async with session.begin():
            tenant = Tenant(name=f"tenant-{title}-{age_days}")
            user = User(email=f"{title}-{age_days}@example.com", password_hash="x")
            session.add_all([tenant, user])
            await session.flush()
            conversation = Conversation(tenant_id=tenant.id, user_id=user.id, title=title)
            session.add(conversation)
            await session.flush()
            stale = now - timedelta(days=age_days)
            conversation.updated_at = stale
            session.add(
                Message(
                    tenant_id=tenant.id,
                    conversation_id=conversation.id,
                    role="user",
                    content="hello",
                    position=0,
                )
            )
            session.add(
                Message(
                    tenant_id=tenant.id,
                    conversation_id=conversation.id,
                    role="assistant",
                    content="hi",
                    position=1,
                )
            )
            conversation_id = conversation.id
    return conversation_id


async def test_purge_deletes_only_expired_conversations_with_messages(migrated_db):
    old_id = await _seed_conversation(migrated_db, age_days=60, title="old")
    new_id = await _seed_conversation(migrated_db, age_days=1, title="new")

    deleted = await purge_expired_conversations(migrated_db.session_factory, 30)

    assert deleted == 1
    async with migrated_db.session_factory() as session:
        remaining_conversations = (await session.execute(select(Conversation.id))).scalars().all()
        assert [new_id] == list(remaining_conversations)
        remaining_messages = (await session.execute(select(func.count(Message.id)))).scalar()
        assert remaining_messages == 2
        assert (
            await session.execute(
                select(func.count(Message.id)).where(Message.conversation_id == old_id)
            )
        ).scalar() == 0


async def test_purge_disabled_is_noop(migrated_db):
    old_id = await _seed_conversation(migrated_db, age_days=60, title="stale")

    assert await purge_expired_conversations(migrated_db.session_factory, 0) == 0

    async with migrated_db.session_factory() as session:
        assert (
            await session.execute(
                select(func.count(Conversation.id)).where(Conversation.id == old_id)
            )
        ).scalar() == 1
        assert (
            await session.execute(
                select(func.count(Message.id)).where(Message.conversation_id == old_id)
            )
        ).scalar() == 2
