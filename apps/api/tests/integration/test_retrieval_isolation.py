"""Integration tests: cross-tenant retrieval isolation gate (task 3.1 RED).

Release-gate proof of the spec scenario "Cross-tenant isolation": with real
migrated PostgreSQL and the deterministic FakeEmbedder, a tenant A member
searching terms that match tenant B content never receives a tenant B chunk
or any of its document context, and a query matching only tenant B content
returns results drawn exclusively from tenant A's corpus. The seeded tenant B
chunk text matches BOTH query terms ("alpha" and "omega"), so a missing
tenant predicate in either signal leaks it through the keyword and/or the
semantic path — the assertions below fail on that leak. No provider network
call is ever made.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.config import Settings, get_settings
from raguard_api.documents.contracts import FakeEmbedder
from raguard_api.documents.models import Chunk, Document
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from raguard_api.retrieval.router import create_retrieval_router

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"


def _embedding(text: str) -> list[float]:
    return FakeEmbedder().embed([text])[0]


def _make_app(db):
    settings = Settings(
        jwt_secret=JWT_SECRET, jwt_issuer="raguard-test", jwt_audience="raguard-api"
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_retrieval_router(
            session_factory=db.session_factory, settings=settings, embedder=FakeEmbedder()
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings


async def _seed(db):
    """Tenant A (admin + member, chat.use) with two chunks; tenant B (carol) with
    one chunk whose text matches both "alpha" and "omega" so any missing tenant
    predicate leaks it through the keyword signal."""
    async with db.session_factory() as session:
        admin = User(email="admin-a@example.com", password_hash="x")
        member = User(email="member-a@example.com", password_hash="x")
        carol = User(email="carol-b@example.com", password_hash="x")
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        session.add_all([admin, member, carol, tenant_a, tenant_b])
        await session.flush()
        admin_role = Role(
            tenant_id=tenant_a.id,
            name="admin",
            capabilities=["documents.manage", "corpus.view", "chat.use"],
        )
        member_role = Role(
            tenant_id=tenant_a.id, name="member", capabilities=["corpus.view", "chat.use"]
        )
        carol_role = Role(tenant_id=tenant_b.id, name="member", capabilities=["chat.use"])
        doc_a = Document(
            tenant_id=tenant_a.id,
            name="alpha-guide.pdf",
            status="indexed",
            storage_key=f"{tenant_a.id}/doc-a/alpha-guide.pdf",
            dispatch_ready=True,
        )
        doc_b = Document(
            tenant_id=tenant_b.id,
            name="omega-notes.pdf",
            status="indexed",
            storage_key=f"{tenant_b.id}/doc-b/omega-notes.pdf",
            dispatch_ready=True,
        )
        session.add_all([admin_role, member_role, carol_role, doc_a, doc_b])
        await session.flush()
        chunks = [
            Chunk(
                tenant_id=tenant_a.id,
                document_id=doc_a.id,
                position=0,
                content="alpha beta gamma",
                embedding=_embedding("alpha beta gamma"),
            ),
            Chunk(
                tenant_id=tenant_a.id,
                document_id=doc_a.id,
                position=1,
                content="delta epsilon zeta",
                embedding=_embedding("delta epsilon zeta"),
            ),
            Chunk(
                tenant_id=tenant_b.id,
                document_id=doc_b.id,
                position=0,
                content="alpha omega secret",
                embedding=_embedding("alpha omega secret"),
            ),
        ]
        session.add_all(chunks)
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
            "carol": carol.id,
            "doc_a": doc_a.id,
            "doc_b": doc_b.id,
            "chunk_a0": chunks[0].id,
            "chunk_a1": chunks[1].id,
            "chunk_b": chunks[2].id,
        }


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings: Settings, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def test_tenant_a_search_returns_only_tenant_a_chunks(migrated_db):
    """Spec "Only authorized tenant chunks return": every result belongs to A."""
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post(
            "/api/search", json={"query": "alpha", "top_k": 50}, headers=_cookie(token)
        )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2  # tenant A owns exactly two chunks; B's must not rank
    assert {r["document_id"] for r in results} == {str(ids["doc_a"])}
    assert {uuid.UUID(r["chunk_id"]) for r in results} == {ids["chunk_a0"], ids["chunk_a1"]}
    assert all(r["document_name"] == "alpha-guide.pdf" for r in results)
    assert all("secret" not in r["content"] for r in results)


async def test_tenant_b_only_query_discloses_no_tenant_b_data(migrated_db):
    """Spec "Cross-tenant isolation (release gate)": a query matching only
    tenant B content never discloses B chunks, context, or existence."""
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/search", json={"query": "omega"}, headers=_cookie(token))
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2  # only tenant A's two chunks can ever rank
    assert {r["document_id"] for r in results} == {str(ids["doc_a"])}
    assert {uuid.UUID(r["chunk_id"]) for r in results} == {ids["chunk_a0"], ids["chunk_a1"]}
    assert all(r["document_name"] == "alpha-guide.pdf" for r in results)
    assert all("secret" not in r["content"] for r in results)


async def test_tenant_b_member_never_sees_tenant_a_chunks(migrated_db):
    """Symmetric direction: tenant B's member searching A-matching terms sees
    only B's own chunk, never A's document context."""
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["carol"], tenant_id=ids["tenant_b"])
    async with _client(app) as client:
        response = await client.post(
            "/api/search", json={"query": "alpha", "top_k": 50}, headers=_cookie(token)
        )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1  # tenant B owns exactly one chunk
    assert [r["document_id"] for r in results] == [str(ids["doc_b"])]
    assert uuid.UUID(results[0]["chunk_id"]) == ids["chunk_b"]
    assert results[0]["document_name"] == "omega-notes.pdf"
    assert "alpha" in results[0]["content"]  # B's chunk matched, only B's chunk returns
