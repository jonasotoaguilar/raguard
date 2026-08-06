"""Integration smoke tests: app factory wiring (PR 4d, task 4d.1).

``create_app`` (``raguard_api.main``) is the production composition root: it
registers the standard error envelope and mounts exactly the auth, org,
documents, and retrieval routers. These smoke tests lock the factory behavior
on the real PostgreSQL harness: unauthenticated requests get the standard 401
envelope, unknown paths return 404, settings are threaded into the auth
router, and the mounted surface is exactly login plus the org operations plus
document ingestion plus retrieval search — no logout route, no new scope.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.config import Settings
from raguard_api.main import create_app

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"

EXPECTED_SURFACE = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/org/users"),
    ("GET", "/api/org/users/{user_id}"),
    ("GET", "/api/org/roles"),
    ("PATCH", "/api/org/roles/{role_id}"),
    ("GET", "/api/org/memberships"),
    ("PATCH", "/api/org/memberships/{membership_id}"),
    ("POST", "/api/documents"),
    ("GET", "/api/documents"),
    ("GET", "/api/documents/{document_id}"),
    ("POST", "/api/search"),
}


def _make_app(db) -> FastAPI:
    return create_app(settings=Settings(jwt_secret=JWT_SECRET), session_factory=db.session_factory)


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _api_surface(app: FastAPI) -> set[tuple[str, str]]:
    """(method, path) of every mounted API route, ignoring FastAPI's HEAD noise.

    Included routers appear as wrapper route objects; their effective routes
    live on ``original_router`` with full prefixed paths.
    """
    surface = set()
    for route in app.routes:
        if hasattr(route, "original_router"):
            candidates = route.original_router.routes
        else:
            candidates = [route]
        for candidate in candidates:
            for method in candidate.methods or set():
                if method != "HEAD" and candidate.path.startswith("/api"):
                    surface.add((method, candidate.path))
    return surface


async def test_no_cookie_org_route_returns_authentication_failed_envelope(migrated_db):
    app = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get("/api/org/users")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_unknown_path_returns_404(migrated_db):
    app = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.get("/api/no-such-route")
    assert response.status_code == 404


async def test_settings_override_threads_into_auth_router(migrated_db):
    settings = Settings(jwt_secret=JWT_SECRET, allowed_origins=["http://allowed.example"])
    app = create_app(settings=settings, session_factory=migrated_db.session_factory)
    async with _client(app) as client:
        foreign = await client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "wrong"},
            headers={"origin": "http://evil.example"},
        )
        allowed = await client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "wrong"},
            headers={"origin": "http://allowed.example"},
        )
    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "forbidden"
    assert allowed.status_code == 401
    assert allowed.json()["error"]["code"] == "authentication_failed"


async def test_mounted_surface_is_login_plus_org_plus_documents(migrated_db):
    app = _make_app(migrated_db)
    surface = _api_surface(app)
    assert surface == EXPECTED_SURFACE
    assert not any(path.endswith("/logout") for _, path in surface)
