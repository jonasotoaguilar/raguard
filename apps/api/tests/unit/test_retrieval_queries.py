"""Unit tests for the parameterized retrieval query builders (task 1.2 RED).

These tests compile the built statements against the PostgreSQL dialect and
assert the spec/design contracts without touching a database: the tenant
predicate is a bound parameter that precedes ranking in both signals, the FTS
signal uses ``plainto_tsquery('simple', :query)``, the semantic signal binds
the embedding as ``HALFVEC(1536)``, both join documents by tenant+document
keys, break signal ties by ascending chunk id, and bound the candidate count.
"""

import uuid

import pytest
import raguard_api.identity.models  # noqa: F401  # register identity tables in Base.metadata
from pgvector.sqlalchemy import HALFVEC
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.retrieval.queries import (
    build_ef_search_statement,
    build_keyword_query,
    build_semantic_query,
)
from sqlalchemy import Float
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import BindParameter
from sqlalchemy.sql.visitors import iterate

pytestmark = pytest.mark.unit

LIMIT = 50
MAX_DISTANCE = 0.5
TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _scope() -> AuthorizationScope:
    return AuthorizationScope(
        tenant_id=TENANT_ID,
        user_id=uuid.uuid4(),
        capabilities=frozenset({"chat.use"}),
    )


def _compiled(statement) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True})
    )


def _bindparam(statement, key: str) -> BindParameter:
    return next(
        bind for bind in iterate(statement) if isinstance(bind, BindParameter) and bind.key == key
    )


def test_keyword_query_applies_tenant_predicate_before_ranking():
    sql = _compiled(build_keyword_query(tenant_predicate=_scope().tenant_predicate, limit=LIMIT))

    where_pos = sql.index("WHERE")
    order_pos = sql.index("ORDER BY")
    assert where_pos < order_pos
    assert "chunks.tenant_id" in sql
    # The tenant id is a bound parameter, never a literal.
    assert str(TENANT_ID) not in sql


def test_keyword_query_uses_simple_plainto_tsquery():
    sql = _compiled(build_keyword_query(tenant_predicate=_scope().tenant_predicate, limit=LIMIT))

    assert "plainto_tsquery('simple', %(query)s)" in sql
    assert "ts_rank(chunks.search_vector" in sql


def test_keyword_query_joins_documents_by_tenant_and_document_keys():
    sql = _compiled(build_keyword_query(tenant_predicate=_scope().tenant_predicate, limit=LIMIT))

    assert "documents.tenant_id = chunks.tenant_id" in sql
    assert "documents.id = chunks.document_id" in sql


def test_keyword_query_orders_by_rank_desc_then_chunk_id_asc():
    sql = _compiled(build_keyword_query(tenant_predicate=_scope().tenant_predicate, limit=LIMIT))

    assert "ORDER BY rank DESC, chunks.id ASC" in sql


def test_keyword_query_filters_on_tsquery_match_after_tenant_predicate():
    """Keyword candidates must be actual tsquery matches, tenant-filtered first.

    Without the ``@@`` predicate the signal ranks every tenant chunk (rank 0.0
    for non-matches), so a no-match query would never return the neutral empty
    result required by the spec.
    """
    sql = _compiled(build_keyword_query(tenant_predicate=_scope().tenant_predicate, limit=LIMIT))

    match = "chunks.search_vector @@ plainto_tsquery('simple', %(query)s)"
    assert match in sql
    assert sql.index("chunks.tenant_id") < sql.index("@@")


def test_keyword_query_limits_candidates():
    statement = build_keyword_query(tenant_predicate=_scope().tenant_predicate, limit=LIMIT)

    assert statement._limit == LIMIT


def test_semantic_query_binds_halfvec_1536_embedding():
    statement = build_semantic_query(
        tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
    )
    sql = _compiled(statement)

    assert "<=>" in sql
    assert "%(embedding)s" in sql
    embedding_bind = _bindparam(statement, "embedding")
    assert isinstance(embedding_bind.type, HALFVEC)
    assert embedding_bind.type.dim == 1536


def test_semantic_query_applies_tenant_predicate_before_ranking():
    statement = build_semantic_query(
        tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
    )
    sql = _compiled(statement)

    where_pos = sql.index("WHERE")
    order_pos = sql.index("ORDER BY")
    assert where_pos < order_pos
    assert "chunks.tenant_id" in sql
    assert str(TENANT_ID) not in sql


def test_semantic_query_joins_documents_by_tenant_and_document_keys():
    sql = _compiled(
        build_semantic_query(
            tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
        )
    )

    assert "documents.tenant_id = chunks.tenant_id" in sql
    assert "documents.id = chunks.document_id" in sql


def test_semantic_query_orders_by_distance_asc_then_chunk_id_asc():
    sql = _compiled(
        build_semantic_query(
            tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
        )
    )

    assert "ORDER BY distance ASC, chunks.id ASC" in sql


def test_semantic_query_limits_candidates():
    statement = build_semantic_query(
        tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
    )

    assert statement._limit == LIMIT


def test_semantic_query_filters_by_max_distance_before_ordering():
    """Semantic candidates must be real matches within the relevance threshold.

    Without a distance predicate the signal ranks every authorized tenant
    chunk as the nearest neighbor, so a populated tenant with no keyword match
    would never return the neutral empty result required by the spec.
    """
    statement = build_semantic_query(
        tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
    )
    sql = _compiled(statement)

    assert "<= %(max_distance)s" in sql
    assert sql.index("<= %(max_distance)s") < sql.index("ORDER BY")


def test_semantic_query_max_distance_is_bound_and_applied_after_tenant_predicate():
    statement = build_semantic_query(
        tenant_predicate=_scope().tenant_predicate, limit=LIMIT, max_distance=MAX_DISTANCE
    )
    sql = _compiled(statement)

    # The threshold is a bound parameter, never a literal in the SQL text.
    assert str(MAX_DISTANCE) not in sql
    assert sql.index("chunks.tenant_id") < sql.index("<= %(max_distance)s")
    max_distance_bind = _bindparam(statement, "max_distance")
    assert isinstance(max_distance_bind.type, Float)
    assert max_distance_bind.value == MAX_DISTANCE


def test_ef_search_statement_is_parameterized():
    sql = str(build_ef_search_statement(ef_search=100).compile(dialect=postgresql.dialect()))

    assert sql == "SELECT set_config('hnsw.ef_search', %(ef)s, true)"
    assert "100" not in sql


def test_query_builders_exported_from_package():
    """Package boundary: PR 2 builders are public; PR 1 exports are preserved."""
    from raguard_api import retrieval as package
    from raguard_api.retrieval import (
        Candidate,
        FusedResult,
        build_ef_search_statement,
        build_keyword_query,
        build_semantic_query,
        rrf_fusion,
    )
    from raguard_api.retrieval.contracts import Candidate as ContractsCandidate
    from raguard_api.retrieval.contracts import FusedResult as ContractsResult
    from raguard_api.retrieval.fusion import rrf_fusion as module_rrf_fusion
    from raguard_api.retrieval.queries import (
        build_ef_search_statement as module_ef_search_statement,
    )
    from raguard_api.retrieval.queries import (
        build_keyword_query as module_keyword_query,
    )
    from raguard_api.retrieval.queries import (
        build_semantic_query as module_semantic_query,
    )

    # The package imports raise ImportError until __init__ re-exports the
    # builders; identity proves each export is the real implementation.
    assert build_keyword_query is module_keyword_query
    assert build_semantic_query is module_semantic_query
    assert build_ef_search_statement is module_ef_search_statement
    assert rrf_fusion is module_rrf_fusion
    assert Candidate is ContractsCandidate
    assert FusedResult is ContractsResult
    for name in (
        "Candidate",
        "FusedResult",
        "rrf_fusion",
        "build_keyword_query",
        "build_semantic_query",
        "build_ef_search_statement",
    ):
        assert name in package.__all__
