"""Unit tests: history reads re-filter citations against current visibility.

``GET /api/conversations/{id}`` must never leak text from documents the
caller can no longer see: stored citations are re-validated against the
caller's CURRENT visibility (same semantics as retrieval) and only visible
ones are returned. The assistant message text itself is preserved — only the
citation allowlist shrinks, down to ``citations: []`` when nothing remains
visible.
"""

import uuid
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.unit

TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _row(citations: list[dict]) -> object:
    from raguard_api.chat.models import Message

    return Message(
        tenant_id=TENANT_ID,
        conversation_id=uuid.uuid4(),
        id=uuid.uuid4(),
        role="assistant",
        content="Grounded [1].",
        citations=citations,
        created_at=datetime.now(UTC),
    )


def _citation(document_id: uuid.UUID, content: str = "secret text") -> dict:
    return {
        "chunk_id": str(uuid.uuid4()),
        "document_id": str(document_id),
        "document_name": "secret.pdf",
        "position": 0,
        "content": content,
    }


def test_revoked_citation_is_dropped_but_message_kept():
    from raguard_api.chat.router import _history_message

    visible_doc = uuid.uuid4()
    revoked_doc = uuid.uuid4()
    message = _history_message(
        _row([_citation(visible_doc, "open text"), _citation(revoked_doc)]),
        visible_document_ids={visible_doc},
    )

    assert message.content == "Grounded [1]."
    assert [c.document_id for c in message.citations] == [visible_doc]
    assert message.citations[0].content == "open text"


def test_all_citations_revoked_yields_empty_list_not_deleted_message():
    from raguard_api.chat.router import _history_message

    message = _history_message(
        _row([_citation(uuid.uuid4())]),
        visible_document_ids=set(),
    )

    assert message.content == "Grounded [1]."
    assert message.citations == []


def test_user_message_without_citations_passes_through():
    from raguard_api.chat.models import Message
    from raguard_api.chat.router import _history_message

    row = Message(
        tenant_id=TENANT_ID,
        conversation_id=uuid.uuid4(),
        id=uuid.uuid4(),
        role="user",
        content="alpha",
        citations=[],
        created_at=datetime.now(UTC),
    )
    message = _history_message(row, visible_document_ids=set())

    assert message.role == "user"
    assert message.content == "alpha"
    assert message.citations == []
