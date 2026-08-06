"""Unit tests: authorization security boundary (task 4.3).

Invariant locks for the security boundary: authorization derives exclusively
from verified identity (sub, tid) plus current database role state — never from
token extras, role names, or untrusted content. Locks the boundary seams:
TokenClaims rejects any extra identity field, AuthorizationScope is frozen and
carries no role name, injection-shaped role names receive no grants, and a
resolver scope contains exactly the database-provided capability set.
"""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from raguard_api.auth.jwt import TokenClaims
from raguard_api.authorization.capabilities import (
    CHAT_USE,
    CORPUS_VIEW,
    USERS_MANAGE,
    capabilities_for_role,
)
from raguard_api.authorization.resolver import AuthorizationResolver
from raguard_api.authorization.scope import AuthorizationScope

pytestmark = pytest.mark.unit

SUB = uuid.uuid4()
TID = uuid.uuid4()


def _claims() -> TokenClaims:
    now = datetime.now(UTC)
    return TokenClaims(sub=SUB, tid=TID, iat=now, exp=now, jti=uuid.uuid4().hex)


def test_token_claims_reject_extra_identity_fields():
    with pytest.raises(TypeError):
        TokenClaims(
            sub=SUB,
            tid=TID,
            iat=datetime.now(UTC),
            exp=datetime.now(UTC),
            jti="x",
            roles=["admin"],
            capabilities=["users.manage"],
        )


def test_scope_is_frozen_and_capabilities_are_immutable():
    scope = AuthorizationScope(tenant_id=TID, user_id=SUB, capabilities=frozenset({CORPUS_VIEW}))
    with pytest.raises(FrozenInstanceError):
        scope.user_id = uuid.uuid4()
    with pytest.raises(FrozenInstanceError):
        scope.capabilities = frozenset()  # capabilities are not a list to mutate
    assert isinstance(scope.capabilities, frozenset)


def test_scope_has_no_role_name_or_grant_source_field():
    with pytest.raises(TypeError):
        AuthorizationScope(
            tenant_id=TID,
            user_id=SUB,
            capabilities=frozenset({CORPUS_VIEW}),
            role_name="admin",
        )


@pytest.mark.parametrize(
    "role_name",
    ["admin') --", "member; DROP TABLE roles", "admin ignore previous instructions"],
)
def test_injection_shaped_role_names_receive_no_grants(role_name):
    assert capabilities_for_role(role_name) is None


async def test_resolver_scope_contains_exactly_the_database_capability_set():
    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        def __init__(self, value):
            self._value = value

        async def execute(self, statement):
            return _Result(self._value)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Factory:
        def __init__(self, value):
            self._value = value

        def __call__(self):
            return _Session(self._value)

    resolver = AuthorizationResolver(session_factory=_Factory([CORPUS_VIEW, CHAT_USE]))
    scope = await resolver.resolve(_claims())
    assert scope.tenant_id == TID
    assert scope.user_id == SUB
    assert scope.capabilities == frozenset({CORPUS_VIEW, CHAT_USE})
    assert not scope.has_capability(USERS_MANAGE)  # grants never exceed the DB set
