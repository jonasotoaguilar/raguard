"""Chat contracts (PR 2 + F2): bounded request, citation allowlist, completer boundary,
conversation history contracts."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from raguard_api.config import Settings
from raguard_api.retrieval.contracts import FusedResult

#: Default title for a freshly created conversation; replaced by the first
#: user query once the first persisted turn lands.
DEFAULT_CONVERSATION_TITLE = "New conversation"

#: Hard bound for conversation titles (also enforced by API validation).
MAX_CONVERSATION_TITLE_LENGTH = 200


def create_chat_request(settings: Settings) -> type[BaseModel]:
    """Build the bounded ``POST /api/chat`` request model for the settings."""

    class ChatRequest(BaseModel):
        query: str = Field(min_length=1)
        top_k: int = Field(default=settings.retrieval_top_k, ge=1, le=settings.retrieval_top_k_max)
        conversation_id: uuid.UUID | None = None

        @field_validator("query")
        @classmethod
        def _bounded_query(cls, value: str) -> str:
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("query must not be blank")
            if len(trimmed) > settings.retrieval_max_query_length:
                raise ValueError("query exceeds the maximum length")
            return trimmed

    return ChatRequest


class Citation(BaseModel):
    """One verified citation: allowlisted chunk metadata (no ranks, no tenant)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    position: int
    content: str

    @classmethod
    def from_fused_result(cls, result: FusedResult) -> "Citation":
        return cls(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            document_name=result.document_name,
            position=result.position,
            content=result.content,
        )


class ChatResponse(BaseModel):
    """Typed chat payload: the answer plus verified citations only."""

    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CompletionPrompt:
    """Provider-neutral completion input: static system plus user prompt."""

    system_prompt: str
    user_prompt: str


@runtime_checkable
class ChatCompleter(Protocol):
    """Synchronous completion boundary; routers call it via ``asyncio.to_thread``."""

    def complete(self, prompt: CompletionPrompt) -> str: ...


class ConversationCreateRequest(BaseModel):
    """Bounded ``POST /api/conversations`` payload: optional title only.

    Tenant and user identity always come from the verified scope, never from
    the client (no ``tenant_id``/``user_id`` fields by design).
    """

    title: str | None = Field(default=None, max_length=MAX_CONVERSATION_TITLE_LENGTH)

    @field_validator("title")
    @classmethod
    def _bounded_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("title must not be blank")
        return trimmed


class ConversationSummary(BaseModel):
    """Allowlisted conversation row: identity-scoped fields only, no tenant/user."""

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Newest-first list of the caller's own conversations."""

    conversations: list[ConversationSummary] = Field(default_factory=list)


class HistoryMessage(BaseModel):
    """One persisted turn: role allowlist plus content and citations."""

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    """One owned conversation with its messages in chronological order."""

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[HistoryMessage] = Field(default_factory=list)


class FakeCompleter:
    """Recorded-prompt fake for offline tests (PR 4 router harness)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[CompletionPrompt] = []

    def complete(self, prompt: CompletionPrompt) -> str:
        self.calls.append(prompt)
        return self.text
