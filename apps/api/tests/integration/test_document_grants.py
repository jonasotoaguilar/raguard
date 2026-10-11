"""Integration tests: per-document grants visibility (F3).

Restricted documents are invisible without a grant on every surface (list,
detail, search, chat); a user grant or a grant to the caller's role restores
visibility; cross-tenant targets stay neutral 404s; ``corpus.view`` alone
never opens a restricted document; tenant-visible documents behave as before.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.config import Settings, get_settings
from raguard_api.documents.contracts import FakeEmbedder, FakeJobQueue, FakeObjectStore
from raguard_api.documents.models import Chunk, Document, DocumentGrant
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from raguard_api.retrieval.router import create_retrieval_router

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"


def _embedding(text: str) -> list[float]:
    return FakeEmbedder().embed([text])[0]


def _settings() -> Settings:
    return Settings(jwt_secret=JWT_SECRET, jwt_issuer="raguard-test", jwt_audience="raguard-api")


def _docs_app(db):
    from raguard_api.documents.router import create_documents_router

    settings = _settings()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_documents_router(
            session_factory=db.session_factory,
            settings=settings,
            store=FakeObjectStore(),
            queue=FakeJobQueue(),
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings


def _search_app(db):
    settings = _settings()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_retrieval_router(
            session_factory=db.session_factory, settings=settings, embedder=FakeEmbedder()
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings


def _chat_app(db, completer):
    from raguard_api.chat.router import create_chat_router

    settings = _settings()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_chat_router(
            session_factory=db.session_factory,
            settings=settings,
            embedder=FakeEmbedder(),
            completer=completer,
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings


class _FakeCompleter:
    def complete(self, prompt: str) -> str:
        return "[1]"


async def _seed(db):
    """Tenant A: admin (manage), member (view+chat, member role), viewer (view+chat,
    viewer role). Tenant B: carol. One tenant doc + one restricted doc (1 chunk each)."""
    async with db.session_factory() as session:
        admin = User(email="admin-a@example.com", password_hash="x")
        member = User(email="member-a@example.com", password_hash="x")
        viewer = User(email="viewer-a@example.com", password_hash="x")
        carol = User(email="carol-b@example.com", password_hash="x")
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        session.add_all([admin, member, viewer, carol, tenant_a, tenant_b])
        await session.flush()
        admin_role = Role(
            tenant_id=tenant_a.id,
            name="admin",
            capabilities=["documents.manage", "corpus.view", "chat.use"],
        )
        member_role = Role(
            tenant_id=tenant_a.id, name="member", capabilities=["corpus.view", "chat.use"]
        )
        viewer_role = Role(
            tenant_id=tenant_a.id, name="viewer", capabilities=["corpus.view", "chat.use"]
        )
        carol_role = Role(
            tenant_id=tenant_b.id,
            name="member",
            capabilities=["documents.manage", "corpus.view", "chat.use"],
        )
        doc_open = Document(
            tenant_id=tenant_a.id,
            name="open.pdf",
            status="indexed",
            storage_key=f"{tenant_a.id}/open/open.pdf",
            dispatch_ready=True,
            visibility="tenant",
        )
        doc_secret = Document(
            tenant_id=tenant_a.id,
            name="secret.pdf",
            status="indexed",
            storage_key=f"{tenant_a.id}/secret/secret.pdf",
            dispatch_ready=True,
            visibility="restricted",
        )
        session.add_all([admin_role, member_role, viewer_role, carol_role, doc_open, doc_secret])
        await session.flush()
        session.add_all(
            [
                Chunk(
                    tenant_id=tenant_a.id,
                    document_id=doc_open.id,
                    position=0,
                    content="open alpha content",
                    embedding=_embedding("open alpha content"),
                ),
                Chunk(
                    tenant_id=tenant_a.id,
                    document_id=doc_secret.id,
                    position=0,
                    content="secret alpha content",
                    embedding=_embedding("secret alpha content"),
                ),
            ]
        )
        session.add_all(
            [
                Membership(tenant_id=tenant_a.id, user_id=admin.id, role_id=admin_role.id),
                Membership(tenant_id=tenant_a.id, user_id=member.id, role_id=member_role.id),
                Membership(tenant_id=tenant_a.id, user_id=viewer.id, role_id=viewer_role.id),
                Membership(tenant_id=tenant_b.id, user_id=carol.id, role_id=carol_role.id),
            ]
        )
        await session.commit()
        return {
            "tenant_a": tenant_a.id,
            "tenant_b": tenant_b.id,
            "admin": admin.id,
            "member": member.id,
            "viewer": viewer.id,
            "carol": carol.id,
            "member_role": member_role.id,
            "viewer_role": viewer_role.id,
            "doc_open": doc_open.id,
            "doc_secret": doc_secret.id,
        }


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings, *, user_id, tenant_id) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def _grant(db, *, tenant_id, document_id, grantee_type, grantee_id):
    async with db.session_factory() as session:
        session.add(
            DocumentGrant(
                tenant_id=tenant_id,
                document_id=document_id,
                grantee_type=grantee_type,
                grantee_id=grantee_id,
            )
        )
        await session.commit()


async def test_restricted_without_grant_hidden_from_list_and_detail(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _docs_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        listed = await client.get("/api/documents", headers=_cookie(token))
        assert {d["id"] for d in listed.json()["documents"]} == {str(ids["doc_open"])}
        detail = await client.get(f"/api/documents/{ids['doc_secret']}", headers=_cookie(token))
        missing = await client.get(f"/api/documents/{uuid.uuid4()}", headers=_cookie(token))
    assert detail.status_code == missing.status_code == 404
    assert detail.json() == missing.json()


async def test_user_grant_restores_list_and_detail(migrated_db):
    ids = await _seed(migrated_db)
    await _grant(
        migrated_db,
        tenant_id=ids["tenant_a"],
        document_id=ids["doc_secret"],
        grantee_type="user",
        grantee_id=ids["member"],
    )
    app, settings = _docs_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        listed = await client.get("/api/documents", headers=_cookie(token))
        assert {d["id"] for d in listed.json()["documents"]} == {
            str(ids["doc_open"]),
            str(ids["doc_secret"]),
        }
        detail = await client.get(f"/api/documents/{ids['doc_secret']}", headers=_cookie(token))
    assert detail.status_code == 200
    assert detail.json()["visibility"] == "restricted"


async def test_role_grant_restores_visibility_for_role_members_only(migrated_db):
    ids = await _seed(migrated_db)
    await _grant(
        migrated_db,
        tenant_id=ids["tenant_a"],
        document_id=ids["doc_secret"],
        grantee_type="role",
        grantee_id=ids["member_role"],
    )
    app, settings = _docs_app(migrated_db)
    member = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    viewer = _token(settings, user_id=ids["viewer"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        granted = await client.get(f"/api/documents/{ids['doc_secret']}", headers=_cookie(member))
        denied = await client.get(f"/api/documents/{ids['doc_secret']}", headers=_cookie(viewer))
    assert granted.status_code == 200
    assert denied.status_code == 404


async def test_cross_tenant_grant_surfaces_stay_neutral_404(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _docs_app(migrated_db)
    carol = _token(settings, user_id=ids["carol"], tenant_id=ids["tenant_b"])
    admin = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        cross = await client.get(f"/api/documents/{ids['doc_secret']}", headers=_cookie(carol))
        missing = await client.get(f"/api/documents/{uuid.uuid4()}", headers=_cookie(admin))
        grants = await client.get(
            f"/api/documents/{ids['doc_secret']}/grants", headers=_cookie(carol)
        )
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()
    assert grants.status_code == 404


async def test_corpus_view_without_grant_stays_hidden(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _docs_app(migrated_db)
    token = _token(settings, user_id=ids["viewer"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.get(f"/api/documents/{ids['doc_secret']}", headers=_cookie(token))
    assert response.status_code == 404  # corpus.view alone never opens restricted docs


async def test_tenant_visibility_unchanged(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _docs_app(migrated_db)
    token = _token(settings, user_id=ids["viewer"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.get(f"/api/documents/{ids['doc_open']}", headers=_cookie(token))
    assert response.status_code == 200
    assert response.json()["visibility"] == "tenant"


async def test_restricted_without_grant_absent_from_search(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _search_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post(
            "/api/search", json={"query": "alpha", "top_k": 50}, headers=_cookie(token)
        )
    assert response.status_code == 200
    assert {r["document_id"] for r in response.json()["results"]} == {str(ids["doc_open"])}
    assert all("secret" not in r["content"] for r in response.json()["results"])


async def test_user_grant_restores_search_visibility(migrated_db):
    ids = await _seed(migrated_db)
    await _grant(
        migrated_db,
        tenant_id=ids["tenant_a"],
        document_id=ids["doc_secret"],
        grantee_type="user",
        grantee_id=ids["member"],
    )
    app, settings = _search_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post(
            "/api/search", json={"query": "alpha", "top_k": 50}, headers=_cookie(token)
        )
    assert response.status_code == 200
    assert {r["document_id"] for r in response.json()["results"]} == {
        str(ids["doc_open"]),
        str(ids["doc_secret"]),
    }


async def test_restricted_without_grant_absent_from_chat(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _chat_app(migrated_db, _FakeCompleter())
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 200
    body = response.json()
    assert all("secret" not in c["content"] for c in body["citations"])


async def test_grants_api_round_trip_with_manage(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _docs_app(migrated_db)
    admin = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    member = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        patched = await client.patch(
            f"/api/documents/{ids['doc_open']}/visibility",
            json={"visibility": "restricted"},
            headers=_cookie(admin),
        )
        assert patched.status_code == 200
        assert patched.json()["visibility"] == "restricted"
        hidden = await client.get(f"/api/documents/{ids['doc_open']}", headers=_cookie(member))
        assert hidden.status_code == 404
        created = await client.post(
            f"/api/documents/{ids['doc_open']}/grants",
            json={"grantee_type": "user", "grantee_id": str(ids["member"])},
            headers=_cookie(admin),
        )
        assert created.status_code == 201
        assert created.json()["grantee_id"] == str(ids["member"])
        dup = await client.post(
            f"/api/documents/{ids['doc_open']}/grants",
            json={"grantee_type": "user", "grantee_id": str(ids["member"])},
            headers=_cookie(admin),
        )
        assert dup.status_code == 409
        listed = await client.get(
            f"/api/documents/{ids['doc_open']}/grants", headers=_cookie(admin)
        )
        assert [g["id"] for g in listed.json()["grants"]] == [created.json()["id"]]
        assert "tenant_id" not in listed.json()["grants"][0]
        foreign = await client.post(
            f"/api/documents/{ids['doc_open']}/grants",
            json={"grantee_type": "user", "grantee_id": str(ids["carol"])},
            headers=_cookie(admin),
        )
        assert foreign.status_code == 404  # carol has no membership in tenant A
        bad = await client.post(
            f"/api/documents/{ids['doc_open']}/grants",
            json={"grantee_type": "tenant", "grantee_id": str(ids["member"])},
            headers=_cookie(admin),
        )
        assert bad.status_code == 400
        removed = await client.delete(
            f"/api/documents/{ids['doc_open']}/grants/{created.json()['id']}",
            headers=_cookie(admin),
        )
        assert removed.status_code == 204
        gone = await client.get(f"/api/documents/{ids['doc_open']}", headers=_cookie(member))
        assert gone.status_code == 404


async def test_grants_api_requires_manage(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _docs_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.get(
            f"/api/documents/{ids['doc_open']}/grants", headers=_cookie(token)
        )
    assert response.status_code == 403


async def test_admin_delete_of_restricted_doc_succeeds(migrated_db):
    """Grants never block the tenant admin's DELETE; grants cascade with the row."""
    ids = await _seed(migrated_db)
    await _grant(
        migrated_db,
        tenant_id=ids["tenant_a"],
        document_id=ids["doc_secret"],
        grantee_type="user",
        grantee_id=ids["member"],
    )
    app, settings = _docs_app(migrated_db)
    admin = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.delete(
            f"/api/documents/{ids['doc_secret']}", headers=_cookie(admin)
        )
    assert response.status_code == 204
    async with migrated_db.session_factory() as session:
        from sqlalchemy import select as _select

        assert await session.get(Document, ids["doc_secret"]) is None
        remaining = (await session.execute(_select(DocumentGrant))).scalars().all()
    assert remaining == []
