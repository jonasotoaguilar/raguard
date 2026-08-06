"""E2E smoke: real OpenAI embedding against the halfvec(1536) contract (task 3.2 RED).

Credential-gated: the whole module is skipped unless ``OPENAI_API_KEY`` is
set, so ordinary test runs never touch the provider. The smoke embeds one
query through the real ``OpenAIEmbedder``, asserts exactly
``EMBEDDING_DIMENSION`` (1536) dimensions, stores the vector in a real
``halfvec(1536)`` chunk column, and runs the tenant-filtered semantic query
against it — proving provider output binds cleanly to the storage contract
(spec: "Query binds against stored embeddings"). The credential is read from
the environment only, never logged, echoed, or asserted.
"""

import asyncio
import os
import uuid

import pytest
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.documents.contracts import EMBEDDING_DIMENSION
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import Tenant
from raguard_api.retrieval.embeddings import OpenAIEmbedder
from raguard_api.retrieval.queries import build_semantic_query

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set; real provider smoke is opt-in",
    ),
]


async def test_real_provider_embedding_is_1536_dims_and_binds_to_halfvec(migrated_db):
    embedder = OpenAIEmbedder(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        timeout_seconds=30.0,
    )
    query_text = "alpha beta gamma"
    vectors = await asyncio.to_thread(embedder.embed, [query_text])
    assert len(vectors) == 1
    vector = vectors[0]
    assert len(vector) == EMBEDDING_DIMENSION  # exactly 1536, per the ingestion contract

    async with migrated_db.session_factory() as session:
        tenant = Tenant(name="Provider Smoke")
        session.add(tenant)
        await session.flush()
        document = Document(
            tenant_id=tenant.id,
            name="smoke.pdf",
            status="indexed",
            storage_key=f"{tenant.id}/smoke.pdf",
            dispatch_ready=True,
        )
        session.add(document)
        await session.flush()
        chunk = Chunk(
            tenant_id=tenant.id,
            document_id=document.id,
            position=0,
            content=query_text,
            embedding=vector,
        )
        session.add(chunk)
        await session.commit()
        chunk_id = chunk.id
        tenant_id = tenant.id

    scope = AuthorizationScope(
        tenant_id=tenant_id, user_id=uuid.uuid4(), capabilities=frozenset({"chat.use"})
    )
    statement = build_semantic_query(tenant_predicate=scope.tenant_predicate, limit=5)
    async with migrated_db.session_factory() as session:
        rows = (await session.execute(statement, {"embedding": vector})).all()
    assert [row.chunk_id for row in rows] == [chunk_id]
