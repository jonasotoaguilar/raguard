"""Request-scoped grounded chat route (PR 4) plus optional history (F2).

``POST /api/chat`` validates the bounded request, resolves a fresh
``AuthorizationScope``, requires ``chat.use``, and delegates to the shared
tenant-filtered ``retrieve_chunks``. Empty evidence short-circuits to the
neutral ``{answer: null, citations: []}`` with zero provider calls; otherwise
the static grounded prompt is completed via ``asyncio.to_thread`` and every
``[n]`` marker is verified against the exact retrieved set. Provider and
citation failures map to the generic 503 envelope — no partial answer, no
fallback, no detail leak.

F2 history is opt-in per request: without ``conversation_id`` the route stays
stateless and performs zero writes. With ``conversation_id`` the conversation
must belong to the caller's tenant+user (neutral 404 otherwise) and the user
turn plus the assistant turn (with its verified citations) are persisted while
``updated_at`` is touched. ``/api/conversations`` (same ``chat.use`` gate,
same tenant+user scoping) creates, lists, reads, and deletes threads.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.capabilities import CHAT_USE
from raguard_api.authorization.resolver import (
    AuthorizationResolver,
    create_scope_dependency,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.chat.citations import CitationVerificationError, verify_citations
from raguard_api.chat.contracts import (
    DEFAULT_CONVERSATION_TITLE,
    ChatCompleter,
    ChatResponse,
    Citation,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    HistoryMessage,
    create_chat_request,
)
from raguard_api.chat.models import Conversation, Message
from raguard_api.chat.prompts import build_completion_prompt
from raguard_api.chat.providers.openai import CompletionError
from raguard_api.config import Settings
from raguard_api.documents.contracts import Embedder
from raguard_api.documents.models import Document
from raguard_api.documents.visibility import scope_visibility_clause
from raguard_api.errors import (
    AuthorizationError,
    NotFoundError,
    ServiceUnavailableError,
)
from raguard_api.retrieval.service import retrieve_chunks

logger = logging.getLogger(__name__)


async def _owned_conversation(
    session: AsyncSession, scope: AuthorizationScope, conversation_id: uuid.UUID
) -> Conversation:
    """Return the conversation owned by the scope's tenant+user, else neutral 404."""
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == scope.tenant_id,
                Conversation.user_id == scope.user_id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


async def _persist_turn(
    session: AsyncSession,
    scope: AuthorizationScope,
    conversation: Conversation,
    *,
    query: str,
    response: ChatResponse,
) -> None:
    """Persist the user turn and the assistant turn; touch ``updated_at``.

    Runs only after the response was fully built, so provider/citation 503s
    leave no partial history behind. Positions are assigned incrementally
    from the current max within the conversation (``func.now()`` is the
    transaction start time, so ``created_at`` alone cannot order the two
    turns of one request).
    """
    next_position = (
        await session.execute(
            select(func.coalesce(func.max(Message.position), -1)).where(
                Message.tenant_id == scope.tenant_id,
                Message.conversation_id == conversation.id,
            )
        )
    ).scalar_one()
    session.add(
        Message(
            tenant_id=scope.tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=query,
            citations=[],
            position=next_position + 1,
        )
    )
    session.add(
        Message(
            tenant_id=scope.tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=response.answer or "",
            citations=[citation.model_dump(mode="json") for citation in response.citations],
            position=next_position + 2,
        )
    )
    if conversation.title == DEFAULT_CONVERSATION_TITLE:
        conversation.title = query[:200] or DEFAULT_CONVERSATION_TITLE
    conversation.updated_at = datetime.now(UTC)
    await session.commit()


def _history_message(
    row: Message, visible_document_ids: set[uuid.UUID] | frozenset
) -> HistoryMessage:
    """Rebuild one stored turn, re-filtering citations against CURRENT visibility.

    Stored citations carry chunk content, so a grant revoked after the turn
    was written must not keep leaking restricted text through history reads:
    each citation is re-validated against the caller's current visibility
    (same semantics as retrieval — ``visibility='tenant'`` or a user/role
    grant) and only still-visible citations are returned. The assistant
    message text itself is preserved; a turn left with no visible citations
    is returned with ``citations: []`` (the message is never deleted here).
    """
    raw = row.citations if isinstance(row.citations, list) else []
    citations = []
    for entry in raw:
        try:
            citations.append(Citation.model_validate(entry))
        except Exception:  # pragma: no cover - fail-closed: skip corrupt entries
            logger.warning(
                "skipping corrupt citation payload conversation_id=%s message_id=%s",
                row.conversation_id,
                row.id,
            )
    visible = [c for c in citations if c.document_id in visible_document_ids]
    return HistoryMessage(
        id=row.id,
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        citations=visible,
        created_at=row.created_at,
    )


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

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    @router.post("")
    async def chat(
        payload: ChatRequest,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> ChatResponse:
        conversation: Conversation | None = None
        if payload.conversation_id is not None:
            # Ownership is verified before any retrieval or completion so a
            # foreign id costs zero provider calls and discloses nothing.
            conversation = await _owned_conversation(session, scope, payload.conversation_id)
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
            response = ChatResponse()
        else:
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
            response = ChatResponse(answer=completion, citations=citations)
        if conversation is not None:
            await _persist_turn(
                session, scope, conversation, query=payload.query, response=response
            )
        return response

    return router


def create_conversations_router(*, session_factory: async_sessionmaker[AsyncSession]) -> APIRouter:
    """Build the ``/api/conversations`` history router (F2, ``chat.use`` gated)."""
    resolver = AuthorizationResolver(session_factory=session_factory)
    GetScope = Annotated[AuthorizationScope, Depends(create_scope_dependency(resolver))]

    def require_capability(capability: str):
        """Dependency: allow only scopes holding the capability (403 otherwise)."""

        def _require(scope: GetScope) -> AuthorizationScope:
            if not scope.has_capability(capability):
                raise AuthorizationError("Insufficient permissions")
            return scope

        return _require

    router = APIRouter(prefix="/api/conversations", tags=["conversations"])

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    @router.post("", status_code=201, response_model=ConversationSummary)
    async def create_conversation(
        payload: ConversationCreateRequest,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> ConversationSummary:
        conversation = Conversation(
            tenant_id=scope.tenant_id,
            user_id=scope.user_id,
            title=payload.title or DEFAULT_CONVERSATION_TITLE,
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @router.get("", response_model=ConversationListResponse)
    async def list_conversations(
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> ConversationListResponse:
        rows = (
            await session.execute(
                select(Conversation)
                .where(
                    Conversation.tenant_id == scope.tenant_id,
                    Conversation.user_id == scope.user_id,
                )
                .order_by(Conversation.updated_at.desc(), Conversation.seq.desc())
            )
        ).scalars()
        return ConversationListResponse(
            conversations=[
                ConversationSummary(
                    id=row.id,
                    title=row.title,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]
        )

    @router.get("/{conversation_id}", response_model=ConversationDetailResponse)
    async def get_conversation(
        conversation_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> ConversationDetailResponse:
        conversation = await _owned_conversation(session, scope, conversation_id)
        rows = (
            await session.execute(
                select(Message)
                .where(
                    Message.tenant_id == scope.tenant_id,
                    Message.conversation_id == conversation.id,
                )
                .order_by(Message.position.asc())
            )
        ).scalars()
        # Re-validate stored citations against the caller's CURRENT document
        # visibility: a revoked grant must stop serving restricted chunk text
        # through history even though the turn was authorized when written.
        visible_document_ids = set(
            (
                await session.execute(
                    select(Document.id).where(
                        Document.tenant_id == scope.tenant_id,
                        scope_visibility_clause(scope),
                    )
                )
            ).scalars()
        )
        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[_history_message(row, visible_document_ids) for row in rows],
        )

    @router.delete("/{conversation_id}", status_code=204)
    async def delete_conversation(
        conversation_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability(CHAT_USE))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> Response:
        conversation = await _owned_conversation(session, scope, conversation_id)
        await session.execute(
            delete(Message).where(
                Message.tenant_id == scope.tenant_id,
                Message.conversation_id == conversation.id,
            )
        )
        await session.delete(conversation)
        await session.commit()
        return Response(status_code=204)

    return router
