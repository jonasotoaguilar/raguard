"""Shared document contracts: status vocabulary, narrow adapter seams, owned fakes (task 1.4).

The public vocabulary (status enum, failure-reason allowlist, embedding
dimension) and the four narrow protocols (ObjectStore, JobQueue, Parser,
Embedder) are defined here once and imported by both the API and the worker.
Internal state — dispatch readiness and storage keys — intentionally never
appears on this surface; it exists only on the ORM model.
"""

import uuid
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

EMBEDDING_DIMENSION = 1536


class DocumentStatus(StrEnum):
    """Public document lifecycle states exposed by the API (spec: pending/indexed/failed)."""

    pending = "pending"
    indexed = "indexed"
    failed = "failed"


# Allowlisted failure reasons from DESIGN.md: malformed/encrypted/limit
# failures and the sweep-owned `failed/source_missing` terminal state.
FAILURE_REASONS = ("malformed", "encrypted", "limit", "source_missing")


@runtime_checkable
class ObjectStore(Protocol):
    """Narrow object-storage seam (S3 adapter in task 2.2, MinIO locally)."""

    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


@runtime_checkable
class JobQueue(Protocol):
    """Narrow job-queue seam (Arq adapter in task 2.2); jobs carry only a document id."""

    def enqueue(self, job_id: str, document_id: uuid.UUID) -> None: ...


@runtime_checkable
class Parser(Protocol):
    """Narrow document parser seam (pypdf implementation lands in PR 4)."""

    def parse(self, data: bytes) -> str: ...


@runtime_checkable
class Embedder(Protocol):
    """Narrow embedding seam; vectors must be EMBEDDING_DIMENSION long (adapter in PR 4)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FakeObjectStore:
    """In-memory ObjectStore used by non-e2e tests; get raises KeyError when missing."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.put_keys: list[str] = []
        self.deleted_keys: list[str] = []

    def put(self, key: str, data: bytes) -> None:
        self._objects[key] = data
        self.put_keys.append(key)

    def get(self, key: str) -> bytes:
        return self._objects[key]

    def delete(self, key: str) -> None:
        self._objects.pop(key, None)
        self.deleted_keys.append(key)


class FakeJobQueue:
    """In-memory JobQueue recording every enqueue as an (job_id, document_id) pair."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, uuid.UUID]] = []

    def enqueue(self, job_id: str, document_id: uuid.UUID) -> None:
        self.enqueued.append((job_id, document_id))


class FakeParser:
    """Parser fake: decodes bytes to text without any format-specific logic."""

    def parse(self, data: bytes) -> str:
        return data.decode("utf-8", errors="replace")


class FakeEmbedder:
    """Deterministic dimension-exact embedding fake; the text index scales the values."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            [
                ((text_index + 1) * (dim_index + 1) / 1000) % 1.0
                for dim_index in range(EMBEDDING_DIMENSION)
            ]
            for text_index in range(len(texts))
        ]
