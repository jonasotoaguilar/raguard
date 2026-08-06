"""Create documents and chunks tables with embeddings and search indexes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

Mirrors the ORM constraints in apps/api/src/raguard_api/documents/models.py:
status enum, allowlisted failure reasons, tenant-id+id uniqueness backing the
chunks composite FK, unique chunk positions, halfvec(1536) embeddings with an
HNSW cosine index, and a generated tsvector search column with a GIN index.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

# Frozen inline copies of the ORM CHECK expressions (same convention as 0001).
_DOCUMENT_STATUS_SQL = "status IN ('pending', 'indexed', 'failed')"
_FAILURE_REASON_ALLOWLIST_SQL = (
    "failure_reason IS NULL OR failure_reason IN "
    "('malformed', 'encrypted', 'limit', 'source_missing')"
)
_SEARCH_VECTOR_SQL = "to_tsvector('simple'::regconfig, content)"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("dispatch_ready", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_documents_tenant_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        sa.CheckConstraint(_DOCUMENT_STATUS_SQL, name="ck_documents_status"),
        sa.CheckConstraint(_FAILURE_REASON_ALLOWLIST_SQL, name="ck_documents_failure_reason"),
    )
    op.create_index("ix_documents_tenant_status", "documents", ["tenant_id", "status"])
    op.create_index("ix_documents_tenant_created_at", "documents", ["tenant_id", "created_at"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", HALFVEC(1536), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_SEARCH_VECTOR_SQL, persisted=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_chunks_tenant_id"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name="fk_chunks_document_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_chunks_tenant_document",
        ),
        sa.UniqueConstraint("document_id", "position", name="uq_chunks_document_position"),
    )
    op.create_index("ix_chunks_tenant_document", "chunks", ["tenant_id", "document_id"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")


def downgrade() -> None:
    # Drop child tables and their indexes first; identity tables stay untouched.
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.drop_index("ix_chunks_tenant_document", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_documents_tenant_created_at", table_name="documents")
    op.drop_index("ix_documents_tenant_status", table_name="documents")
    op.drop_table("documents")
