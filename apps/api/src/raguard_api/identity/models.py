"""Identity models: tenants, users, roles, and memberships (task 1.4).

Constraints mirror the migration exactly (apps/api/alembic/versions/0001_identity_tables.py):
- users.email unique system-wide (canonical form enforced by callers);
- roles: name unique per tenant, composite (tenant_id, id) unique backing the
  memberships composite FK, capabilities restricted to the DESIGN.md allowlist;
- memberships: one per user/tenant, and the composite tenant+role FK prevents
  cross-tenant role grants.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from raguard_api.db import Base

# Capability tokens from DESIGN.md; enforced by a CHECK constraint on roles.
ALLOWED_CAPABILITIES = (
    "org.settings.manage",
    "users.manage",
    "documents.manage",
    "corpus.view",
    "chat.use",
)

_CAPABILITY_ALLOWLIST_SQL = (
    "capabilities <@ ARRAY['org.settings.manage', 'users.manage', "
    "'documents.manage', 'corpus.view', 'chat.use']::text[]"
)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
        CheckConstraint(_CAPABILITY_ALLOWLIST_SQL, name="ck_roles_capabilities_allowlist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", name="fk_roles_tenant_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_memberships_tenant_role",
        ),
        UniqueConstraint("user_id", "tenant_id", name="uq_memberships_user_tenant"),
        Index("ix_memberships_tenant_user", "tenant_id", "user_id"),
        Index("ix_memberships_tenant_role", "tenant_id", "role_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", name="fk_memberships_tenant_id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", name="fk_memberships_user_id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
