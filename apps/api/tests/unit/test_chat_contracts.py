"""Unit tests for chat contracts (task 2.1 RED): bounded request, citation allowlist."""

import uuid

import pytest
from pydantic import ValidationError
from raguard_api.chat.contracts import (
    ChatCompleter,
    ChatResponse,
    Citation,
    CompletionPrompt,
    FakeCompleter,
    create_chat_request,
)
from raguard_api.config import Settings
from raguard_api.retrieval.contracts import FusedResult

pytestmark = pytest.mark.unit

JWT_SECRET = "a" * 32


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret=JWT_SECRET, **overrides)


def _fused() -> FusedResult:
    return FusedResult(uuid.uuid4(), uuid.uuid4(), "report.pdf", 3, "grounding content", 1, 2, 0.5)


def test_chat_request_defaults_top_k_to_retrieval_default():
    request = create_chat_request(_settings())

    assert request(query="hello").top_k == 10
    assert create_chat_request(_settings(retrieval_top_k=4))(query="hello").top_k == 4
    with pytest.raises(ValidationError):
        request(query="hello", top_k=0)
    with pytest.raises(ValidationError):
        request(query="hello", top_k=51)


def test_chat_request_trims_query_and_enforces_settings_bounds():
    request = create_chat_request(
        _settings(retrieval_top_k=5, retrieval_top_k_max=5, retrieval_max_query_length=10)
    )

    assert request(query="  hello  ").query == "hello"
    assert request(query="1234567890", top_k=5).top_k == 5
    with pytest.raises(ValidationError):
        request(query="12345678901")
    with pytest.raises(ValidationError):
        request(query="ok", top_k=6)


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_chat_request_rejects_blank_query(query):
    with pytest.raises(ValidationError):
        create_chat_request(_settings())(query=query)


def test_citation_is_an_allowlist_of_chunk_metadata_only():
    citation = Citation.from_fused_result(_fused())
    allowed = {"chunk_id", "document_id", "document_name", "position", "content"}

    assert set(Citation.model_fields) == allowed
    assert set(citation.model_dump()) == allowed
    assert citation.document_name == "report.pdf"
    assert citation.position == 3
    assert citation.content == "grounding content"


def test_chat_response_serializes_answer_and_citations_only():
    filled = ChatResponse(answer="a", citations=[Citation.from_fused_result(_fused())])

    assert filled.model_dump()["answer"] == "a"
    assert len(filled.model_dump()["citations"]) == 1
    assert ChatResponse(answer=None).model_dump() == {"answer": None, "citations": []}


def test_fake_completer_returns_configured_text_and_records_prompts():
    fake = FakeCompleter(text="answer text")
    prompt = CompletionPrompt(system_prompt="sys", user_prompt="usr")

    assert fake.complete(prompt) == "answer text"
    assert fake.calls == [prompt]
    assert isinstance(fake, ChatCompleter)
