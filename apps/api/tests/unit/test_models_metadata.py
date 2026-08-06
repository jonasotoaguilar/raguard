"""Unit tests for the identity ORM metadata contract (task 1a.1).

These tests inspect SQLAlchemy metadata only — no Alembic, no PostgreSQL — so
the schema contract declared by the ORM (table names, constraints, indexes) is
verified deterministically in the unit layer. The assertions mirror the named
constraints that the migration enforces in PostgreSQL.
"""

import pytest
from raguard_api.db import Base
from raguard_api.identity.models import ALLOWED_CAPABILITIES
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def metadata():
    """The SQLAlchemy metadata populated by the identity models."""
    return Base.metadata


def _constraint_by_name(table, name):
    """Return the named constraint of a table (constraints is an unkeyed set)."""
    return {constraint.name: constraint for constraint in table.constraints}[name]


def test_identity_tables_are_registered(metadata):
    table_names = set(metadata.tables)
    assert table_names >= {"tenants", "users", "roles", "memberships"}


def test_users_email_is_globally_unique(metadata):
    users = metadata.tables["users"]
    constraint = _constraint_by_name(users, "uq_users_email")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["email"]


def test_roles_name_is_unique_per_tenant(metadata):
    roles = metadata.tables["roles"]
    constraint = _constraint_by_name(roles, "uq_roles_tenant_name")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "name"]


def test_roles_has_unique_tenant_id_and_id_backing_the_composite_fk(metadata):
    roles = metadata.tables["roles"]
    constraint = _constraint_by_name(roles, "uq_roles_tenant_id")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "id"]


def test_memberships_composite_role_fk_targets_roles_tenant_and_id(metadata):
    memberships = metadata.tables["memberships"]
    constraint = _constraint_by_name(memberships, "fk_memberships_tenant_role")
    assert isinstance(constraint, ForeignKeyConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "role_id"]
    targets = [
        (element.parent.name, element.column.table.name, element.column.name)
        for element in constraint.elements
    ]
    assert targets == [
        ("tenant_id", "roles", "tenant_id"),
        ("role_id", "roles", "id"),
    ]


def test_memberships_indexes_lead_with_tenant_id(metadata):
    memberships = metadata.tables["memberships"]
    indexes = {
        index.name: [column.name for column in index.columns] for index in memberships.indexes
    }
    assert indexes["ix_memberships_tenant_user"] == ["tenant_id", "user_id"]
    assert indexes["ix_memberships_tenant_role"] == ["tenant_id", "role_id"]


def test_memberships_unique_per_user_and_tenant(metadata):
    memberships = metadata.tables["memberships"]
    constraint = _constraint_by_name(memberships, "uq_memberships_user_tenant")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["user_id", "tenant_id"]


def test_roles_capability_allowlist_constraint_contains_every_token(metadata):
    roles = metadata.tables["roles"]
    constraint = _constraint_by_name(roles, "ck_roles_capabilities_allowlist")
    assert isinstance(constraint, CheckConstraint)
    sql_text = constraint.sqltext.text
    assert "<@" in sql_text
    for capability in ALLOWED_CAPABILITIES:
        assert capability in sql_text


def test_capability_allowlist_matches_design_tokens(metadata):
    assert ALLOWED_CAPABILITIES == (
        "org.settings.manage",
        "users.manage",
        "documents.manage",
        "corpus.view",
        "chat.use",
    )
