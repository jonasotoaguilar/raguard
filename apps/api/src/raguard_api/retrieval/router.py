"""Tenant-scoped hybrid search route (task 2.2).

``POST /api/search`` embeds the trimmed query once, then runs the keyword and
semantic signals concurrently in independent sessions, fuses candidates with
RRF, and returns at most ``top_k`` deterministic results. Any embedding or
query failure maps to the generic 503 envelope — partial candidates are never
returned. The tenant predicate comes from a fresh ``AuthorizationScope``, so
no cross-tenant chunk can ever be ranked or disclosed.
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.capabilities import CHAT_USE
from raguard_api.authorization.resolver import (
    AuthorizationResolver,
    create_scope_dependency,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.config import Settings
from raguard_api.documents.contracts import Embedder
from raguard_api.errors import AuthorizationError, ServiceUnavailableError
from raguard_api.retrieval.contracts import Candidate, FusedResult
from raguard_api.retrieval.fusion import rrf_fusion
from raguard_api.retrieval.queries import (
    build_ef_search_statement,
    build_keyword_query,
    build_semantic_query,
)

logger = logging.getLogger(__name__)


def create_retrieval_router(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    embedder: Embedder,
) -> APIRouter:
    """Build the ``POST /api/search`` router with bounded request validation."""

    class SearchRequest(BaseModel):
        query: str = Field(min_length=1)
        top_k: int = Field(default=settings.retrieval_top_k, ge=1, le=settings.retrieval_top_k_max)

        @field_validator("query")
        @classmethod
        def _bounded_query(cls, value: str) -> str:
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("query must not be blank")
            if len(trimmed) > settings.retrieval_max_query_length:
                raise ValueError("query exceeds the maximum length")
            return trimmed

    resolver = AuthorizationResolver(session_factory=session_factory)
    GetScope = Annotated[AuthorizationScope, Depends(create_scope_dependency(resolver))]

    def require_capability(capability: str):
        """Dependency: allow only scopes holding the capability (403 otherwise)."""

        def _require(scope: GetScope) -> AuthorizationScope:
            if not scope.has_capability(capability):
                raise AuthorizationError("Insufficient permissions")
            return scope

        return _require

    router = APIRouter(prefix="/api/search", tags=["retrieval"])

    @router.post("")
    async def search(
        payload: SearchRequest,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
    ) -> dict:
        try:
            vectors = await asyncio.to_thread(embedder.embed, [payload.query])
            keyword, semantic = await asyncio.gather(
                _keyword_candidates(
                    session_factory, scope, settings.retrieval_candidates, payload.query
                ),
                _semantic_candidates(
                    session_factory,
                    scope,
                    settings.retrieval_candidates,
                    settings.retrieval_ef_search,
                    vectors[0],
                ),
            )
            fused = rrf_fusion(keyword, semantic, k=settings.rrf_k)
        except Exception as exc:
            logger.warning(
                "search failed tenant_id=%s exception=%s",
                scope.tenant_id,
                type(exc).__name__,
            )
            raise ServiceUnavailableError("Search unavailable") from exc
        return {"results": [_result(result) for result in fused[: payload.top_k]]}

    return router


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
    embedding: list[float],
) -> list[Candidate]:
    statement = build_semantic_query(tenant_predicate=scope.tenant_predicate, limit=limit)
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


def _result(result: FusedResult) -> dict:
    return {
        "chunk_id": str(result.chunk_id),
        "document_id": str(result.document_id),
        "document_name": result.document_name,
        "position": result.position,
        "content": result.content,
        "keyword_rank": result.keyword_rank,
        "semantic_rank": result.semantic_rank,
        "score": result.score,
    }
