"""Integration tests: protected /api/org route behavior (tasks 3.4, 3b.3).

Route-behavior subset split from ``test_authorization.py`` (PR 3b delivery):
protected ops, standard 400/401/403/404 envelopes, fresh-resolver role
changes on real PostgreSQL via ``migrated_db``. Release gates: test_authorization_release_gates.py.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.config import Settings, get_settings
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from raguard_api.org.router import create_org_router

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"


def _make_app(db):
    settings = Settings(
        jwt_secret=JWT_SECRET,
        jwt_issuer="raguard-test",
        jwt_audience="raguard-api",
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_org_router(session_factory=db.session_factory))
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings


async def _seed(db):
    """Tenant A: admin + member. Tenant B: carol (member). Returns id map."""
    async with db.session_factory() as session:
        admin = User(email="admin-a@example.com", password_hash="x")
        member = User(email="member-a@example.com", password_hash="x")
        carol = User(email="carol-b@example.com", password_hash="x")
        session.add_all([admin, member, carol])
        await session.flush()
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        session.add_all([tenant_a, tenant_b])
        await session.flush()
        admin_role = Role(
            tenant_id=tenant_a.id,
            name="admin",
            capabilities=[
                "org.settings.manage",
                "users.manage",
                "documents.manage",
                "corpus.view",
                "chat.use",
            ],
        )
        member_role = Role(
            tenant_id=tenant_a.id,
            name="member",
            capabilities=[
                "corpus.view",
                "chat.use",
            ],
        )
        carol_role = Role(
            tenant_id=tenant_b.id,
            name="member",
            capabilities=[
                "corpus.view",
                "chat.use",
            ],
        )
        session.add_all([admin_role, member_role, carol_role])
        await session.flush()
        session.add_all(
            [
                Membership(tenant_id=tenant_a.id, user_id=admin.id, role_id=admin_role.id),
                Membership(tenant_id=tenant_a.id, user_id=member.id, role_id=member_role.id),
                Membership(tenant_id=tenant_b.id, user_id=carol.id, role_id=carol_role.id),
            ]
        )
        await session.commit()
        return {
            "tenant_a": tenant_a.id,
            "tenant_b": tenant_b.id,
            "admin": admin.id,
            "member": member.id,
            "carol": carol.id,
            "admin_role": admin_role.id,
            "member_role": member_role.id,
            "carol_role": carol_role.id,
        }


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings: Settings, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def test_admin_lists_users_of_own_tenant_only(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get(
            "/api/org/users",
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 200
    users = response.json()["users"]
    assert {user["email"] for user in users} == {"admin-a@example.com", "member-a@example.com"}
    assert "carol-b@example.com" not in response.text
    assert "password_hash" not in response.text


async def test_admin_reads_own_tenant_user(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get(
            f"/api/org/users/{ids['member']}",
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 200
    assert response.json() == {"id": str(ids["member"]), "email": "member-a@example.com"}


async def test_missing_and_invalid_cookies_return_401_envelope(migrated_db):
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        missing = await client.get("/api/org/users")
        invalid = await client.get("/api/org/users", headers=_cookie("not-a-jwt"))
    for response in (missing, invalid):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_failed"


async def test_admin_updates_role_capabilities(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.patch(
            f"/api/org/roles/{ids['member_role']}",
            json={"capabilities": ["corpus.view", "chat.use", "users.manage"]},
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 200
    assert response.json()["capabilities"] == ["corpus.view", "chat.use", "users.manage"]


async def test_role_update_rejects_unknown_capability_with_400(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.patch(
            f"/api/org/roles/{ids['member_role']}",
            json={"capabilities": ["corpus.view", "delete.everything"]},
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


async def test_role_change_is_visible_on_next_request_with_same_token(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        denied = await client.get("/api/org/users", headers=_cookie(token))
        assert denied.status_code == 403
        updated = await client.patch(
            f"/api/org/roles/{ids['member_role']}",
            json={"capabilities": ["corpus.view", "chat.use", "users.manage"]},
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
        assert updated.status_code == 200
        granted = await client.get("/api/org/users", headers=_cookie(token))
    assert granted.status_code == 200  # same token, fresh resolution, no cache


async def test_token_without_current_membership_is_rejected(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    ghost = uuid.uuid4()
    async with _client(app) as client:
        response = await client.get(
            "/api/org/users",
            headers=_cookie(_token(settings, user_id=ghost, tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
