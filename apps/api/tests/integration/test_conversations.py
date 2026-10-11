"""Integration tests: F2 optional chat history persistence.

On real migrated PostgreSQL with the FakeEmbedder and recorded FakeCompleter
injected through the router factories: conversations are created, listed
(newest first), read (messages chronological), and deleted (204, idempotent
neutral 404 afterwards) strictly within the caller's tenant+user scope;
cross-tenant and cross-user access is a neutral 404 on every surface;
``POST /api/chat`` with an owned ``conversation_id`` persists the user turn
plus the assistant turn with its verified citations while the stateless path
(without ``conversation_id``) performs zero writes.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.chat.contracts import FakeCompleter
from raguard_api.chat.router import create_chat_router, create_conversations_router
from raguard_api.config import Settings, get_settings
from raguard_api.documents.contracts import FakeEmbedder
from raguard_api.documents.models import Chunk, Document, DocumentGrant
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from sqlalchemy import delete, func, select, text

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"


def _make_app(db, *, embedder=None, completer=None):
    embedder = embedder if embedder is not None else FakeEmbedder()
    completer = completer if completer is not None else FakeCompleter("Grounded [1].")
    settings = Settings(
        jwt_secret=JWT_SECRET, jwt_issuer="raguard-test", jwt_audience="raguard-api"
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_chat_router(
            session_factory=db.session_factory,
            settings=settings,
            embedder=embedder,
            completer=completer,
        )
    )
    app.include_router(create_conversations_router(session_factory=db.session_factory))
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings, completer


async def _seed(db):
    """Tenant A: owner + peer (both chat.use) and a viewer (no chat.use).

    Tenant B: carol (chat.use) with her own conversation scope.
    """
    async with db.session_factory() as session:
        owner = User(email="owner-a@example.com", password_hash="x")
        peer = User(email="peer-a@example.com", password_hash="x")
        viewer = User(email="viewer-a@example.com", password_hash="x")
        carol = User(email="carol-b@example.com", password_hash="x")
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        session.add_all([owner, peer, viewer, carol, tenant_a, tenant_b])
        await session.flush()
        chat_role_a = Role(
            tenant_id=tenant_a.id,
            name="chatter",
            capabilities=["corpus.view", "chat.use"],
        )
        viewer_role_a = Role(tenant_id=tenant_a.id, name="viewer", capabilities=["corpus.view"])
        chat_role_b = Role(tenant_id=tenant_b.id, name="chatter", capabilities=["chat.use"])
        doc = Document(
            tenant_id=tenant_a.id,
            name="alpha-guide.pdf",
            storage_key=f"{tenant_a.id}/doc-a/alpha-guide.pdf",
        )
        session.add_all([chat_role_a, viewer_role_a, chat_role_b, doc])
        await session.flush()
        session.add(
            Chunk(
                tenant_id=tenant_a.id,
                document_id=doc.id,
                position=0,
                content="alpha beta gamma",
                embedding=FakeEmbedder().embed(["alpha beta gamma"])[0],
            )
        )
        session.add_all(
            [
                Membership(tenant_id=tenant_a.id, user_id=owner.id, role_id=chat_role_a.id),
                Membership(tenant_id=tenant_a.id, user_id=peer.id, role_id=chat_role_a.id),
                Membership(tenant_id=tenant_a.id, user_id=viewer.id, role_id=viewer_role_a.id),
                Membership(tenant_id=tenant_b.id, user_id=carol.id, role_id=chat_role_b.id),
            ]
        )
        await session.commit()
        return {
            "tenant_a": tenant_a.id,
            "tenant_b": tenant_b.id,
            "owner": owner.id,
            "peer": peer.id,
            "viewer": viewer.id,
            "carol": carol.id,
            "doc": doc.id,
        }


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings: Settings, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def _message_count(db) -> int:
    async with db.session_factory() as session:
        return (
            await session.execute(select(func.count()).select_from(text("messages")))
        ).scalar_one()


async def test_create_lists_own_conversation_newest_first(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        first = await client.post(
            "/api/conversations", json={"title": "First"}, headers=_cookie(token)
        )
        assert first.status_code == 201
        first_body = first.json()
        assert set(first_body) == {"id", "title", "created_at", "updated_at"}
        assert first_body["title"] == "First"
        assert "tenant_id" not in first_body and "user_id" not in first_body
        second = await client.post("/api/conversations", json={}, headers=_cookie(token))
        assert second.status_code == 201
        assert second.json()["title"] == "New conversation"
        # Touch the second thread so recency ordering is deterministic.
        chatted = await client.post(
            "/api/chat",
            json={"query": "alpha", "conversation_id": second.json()["id"]},
            headers=_cookie(token),
        )
        assert chatted.status_code == 200
        listing = await client.get("/api/conversations", headers=_cookie(token))
    assert listing.status_code == 200
    conversations = listing.json()["conversations"]
    assert [row["title"] for row in conversations] == ["New conversation", "First"]
    for row in conversations:
        assert set(row) == {"id", "title", "created_at", "updated_at"}


async def test_get_returns_messages_in_chronological_order(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        created = await client.post(
            "/api/conversations", json={"title": "Thread"}, headers=_cookie(token)
        )
        conversation_id = created.json()["id"]
        chat = await client.post(
            "/api/chat",
            json={"query": "alpha", "conversation_id": conversation_id},
            headers=_cookie(token),
        )
        assert chat.status_code == 200
        detail = await client.get(f"/api/conversations/{conversation_id}", headers=_cookie(token))
    assert detail.status_code == 200
    body = detail.json()
    assert set(body) == {"id", "title", "created_at", "updated_at", "messages"}
    roles = [message["role"] for message in body["messages"]]
    assert roles == ["user", "assistant"]
    assert body["messages"][0]["content"] == "alpha"
    assert body["messages"][0]["citations"] == []
    assert body["messages"][1]["content"] == "Grounded [1]."
    assert len(body["messages"][1]["citations"]) == 1
    citation = body["messages"][1]["citations"][0]
    assert set(citation) == {"chunk_id", "document_id", "document_name", "position", "content"}
    assert citation["content"] == "alpha beta gamma"
    assert "tenant_id" not in body and "user_id" not in body


async def test_delete_removes_thread_and_messages_then_404s_neutrally(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        created = await client.post(
            "/api/conversations", json={"title": "Gone"}, headers=_cookie(token)
        )
        conversation_id = created.json()["id"]
        await client.post(
            "/api/chat",
            json={"query": "alpha", "conversation_id": conversation_id},
            headers=_cookie(token),
        )
        deleted = await client.delete(
            f"/api/conversations/{conversation_id}", headers=_cookie(token)
        )
        assert deleted.status_code == 204
        assert await _message_count(migrated_db) == 0
        reread = await client.get(f"/api/conversations/{conversation_id}", headers=_cookie(token))
        assert reread.status_code == 404
        assert reread.json()["error"]["code"] == "not_found"
        redelete = await client.delete(
            f"/api/conversations/{conversation_id}", headers=_cookie(token)
        )
        assert redelete.status_code == 404
        assert redelete.json()["error"]["code"] == "not_found"
        listing = await client.get("/api/conversations", headers=_cookie(token))
    assert listing.json() == {"conversations": []}


async def test_cross_tenant_access_is_neutral_404(migrated_db):
    ids = await _seed(migrated_db)
    completer = FakeCompleter("Grounded [1].")
    app, settings, _ = _make_app(migrated_db, completer=completer)
    carol_token = _token(settings, user_id=ids["carol"], tenant_id=ids["tenant_b"])
    owner_token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        created = await client.post(
            "/api/conversations", json={"title": "Carol"}, headers=_cookie(carol_token)
        )
        foreign_id = created.json()["id"]
        reread = await client.get(f"/api/conversations/{foreign_id}", headers=_cookie(owner_token))
        assert reread.status_code == 404
        assert reread.json()["error"]["code"] == "not_found"
        redelete = await client.delete(
            f"/api/conversations/{foreign_id}", headers=_cookie(owner_token)
        )
        assert redelete.status_code == 404
        chat = await client.post(
            "/api/chat",
            json={"query": "alpha", "conversation_id": foreign_id},
            headers=_cookie(owner_token),
        )
        assert chat.status_code == 404
        assert chat.json()["error"]["code"] == "not_found"
        listing = await client.get("/api/conversations", headers=_cookie(owner_token))
    assert listing.json() == {"conversations": []}
    assert completer.calls == []  # foreign id rejected before any provider call


async def test_cross_user_access_within_tenant_is_neutral_404(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    owner_token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    peer_token = _token(settings, user_id=ids["peer"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        created = await client.post(
            "/api/conversations", json={"title": "Mine"}, headers=_cookie(owner_token)
        )
        conversation_id = created.json()["id"]
        reread = await client.get(
            f"/api/conversations/{conversation_id}", headers=_cookie(peer_token)
        )
        assert reread.status_code == 404
        redelete = await client.delete(
            f"/api/conversations/{conversation_id}", headers=_cookie(peer_token)
        )
        assert redelete.status_code == 404
        chat = await client.post(
            "/api/chat",
            json={"query": "alpha", "conversation_id": conversation_id},
            headers=_cookie(peer_token),
        )
        assert chat.status_code == 404
        listing = await client.get("/api/conversations", headers=_cookie(peer_token))
    assert listing.json() == {"conversations": []}


async def test_chat_with_unknown_conversation_id_404s_before_provider_call(migrated_db):
    ids = await _seed(migrated_db)
    completer = FakeCompleter("Should never run.")
    app, settings, _ = _make_app(migrated_db, completer=completer)
    token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post(
            "/api/chat",
            json={"query": "alpha", "conversation_id": str(uuid.uuid4())},
            headers=_cookie(token),
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert completer.calls == []
    assert await _message_count(migrated_db) == 0


async def test_stateless_chat_writes_nothing(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 200
    assert response.json()["answer"] == "Grounded [1]."
    assert await _message_count(migrated_db) == 0
    async with migrated_db.session_factory() as session:
        remaining = (
            await session.execute(select(func.count()).select_from(text("conversations")))
        ).scalar_one()
    assert remaining == 0


async def test_conversations_require_chat_use_capability(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    viewer_token = _token(settings, user_id=ids["viewer"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        created = await client.post(
            "/api/conversations", json={"title": "Nope"}, headers=_cookie(viewer_token)
        )
        assert created.status_code == 403
        listing = await client.get("/api/conversations", headers=_cookie(viewer_token))
        assert listing.status_code == 403
        detail = await client.get(
            f"/api/conversations/{uuid.uuid4()}", headers=_cookie(viewer_token)
        )
        assert detail.status_code == 403


async def test_unauthenticated_conversation_access_is_401(migrated_db):
    await _seed(migrated_db)
    app, _, _ = _make_app(migrated_db)
    async with _client(app) as client:
        created = await client.post("/api/conversations", json={"title": "Nope"})
        assert created.status_code == 401
        listing = await client.get("/api/conversations")
        assert listing.status_code == 401


async def test_get_refilters_citations_after_grant_revoked(migrated_db):
    """History reads re-validate citations: a revoked grant hides chunk text.

    The assistant message text is preserved but its citations shrink to []
    once the underlying restricted document is no longer visible — the same
    visibility semantics retrieval enforces before ranking.
    """
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["owner"], tenant_id=ids["tenant_a"])
    async with migrated_db.session_factory() as session:
        doc = Document(
            tenant_id=ids["tenant_a"],
            name="secret.pdf",
            status="indexed",
            storage_key=f"{ids['tenant_a']}/secret/secret.pdf",
            dispatch_ready=True,
            visibility="restricted",
        )
        session.add(doc)
        await session.flush()
        session.add(
            Chunk(
                tenant_id=ids["tenant_a"],
                document_id=doc.id,
                position=0,
                content="quasar tango",
                embedding=FakeEmbedder().embed(["quasar tango"])[0],
            )
        )
        session.add(
            DocumentGrant(
                tenant_id=ids["tenant_a"],
                document_id=doc.id,
                grantee_type="user",
                grantee_id=ids["owner"],
            )
        )
        await session.commit()
        doc_id = doc.id
    async with _client(app) as client:
        created = await client.post("/api/conversations", json={}, headers=_cookie(token))
        conversation_id = created.json()["id"]
        chat = await client.post(
            "/api/chat",
            json={"query": "quasar tango", "conversation_id": conversation_id},
            headers=_cookie(token),
        )
        assert chat.status_code == 200
        assert len(chat.json()["citations"]) == 1
        before = await client.get(f"/api/conversations/{conversation_id}", headers=_cookie(token))
        assert len(before.json()["messages"][1]["citations"]) == 1
        # Revoke the grant: fresh retrieval would now hide the chunk...
        async with migrated_db.session_factory() as session:
            await session.execute(
                delete(DocumentGrant).where(
                    DocumentGrant.tenant_id == ids["tenant_a"],
                    DocumentGrant.document_id == doc_id,
                )
            )
            await session.commit()
        # ...and so must the history read: text kept, citations emptied.
        after = await client.get(f"/api/conversations/{conversation_id}", headers=_cookie(token))
    assert after.status_code == 200
    messages = after.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Grounded [1]."
    assert messages[1]["citations"] == []


async def test_0004_tables_exist_and_round_trip(migrated_db):
    async with migrated_db.engine.connect() as conn:
        tables = {
            row["tablename"]
            for row in (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            ).mappings()
        }
    assert {"conversations", "messages"} <= tables
    await migrated_db.alembic("down", "0003")
    async with migrated_db.engine.connect() as conn:
        tables = {
            row["tablename"]
            for row in (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            ).mappings()
        }
    assert {"conversations", "messages"}.isdisjoint(tables)
    await migrated_db.alembic("up", "head")
    async with migrated_db.engine.connect() as conn:
        tables = {
            row["tablename"]
            for row in (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            ).mappings()
        }
    assert {"conversations", "messages"} <= tables
