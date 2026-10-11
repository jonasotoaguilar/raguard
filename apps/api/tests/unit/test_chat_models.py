"""Unit tests for the chat history ORM metadata contract (F2).

These tests inspect SQLAlchemy metadata only — no Alembic, no PostgreSQL — so
the schema contract declared by the ORM (table names, constraints, indexes) is
verified deterministically in the unit layer. The assertions mirror the named
constraints that migration 0004 enforces in PostgreSQL.
"""

import pytest
import raguard_api.chat.models  # noqa: F401  # register chat tables in Base.metadata
from raguard_api.db import Base
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def metadata():
    """The SQLAlchemy metadata populated by the chat history models."""
    return Base.metadata


def _constraint_by_name(table, name):
    """Return the named constraint of a table (constraints is an unkeyed set)."""
    return {constraint.name: constraint for constraint in table.constraints}[name]


def test_conversation_tables_are_registered(metadata):
    table_names = set(metadata.tables)
    assert table_names >= {"conversations", "messages"}


def test_conversations_has_unique_tenant_id_and_id_backing_the_composite_fk(metadata):
    conversations = metadata.tables["conversations"]
    constraint = _constraint_by_name(conversations, "uq_conversations_tenant_id")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "id"]


def test_conversations_listing_index_leads_with_tenant_and_user(metadata):
    conversations = metadata.tables["conversations"]
    indexes = {
        index.name: [column.name for column in index.columns] for index in conversations.indexes
    }
    assert indexes["ix_conversations_tenant_user_updated"] == [
        "tenant_id",
        "user_id",
        "updated_at",
    ]


def test_messages_composite_conversation_fk_targets_conversations_tenant_and_id(metadata):
    messages = metadata.tables["messages"]
    constraint = _constraint_by_name(messages, "fk_messages_tenant_conversation")
    assert isinstance(constraint, ForeignKeyConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "conversation_id"]
    targets = [
        (element.parent.name, element.column.table.name, element.column.name)
        for element in constraint.elements
    ]
    assert targets == [
        ("tenant_id", "conversations", "tenant_id"),
        ("conversation_id", "conversations", "id"),
    ]


def test_messages_role_allowlist_constraint_contains_both_roles(metadata):
    messages = metadata.tables["messages"]
    constraint = _constraint_by_name(messages, "ck_messages_role")
    assert isinstance(constraint, CheckConstraint)
    sql_text = constraint.sqltext.text
    assert "'user'" in sql_text
    assert "'assistant'" in sql_text


def test_messages_chronological_index_leads_with_conversation(metadata):
    messages = metadata.tables["messages"]
    indexes = {index.name: [column.name for column in index.columns] for index in messages.indexes}
    assert indexes["ix_messages_conversation_created"] == ["conversation_id", "created_at"]


def test_conversations_seq_is_non_nullable_bigint_for_deterministic_newest_first(metadata):
    """``seq`` breaks ``updated_at`` ties: ``now()`` is the transaction start,
    so threads created in one transaction share the same timestamp."""
    from sqlalchemy import BigInteger

    conversations = metadata.tables["conversations"]
    column = conversations.columns["seq"]
    assert isinstance(column.type, BigInteger)
    assert column.nullable is False


def test_messages_position_is_unique_per_conversation(metadata):
    """``position`` — not ``created_at`` — is the chronological order key."""
    from sqlalchemy import Integer

    messages = metadata.tables["messages"]
    column = messages.columns["position"]
    assert isinstance(column.type, Integer)
    assert column.nullable is False
    constraint = _constraint_by_name(messages, "uq_messages_conversation_position")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["conversation_id", "position"]
