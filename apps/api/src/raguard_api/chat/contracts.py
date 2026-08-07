"""Chat contracts (PR 2): bounded request, citation allowlist, completer boundary."""

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from raguard_api.config import Settings
from raguard_api.retrieval.contracts import FusedResult


def create_chat_request(settings: Settings) -> type[BaseModel]:
    """Build the bounded ``POST /api/chat`` request model for the settings."""

    class ChatRequest(BaseModel):
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


class FakeCompleter:
    """Recorded-prompt fake for offline tests (PR 4 router harness)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[CompletionPrompt] = []

    def complete(self, prompt: CompletionPrompt) -> str:
        self.calls.append(prompt)
        return self.text
