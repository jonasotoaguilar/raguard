"""Request-scoped grounded chat route (PR 4).

``POST /api/chat`` validates the bounded request, resolves a fresh
``AuthorizationScope``, requires ``chat.use``, and delegates to the shared
tenant-filtered ``retrieve_chunks``. Empty evidence short-circuits to the
neutral ``{answer: null, citations: []}`` with zero provider calls; otherwise
the static grounded prompt is completed via ``asyncio.to_thread`` and every
``[n]`` marker is verified against the exact retrieved set. Provider and
citation failures map to the generic 503 envelope — no partial answer, no
fallback, no detail leak.
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.capabilities import CHAT_USE
from raguard_api.authorization.resolver import (
    AuthorizationResolver,
    create_scope_dependency,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.chat.citations import CitationVerificationError, verify_citations
from raguard_api.chat.contracts import ChatCompleter, ChatResponse, create_chat_request
from raguard_api.chat.prompts import build_completion_prompt
from raguard_api.chat.providers.openai import CompletionError
from raguard_api.config import Settings
from raguard_api.documents.contracts import Embedder
from raguard_api.errors import AuthorizationError, ServiceUnavailableError
from raguard_api.retrieval.service import retrieve_chunks

logger = logging.getLogger(__name__)


def create_chat_router(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    embedder: Embedder,
    completer: ChatCompleter,
) -> APIRouter:
    """Build the ``POST /api/chat`` router with bounded validation and typing."""
    ChatRequest = create_chat_request(settings)

    resolver = AuthorizationResolver(session_factory=session_factory)
    GetScope = Annotated[AuthorizationScope, Depends(create_scope_dependency(resolver))]

    def require_capability(capability: str):
        """Dependency: allow only scopes holding the capability (403 otherwise)."""

        def _require(scope: GetScope) -> AuthorizationScope:
            if not scope.has_capability(capability):
                raise AuthorizationError("Insufficient permissions")
            return scope

        return _require

    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.post("")
    async def chat(
        payload: ChatRequest,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
    ) -> ChatResponse:
        try:
            chunks = await retrieve_chunks(
                session_factory,
                scope,
                settings,
                embedder,
                payload.query,
                top_k=payload.top_k,
            )
        except Exception as exc:
            logger.warning(
                "chat retrieval failed tenant_id=%s exception=%s",
                scope.tenant_id,
                type(exc).__name__,
            )
            raise ServiceUnavailableError("Chat unavailable") from exc
        if not chunks:
            return ChatResponse()
        try:
            completion = await asyncio.to_thread(
                completer.complete, build_completion_prompt(payload.query, chunks)
            )
            citations = verify_citations(completion, chunks)
        except (CompletionError, CitationVerificationError) as exc:
            logger.warning(
                "chat completion rejected tenant_id=%s exception=%s",
                scope.tenant_id,
                type(exc).__name__,
            )
            raise ServiceUnavailableError("Chat unavailable") from exc
        return ChatResponse(answer=completion, citations=citations)

    return router
