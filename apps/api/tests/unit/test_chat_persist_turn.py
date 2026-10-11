"""Unit tests: ``_persist_turn`` serializes concurrent appends (G2).

``max(position) + 1`` computed by two concurrent requests on the same thread
would read the same max and collide on ``uq_messages_conversation_position``.
``_persist_turn`` must therefore take ``SELECT ... FOR UPDATE`` on the owned
conversation row before reading the max, and assign contiguous positions.
These tests use a fake session (no PostgreSQL) to verify statement order and
atomicity of the position math.
"""

import uuid

import pytest

pytestmark = pytest.mark.unit


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _FakeSession:
    """Minimal AsyncSession stand-in recording executes/adds/commit."""

    def __init__(self, max_position: int):
        self.max_position = max_position
        self.statements: list = []
        self.added: list = []
        self.committed = False

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self.max_position)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


class _FakeScope:
    def __init__(self, tenant_id, user_id):
        self.tenant_id = tenant_id
        self.user_id = user_id


def _conversation():
    from raguard_api.chat.models import Conversation

    return Conversation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="New conversation",
    )


def _response():
    from raguard_api.chat.contracts import ChatResponse

    return ChatResponse(answer="Grounded [1].", citations=[])


async def _run(max_position: int):
    from raguard_api.chat.router import _persist_turn

    conversation = _conversation()
    scope = _FakeScope(conversation.tenant_id, conversation.user_id)
    session = _FakeSession(max_position)
    await _persist_turn(
        session,
        scope,
        conversation,
        query="alpha",
        response=_response(),  # type: ignore[arg-type]
    )
    return session


async def test_persist_turn_locks_conversation_before_reading_max():
    session = await _run(4)
    assert len(session.statements) == 2
    # The lock statement must precede the max(position) read and carry FOR UPDATE.
    assert "FOR UPDATE" in str(session.statements[0])
    assert "FOR UPDATE" not in str(session.statements[1])


async def test_persist_turn_assigns_contiguous_positions_atomically():
    session = await _run(4)
    assert [(m.role, m.position) for m in session.added] == [
        ("user", 5),
        ("assistant", 6),
    ]
    assert session.committed is True


async def test_persist_turn_positions_start_at_zero_on_empty_thread():
    session = await _run(-1)
    assert [(m.role, m.position) for m in session.added] == [
        ("user", 0),
        ("assistant", 1),
    ]
