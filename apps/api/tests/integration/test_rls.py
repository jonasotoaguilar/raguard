"""Integration tests: RLS tenant isolation as defense-in-depth (F5).

Migration ``0006`` enables (non-FORCE) RLS with a ``tenant_isolation`` policy
on every tenant-scoped table and creates the opt-in ``raguard_app`` role.
These tests run against a real PostgreSQL (CI; skipped without the local
stack via the ``migrated_db`` fixture):

- RLS is enabled without FORCE on all seven tables (owner still bypasses, so
  Alembic/bootstrap and the current default behavior are unchanged).
- As ``raguard_app`` (via ``SET LOCAL ROLE``), a raw query with no
  application predicate sees no foreign-tenant rows; with ``app.tenant_id``
  set it sees only its own rows.

If the environment cannot create/assume the app role (e.g. a restricted
managed database), the tests skip explicitly with the reason — they never
pass silently without exercising the RLS path.
"""

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

RLS_TABLES = {
    "documents",
    "chunks",
    "conversations",
    "messages",
    "document_grants",
    "memberships",
    "roles",
}


async def _rls_state(engine) -> dict[str, tuple[bool, bool]]:
    """Map table name -> (rowsecurity_enabled, force)."""
    sql = text(
        """
        SELECT c.relname AS table_name, c.relrowsecurity AS enabled, c.relforcerowsecurity AS force
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(sql, {"tables": list(RLS_TABLES)})
        return {row["table_name"]: (row["enabled"], row["force"]) for row in result.mappings()}


async def _role_exists(engine, role: str) -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
        )
        return result.first() is not None


async def _require_app_role(engine) -> None:
    """Skip explicitly when the environment cannot provide the app role."""
    if not await _role_exists(engine, "raguard_app"):
        pytest.skip(
            "raguard_app role unavailable: migration 0006 could not create it "
            "(restricted managed database?). RLS path not exercised."
        )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET ROLE raguard_app"))
            await conn.execute(text("RESET ROLE"))
    except Exception as exc:
        pytest.skip(
            f"cannot assume raguard_app role ({exc.__class__.__name__}: {exc}); "
            "RLS path not exercised."
        )


async def test_0006_enables_rls_without_force(migrated_db):
    state = await _rls_state(migrated_db.engine)
    assert set(state) == RLS_TABLES
    for table, (enabled, force) in state.items():
        assert enabled is True, f"RLS not enabled on {table}"
        assert force is False, f"RLS must not be FORCE on {table} (owner must bypass)"


async def test_0006_creates_tenant_isolation_policy_per_table(migrated_db):
    sql = text(
        """
        SELECT c.relname AS table_name, p.polname AS policy_name
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
        """
    )
    async with migrated_db.engine.connect() as conn:
        result = await conn.execute(sql, {"tables": list(RLS_TABLES)})
        found = {row["table_name"]: row["policy_name"] for row in result.mappings()}
    assert set(found) == RLS_TABLES
    assert set(found.values()) == {"tenant_isolation"}


async def _seed_two_tenants(migrated_db) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    async with migrated_db.engine.begin() as conn:
        for tenant_id in (tenant_a, tenant_b):
            await conn.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, 'rls-probe')"),
                {"id": tenant_id},
            )
        await conn.execute(
            text(
                "INSERT INTO documents (id, tenant_id, name, status, storage_key) "
                "VALUES (:id, :tenant_id, 'a.pdf', 'indexed', 'a/a.pdf')"
            ),
            {"id": doc_a, "tenant_id": tenant_a},
        )
        await conn.execute(
            text(
                "INSERT INTO documents (id, tenant_id, name, status, storage_key) "
                "VALUES (:id, :tenant_id, 'b.pdf', 'indexed', 'b/b.pdf')"
            ),
            {"id": doc_b, "tenant_id": tenant_b},
        )
    return tenant_a, tenant_b


async def _select_documents_as_app_role(engine, tenant_guc: str | None) -> list:
    """Raw SELECT on documents as raguard_app, optionally scoping the GUC."""
    if tenant_guc is None:
        guc_literal = "''"
    else:
        # Validated UUID literal: SET LOCAL takes no bind parameters.
        guc_literal = f"'{uuid.UUID(tenant_guc)}'"
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL ROLE raguard_app"))
        await conn.execute(text(f"SET LOCAL app.tenant_id = {guc_literal}"))
        result = await conn.execute(text("SELECT tenant_id FROM documents"))
        return list(result.mappings())


async def test_app_role_sees_nothing_without_tenant_guc(migrated_db):
    await _require_app_role(migrated_db.engine)
    tenant_a, tenant_b = await _seed_two_tenants(migrated_db)

    rows = await _select_documents_as_app_role(migrated_db.engine, None)

    assert rows == [], (
        f"app role without tenant GUC must see no rows, saw tenants "
        f"{[r['tenant_id'] for r in rows]} (seeded {tenant_a}, {tenant_b})"
    )


async def test_app_role_sees_only_its_tenant(migrated_db):
    await _require_app_role(migrated_db.engine)
    tenant_a, tenant_b = await _seed_two_tenants(migrated_db)

    rows_a = await _select_documents_as_app_role(migrated_db.engine, str(tenant_a))
    rows_b = await _select_documents_as_app_role(migrated_db.engine, str(tenant_b))

    assert [r["tenant_id"] for r in rows_a] == [tenant_a]
    assert [r["tenant_id"] for r in rows_b] == [tenant_b]


async def test_owner_default_still_sees_all_rows(migrated_db):
    """The default (owner) path is unchanged: no GUC, all rows visible."""
    tenant_a, tenant_b = await _seed_two_tenants(migrated_db)
    async with migrated_db.engine.connect() as conn:
        result = await conn.execute(text("SELECT tenant_id FROM documents"))
        seen = {r["tenant_id"] for r in result.mappings()}
    assert seen == {tenant_a, tenant_b}
