"""Unit tests for the document/chunk ORM metadata and contract surface (task 1.3).

These tests inspect SQLAlchemy metadata only — no Alembic, no PostgreSQL — so
the schema contract declared by the ORM (tables, constraints, indexes, vector
shape) is verified deterministically in the unit layer. The assertions mirror
the named constraints that migration 0002 enforces in PostgreSQL and the
boundaries the design places on the public contract surface: readiness and
storage keys stay internal to the model, never on the shared contracts module.
"""

import pytest
import raguard_api.identity.models  # noqa: F401  # register identity tables in Base.metadata
from pgvector.sqlalchemy import HALFVEC
from raguard_api.db import Base
from raguard_api.documents.contracts import (
    EMBEDDING_DIMENSION,
    FAILURE_REASONS,
    DocumentStatus,
    FakeEmbedder,
    FakeJobQueue,
    FakeObjectStore,
    FakeParser,
)
from sqlalchemy import CheckConstraint, Computed, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def metadata():
    """The SQLAlchemy metadata populated by the identity and documents models."""
    return Base.metadata


def _constraint_by_name(table, name):
    """Return the named constraint of a table (constraints is an unkeyed set)."""
    return {constraint.name: constraint for constraint in table.constraints}[name]


def _index_by_name(table, name):
    """Return the named index of a table (indexes is an unkeyed set)."""
    return {index.name: index for index in table.indexes}[name]


def test_document_and_chunk_tables_are_registered(metadata):
    assert {"documents", "chunks"} <= set(metadata.tables)


def test_document_status_enum_values_match_spec(metadata):
    assert [status.value for status in DocumentStatus] == ["pending", "indexed", "failed"]


def test_documents_tenant_fk_targets_tenants(metadata):
    documents = metadata.tables["documents"]
    constraint = _constraint_by_name(documents, "fk_documents_tenant_id")
    assert isinstance(constraint, ForeignKeyConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id"]
    targets = [
        (element.parent.name, element.column.table.name, element.column.name)
        for element in constraint.elements
    ]
    assert targets == [("tenant_id", "tenants", "id")]


def test_documents_unique_tenant_id_and_id_backing_the_composite_fk(metadata):
    documents = metadata.tables["documents"]
    constraint = _constraint_by_name(documents, "uq_documents_tenant_id")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "id"]


def test_documents_status_check_contains_every_enum_value(metadata):
    documents = metadata.tables["documents"]
    constraint = _constraint_by_name(documents, "ck_documents_status")
    assert isinstance(constraint, CheckConstraint)
    sql_text = constraint.sqltext.text
    for status in DocumentStatus:
        assert repr(status.value) in sql_text


def test_documents_failure_reason_allowlist_matches_design(metadata):
    documents = metadata.tables["documents"]
    constraint = _constraint_by_name(documents, "ck_documents_failure_reason")
    assert isinstance(constraint, CheckConstraint)
    sql_text = constraint.sqltext.text
    assert "IS NULL OR" in sql_text
    for reason in FAILURE_REASONS:
        assert repr(reason) in sql_text


def test_failure_reason_allowlist_matches_design_tokens(metadata):
    assert FAILURE_REASONS == ("malformed", "encrypted", "limit", "source_missing")


def test_documents_readiness_flag_is_internal_and_defaults_false(metadata):
    documents = metadata.tables["documents"]
    column = documents.c.dispatch_ready
    assert str(column.type) == "BOOLEAN"
    assert column.server_default is not None
    assert column.server_default.arg.text == "false"


def test_documents_indexes_lead_with_tenant_id(metadata):
    documents = metadata.tables["documents"]
    indexes = {index.name: [column.name for column in index.columns] for index in documents.indexes}
    assert indexes["ix_documents_tenant_status"] == ["tenant_id", "status"]
    assert indexes["ix_documents_tenant_created_at"] == ["tenant_id", "created_at"]


def test_chunks_embedding_is_halfvec_1536(metadata):
    chunks = metadata.tables["chunks"]
    column = chunks.c.embedding
    assert isinstance(column.type, HALFVEC)
    assert column.type.dim == EMBEDDING_DIMENSION == 1536


def test_chunks_composite_fk_targets_documents_tenant_and_id(metadata):
    chunks = metadata.tables["chunks"]
    constraint = _constraint_by_name(chunks, "fk_chunks_tenant_document")
    assert isinstance(constraint, ForeignKeyConstraint)
    assert [column.name for column in constraint.columns] == ["tenant_id", "document_id"]
    targets = [
        (element.parent.name, element.column.table.name, element.column.name)
        for element in constraint.elements
    ]
    assert targets == [
        ("tenant_id", "documents", "tenant_id"),
        ("document_id", "documents", "id"),
    ]


def test_chunks_position_unique_per_document(metadata):
    chunks = metadata.tables["chunks"]
    constraint = _constraint_by_name(chunks, "uq_chunks_document_position")
    assert isinstance(constraint, UniqueConstraint)
    assert [column.name for column in constraint.columns] == ["document_id", "position"]


def test_chunks_index_leads_with_tenant_id(metadata):
    chunks = metadata.tables["chunks"]
    index = _index_by_name(chunks, "ix_chunks_tenant_document")
    assert [column.name for column in index.columns] == ["tenant_id", "document_id"]


def test_chunks_hnsw_index_uses_halfvec_cosine_ops(metadata):
    chunks = metadata.tables["chunks"]
    index = _index_by_name(chunks, "ix_chunks_embedding")
    postgresql_options = index.dialect_options["postgresql"]
    assert postgresql_options["using"] == "hnsw"
    assert postgresql_options["ops"] == {"embedding": "halfvec_cosine_ops"}
    assert postgresql_options["with"] == {"m": 16, "ef_construction": 64}
    assert [column.name for column in index.columns] == ["embedding"]


def test_chunks_gin_index_covers_generated_search_vector(metadata):
    chunks = metadata.tables["chunks"]
    index = _index_by_name(chunks, "ix_chunks_search_vector")
    assert index.dialect_options["postgresql"]["using"] == "gin"
    assert [column.name for column in index.columns] == ["search_vector"]

    column = chunks.c.search_vector
    assert isinstance(column.type, TSVECTOR)
    assert isinstance(column.computed, Computed)
    assert "to_tsvector" in column.computed.sqltext.text
    assert column.computed.persisted is True


def test_contract_surface_exposes_no_internal_readiness_or_storage_key(metadata):
    """The public contract vocabulary never leaks internal state.

    Readiness and storage keys are model-internal (documents.dispatch_ready,
    documents.storage_key); the shared contracts module must not carry them.
    """
    import raguard_api.documents.contracts as contracts

    assert not hasattr(contracts, "dispatch_ready")
    assert not hasattr(contracts, "storage_key")
    assert {status.value for status in DocumentStatus} == {"pending", "indexed", "failed"}


def test_fake_object_store_round_trips_and_deletes():
    store = FakeObjectStore()
    store.put("tenant-a/report.pdf", b"pdf-bytes")
    store.put("tenant-b/notes.md", b"md-bytes")

    assert store.get("tenant-a/report.pdf") == b"pdf-bytes"
    assert store.get("tenant-b/notes.md") == b"md-bytes"
    assert store.put_keys == ["tenant-a/report.pdf", "tenant-b/notes.md"]

    store.delete("tenant-a/report.pdf")
    assert store.deleted_keys == ["tenant-a/report.pdf"]
    with pytest.raises(KeyError):
        store.get("tenant-a/report.pdf")


def test_fake_job_queue_records_exactly_one_job_with_document_id():
    import uuid

    queue = FakeJobQueue()
    document_id = uuid.uuid4()

    queue.enqueue(f"ingest:{document_id}", document_id)

    assert queue.enqueued == [(f"ingest:{document_id}", document_id)]


def test_fake_parser_returns_decoded_text():
    parser = FakeParser()

    assert parser.parse(b"plain text") == "plain text"
    assert parser.parse("caf\xe9".encode()) == "caf\xe9"


def test_fake_embedder_returns_dimension_exact_distinct_vectors():
    embedder = FakeEmbedder()

    vectors = embedder.embed(["alpha", "beta"])

    assert len(vectors) == 2
    assert [len(vector) for vector in vectors] == [EMBEDDING_DIMENSION, EMBEDDING_DIMENSION]
    assert vectors[0] != vectors[1]
    assert embedder.embed(["alpha", "beta"]) == vectors  # deterministic
