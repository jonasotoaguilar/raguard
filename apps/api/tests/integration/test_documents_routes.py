"""Integration tests: authorized upload and tenant-scoped reads (task 2.3 RED).

Route behavior on real PostgreSQL with fake storage/queue injected through the
router factory: valid uploads land as ``pending`` with one ID-only job and a
tenant-prefixed object; auth/type/size/signature rejections persist nothing;
storage/enqueue failures and the enqueue-accepted/response-failed ghost are
compensated so no row, chunk, object, or status survives; reads are scoped by
the parameterized tenant predicate with a neutral cross-tenant 404.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.config import Settings, get_settings
from raguard_api.documents.contracts import FakeJobQueue, FakeObjectStore
from raguard_api.documents.models import Document
from raguard_api.documents.router import create_documents_router
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from sqlalchemy import select

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"
DEFAULT_MAX_UPLOAD = 20 * 1024 * 1024


def _make_app(db, *, store=None, queue=None, max_upload_bytes=DEFAULT_MAX_UPLOAD):
    store = store if store is not None else FakeObjectStore()
    queue = queue if queue is not None else FakeJobQueue()
    settings = Settings(
        jwt_secret=JWT_SECRET,
        jwt_issuer="raguard-test",
        jwt_audience="raguard-api",
        max_upload_bytes=max_upload_bytes,
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_documents_router(
            session_factory=db.session_factory, settings=settings, store=store, queue=queue
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings, store, queue


async def _seed(db):
    """Tenant A: admin (manage+view), member (view only). Tenant B: carol (view)."""
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
            capabilities=["documents.manage", "corpus.view", "chat.use"],
        )
        member_role = Role(
            tenant_id=tenant_a.id, name="member", capabilities=["corpus.view", "chat.use"]
        )
        carol_role = Role(
            tenant_id=tenant_b.id, name="member", capabilities=["corpus.view", "chat.use"]
        )
        session.add_all([admin_role, member_role, carol_role])
        await session.flush()
        doc_a1 = Document(
            tenant_id=tenant_a.id,
            name="annual.pdf",
            status="indexed",
            storage_key=f"{tenant_a.id}/seed-a1/annual.pdf",
            dispatch_ready=True,
        )
        doc_a2 = Document(
            tenant_id=tenant_a.id,
            name="broken.md",
            status="failed",
            failure_reason="malformed",
            storage_key=f"{tenant_a.id}/seed-a2/broken.md",
            dispatch_ready=True,
        )
        doc_b1 = Document(
            tenant_id=tenant_b.id,
            name="other.pdf",
            status="pending",
            storage_key=f"{tenant_b.id}/seed-b1/other.pdf",
        )
        session.add_all([doc_a1, doc_a2, doc_b1])
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
            "member_role": member_role.id,
            "doc_a1": doc_a1.id,
            "doc_a2": doc_a2.id,
            "doc_b1": doc_b1.id,
        }


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings: Settings, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def _upload(
    client,
    token,
    *,
    filename="report.pdf",
    content=b"%PDF-1.4\nhello",
    content_type="application/pdf",
):
    return await client.post(
        "/api/documents",
        files={"file": (filename, content, content_type)},
        headers=_cookie(token),
    )


async def _document_rows(db):
    async with db.session_factory() as session:
        return (await session.execute(select(Document))).scalars().all()


async def _uploaded_document_names(db):
    return {row.name for row in await _document_rows(db)}


def test_default_size_bound_is_20_mib():
    assert Settings(jwt_secret=JWT_SECRET).max_upload_bytes == 20 * 1024 * 1024


async def test_admin_uploads_valid_pdf_accepted_pending(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, store, queue = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(client, token)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["name"] == "report.pdf"
    assert body["failure_reason"] is None
    document_id = uuid.UUID(body["id"])
    key = f"{ids['tenant_a']}/{document_id}/report.pdf"
    assert store.get(key) == b"%PDF-1.4\nhello"
    assert queue.enqueued == [(f"ingest:{document_id}", document_id)]
    rows = await _document_rows(migrated_db)
    row = next(row for row in rows if row.id == document_id)
    assert row.tenant_id == ids["tenant_a"]
    assert row.dispatch_ready is True  # unready -> enqueue -> ready


async def test_markdown_upload_accepted_pending(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(
            client, token, filename="notes.md", content=b"# Title", content_type="text/markdown"
        )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"


async def test_upload_without_cookie_returns_401(migrated_db):
    await _seed(migrated_db)
    app, _, _, _ = _make_app(migrated_db)
    async with _client(app) as client:
        response = await client.post(
            "/api/documents", files={"file": ("r.pdf", b"%PDF-1.4", "application/pdf")}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_member_without_manage_capability_cannot_upload(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, store, queue = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(client, token)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert store.put_keys == []
    assert queue.enqueued == []
    assert "report.pdf" not in await _uploaded_document_names(migrated_db)  # nothing persisted


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "max_bytes"),
    [
        ("evil.exe", b"MZ", "application/octet-stream", DEFAULT_MAX_UPLOAD),
        ("report.pdf", b"not a pdf at all", "application/pdf", DEFAULT_MAX_UPLOAD),
        ("report.pdf", b"x" * 2048, "application/pdf", 1024),
    ],
)
async def test_upload_rejects_invalid_files(
    migrated_db, filename, content, content_type, max_bytes
):
    ids = await _seed(migrated_db)
    app, settings, store, queue = _make_app(migrated_db, max_upload_bytes=max_bytes)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(
            client, token, filename=filename, content=content, content_type=content_type
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert store.put_keys == []
    assert queue.enqueued == []
    assert filename not in await _uploaded_document_names(migrated_db)


async def test_upload_sanitizes_path_traversal_basename(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, store, queue = _make_app(migrated_db)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(client, token, filename="../evil.pdf")
    assert response.status_code == 201  # client path is stripped, never trusted
    assert response.json()["name"] == "evil.pdf"
    document_id = uuid.UUID(response.json()["id"])
    key = f"{ids['tenant_a']}/{document_id}/evil.pdf"
    assert store.get(key) == b"%PDF-1.4\nhello"
    assert ".." not in key
    assert queue.enqueued == [(f"ingest:{document_id}", document_id)]


class FailingStore(FakeObjectStore):
    def put(self, key: str, data: bytes) -> None:
        raise OSError("s3 unreachable")


class FailingQueue(FakeJobQueue):
    def enqueue(self, job_id: str, document_id: uuid.UUID) -> None:
        raise RuntimeError("redis down")


async def test_storage_failure_rejects_cleanly(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _, queue = _make_app(migrated_db, store=FailingStore())
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(client, token)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert queue.enqueued == []
    assert "report.pdf" not in await _uploaded_document_names(migrated_db)


async def test_enqueue_failure_compensates_object_and_row(migrated_db):
    ids = await _seed(migrated_db)
    store = FakeObjectStore()
    app, settings, _, _ = _make_app(migrated_db, store=store, queue=FailingQueue())
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(client, token)
    assert response.status_code == 503
    assert store.deleted_keys == store.put_keys  # object put then compensated away
    assert len(store.deleted_keys) == 1
    assert "report.pdf" not in await _uploaded_document_names(migrated_db)


class _FlakySession:
    """Delegates to a real AsyncSession but fails the 2nd commit (the ready commit)."""

    def __init__(self, inner, gate: dict) -> None:
        self._inner = inner
        self._gate = gate

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return await self._inner.__aexit__(*exc)

    async def commit(self) -> None:
        self._gate["commits"] += 1
        if self._gate["commits"] == 2:
            raise RuntimeError("response failed after enqueue accepted")
        await self._inner.commit()


def _flaky_factory(factory):
    gate = {"commits": 0}
    return lambda: _FlakySession(factory(), gate), gate


async def test_enqueue_accepted_but_response_failed_compensates_fully(migrated_db):
    ids = await _seed(migrated_db)
    store = FakeObjectStore()
    queue = FakeJobQueue()
    session_factory, _gate = _flaky_factory(migrated_db.session_factory)
    settings = Settings(
        jwt_secret=JWT_SECRET, jwt_issuer="raguard-test", jwt_audience="raguard-api"
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_documents_router(
            session_factory=session_factory, settings=settings, store=store, queue=queue
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await _upload(client, token)
    assert response.status_code == 503
    # The job was accepted (ghost) but the ghost row, chunks, object, and
    # status are all gone: compensation leaves nothing behind.
    assert len(queue.enqueued) == 1
    assert store.deleted_keys == store.put_keys
    assert len(store.deleted_keys) == 1
    assert "report.pdf" not in await _uploaded_document_names(migrated_db)


async def test_member_lists_only_own_tenant_documents(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.get("/api/documents", headers=_cookie(token))
    assert response.status_code == 200
    documents = response.json()["documents"]
    assert {document["id"] for document in documents} == {str(ids["doc_a1"]), str(ids["doc_a2"])}
    by_id = {document["id"]: document for document in documents}
    assert by_id[str(ids["doc_a1"])]["status"] == "indexed"
    assert by_id[str(ids["doc_a1"])]["failure_reason"] is None
    assert by_id[str(ids["doc_a2"])]["status"] == "failed"
    assert by_id[str(ids["doc_a2"])]["failure_reason"] == "malformed"
    assert "other.pdf" not in response.text


async def test_member_reads_own_document_detail(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.get(f"/api/documents/{ids['doc_a1']}", headers=_cookie(token))
    assert response.status_code == 200
    assert response.json() == {
        "id": str(ids["doc_a1"]),
        "name": "annual.pdf",
        "status": "indexed",
        "failure_reason": None,
    }


async def test_cross_tenant_detail_is_neutral_404(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _, _ = _make_app(migrated_db)
    carol_token = _token(settings, user_id=ids["carol"], tenant_id=ids["tenant_b"])
    admin_token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        cross = await client.get(f"/api/documents/{ids['doc_a1']}", headers=_cookie(carol_token))
        missing = await client.get(f"/api/documents/{uuid.uuid4()}", headers=_cookie(admin_token))
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()  # neutral: no existence disclosed
    assert cross.json()["error"]["code"] == "not_found"


async def test_reads_require_corpus_view(migrated_db):
    ids = await _seed(migrated_db)
    async with migrated_db.session_factory() as session:
        role = await session.get(Role, ids["member_role"])
        role.capabilities = ["chat.use"]
        await session.commit()
    app, settings, _, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant_a"])
    async with _client(app) as client:
        response = await client.get("/api/documents", headers=_cookie(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
