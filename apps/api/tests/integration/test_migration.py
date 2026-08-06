"""Integration tests: identity migration up/down and composite indexes (task 1.1).

The `migrated_db` fixture (apps/api/tests/conftest.py) provides a disposable
per-test database migrated to head; these tests assert the resulting schema and
the safe down migration.
"""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

IDENTITY_TABLES = {"tenants", "users", "roles", "memberships"}
DOCUMENT_TABLES = {"documents", "chunks"}


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    return {row["tablename"] for row in result.mappings()}


async def _index_columns(engine) -> dict[str, list[str]]:
    """Map index name -> ordered column list, read from pg_index/pg_attribute."""
    sql = text(
        """
        SELECT i.relname AS index_name,
               array_agg(a.attname ORDER BY k.ordinality) AS columns
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class t ON t.oid = ix.indrelid
        CROSS JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE t.relkind = 'r'
        GROUP BY i.relname
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(sql)
    return {row["index_name"]: list(row["columns"]) for row in result.mappings()}


async def test_up_creates_identity_tables(migrated_db):
    assert IDENTITY_TABLES <= await _table_names(migrated_db.engine)


async def test_up_creates_composite_indexes_leading_with_tenant_id(migrated_db):
    indexes = await _index_columns(migrated_db.engine)

    expected = {
        "uq_users_email": ["email"],
        "uq_roles_tenant_name": ["tenant_id", "name"],
        "uq_roles_tenant_id": ["tenant_id", "id"],
        "ix_memberships_tenant_user": ["tenant_id", "user_id"],
        "ix_memberships_tenant_role": ["tenant_id", "role_id"],
        "uq_memberships_user_tenant": ["user_id", "tenant_id"],
    }
    for name, columns in expected.items():
        assert indexes.get(name) == columns, (
            f"index {name}: expected columns {columns}, got {indexes.get(name)}"
        )


async def test_down_drops_identity_tables_without_affecting_others(migrated_db):
    async with migrated_db.engine.begin() as conn:
        await conn.execute(text("CREATE TABLE sentinel_probe (id integer PRIMARY KEY)"))

    await migrated_db.alembic("down", "base")

    remaining = await _table_names(migrated_db.engine)
    assert IDENTITY_TABLES.isdisjoint(remaining)
    assert "sentinel_probe" in remaining


async def _access_method(engine, index_name: str) -> tuple[str, str]:
    """Return (table_name, access_method) for a named index via pg_class/pg_am."""
    sql = text(
        """
        SELECT c.relname AS table_name, a.amname AS access_method
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class c ON c.oid = ix.indrelid
        JOIN pg_am a ON a.oid = i.relam
        WHERE i.relname = :index_name
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(sql, {"index_name": index_name})
        row = result.mappings().first()
    return (row["table_name"], row["access_method"])


async def _column_sql_type(engine, table_name: str, column_name: str) -> str:
    sql = text(
        """
        SELECT format_type(a.atttypid, a.atttypmod) AS column_type
        FROM pg_attribute a
        WHERE a.attrelid = CAST(:table_name AS regclass) AND a.attname = :column_name
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(sql, {"table_name": table_name, "column_name": column_name})
        row = result.mappings().first()
    return row["column_type"]


async def test_up_creates_document_tables(migrated_db):
    assert DOCUMENT_TABLES <= await _table_names(migrated_db.engine)


async def test_up_creates_document_indexes_leading_with_tenant_id(migrated_db):
    indexes = await _index_columns(migrated_db.engine)

    expected = {
        "uq_documents_tenant_id": ["tenant_id", "id"],
        "ix_documents_tenant_status": ["tenant_id", "status"],
        "ix_documents_tenant_created_at": ["tenant_id", "created_at"],
        "ix_chunks_tenant_document": ["tenant_id", "document_id"],
        "uq_chunks_document_position": ["document_id", "position"],
    }
    for name, columns in expected.items():
        assert indexes.get(name) == columns, (
            f"index {name}: expected columns {columns}, got {indexes.get(name)}"
        )


async def test_up_creates_vector_extension(migrated_db):
    async with migrated_db.engine.connect() as conn:
        result = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        row = result.mappings().first()
    assert row is not None


async def test_up_creates_halfvec_1536_embedding_column(migrated_db):
    assert await _column_sql_type(migrated_db.engine, "chunks", "embedding") == "halfvec(1536)"


async def test_up_creates_hnsw_index_on_chunks_embedding(migrated_db):
    table_name, access_method = await _access_method(migrated_db.engine, "ix_chunks_embedding")
    assert table_name == "chunks"
    assert access_method == "hnsw"


async def test_up_creates_gin_index_on_generated_search_vector(migrated_db):
    table_name, access_method = await _access_method(migrated_db.engine, "ix_chunks_search_vector")
    assert table_name == "chunks"
    assert access_method == "gin"

    sql = text(
        """
        SELECT format_type(a.atttypid, a.atttypmod) AS column_type,
               a.attgenerated = 's' AS stored_generated
        FROM pg_attribute a
        WHERE a.attrelid = 'chunks'::regclass AND a.attname = 'search_vector'
        """
    )
    async with migrated_db.engine.connect() as conn:
        row = (await conn.execute(sql)).mappings().first()
    assert row["column_type"] == "tsvector"
    assert row["stored_generated"] is True


async def test_down_drops_document_tables_without_affecting_identity(migrated_db):
    async with migrated_db.engine.begin() as conn:
        await conn.execute(text("CREATE TABLE sentinel_probe2 (id integer PRIMARY KEY)"))

    await migrated_db.alembic("down", "0001")

    remaining = await _table_names(migrated_db.engine)
    assert DOCUMENT_TABLES.isdisjoint(remaining)
    assert IDENTITY_TABLES <= remaining
    assert "sentinel_probe2" in remaining
