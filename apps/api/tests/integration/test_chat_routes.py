"""Integration tests: POST /api/chat route contract (tasks 4.1-4.2 RED, 4.3 GREEN).

Route behavior on real PostgreSQL with the FakeEmbedder and recorded
FakeCompleter injected through the router factory: valid requests return a
grounded answer with at most ``top_k`` allowlisted citations and the prompt
built from authorized chunks; invalid payloads are rejected (400) before any
retrieval or completion; missing/invalid tokens yield 401 and a missing
``chat.use`` 403 with zero provider calls; grants apply on the next request
(fresh resolution); empty corpus and populated no-match return the
byte-identical neutral ``{answer: null, citations: []}`` with zero completer
calls. No provider network call is ever made.

PR4b failure gates (route-level): a typed provider failure and an out-of-set
citation marker both map to the generic 503 envelope with no partial answer or
citations and no internal detail leak.
"""

import hashlib
import math
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.chat.contracts import FakeCompleter
from raguard_api.chat.prompts import SYSTEM_PROMPT, UNTRUSTED_SOURCES_END, UNTRUSTED_SOURCES_START
from raguard_api.chat.providers import CompletionError
from raguard_api.chat.router import create_chat_router
from raguard_api.config import Settings, get_settings
from raguard_api.documents.contracts import EMBEDDING_DIMENSION, FakeEmbedder
from raguard_api.documents.models import Chunk, Document
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from sqlalchemy import text

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"

CITATION_FIELDS = {"chunk_id", "document_id", "document_name", "position", "content"}


class _FailingEmbedder:
    def embed(self, texts):
        raise RuntimeError("openai unreachable")


class _ContentEmbedder:
    """Deterministic: a shared token lands inside the 0.5 distance cutoff, no
    shared token orthogonal (outside it), so populated no-match is neutral."""

    def embed(self, texts):
        vectors = []
        for item in texts:
            axes = {}
            for token in item.lower().split():
                axis = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big") % 1536
                axes[axis] = 1.0
            norm = math.sqrt(len(axes)) if axes else 1.0
            vector = [0.0] * EMBEDDING_DIMENSION
            for axis in axes:
                vector[axis] = 1.0 / norm
            vectors.append(vector)
        return vectors


class _FailureCompleter:
    """Completer that raises a typed provider failure when invoked."""

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = []

    def complete(self, prompt):
        self.calls.append(prompt)
        raise self.exc


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
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings, completer


async def _seed(db, *, chunks: bool = True, embedder=None):
    """Tenant A with an admin (chat.use) and a member (corpus.view only)."""
    async with db.session_factory() as session:
        admin = User(email="admin@example.com", password_hash="x")
        member = User(email="member@example.com", password_hash="x")
        tenant = Tenant(name="Tenant A")
        session.add_all([admin, member, tenant])
        await session.flush()
        admin_role = Role(
            tenant_id=tenant.id,
            name="admin",
            capabilities=["documents.manage", "corpus.view", "chat.use"],
        )
        member_role = Role(tenant_id=tenant.id, name="member", capabilities=["corpus.view"])
        doc = Document(
            tenant_id=tenant.id,
            name="alpha-guide.pdf",
            storage_key=f"{tenant.id}/doc-a/alpha-guide.pdf",
        )
        session.add_all([admin_role, member_role, doc])
        await session.flush()
        if chunks:
            session.add(
                Chunk(
                    tenant_id=tenant.id,
                    document_id=doc.id,
                    position=0,
                    content="alpha beta gamma",
                    embedding=(embedder or FakeEmbedder()).embed(["alpha beta gamma"])[0],
                )
            )
        session.add_all(
            [
                Membership(tenant_id=tenant.id, user_id=admin.id, role_id=admin_role.id),
                Membership(tenant_id=tenant.id, user_id=member.id, role_id=member_role.id),
            ]
        )
        await session.commit()
        return {
            "tenant": tenant.id,
            "admin": admin.id,
            "member": member.id,
            "doc": doc.id,
            "member_role": member_role.id,
        }


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"raguard_session={token}"}


def _token(settings: Settings, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, settings=settings)


async def test_valid_chat_returns_grounded_answer_within_top_k(migrated_db):
    ids = await _seed(migrated_db)
    completer = FakeCompleter("Alpha sources say [1].")
    app, settings, _ = _make_app(migrated_db, completer=completer)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        response = await client.post(
            "/api/chat", json={"query": "alpha", "top_k": 1}, headers=_cookie(token)
        )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Alpha sources say [1]."
    assert len(body["citations"]) <= 1  # at most top_k
    citation = body["citations"][0]
    assert set(citation) == CITATION_FIELDS  # allowlisted fields only
    assert citation["content"] == "alpha beta gamma"
    assert citation["document_name"] == "alpha-guide.pdf"
    assert citation["position"] == 0
    assert uuid.UUID(citation["chunk_id"]) is not None
    assert uuid.UUID(citation["document_id"]) == ids["doc"]
    # The completion prompt the provider received came from the authorized set.
    assert len(completer.calls) == 1
    prompt = completer.calls[0]
    assert prompt.system_prompt == SYSTEM_PROMPT  # static secret-free system prompt
    assert "alpha beta gamma" in prompt.user_prompt  # authorized chunk content only
    assert UNTRUSTED_SOURCES_START in prompt.user_prompt  # delimited untrusted data
    assert UNTRUSTED_SOURCES_END in prompt.user_prompt


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
async def test_invalid_requests_rejected_with_400_before_retrieval_or_completion(
    migrated_db, payload
):
    ids = await _seed(migrated_db)
    completer = FakeCompleter("Should never run.")
    app, settings, _ = _make_app(migrated_db, embedder=_FailingEmbedder(), completer=completer)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        response = await client.post("/api/chat", json=payload, headers=_cookie(token))
    assert response.status_code == 400  # not 503: retrieval never ran
    assert response.json()["error"]["code"] == "invalid_request"
    assert completer.calls == []  # zero provider calls
    assert "answer" not in response.json()


async def test_chat_requires_valid_token_and_chat_use_capability(migrated_db):
    ids = await _seed(migrated_db)
    completer = FakeCompleter("Should never run.")
    app, settings, _ = _make_app(migrated_db, completer=completer)
    member_token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        missing = await client.post("/api/chat", json={"query": "alpha"})
        invalid = await client.post(
            "/api/chat", json={"query": "alpha"}, headers=_cookie("not-a-token")
        )
        forbidden = await client.post(
            "/api/chat", json={"query": "alpha"}, headers=_cookie(member_token)
        )
    for response in (missing, invalid):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_failed"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"
    assert completer.calls == []  # no retrieval, generation, or disclosure


async def test_authorization_resolves_freshly_per_request(migrated_db):
    ids = await _seed(migrated_db)
    app, settings, _ = _make_app(migrated_db)
    token = _token(settings, user_id=ids["member"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        denied = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
        assert denied.status_code == 403
        async with migrated_db.session_factory() as session:
            role = await session.get(Role, ids["member_role"])
            role.capabilities = ["corpus.view", "chat.use"]
            await session.commit()
        granted = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
    assert granted.status_code == 200  # grant applied on the very next request


async def test_empty_corpus_and_populated_no_match_return_byte_identical_neutral(migrated_db):
    """Task 4.2: no evidence short-circuits with zero completer calls.

    The content-based fake keeps a matching query inside the distance cutoff
    (positive control) while a query sharing no token axis stays outside it;
    the empty-corpus case reuses the same tenant after deleting its chunks.
    """
    embedder = _ContentEmbedder()
    completer = FakeCompleter("Should never run.")
    ids = await _seed(migrated_db, embedder=embedder)
    app, settings, _ = _make_app(migrated_db, embedder=embedder, completer=completer)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        match = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
        populated_no_match = await client.post(
            "/api/chat", json={"query": "omega"}, headers=_cookie(token)
        )
    assert match.status_code == 200
    assert match.json()["answer"] is not None  # positive control: pipeline really ran
    assert len(completer.calls) == 1
    async with migrated_db.session_factory() as session:
        await session.execute(text("DELETE FROM chunks"))
        await session.commit()
    async with _client(app) as client:
        empty_corpus = await client.post(
            "/api/chat", json={"query": "alpha"}, headers=_cookie(token)
        )
    neutral = {"answer": None, "citations": []}
    assert populated_no_match.json() == neutral  # neutral, nothing disclosed
    assert empty_corpus.json() == neutral
    assert populated_no_match.json() == empty_corpus.json()  # byte-identical
    assert len(completer.calls) == 1  # both no-evidence requests made zero calls


async def test_provider_failure_returns_safe_503_with_no_partial_answer(migrated_db):
    """PR4b: typed provider failure at the HTTP boundary -> generic safe 503.

    The completion is reached (retrieval ran, one attempt) but its typed
    failure maps to the generic envelope: no partial answer, no citations, no
    provider detail leak, no fallback.
    """
    ids = await _seed(migrated_db)
    completer = _FailureCompleter(CompletionError("internal provider detail"))
    app, settings, _ = _make_app(migrated_db, completer=completer)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        response = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "service_unavailable", "message": "Chat unavailable"}
    }
    assert "answer" not in response.json()  # no partial answer
    assert "citations" not in response.json()  # no partial citations
    assert "internal provider detail" not in response.text  # no detail leak
    assert len(completer.calls) == 1  # provider was reached; no fallback ran


async def test_out_of_set_citation_returns_safe_503_with_no_partial_answer(migrated_db):
    """PR4b: an out-of-set citation marker at the HTTP boundary -> safe 503.

    Exactly one authorized chunk is retrieved and the completion cites [9];
    verification rejects the whole response: same generic envelope, nothing
    partial rendered.
    """
    ids = await _seed(migrated_db)
    completer = FakeCompleter("Claims [9].")
    app, settings, _ = _make_app(migrated_db, completer=completer)
    token = _token(settings, user_id=ids["admin"], tenant_id=ids["tenant"])
    async with _client(app) as client:
        response = await client.post("/api/chat", json={"query": "alpha"}, headers=_cookie(token))
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "service_unavailable", "message": "Chat unavailable"}
    }
    assert "answer" not in response.json()
    assert "citations" not in response.json()
    assert len(completer.calls) == 1  # completion ran; verification rejected it whole
    assert "alpha beta gamma" in completer.calls[0].user_prompt  # one chunk retrieved
