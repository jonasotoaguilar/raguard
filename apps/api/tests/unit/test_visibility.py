"""Unit tests: per-document visibility SQL helper and grantee validation (F3 RED).

The visibility invariant is SQL-level: ``visibility='tenant'`` is visible to
anyone with ``corpus.view``; ``visibility='restricted'`` is visible only with
an explicit user or role grant. These tests compile the clause without a
database and assert bound parameters (never literals for ids).
"""

import uuid

import pytest
from raguard_api.errors import ValidationError

pytestmark = pytest.mark.unit


def test_visibility_clause_covers_tenant_and_grants():
    from raguard_api.documents.visibility import visibility_clause

    user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    clause = visibility_clause(user_id=user_id, role_ids=frozenset({role_id}))
    sql = str(clause.compile(compile_kwargs={"render_postcompile": True}))
    assert "documents.visibility" in sql
    assert "document_grants" in sql
    assert str(user_id) not in sql
    assert str(role_id) not in sql


def test_visibility_clause_without_roles_omits_role_branch():
    from raguard_api.documents.visibility import visibility_clause

    clause = visibility_clause(user_id=uuid.uuid4(), role_ids=frozenset())
    sql = str(clause.compile(compile_kwargs={"render_postcompile": True}))
    assert "documents.visibility" in sql
    assert "document_grants" in sql


def test_validate_visibility_rejects_unknown():
    from raguard_api.documents.visibility import validate_visibility

    assert validate_visibility("tenant") == "tenant"
    assert validate_visibility("restricted") == "restricted"
    with pytest.raises(ValidationError):
        validate_visibility("private")


def test_validate_grantee_type_rejects_unknown():
    from raguard_api.documents.visibility import validate_grantee_type

    assert validate_grantee_type("user") == "user"
    assert validate_grantee_type("role") == "role"
    with pytest.raises(ValidationError):
        validate_grantee_type("tenant")
