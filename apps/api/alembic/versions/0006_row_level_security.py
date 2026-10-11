"""Enable Row Level Security as defense-in-depth on tenant-scoped tables (F5).

Revision ID: 0006
Revises: 0005

Deliberately conservative second line of defense:

- ``ENABLE ROW LEVEL SECURITY`` (never ``FORCE``): the table owner keeps
  bypassing RLS, so Alembic/bootstrap and the current owner-based default
  behavior are unchanged. Enforcement only applies to non-owner roles such
  as the opt-in ``raguard_app`` application role created here.
- One ``tenant_isolation`` policy per table matching
  ``tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid``
  in both ``USING`` and ``WITH CHECK``. With an empty/unset GUC the
  expression is NULL, so policies match nothing for the app role; the owner
  path (today's behavior) is unaffected.
- Application role ``raguard_app`` (idempotent ``DO`` block; ``NOLOGIN``
  unless the operator later sets a password) with ``GRANT USAGE ON SCHEMA
  public`` plus ``SELECT, INSERT, UPDATE, DELETE`` on the RLS tables.
  Pointing ``DATABASE_URL`` at this role is opt-in and documented in the
  README hardening section; the compose default still uses the owner.

Downgrade drops the policies and disables RLS. It intentionally does NOT
drop the ``raguard_app`` role, so existing deployments that already pointed
their app at it do not break on downgrade.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_RLS_TABLES = (
    "documents",
    "chunks",
    "conversations",
    "messages",
    "document_grants",
    "memberships",
    "roles",
)

# Every table above carries its own tenant_id column (roles/memberships
# directly; chunks/messages/document_grants via their own tenant_id).
_POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_APP_ROLE = "raguard_app"

_CREATE_APP_ROLE_SQL = """DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'raguard_app') THEN
    CREATE ROLE raguard_app NOLOGIN;
  END IF;
END $$;"""


def upgrade() -> None:
    op.execute(_CREATE_APP_ROLE_SQL)
    op.execute("GRANT USAGE ON SCHEMA public TO raguard_app")
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_POLICY_EXPR}) "
            f"WITH CHECK ({_POLICY_EXPR})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO raguard_app")


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    # NOTE: the raguard_app role is intentionally preserved so deployments
    # that adopted it keep working after a downgrade.
