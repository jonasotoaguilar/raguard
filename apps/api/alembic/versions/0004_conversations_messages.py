"""Create conversations and messages tables for optional chat history (F2).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11

Mirrors the ORM constraints in apps/api/src/raguard_api/chat/models.py exactly:
- conversations: tenant+user scoped threads with a title, (tenant_id, id)
  unique backing the messages composite FK, tenant-leading index for
  recency-ordered listing, plus a BIGSERIAL ``seq`` so "newest first"
  has a deterministic tiebreak when ``updated_at`` collides
  (``func.now()`` is the transaction start time, so rows written in one
  transaction share the same timestamp);
- messages: one turn row per user/assistant message with a role allowlist and
  a JSONB citations payload, composite tenant+conversation FK preventing
  cross-tenant message attachment, conversation-leading index for
  chronological reads, plus a per-conversation ``position`` (unique per
  conversation) so chronological order never depends on ``created_at``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

# Frozen inline copy of the ORM CHECK expression (same convention as 0002).
_MESSAGE_ROLE_SQL = "role IN ('user', 'assistant')"


_CONVERSATIONS_SEQ = "conversations_seq"


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence(_CONVERSATIONS_SEQ)))
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "seq",
            sa.BigInteger(),
            server_default=sa.text(f"nextval('{_CONVERSATIONS_SEQ}')"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_conversations_tenant_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_conversations_user_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
    )
    op.create_index(
        "ix_conversations_tenant_user_updated",
        "conversations",
        ["tenant_id", "user_id", "updated_at"],
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_messages_tenant_id"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_messages_conversation_id"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_tenant_conversation",
        ),
        sa.CheckConstraint(_MESSAGE_ROLE_SQL, name="ck_messages_role"),
        sa.UniqueConstraint(
            "conversation_id", "position", name="uq_messages_conversation_position"
        ),
    )
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )


def downgrade() -> None:
    # Drop child tables and their indexes first; identity tables stay untouched.
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_tenant_user_updated", table_name="conversations")
    op.drop_table("conversations")
    op.execute(sa.schema.DropSequence(sa.Sequence(_CONVERSATIONS_SEQ)))
