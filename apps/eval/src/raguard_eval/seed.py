"""Seed a migrated evaluation database from a validated dataset directory (ODD-2).

Reads the dataset through :func:`raguard_eval.dataset.load_dataset` (so only
a validated ``Dataset`` is ever seeded) plus the raw ``corpus.json`` /
``actors.json`` topology with ``json.loads`` only. Tenant, actor, capability,
document, and chunk relationships are preserved through the production
tenant-leading foreign keys; chunk embeddings come from the deterministic
offline embedder and the returned mapping carries external chunk ids to row
UUIDs for the future runner. Nothing here is logged or serialized.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from raguard_api.documents.contracts import EMBEDDING_DIMENSION, DocumentStatus, Embedder
from raguard_api.documents.models import Chunk, Document
from raguard_api.identity.models import ALLOWED_CAPABILITIES, Membership, Role, Tenant, User
from sqlalchemy.ext.asyncio import async_sessionmaker

from raguard_eval.dataset import load_dataset
from raguard_eval.embedder import Sha256TokenEmbedder
from raguard_eval.errors import DatasetInvalid

_ALLOWED_CAPABILITIES = frozenset(ALLOWED_CAPABILITIES)


@dataclass(frozen=True)
class SeededEvaluationData:
    """UUID mappings from external dataset ids to seeded rows."""

    tenant_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    actor_user_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    document_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    chunk_ids: dict[str, uuid.UUID] = field(default_factory=dict)


async def seed_evaluation_database(
    session_factory: async_sessionmaker,
    dataset_dir: str | Path,
    *,
    embedder: Embedder | None = None,
) -> SeededEvaluationData:
    """Seed tenants, actors, documents, and chunks; return the id mappings."""
    root = Path(dataset_dir)
    dataset = load_dataset(root)
    corpus = json.loads((root / "corpus.json").read_text(encoding="utf-8"))

    content_by_chunk = {c["id"]: c for c in corpus["chunks"]}
    documents = {d["id"]: d for d in corpus["documents"]}
    for actor_id in sorted(dataset.actor_tenant):
        unknown = set(dataset.actor_capabilities[actor_id]) - _ALLOWED_CAPABILITIES
        if unknown:
            raise DatasetInvalid(
                f"actor {actor_id!r} has unsupported capabilities: {sorted(unknown)!r}"
            )
    embed = embedder or Sha256TokenEmbedder()

    tenant_ids: dict[str, uuid.UUID] = {}
    actor_user_ids: dict[str, uuid.UUID] = {}
    document_ids: dict[str, uuid.UUID] = {}
    chunk_ids: dict[str, uuid.UUID] = {}

    async with session_factory() as session:
        for entry in corpus["tenants"]:
            tenant = Tenant(name=f"eval {entry['id']}")
            session.add(tenant)
            await session.flush()
            tenant_ids[entry["id"]] = tenant.id

        for actor_id in sorted(dataset.actor_tenant):
            tenant_id = tenant_ids[dataset.actor_tenant[actor_id]]
            user = User(
                email=f"{actor_id}@eval.invalid",
                password_hash="eval-seed-not-a-real-hash",
            )
            session.add(user)
            await session.flush()
            capabilities = sorted(dataset.actor_capabilities[actor_id])
            role = Role(
                tenant_id=tenant_id,
                name=f"eval-{actor_id}",
                capabilities=capabilities,
            )
            session.add(role)
            await session.flush()
            session.add(Membership(tenant_id=tenant_id, user_id=user.id, role_id=role.id))
            actor_user_ids[actor_id] = user.id

        for doc_id, doc in documents.items():
            document = Document(
                tenant_id=tenant_ids[doc["tenant_id"]],
                name=doc_id,
                status=DocumentStatus.indexed.value,
                storage_key=f"eval/{doc_id}",
            )
            session.add(document)
            await session.flush()
            document_ids[doc_id] = document.id

        positions: dict[str, int] = {}
        for chunk_id, chunk in content_by_chunk.items():
            doc_id = chunk.get("document_id")
            document_entry = documents.get(doc_id)
            if document_entry is None:
                raise DatasetInvalid(f"chunk {chunk_id!r} has unknown document")
            if chunk["tenant_id"] != document_entry["tenant_id"]:
                raise DatasetInvalid(f"chunk {chunk_id!r} crosses document tenant")
            (vector,) = embed.embed([chunk["content"]])
            if len(vector) != EMBEDDING_DIMENSION:
                raise DatasetInvalid(f"chunk {chunk_id!r} embedding has wrong dimension")
            position = positions.get(doc_id, 0)
            positions[doc_id] = position + 1
            row = Chunk(
                tenant_id=tenant_ids[chunk["tenant_id"]],
                document_id=document_ids[doc_id],
                position=position,
                content=chunk["content"],
                embedding=vector,
            )
            session.add(row)
            await session.flush()
            chunk_ids[chunk_id] = row.id

        await session.commit()

    return SeededEvaluationData(
        tenant_ids=tenant_ids,
        actor_user_ids=actor_user_ids,
        document_ids=document_ids,
        chunk_ids=chunk_ids,
    )
