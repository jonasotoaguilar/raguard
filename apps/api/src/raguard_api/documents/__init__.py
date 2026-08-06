"""Document ingestion domain: shared contracts, protocols, and ORM models."""

from raguard_api.documents.contracts import (
    EMBEDDING_DIMENSION,
    FAILURE_REASONS,
    DocumentStatus,
    Embedder,
    FakeEmbedder,
    FakeJobQueue,
    FakeObjectStore,
    FakeParser,
    JobQueue,
    ObjectStore,
    Parser,
)
from raguard_api.documents.models import Chunk, Document

__all__ = [
    "EMBEDDING_DIMENSION",
    "FAILURE_REASONS",
    "DocumentStatus",
    "Chunk",
    "Document",
    "Embedder",
    "JobQueue",
    "ObjectStore",
    "Parser",
    "FakeEmbedder",
    "FakeJobQueue",
    "FakeObjectStore",
    "FakeParser",
]
