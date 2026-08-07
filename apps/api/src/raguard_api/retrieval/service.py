"""Shared tenant-scoped hybrid retrieval orchestration (PR 1 extraction).

``retrieve_chunks`` is the single hybrid pipeline used by ``/api/search`` and
the future ``/api/chat``: embed once, tenant-filtered keyword/semantic signals
in concurrent sessions, deterministic RRF, top-k bound. The tenant predicate
comes from a fresh ``AuthorizationScope``; failures propagate to the caller,
which owns the HTTP envelope.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.config import Settings
from raguard_api.documents.contracts import Embedder
from raguard_api.retrieval.contracts import Candidate, FusedResult
from raguard_api.retrieval.fusion import rrf_fusion
from raguard_api.retrieval.queries import (
    build_ef_search_statement,
    build_keyword_query,
    build_semantic_query,
)


async def retrieve_chunks(
    session_factory: async_sessionmaker[AsyncSession],
    scope: AuthorizationScope,
    settings: Settings,
    embedder: Embedder,
    query: str,
    top_k: int | None = None,
) -> list[FusedResult]:
    """Embed once, tenant-filtered candidates, RRF fusion, top-k bound.

    Returns at most ``top_k`` (default ``settings.retrieval_top_k``) results
    from the caller's tenant; failures propagate to the caller's envelope.
    """
    limit = top_k if top_k is not None else settings.retrieval_top_k
    vectors = await asyncio.to_thread(embedder.embed, [query])
    keyword, semantic = await asyncio.gather(
        _keyword_candidates(session_factory, scope, settings.retrieval_candidates, query),
        _semantic_candidates(
            session_factory,
            scope,
            settings.retrieval_candidates,
            settings.retrieval_ef_search,
            settings.retrieval_semantic_max_distance,
            vectors[0],
        ),
    )
    fused = rrf_fusion(keyword, semantic, k=settings.rrf_k)
    return fused[:limit]


async def _keyword_candidates(
    session_factory: async_sessionmaker[AsyncSession],
    scope: AuthorizationScope,
    limit: int,
    query: str,
) -> list[Candidate]:
    statement = build_keyword_query(tenant_predicate=scope.tenant_predicate, limit=limit)
    async with session_factory() as session:
        rows = (await session.execute(statement, {"query": query})).all()
    return [_candidate(row) for row in rows]


async def _semantic_candidates(
    session_factory: async_sessionmaker[AsyncSession],
    scope: AuthorizationScope,
    limit: int,
    ef_search: int,
    max_distance: float,
    embedding: list[float],
) -> list[Candidate]:
    statement = build_semantic_query(
        tenant_predicate=scope.tenant_predicate, limit=limit, max_distance=max_distance
    )
    async with session_factory() as session:
        await session.execute(build_ef_search_statement(ef_search=ef_search))
        rows = (await session.execute(statement, {"embedding": embedding})).all()
    return [_candidate(row) for row in rows]


def _candidate(row) -> Candidate:
    return Candidate(
        chunk_id=row.chunk_id,
        document_id=row.document_id,
        document_name=row.document_name,
        position=row.position,
        content=row.content,
    )
