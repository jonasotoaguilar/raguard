"""Chat domain: contracts, grounded prompt, citation verification (PR 2)."""

from raguard_api.chat.citations import CitationVerificationError, verify_citations
from raguard_api.chat.contracts import (
    DEFAULT_CONVERSATION_TITLE,
    MAX_CONVERSATION_TITLE_LENGTH,
    ChatCompleter,
    ChatResponse,
    Citation,
    CompletionPrompt,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    FakeCompleter,
    HistoryMessage,
    create_chat_request,
)
from raguard_api.chat.prompts import SYSTEM_PROMPT, build_completion_prompt

__all__ = [
    "ChatCompleter",
    "ChatResponse",
    "Citation",
    "CitationVerificationError",
    "CompletionPrompt",
    "ConversationCreateRequest",
    "ConversationDetailResponse",
    "ConversationListResponse",
    "ConversationSummary",
    "DEFAULT_CONVERSATION_TITLE",
    "FakeCompleter",
    "HistoryMessage",
    "MAX_CONVERSATION_TITLE_LENGTH",
    "SYSTEM_PROMPT",
    "build_completion_prompt",
    "create_chat_request",
    "verify_citations",
]
