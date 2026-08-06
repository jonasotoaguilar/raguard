"""Unit tests: AuthorizationScope predicates and capability checks (task 3.2).

The scope renders tenant scoping as parameterized SQLAlchemy expressions with
bound values — never SQL strings and never literals concatenated from client
input — so future retrieval and citation queries can compose the predicate
before generation. A missing capability must yield False.
"""

import uuid

import pytest
from raguard_api.authorization.capabilities import (
    CHAT_USE,
    CORPUS_VIEW,
    USERS_MANAGE,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.identity.models import Membership, Role
from sqlalchemy.sql.elements import BindParameter, ColumnElement

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _member_scope() -> AuthorizationScope:
    return AuthorizationScope(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        capabilities=frozenset({CORPUS_VIEW, CHAT_USE}),
    )


def test_granted_capabilities_return_true():
    scope = _member_scope()
    assert scope.has_capability(CORPUS_VIEW) is True
    assert scope.has_capability(CHAT_USE) is True


def test_missing_capability_returns_false():
    scope = _member_scope()
    assert scope.has_capability(USERS_MANAGE) is False


@pytest.mark.parametrize("column", [Membership.tenant_id, Role.tenant_id])
def test_tenant_predicate_is_parameterized_expression(column):
    scope = _member_scope()
    predicate = scope.tenant_predicate(column)
    assert isinstance(predicate, ColumnElement)
    assert not isinstance(predicate, str)
    compiled = predicate.compile()
    assert str(TENANT_ID) not in str(compiled), "tenant id must not be inlined"
    params = compiled.params
    assert params, "predicate must carry bound parameters"
    assert list(params.values()) == [TENANT_ID]


def test_tenant_predicate_binds_requested_column_only():
    scope = _member_scope()
    predicate = scope.tenant_predicate(Membership.tenant_id)
    assert "memberships.tenant_id" in str(predicate.compile())
    bind = predicate.right
    assert isinstance(bind, BindParameter)
    assert bind.value == TENANT_ID


def test_scope_carries_verified_identity():
    scope = _member_scope()
    assert scope.tenant_id == TENANT_ID
    assert scope.user_id == USER_ID
