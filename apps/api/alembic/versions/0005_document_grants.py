"""Add per-document visibility and grants (F3).

Revision ID: 0005
Revises: 0004

- documents.visibility TEXT NOT NULL DEFAULT 'tenant', CHECK IN
  ('tenant', 'restricted'). 'tenant' keeps the current behavior (anyone with
  corpus.view); 'restricted' requires an explicit user or role grant.
- document_grants: per-document grants to a user or a role, tenant-scoped,
  composite FK (tenant_id, document_id) -> documents(tenant_id, id) ON DELETE
  CASCADE so deleting a document removes its grants; UNIQUE
  (tenant_id, document_id, grantee_type, grantee_id); tenant-leading indexes
  for document reads and grantee lookups.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None

_VISIBILITY_SQL = "visibility IN ('tenant', 'restricted')"
_GRANTEE_TYPE_SQL = "grantee_type IN ('user', 'role')"


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("visibility", sa.Text(), nullable=False, server_default="tenant"),
    )
    op.create_check_constraint("ck_documents_visibility", "documents", _VISIBILITY_SQL)
    op.create_table(
        "document_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("grantee_type", sa.Text(), nullable=False),
        sa.Column("grantee_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_grants"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_document_grants_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_grants_tenant_document",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "grantee_type",
            "grantee_id",
            name="uq_document_grants_scope",
        ),
        sa.CheckConstraint(_GRANTEE_TYPE_SQL, name="ck_document_grants_grantee_type"),
    )
    op.create_index(
        "ix_document_grants_tenant_document",
        "document_grants",
        ["tenant_id", "document_id"],
    )
    op.create_index(
        "ix_document_grants_tenant_grantee",
        "document_grants",
        ["tenant_id", "grantee_type", "grantee_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_grants_tenant_grantee", table_name="document_grants")
    op.drop_index("ix_document_grants_tenant_document", table_name="document_grants")
    op.drop_table("document_grants")
    op.drop_constraint("ck_documents_visibility", "documents", type_="check")
    op.drop_column("documents", "visibility")
