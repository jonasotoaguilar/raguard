"""Integration tests: POST /api/search route contract (task 2.1 RED).

Route behavior on real PostgreSQL with the dimension-exact FakeEmbedder
injected through the router factory: valid requests return at most ``top_k``
fused, tenant-A-only results; empty/oversized queries and out-of-bounds
``top_k`` are rejected (400) with no retrieval; a missing ``chat.use``
capability yields 403; a no-match query and an empty corpus return the
identical neutral ``{"results": []}``; and an embedding-provider failure
returns 503 with no partial results. No provider network call is ever made.
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

RESULT_FIELDS = {
    "chunk_id",
    "document_id",
    "document_name",
    "position",
    "content",
    "keyword_rank",
    "semantic_rank",
    "score",
}


def _embedding(text: str) -> list[float]:
    return FakeEmbedder().embed([text])[0]


class _FailingEmbedder:
    def embed(self, texts):
        raise RuntimeError("openai unreachable")


def _make_app(db, *, embedder=None):
    embedder = embedder if embedder is not None else FakeEmbedder()
    settings = Settings(
        jwt_secret=JWT_SECRET, jwt_issuer="raguard-test", jwt_audience="raguard-api"
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_retrieval_router(
            session_factory=db.session_factory, settings=settings, embedder=embedder
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings


async def _seed(db, *, a_chunks: bool = True):
    """Tenant A admin (all caps) + member (no chat.use); tenant B carol (chat.use)."""
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
        member_role = Role(tenant_id=tenant_a.id, name="member", capabilities=["corpus.view"])
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
                tenant_id=tenant_b.id,
                document_id=doc_b.id,
                position=0,
                content="omega notes final",
                embedding=_embedding("omega notes final"),
            ),
        ]
        if a_chunks:
            chunks += [
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
            ]
        session.add_all(chunks)
        session.add_all(
            [
                Membership(tenant_id=tenant_a.id, user_id=admin.id, role_id=admin_role.id),
                Membership(tenant_id=tenant_a.id, user_id=member.id, role_id=member_role.id),
                Membership(tenant_id=tenant_b.id, user_id=carol.id, role_id=carol_role.id),
            ]
        )
        await session.commit()
        return {"tenant_a": tenant_a.id, "admin": admin.id, "member": member.id, "doc_a": doc_a.id}


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings: Settings, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def test_valid_search_returns_at_most_top_k_fused_results(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post(
            "/api/search", json={"query": "alpha", "top_k": 1}, headers=_cookie(token)
        )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    result = results[0]
    assert set(result) == RESULT_FIELDS
    assert result["content"] == "alpha beta gamma"  # keyword rank 1 wins after fusion
    assert result["document_name"] == "alpha-guide.pdf"
    assert result["keyword_rank"] == 1
    assert result["semantic_rank"] is not None  # dual-signal fusion really ran
    assert result["score"] > 0


async def test_valid_search_defaults_top_k_and_returns_only_tenant_chunks(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/search", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 200
    results = response.json()["results"]
    assert 1 <= len(results) <= 10  # default top_k; both signals contributed
    for result in results:
        assert set(result) == RESULT_FIELDS
        assert result["document_id"] == str(ids["doc_a"])
        assert uuid.UUID(result["chunk_id"]) is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 2001},
        {"query": "alpha", "top_k": 0},
        {"query": "alpha", "top_k": 51},
        {},
    ],
)
async def test_invalid_requests_rejected_with_400_and_no_retrieval(migrated_db, payload):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/search", json=payload, headers=_cookie(token))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "results" not in response.json()


async def test_search_requires_chat_use_capability(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/search", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert "results" not in response.json()


async def test_no_match_and_empty_corpus_return_identical_neutral_empty(migrated_db):
    ids = await _seed(migrated_db, a_chunks=False)  # tenant B keeps its chunks
    app, settings = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        no_match = await client.post("/api/search", json={"query": "omega"}, headers=_cookie(token))
        empty = await client.post("/api/search", json={"query": "alpha"}, headers=_cookie(token))
    assert no_match.status_code == empty.status_code == 200
    assert no_match.json() == empty.json() == {"results": []}  # neutral, nothing disclosed


async def test_provider_failure_returns_503_without_partial_results(migrated_db):
    ids = await _seed(migrated_db)
    app, settings = _make_app(migrated_db, embedder=_FailingEmbedder())
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/search", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "results" not in response.json()
