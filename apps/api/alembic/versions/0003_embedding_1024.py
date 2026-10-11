"""Resize chunks.embedding HNSW from halfvec(1536) to halfvec(1024).

Revision ID: 0003
Revises: 0002

Fail-closed MVP behavior: 1536-dim vectors cannot be converted to 1024 dims
without re-embedding from source, so both directions refuse to run when any
chunk row exists instead of silently truncating, padding, or deleting
production vectors. The operator must reindex/re-upload from source on an
empty chunks table. Empty tables migrate by dropping the HNSW index, altering
the column typmod, and recreating the HNSW index with the same parameters.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_HNSW_SQL = (
    "CREATE INDEX ix_chunks_embedding ON chunks "
    "USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)"
)

_UPGRADE_BLOCKED = (
    "REFUSING chunks.embedding resize 1536 -> 1024: "
    "chunks holds existing rows whose 1536-dim vectors are invalid at 1024 dims. "
    "Reindex/re-upload from source on an empty chunks table, then retry this migration."
)
_DOWNGRADE_BLOCKED = (
    "REFUSING chunks.embedding resize 1024 -> 1536: "
    "chunks holds existing rows whose 1024-dim vectors are invalid at 1536 dims. "
    "Reindex/re-upload from source on an empty chunks table, then retry this migration."
)


def _chunk_row_count() -> int:
    connection = op.get_bind()
    return connection.execute(sa.text("SELECT count(*) FROM chunks")).scalar_one()


def upgrade() -> None:
    if _chunk_row_count() > 0:
        raise RuntimeError(_UPGRADE_BLOCKED)
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(1024)")
    op.execute(_HNSW_SQL)


def downgrade() -> None:
    if _chunk_row_count() > 0:
        raise RuntimeError(_DOWNGRADE_BLOCKED)
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(1536)")
    op.execute(_HNSW_SQL)
