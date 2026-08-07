"""Integration tests: shared retrieval service contract (task 1.1 RED).

``retrieve_chunks`` is the extracted hybrid pipeline shared by ``/api/search``
and the future ``/api/chat``, exercised directly against migrated PostgreSQL
with the dimension-exact FakeEmbedder: tenant predicate before ranking, RRF
ordering, top_k cap, deterministic output, provider-failure propagation.
"""

import dataclasses
import uuid

import pytest
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.config import Settings
from raguard_api.documents.contracts import FakeEmbedder
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import Tenant
from raguard_api.retrieval.contracts import FusedResult
from raguard_api.retrieval.service import retrieve_chunks

pytestmark = pytest.mark.integration

JWT_SECRET = "test-secret-0123456789abcdef1234"

FUSED_FIELDS = {
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


def _settings(**overrides) -> Settings:
    return Settings(
        jwt_secret=JWT_SECRET,
        jwt_issuer="raguard-test",
        jwt_audience="raguard-api",
        **overrides,
    )


def _scope(tenant_id: uuid.UUID, user_id: uuid.UUID) -> AuthorizationScope:
    return AuthorizationScope(
        tenant_id=tenant_id, user_id=user_id, capabilities=frozenset({"chat.use"})
    )


class _FailingEmbedder:
    def embed(self, texts):
        raise RuntimeError("openai unreachable")


async def _seed(db):
    """Tenant A with two indexed chunks; tenant B with one chunk matching both
    "alpha" and "omega" so a missing tenant predicate leaks in either signal."""
    async with db.session_factory() as session:
        tenant_a = Tenant(name="Tenant A")
        tenant_b = Tenant(name="Tenant B")
        session.add_all([tenant_a, tenant_b])
        await session.flush()
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
        session.add_all([doc_a, doc_b])
        await session.flush()
        chunks = [
            Chunk(
                tenant_id=tenant_b.id,
                document_id=doc_b.id,
                position=0,
                content="alpha omega secret",
                embedding=_embedding("alpha omega secret"),
            ),
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
        await session.commit()
        return {
            "tenant_a": tenant_a.id,
            "tenant_b": tenant_b.id,
            "doc_a": doc_a.id,
            "doc_b": doc_b.id,
            "chunk_a0": chunks[1].id,
            "chunk_a1": chunks[2].id,
            "chunk_b": chunks[0].id,
        }


async def test_retrieve_chunks_returns_fused_results_matching_search_fusion(migrated_db):
    ids = await _seed(migrated_db)
    results = await retrieve_chunks(
        migrated_db.session_factory,
        _scope(ids["tenant_a"], uuid.uuid4()),
        _settings(),
        FakeEmbedder(),
        "alpha",
        top_k=1,
    )
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, FusedResult)
    assert {field.name for field in dataclasses.fields(result)} == FUSED_FIELDS
    assert result.chunk_id == ids["chunk_a0"]  # keyword rank 1 wins after fusion
    assert result.document_id == ids["doc_a"]
    assert result.document_name == "alpha-guide.pdf"
    assert result.position == 0
    assert result.content == "alpha beta gamma"
    assert result.keyword_rank == 1
    assert result.semantic_rank is not None  # dual-signal fusion really ran
    assert result.score > 0


async def test_retrieve_chunks_caps_results_at_top_k(migrated_db):
    ids = await _seed(migrated_db)
    scope = _scope(ids["tenant_a"], uuid.uuid4())
    settings = _settings()
    one = await retrieve_chunks(
        migrated_db.session_factory, scope, settings, FakeEmbedder(), "alpha", top_k=1
    )
    many = await retrieve_chunks(
        migrated_db.session_factory, scope, settings, FakeEmbedder(), "alpha", top_k=50
    )
    assert len(one) == 1
    assert one[0].chunk_id == ids["chunk_a0"]
    assert len(many) == 2  # tenant A owns exactly two chunks; the cap only trims
    assert {result.chunk_id for result in many} == {ids["chunk_a0"], ids["chunk_a1"]}
    assert {result.document_id for result in many} == {ids["doc_a"]}


async def test_retrieve_chunks_never_ranks_cross_tenant_chunks(migrated_db):
    """Spec "Only authorized tenant chunks return": every result belongs to A."""
    ids = await _seed(migrated_db)
    results = await retrieve_chunks(
        migrated_db.session_factory,
        _scope(ids["tenant_a"], uuid.uuid4()),
        _settings(),
        FakeEmbedder(),
        "omega",
        top_k=50,
    )
    assert len(results) == 2  # tenant A owns exactly two chunks; B's must not rank
    assert {result.document_id for result in results} == {ids["doc_a"]}
    assert {result.chunk_id for result in results} == {ids["chunk_a0"], ids["chunk_a1"]}
    assert all(result.document_name == "alpha-guide.pdf" for result in results)
    assert all("secret" not in result.content for result in results)


async def test_retrieve_chunks_output_is_deterministic(migrated_db):
    ids = await _seed(migrated_db)
    scope = _scope(ids["tenant_a"], uuid.uuid4())
    settings = _settings()
    first = await retrieve_chunks(
        migrated_db.session_factory, scope, settings, FakeEmbedder(), "alpha", top_k=50
    )
    second = await retrieve_chunks(
        migrated_db.session_factory, scope, settings, FakeEmbedder(), "alpha", top_k=50
    )
    assert first == second  # frozen dataclass equality: same order, same scores
    assert [result.score for result in first] == sorted(
        (result.score for result in first), reverse=True
    )


async def test_retrieve_chunks_defaults_top_k_to_settings(migrated_db):
    ids = await _seed(migrated_db)
    settings = _settings(retrieval_top_k=1)
    results = await retrieve_chunks(
        migrated_db.session_factory,
        _scope(ids["tenant_a"], uuid.uuid4()),
        settings,
        FakeEmbedder(),
        "alpha",
    )
    assert len(results) == 1
    assert results[0].chunk_id == ids["chunk_a0"]


async def test_retrieve_chunks_propagates_embedding_failure(migrated_db):
    ids = await _seed(migrated_db)
    with pytest.raises(RuntimeError, match="openai unreachable"):
        await retrieve_chunks(
            migrated_db.session_factory,
            _scope(ids["tenant_a"], uuid.uuid4()),
            _settings(),
            _FailingEmbedder(),
            "alpha",
        )
