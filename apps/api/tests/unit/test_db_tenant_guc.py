"""Unit tests: RLS tenant-GUC session wiring is opt-in and behavior-preserving (F5).

The default (owner) path must not change: routers keep using a plain
``session_factory()`` with no tenant in ``session.info``, so the
``after_begin`` listener is a no-op and no ``SET LOCAL`` is emitted.
``tenant_scoped_session`` / ``set_session_tenant`` are the explicit opt-in.
"""

import uuid

import pytest
from raguard_api.db import (
    TENANT_GUC,
    _after_begin_set_tenant,
    assert_rls_ready,
    clear_session_tenant,
    database_url_uses_app_role,
    get_session_tenant,
    set_session_tenant,
    tenant_scoped_session,
)
from sqlalchemy import text

pytestmark = pytest.mark.unit


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, clause, *args, **kwargs):
        self.statements.append(str(clause))
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}


class _FakeSessionCM:
    """Minimal async-CM session stub for the tenant_scoped_session helper."""

    def __init__(self) -> None:
        self.session = _FakeSession()

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(self, *exc_info) -> bool:
        return False


def _stub_factory():
    holder: dict = {}

    def _factory():
        cm = _FakeSessionCM()
        holder["session"] = cm.session
        return cm

    _factory.holder = holder  # type: ignore[attr-defined]
    return _factory


def test_after_begin_emits_set_local_with_tenant_uuid():
    tenant_id = uuid.uuid4()
    session = _FakeSession()
    set_session_tenant(session, tenant_id)
    conn = _FakeConnection()

    _after_begin_set_tenant(session, None, conn)

    assert len(conn.statements) == 1
    statement = conn.statements[0]
    assert "SET LOCAL" in statement
    assert TENANT_GUC in statement
    assert str(tenant_id) in statement


def test_after_begin_noop_without_tenant():
    session = _FakeSession()
    conn = _FakeConnection()

    _after_begin_set_tenant(session, None, conn)

    assert conn.statements == []


def test_set_local_statement_is_safe_to_render():
    """The emitted GUC value is a validated UUID, never raw caller input."""
    session = _FakeSession()
    with pytest.raises(ValueError, match="[Uu]uid|tenant"):
        set_session_tenant(session, "admin') --")
    assert get_session_tenant(session) is None
    conn = _FakeConnection()
    _after_begin_set_tenant(session, None, conn)
    assert conn.statements == []


async def test_tenant_scoped_session_sets_info_without_touching_default():
    factory = _stub_factory()
    tenant_id = uuid.uuid4()

    async with tenant_scoped_session(factory, tenant_id) as session:  # type: ignore[arg-type]
        assert get_session_tenant(session) == str(tenant_id)

    # A plain session from the same shape of factory carries no tenant:
    # the default path stays behavior-preserving (no SET LOCAL).
    plain = _FakeSession()
    assert get_session_tenant(plain) is None
    conn = _FakeConnection()
    _after_begin_set_tenant(plain, None, conn)
    assert conn.statements == []


async def test_clear_session_tenant_restores_default_noop():
    session = _FakeSession()
    set_session_tenant(session, uuid.uuid4())
    clear_session_tenant(session)
    assert get_session_tenant(session) is None
    conn = _FakeConnection()
    _after_begin_set_tenant(session, None, conn)
    assert conn.statements == []


def test_emitted_sql_matches_set_local_shape():
    """Lock the exact SET LOCAL shape the wiring emits (parsed via str)."""
    tenant_id = uuid.uuid4()
    session = _FakeSession()
    set_session_tenant(session, tenant_id)
    conn = _FakeConnection()
    _after_begin_set_tenant(session, None, conn)
    expected = text(f"SET LOCAL {TENANT_GUC} = '{tenant_id}'")
    assert conn.statements[0] == str(expected)


def test_assert_rls_ready_passes_for_owner_without_tenant():
    """The default owner path bypasses RLS: no tenant context required."""
    assert_rls_ready(current_role="raguard", tenant_id=None)


def test_assert_rls_ready_rejects_app_role_without_tenant():
    """Under raguard_app with no GUC every policy matches nothing: fail loud."""
    with pytest.raises(RuntimeError, match="app.tenant_id"):
        assert_rls_ready(current_role="raguard_app", tenant_id=None)


def test_assert_rls_ready_passes_for_app_role_with_tenant():
    assert_rls_ready(current_role="raguard_app", tenant_id=str(uuid.uuid4()))


def test_database_url_uses_app_role_detects_restricted_credential():
    assert database_url_uses_app_role(
        "postgresql+psycopg://raguard_app:secret@127.0.0.1:5432/raguard"
    )
    assert not database_url_uses_app_role(
        "postgresql+psycopg://raguard:secret@127.0.0.1:5432/raguard"
    )
    assert not database_url_uses_app_role("")
    assert not database_url_uses_app_role("not-a-url")


def test_create_app_warns_when_database_url_points_at_app_role(monkeypatch, caplog):
    """Startup honesty: serving on raguard_app without tenant wiring fails."""
    from unittest.mock import MagicMock

    from raguard_api.config import Settings
    from raguard_api.main import create_app

    settings = Settings(jwt_secret="test-secret-0123456789abcdef1234")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://raguard_app:s3cret@db:5432/raguard")
    with caplog.at_level("WARNING", logger="raguard_api.main"):
        create_app(settings=settings, session_factory=MagicMock())
    assert any("raguard_app" in record.message for record in caplog.records)


def test_create_app_quiet_when_database_url_uses_owner(monkeypatch, caplog):
    from unittest.mock import MagicMock

    from raguard_api.config import Settings
    from raguard_api.main import create_app

    settings = Settings(jwt_secret="test-secret-0123456789abcdef1234")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://raguard:s3cret@db:5432/raguard")
    with caplog.at_level("WARNING", logger="raguard_api.main"):
        create_app(settings=settings, session_factory=MagicMock())
    assert not any("raguard_app" in record.message for record in caplog.records)
