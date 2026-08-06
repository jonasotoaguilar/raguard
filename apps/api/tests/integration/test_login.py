"""Integration tests: POST /api/auth/login and the protected-route dependency (task 2.3).

Runs against a real disposable migrated PostgreSQL via the ``migrated_db``
fixture and a minimal FastAPI harness (no PR 4 main app): login issues only a
thin DB-derived JWT in an HttpOnly SameSite cookie, wrong email and wrong
password are indistinguishable, the tenant comes only from the verified token,
foreign Origins are rejected, and malformed credentials never echo the supplied
password back through the validation error envelope.
"""

import uuid
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.dependencies import get_token_claims
from raguard_api.auth.jwt import TokenClaims, decode_access_token
from raguard_api.auth.passwords import hash_password
from raguard_api.auth.router import create_auth_router
from raguard_api.config import Settings, get_settings
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User

pytestmark = pytest.mark.integration

ORIGIN = "http://localhost:5173"
EMAIL = "alice@example.com"
PASSWORD = "s3cret-password"


def _make_app(db, *, secure=False):
    settings = Settings(
        jwt_secret="test-secret-0123456789abcdef1234",
        jwt_issuer="raguard-test",
        jwt_audience="raguard-api",
        session_cookie_secure=secure,
        allowed_origins=[ORIGIN],
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_auth_router(settings=settings, session_factory=db.session_factory))
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/api/auth/probe")
    async def probe(claims: Annotated[TokenClaims, Depends(get_token_claims)]):
        return {"sub": str(claims.sub), "tid": str(claims.tid)}

    return app, settings


async def _seed(db, *, tenants=1):
    async with db.session_factory() as session:
        user = User(email=EMAIL, password_hash=hash_password(PASSWORD))
        session.add(user)
        await session.flush()
        ids = []
        for index in range(tenants):
            tenant = Tenant(name=f"Tenant {index}")
            session.add(tenant)
            await session.flush()
            role = Role(
                tenant_id=tenant.id, name="member", capabilities=["corpus.view", "chat.use"]
            )
            session.add(role)
            await session.flush()
            session.add(Membership(tenant_id=tenant.id, user_id=user.id, role_id=role.id))
            ids.append(tenant.id)
        await session.commit()
        return user.id, ids


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _login(client, **overrides):
    body = {"email": EMAIL, "password": PASSWORD, **overrides}
    return await client.post("/api/auth/login", json=body, headers={"Origin": ORIGIN})


def _cookie_token(response) -> str:
    return response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]


@pytest.mark.parametrize("secure", [False, True])
async def test_login_issues_thin_jwt_in_httponly_cookie(migrated_db, secure):
    user_id, (tenant_id,) = await _seed(migrated_db)
    app, settings = _make_app(migrated_db, secure=secure)
    async with _client(app) as client:
        response = await _login(client)
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith("raguard_session=")
    for attribute in ("HttpOnly", "SameSite=lax", "Path=/api"):
        assert attribute in set_cookie
    assert ("Secure" in set_cookie) is secure
    token = _cookie_token(response)
    assert token not in response.text  # token only in the cookie, never the body
    claims = decode_access_token(token, settings)
    assert claims.sub == user_id
    assert claims.tid == tenant_id


async def test_wrong_password_and_unknown_email_are_indistinguishable(migrated_db):
    await _seed(migrated_db)
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        wrong_password = await _login(client, password="wrong-password")
        unknown_email = await _login(client, email="ghost@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    body = wrong_password.text.lower()
    assert "alice@example.com" not in body and "ghost@example.com" not in body
    assert "wrong-password" not in body and PASSWORD not in body and "$argon2" not in body


@pytest.mark.parametrize(
    "password_value",
    [
        {"user-supplied": "super-secret-value"},
        ["super-secret-value", "another-secret"],
    ],
)
async def test_malformed_password_400_envelope_never_echoes_credential(migrated_db, password_value):
    """Malformed login credentials return the 400 envelope with loc/type/msg only.

    The supplied password object/list must never appear in the response, and
    validation details must keep only the stable allowlist fields — never raw
    ``input``, error context, or pydantic URLs (jwt-authentication secrecy).
    """
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        response = await _login(client, password=password_value)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    details = error["details"]
    assert details, "expected at least one validation detail"
    body = response.text.lower()
    assert "super-secret-value" not in body and "another-secret" not in body
    assert "$argon2" not in body
    for detail in details:
        assert set(detail) <= {"loc", "type", "msg"}
        assert detail["loc"] and detail["type"] and detail["msg"]
    password_detail = next(d for d in details if "password" in d["loc"])
    assert password_detail["type"] == "string_type"


async def test_client_supplied_tenant_is_ignored(migrated_db):
    user_id, (tenant_id,) = await _seed(migrated_db)
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        token = _cookie_token(await _login(client))
        probe = await client.get(
            "/api/auth/probe",
            headers={"Cookie": f"raguard_session={token}", "X-Tenant-Id": str(uuid.uuid4())},
        )
    assert probe.status_code == 200
    assert probe.json() == {"sub": str(user_id), "tid": str(tenant_id)}


async def test_foreign_origin_rejected_without_cookie(migrated_db):
    await _seed(migrated_db)
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            headers={"Origin": "https://evil.example"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert "set-cookie" not in response.headers


async def test_multiple_memberships_login_denied_generic(migrated_db):
    await _seed(migrated_db, tenants=2)
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        response = await _login(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_invalid_cookie_on_protected_route_returns_401(migrated_db):
    app, _ = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get(
            "/api/auth/probe", headers={"Cookie": "raguard_session=not-a-jwt"}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
