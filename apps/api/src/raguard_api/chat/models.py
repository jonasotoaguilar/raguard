"""Conversation and message ORM models mirroring migration 0004 (F2).

Constraints mirror apps/api/alembic/versions/0004_conversations_messages.py exactly:
- conversations: tenant+user scoped threads with a title, (tenant_id, id)
  unique backing the messages composite FK, tenant-leading index for
  recency-ordered listing, BIGSERIAL ``seq`` as the deterministic
  newest-first tiebreak;
- messages: role restricted to the user/assistant allowlist, citations as a
  JSONB payload defaulting to '[]', composite tenant+conversation FK
  preventing cross-tenant message attachment, conversation-leading index for
  chronological reads, per-conversation ``position`` (unique per
  conversation) as the chronological order key.

Tenant and user identity live only here, never on the public contract surface
(raguard_api.chat.contracts).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Sequence,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from raguard_api.db import Base

# Single source for the CHECK expression: the role allowlist shared by the
# ORM and the migration so the two cannot drift.
_MESSAGE_ROLE_SQL = "role IN ('user', 'assistant')"


class Conversation(Base):
    """One persisted chat thread, scoped to a single tenant+user pair."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
        Index("ix_conversations_tenant_user_updated", "tenant_id", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", name="fk_conversations_tenant_id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", name="fk_conversations_user_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(
        BigInteger,
        Sequence("conversations_seq", optional=True),
        server_default=text("nextval('conversations_seq')"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Message(Base):
    """One persisted turn row: a user query or an assistant answer with citations."""

    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_tenant_conversation",
        ),
        CheckConstraint(_MESSAGE_ROLE_SQL, name="ck_messages_role"),
        UniqueConstraint("conversation_id", "position", name="uq_messages_conversation_position"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", name="fk_messages_tenant_id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", name="fk_messages_conversation_id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
