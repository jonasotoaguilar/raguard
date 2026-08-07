"""Tenant-scoped hybrid search route (task 2.2, PR 1 extraction).

``POST /api/search`` validates the bounded request, resolves a fresh
``AuthorizationScope``, and delegates retrieval to the shared
``retrieve_chunks`` service (embedding, tenant-predicated keyword/semantic
signals, RRF fusion, top-k bound). The route keeps validation, the ``chat.use``
gate, the generic 503 envelope, and the response mapping. Any embedding or
query failure maps to the generic 503 envelope — partial candidates are never
returned, and no cross-tenant chunk can ever be ranked or disclosed.
"""

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
from raguard_api.retrieval.contracts import FusedResult
from raguard_api.retrieval.service import retrieve_chunks

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
            results = await retrieve_chunks(
                session_factory,
                scope,
                settings,
                embedder,
                payload.query,
                top_k=payload.top_k,
            )
        except Exception as exc:
            logger.warning(
                "search failed tenant_id=%s exception=%s",
                scope.tenant_id,
                type(exc).__name__,
            )
            raise ServiceUnavailableError("Search unavailable") from exc
        return {"results": [_result(result) for result in results]}

    return router


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
