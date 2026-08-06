"""Create identity tables (tenants, users, roles, memberships).

Revision ID: 0001
Revises:
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_CAPABILITY_ALLOWLIST_SQL = (
    "capabilities <@ ARRAY['org.settings.manage', 'users.manage', "
    "'documents.manage', 'corpus.view', 'chat.use']::text[]"
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("capabilities", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_roles_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
        sa.CheckConstraint(_CAPABILITY_ALLOWLIST_SQL, name="ck_roles_capabilities_allowlist"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_memberships_tenant_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_memberships_tenant_role",
        ),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_memberships_user_tenant"),
    )
    op.create_index("ix_memberships_tenant_user", "memberships", ["tenant_id", "user_id"])
    op.create_index("ix_memberships_tenant_role", "memberships", ["tenant_id", "role_id"])


def downgrade() -> None:
    # Drop child tables first, then their parents; other tables are untouched.
    op.drop_index("ix_memberships_tenant_role", table_name="memberships")
    op.drop_index("ix_memberships_tenant_user", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("tenants")
