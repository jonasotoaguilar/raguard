"""Chat domain: contracts, grounded prompt, citation verification (PR 2)."""

from raguard_api.chat.citations import CitationVerificationError, verify_citations
from raguard_api.chat.contracts import (
    ChatCompleter,
    ChatResponse,
    Citation,
    CompletionPrompt,
    FakeCompleter,
    create_chat_request,
)
from raguard_api.chat.prompts import SYSTEM_PROMPT, build_completion_prompt

__all__ = [
    "ChatCompleter",
    "ChatResponse",
    "Citation",
    "CitationVerificationError",
    "CompletionPrompt",
    "FakeCompleter",
    "SYSTEM_PROMPT",
    "build_completion_prompt",
    "create_chat_request",
    "verify_citations",
]
