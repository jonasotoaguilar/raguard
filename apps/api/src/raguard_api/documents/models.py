"""Document and chunk ORM models mirroring migration 0002 (task 1.4).

Constraints mirror apps/api/alembic/versions/0002_documents_chunks.py exactly:
- documents: status restricted to the public enum, failure_reason restricted to
  the DESIGN.md allowlist, (tenant_id, id) unique backing the chunks composite
  FK, tenant-leading indexes for scoped status reads and sweep freshness;
- chunks: one position per document, composite tenant+document FK preventing
  cross-tenant chunk attachment, halfvec(1536) embeddings with an HNSW cosine
  index, and a generated tsvector search column covered by a GIN index.

Internal readiness (dispatch_ready) and storage keys live only here, never on
the public contract surface (raguard_api.documents.contracts).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from raguard_api.db import Base
from raguard_api.documents.contracts import (
    EMBEDDING_DIMENSION,
    FAILURE_REASONS,
    DocumentStatus,
)

# Single source for the CHECK expressions: generated from the public enum and
# the design's allowlist so the ORM and the contract vocabulary cannot drift.
_DOCUMENT_STATUS_SQL = "status IN (" + ", ".join(f"'{s.value}'" for s in DocumentStatus) + ")"
_FAILURE_REASON_ALLOWLIST_SQL = (
    "failure_reason IS NULL OR failure_reason IN ("
    + ", ".join(f"'{reason}'" for reason in FAILURE_REASONS)
    + ")"
)
_SEARCH_VECTOR_SQL = "to_tsvector('simple'::regconfig, content)"


class Document(Base):
    """One uploaded document, tenant-scoped, with a lifecycle and dispatch gate."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_DOCUMENT_STATUS_SQL, name="ck_documents_status"),
        CheckConstraint(_FAILURE_REASON_ALLOWLIST_SQL, name="ck_documents_failure_reason"),
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index("ix_documents_tenant_created_at", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", name="fk_documents_tenant_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=DocumentStatus.pending.value)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatch_ready: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Chunk(Base):
    """One indexed chunk of a document: content, embedding, and search vector."""

    __tablename__ = "chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_chunks_tenant_document",
        ),
        UniqueConstraint("document_id", "position", name="uq_chunks_document_position"),
        Index("ix_chunks_tenant_document", "tenant_id", "document_id"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", name="fk_chunks_tenant_id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", name="fk_chunks_document_id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(HALFVEC(EMBEDDING_DIMENSION), nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(_SEARCH_VECTOR_SQL, persisted=True),
        nullable=False,
    )
