"""E2E smoke: real OpenAI chat contract against PostgreSQL (task 5.4 opt-in).

Credential-gated: the whole module is skipped unless ``OPENAI_API_KEY`` is
set, so ordinary test runs never touch the provider. With the real embedder
and the real ``OpenAICompleter`` wired through the chat router, the smoke
proves the answer/citation contract end to end: one authorized tenant A chunk
is retrieved and completed, the response returns a grounded ``answer`` plus
``citations`` referencing exactly that chunk (same authorized chunk
membership) with allowlisted fields only, and no tenant id appears anywhere.
The credential is read from the environment only, never logged, echoed, or
asserted.
"""

import asyncio
import os
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from raguard_api.auth.jwt import create_access_token
from raguard_api.chat.providers.openai import OpenAICompleter
from raguard_api.chat.router import create_chat_router
from raguard_api.config import Settings, get_settings
from raguard_api.documents.models import Chunk, Document
from raguard_api.errors import register_error_handlers
from raguard_api.identity.models import Membership, Role, Tenant, User
from raguard_api.retrieval.embeddings import OpenAIEmbedder

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set; real provider smoke is opt-in",
    ),
]

JWT_SECRET = "test-secret-0123456789abcdef1234"

CITATION_FIELDS = {"chunk_id", "document_id", "document_name", "position", "content"}


async def test_real_chat_returns_grounded_answer_with_same_authorized_chunk_membership(
    migrated_db,
):
    embedder = OpenAIEmbedder(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        timeout_seconds=30.0,
    )
    settings = Settings(
        jwt_secret=JWT_SECRET, jwt_issuer="raguard-test", jwt_audience="raguard-api"
    )
    completer = OpenAICompleter(
        api_key=os.environ["OPENAI_API_KEY"],
        model=settings.chat_model,
        max_output_tokens=settings.chat_max_output_tokens,
        timeout_seconds=settings.provider_timeout_seconds,
        retries=settings.chat_retries,
    )

    content = "alpha beta gamma"
    vector = (await asyncio.to_thread(embedder.embed, [content]))[0]
    async with migrated_db.session_factory() as session:
        admin = User(email="admin@example.com", password_hash="x")
        tenant = Tenant(name="E2E Tenant")
        session.add_all([admin, tenant])
        await session.flush()
        role = Role(tenant_id=tenant.id, name="admin", capabilities=["chat.use"])
        document = Document(
            tenant_id=tenant.id,
            name="alpha-guide.pdf",
            status="indexed",
            storage_key=f"{tenant.id}/alpha-guide.pdf",
            dispatch_ready=True,
        )
        session.add_all([role, document])
        await session.flush()
        chunk = Chunk(
            tenant_id=tenant.id,
            document_id=document.id,
            position=0,
            content=content,
            embedding=vector,
        )
        session.add(chunk)
        session.add(Membership(tenant_id=tenant.id, user_id=admin.id, role_id=role.id))
        await session.commit()
        chunk_id = chunk.id
        document_id = document.id
        tenant_id = tenant.id

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(
        create_chat_router(
            session_factory=migrated_db.session_factory,
            settings=settings,
            embedder=embedder,
            completer=completer,
        )
    )
    app.dependency_overrides[get_settings] = lambda: settings
    token = create_access_token(user_id=admin.id, tenant_id=tenant_id, settings=settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/chat",
            json={"query": "alpha", "top_k": 1},
            headers={"Cookie": f"raguard_session={token}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["answer"], str) and body["answer"]  # grounded answer
    assert len(body["citations"]) == 1  # cites the authorized chunk
    citation = body["citations"][0]
    assert set(citation) == CITATION_FIELDS  # allowlisted fields only
    assert uuid.UUID(citation["chunk_id"]) == chunk_id  # same authorized chunk membership
    assert uuid.UUID(citation["document_id"]) == document_id
    assert citation["document_name"] == "alpha-guide.pdf"
    assert citation["position"] == 0
    assert str(tenant_id) not in response.text  # no tenant disclosure
