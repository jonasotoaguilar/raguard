"""Integration tests: authorization release gates (PRD KPI 2) — PR 3c delivery (task 4b.1).

The four PR 3c gates run verbatim on the minimal auth+org harness
(``create_auth_router`` + ``create_org_router`` + standard error handlers; no
``raguard_api.main`` import — the app factory lands in PR 4d): cross-tenant
reads/mutations denied with DB rows unchanged, cross-role escalation denied
(403), client-supplied tenant ignored, neutral 404s without existence
disclosure. The PR 4 isolation gates are delivered as the independent PR 4c
boundary file ``test_isolation_gates.py`` (kept split per tasks.md 4c.3).
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.auth.router import create_auth_router
from raguard_api.config import Settings, get_settings
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from raguard_api.org.router import create_org_router
from sqlalchemy import select

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"
ALL_CAPS = [
    "org.settings.manage",
    "users.manage",
    "documents.manage",
    "corpus.view",
    "chat.use",
]
MEMBER_CAPS = ["corpus.view", "chat.use"]


def _make_app(db) -> tuple[FastAPI, Settings]:
    settings = Settings(
        jwt_secret=JWT_SECRET,
        jwt_issuer="raguard-test",
        jwt_audience="raguard-api",
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_auth_router(settings=settings, session_factory=db.session_factory))
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
        admin_role = Role(tenant_id=tenant_a.id, name="admin", capabilities=ALL_CAPS)
        member_role = Role(tenant_id=tenant_a.id, name="member", capabilities=MEMBER_CAPS)
        carol_role = Role(tenant_id=tenant_b.id, name="member", capabilities=MEMBER_CAPS)
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


async def _carol_membership_id(db, ids) -> uuid.UUID:
    async with db.session_factory() as session:
        membership = (
            await session.execute(select(Membership).where(Membership.user_id == ids["carol"]))
        ).scalar_one()
        return membership.id


async def test_cross_tenant_user_read_is_neutral_404(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get(
            f"/api/org/users/{ids['carol']}",
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "carol-b@example.com" not in response.text


async def test_cross_tenant_membership_mutation_denied_and_unchanged(migrated_db):
    ids = await _seed(migrated_db)
    carol_membership = await _carol_membership_id(migrated_db, ids)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.patch(
            f"/api/org/memberships/{carol_membership}",
            json={"role_id": str(ids["admin_role"])},
            headers=_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    async with migrated_db.session_factory() as session:
        current = (
            await session.execute(select(Membership).where(Membership.id == carol_membership))
        ).scalar_one()
        assert current.role_id == ids["carol_role"]


async def test_member_cannot_escalate_to_admin_operations(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    headers = _cookie(_token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"]))
    async with _client(app) as client:
        listed = await client.get("/api/org/users", headers=headers)
        patched_role = await client.patch(
            f"/api/org/roles/{ids['member_role']}",
            json={"capabilities": ["org.settings.manage"]},
            headers=headers,
        )
    assert listed.status_code == patched_role.status_code == 403
    assert listed.json()["error"]["code"] == patched_role.json()["error"]["code"] == "forbidden"
    async with migrated_db.session_factory() as session:
        role = (
            await session.execute(select(Role).where(Role.id == ids["member_role"]))
        ).scalar_one()
        assert role.capabilities == MEMBER_CAPS


async def test_client_supplied_tenant_is_ignored(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get(
            "/api/org/users",
            headers={
                **_cookie(_token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])),
                "X-Tenant-Id": str(ids["tenant_b"]),
            },
        )
    assert response.status_code == 200
    emails = {user["email"] for user in response.json()["users"]}
    assert "carol-b@example.com" not in emails
    assert "admin-a@example.com" in emails
