"""Parameterized retrieval query builders (task 1.2/1.4).

Both signals bind every value: the tenant predicate comes from an
``AuthorizationScope`` (a bound parameter, never a literal), the FTS query
text binds as ``:query``, and the semantic embedding binds as ``:embedding``
with an explicit ``HALFVEC(1536)`` type matching the stored column. Each
statement joins documents by tenant+document keys, orders within the signal
with a chunk-id tiebreak, and limits candidates; fusion re-ranks by position.
"""

from collections.abc import Callable

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import Select, String, TextClause, and_, bindparam, func, select, text
from sqlalchemy.sql.elements import ColumnElement

from raguard_api.documents.contracts import EMBEDDING_DIMENSION
from raguard_api.documents.models import Chunk, Document

# The FTS configuration used at ingestion (models.py: to_tsvector('simple')).
_FTS_CONFIG = "simple"

TenantPredicate = Callable[[ColumnElement], ColumnElement[bool]]


def build_keyword_query(*, tenant_predicate: TenantPredicate, limit: int) -> Select:
    """Tenant-filtered FTS query: ts_rank desc, chunk id asc, bounded candidates."""
    query = bindparam("query", type_=String)
    # The FTS config is a fixed code-level constant; only the query text binds.
    rank = func.ts_rank(
        Chunk.search_vector, func.plainto_tsquery(text(f"'{_FTS_CONFIG}'"), query)
    ).label("rank")
    return (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.document_id,
            Document.name.label("document_name"),
            Chunk.position,
            Chunk.content,
            rank,
        )
        .join(
            Document,
            and_(Document.tenant_id == Chunk.tenant_id, Document.id == Chunk.document_id),
        )
        .where(tenant_predicate(Chunk.tenant_id))
        .order_by(rank.desc(), Chunk.id.asc())
        .limit(limit)
    )


def build_semantic_query(*, tenant_predicate: TenantPredicate, limit: int) -> Select:
    """Tenant-filtered cosine query: distance asc, chunk id asc, bounded candidates."""
    embedding = bindparam("embedding", type_=HALFVEC(EMBEDDING_DIMENSION))
    distance = Chunk.embedding.cosine_distance(embedding).label("distance")
    return (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.document_id,
            Document.name.label("document_name"),
            Chunk.position,
            Chunk.content,
            distance,
        )
        .join(
            Document,
            and_(Document.tenant_id == Chunk.tenant_id, Document.id == Chunk.document_id),
        )
        .where(tenant_predicate(Chunk.tenant_id))
        .order_by(distance.asc(), Chunk.id.asc())
        .limit(limit)
    )


def build_ef_search_statement(*, ef_search: int) -> TextClause:
    """Parameterized hnsw.ef_search setter for the semantic transaction."""
    return text("SELECT set_config('hnsw.ef_search', :ef, true)").bindparams(
        bindparam("ef", value=str(ef_search), type_=String)
    )
