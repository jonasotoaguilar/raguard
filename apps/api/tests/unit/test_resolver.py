"""Unit tests: the single fresh-per-request authorization resolver (task 3.3).

Resolution derives the scope exclusively from verified JWT claims (sub, tid)
plus current database membership/role state. It must run a fresh query on every
call, hold no capability state, and raise a generic authentication error when
no current membership exists for the claimed tenant.
"""

import uuid
from datetime import UTC, datetime

import pytest
from raguard_api.auth.jwt import TokenClaims
from raguard_api.authorization.capabilities import CORPUS_VIEW, USERS_MANAGE
from raguard_api.authorization.resolver import AuthorizationResolver
from raguard_api.errors import AuthenticationError

SUB = uuid.uuid4()
TID = uuid.uuid4()


def _claims() -> TokenClaims:
    now = datetime.now(UTC)
    return TokenClaims(
        sub=SUB,
        tid=TID,
        iat=now,
        exp=now,
        jti=uuid.uuid4().hex,
    )


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, value_provider):
        self._value_provider = value_provider
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self._value_provider())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeFactory:
    def __init__(self, value_provider):
        self._value_provider = value_provider
        self.sessions = []

    def __call__(self):
        session = _FakeSession(self._value_provider)
        self.sessions.append(session)
        return session


class _CountingFactory(_FakeFactory):
    def __init__(self, value_provider):
        super().__init__(value_provider)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return super().__call__()


async def test_resolve_returns_scope_from_claims_and_db_role():
    factory = _FakeFactory(lambda: [CORPUS_VIEW])
    resolver = AuthorizationResolver(session_factory=factory)
    scope = await resolver.resolve(_claims())
    assert scope.tenant_id == TID
    assert scope.user_id == SUB
    assert scope.has_capability(CORPUS_VIEW)
    assert not scope.has_capability(USERS_MANAGE)


async def test_role_change_is_visible_on_next_request_without_cache():
    state = {"capabilities": [CORPUS_VIEW]}
    factory = _FakeFactory(lambda: state["capabilities"])
    resolver = AuthorizationResolver(session_factory=factory)
    before = await resolver.resolve(_claims())
    assert not before.has_capability(USERS_MANAGE)
    state["capabilities"] = [CORPUS_VIEW, USERS_MANAGE]
    after = await resolver.resolve(_claims())
    assert after.has_capability(USERS_MANAGE)


async def test_every_resolution_runs_a_fresh_query():
    factory = _CountingFactory(lambda: [CORPUS_VIEW])
    resolver = AuthorizationResolver(session_factory=factory)
    await resolver.resolve(_claims())
    await resolver.resolve(_claims())
    assert factory.calls == 2  # each resolve opened a brand-new session/query


async def test_resolution_query_is_parameterized_and_scoped_by_both_claims():
    factory = _FakeFactory(lambda: [CORPUS_VIEW])
    resolver = AuthorizationResolver(session_factory=factory)
    await resolver.resolve(_claims())
    (statement,) = factory.sessions[0].statements
    compiled = statement.compile()
    params = compiled.params
    assert list(params.values()) == [SUB, TID]
    assert str(SUB) not in str(compiled) and str(TID) not in str(compiled)


async def test_missing_membership_raises_generic_authentication_error():
    factory = _FakeFactory(lambda: None)
    resolver = AuthorizationResolver(session_factory=factory)
    with pytest.raises(AuthenticationError) as excinfo:
        await resolver.resolve(_claims())
    assert excinfo.value.status_code == 401
    assert excinfo.value.code == "authentication_failed"
