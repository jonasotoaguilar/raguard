"""Versioned eval dataset loading, validation, and identity hash.

Reads ``manifest.json``, ``corpus.json``, ``actors.json``, ``cases.jsonl``
from a dataset directory with ``json.loads`` only. Invalid datasets raise
:exc:`DatasetInvalid` (exit 3) before any scoring, so no verdict is produced.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from raguard_eval.errors import DatasetInvalid

SCHEMA_VERSION = 1
REQUIRED_CASE_KINDS = ("relevant", "neutral", "cross-tenant", "capability-denied", "adversarial")
ALLOWED_KINDS = frozenset(REQUIRED_CASE_KINDS)
QUERY_MAX_CHARS = 2000
FILE_MAX_BYTES = 5 * 1024 * 1024
FILES_IN_HASH_ORDER = ("manifest.json", "corpus.json", "actors.json", "cases.jsonl")

_KEY_FRAGMENTS = ("password", "secret", "token", "api_key", "apikey", "api-key")
_VALUE_RE = re.compile(
    r"-----BEGIN[^-]*PRIVATE KEY-----|sk-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}"
    r"|(?:ghp|gsk|xox[bpas])[_-][A-Za-z0-9-]+"
)


@dataclass(frozen=True)
class Case:
    id: str
    kind: str
    actor_id: str
    query: str
    relevant_chunk_ids: tuple[str, ...] = ()
    top_k: int | None = None
    completion_text: str = ""
    uuid: uuid.UUID = uuid.UUID(int=0)


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    dataset_sha256: str
    cases: tuple[Case, ...]
    chunk_tenant: dict[str, str]
    actor_tenant: dict[str, str]
    actor_capabilities: dict[str, frozenset[str]]


def stable_case_uuid(kind: str, case_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"raguard.eval.mvp-v1:{kind}:{case_id}")


def compute_dataset_sha256(*raw_files: bytes) -> str:
    framed = b"".join(len(raw).to_bytes(8, "big") + raw for raw in raw_files)
    return sha256(framed).hexdigest()


def _scan_secrets(node: object) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if any(fragment in str(key).lower() for fragment in _KEY_FRAGMENTS):
                raise DatasetInvalid(f"secret-like key rejected: {key!r}")
            _scan_secrets(value)
    elif isinstance(node, list):
        for value in node:
            _scan_secrets(value)
    elif isinstance(node, str):
        if _VALUE_RE.search(node):
            raise DatasetInvalid("secret-like content rejected")


def _read_raw(dataset_dir: Path, name: str) -> bytes:
    try:
        raw = (dataset_dir / name).read_bytes()
    except OSError as exc:
        raise DatasetInvalid(f"missing dataset file: {name}") from exc
    if len(raw) > FILE_MAX_BYTES:
        raise DatasetInvalid(f"dataset file oversize: {name}")
    return raw


def _unique_ids(items: object, what: str) -> dict[str, dict]:
    if not isinstance(items, list):
        raise DatasetInvalid(f"{what} entries must be a list")
    seen: dict[str, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            raise DatasetInvalid(f"{what} entry must be an object")
        ident = item.get("id")
        if not isinstance(ident, str) or not ident:
            raise DatasetInvalid(f"{what} entry without string id")
        if ident in seen:
            raise DatasetInvalid(f"duplicate {what} id: {ident!r}")
        seen[ident] = item
    return seen


def load_dataset(dataset_dir: str | Path) -> Dataset:
    root = Path(dataset_dir)
    raw_files = [_read_raw(root, name) for name in FILES_IN_HASH_ORDER]
    try:
        manifest = json.loads(raw_files[0].decode("utf-8"))
        corpus = json.loads(raw_files[1].decode("utf-8"))
        actors_doc = json.loads(raw_files[2].decode("utf-8"))
        lines = [ln for ln in raw_files[3].decode("utf-8").splitlines() if ln.strip()]
        cases_raw = [json.loads(ln) for ln in lines]
    except ValueError as exc:
        raise DatasetInvalid(f"dataset is not valid JSON: {exc}") from exc

    for node in (manifest, corpus, actors_doc, *cases_raw):
        _scan_secrets(node)

    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise DatasetInvalid("unsupported manifest schema_version (want 1)")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise DatasetInvalid("manifest dataset_id must be a non-empty string")
    if not isinstance(manifest.get("draft_precision_at_10"), (int, float)):
        raise DatasetInvalid("manifest draft_precision_at_10 must be numeric")

    if not isinstance(corpus, dict):
        raise DatasetInvalid("corpus must be a JSON object")
    tenants = {t.get("id") for t in corpus.get("tenants", []) if isinstance(t, dict)}
    docs = _unique_ids(corpus.get("documents", []), "document")
    chunks = _unique_ids(corpus.get("chunks", []), "chunk")
    chunk_tenant: dict[str, str] = {}
    for cid, chunk in chunks.items():
        if chunk.get("tenant_id") not in tenants:
            raise DatasetInvalid(f"chunk {cid!r} has unknown tenant")
        if not isinstance(chunk.get("content"), str) or not chunk["content"]:
            raise DatasetInvalid(f"chunk {cid!r} needs non-empty content")
        chunk_tenant[cid] = chunk["tenant_id"]
    for did, doc in docs.items():
        if doc.get("tenant_id") not in tenants:
            raise DatasetInvalid(f"document {did!r} has unknown tenant")

    actors_list = actors_doc.get("actors") if isinstance(actors_doc, dict) else actors_doc
    actors = _unique_ids(actors_list, "actor")
    actor_tenant: dict[str, str] = {}
    actor_capabilities: dict[str, frozenset[str]] = {}
    for aid, actor in actors.items():
        if actor.get("tenant_id") not in tenants:
            raise DatasetInvalid(f"actor {aid!r} has unknown tenant")
        caps = actor.get("capabilities", [])
        if not isinstance(caps, list) or any(not isinstance(c, str) for c in caps):
            raise DatasetInvalid(f"actor {aid!r} capabilities must be strings")
        actor_tenant[aid] = actor["tenant_id"]
        actor_capabilities[aid] = frozenset(caps)

    cases: list[Case] = []
    for cid, entry in _unique_ids(cases_raw, "case").items():
        kind = entry.get("kind")
        if kind not in ALLOWED_KINDS:
            raise DatasetInvalid(f"case {cid!r} has unsupported kind {kind!r}")
        if entry.get("actor_id") not in actors:
            raise DatasetInvalid(f"case {cid!r} has unknown actor")
        query = entry.get("query")
        if not isinstance(query, str) or not query:
            raise DatasetInvalid(f"case {cid!r} needs a non-empty query")
        if len(query) > QUERY_MAX_CHARS:
            raise DatasetInvalid(f"case {cid!r} query oversize")
        rel = entry.get("relevant_chunk_ids", [])
        if not isinstance(rel, list) or any(r not in chunks for r in rel):
            raise DatasetInvalid(f"case {cid!r} has unknown relevant_chunk_ids")
        top_k = entry.get("top_k")
        if top_k is not None and (
            isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0
        ):
            raise DatasetInvalid(f"case {cid!r} top_k must be a positive int")
        completion = entry.get("completion_text", "")
        if not isinstance(completion, str):
            raise DatasetInvalid(f"case {cid!r} completion_text must be a string")
        cases.append(
            Case(
                cid,
                kind,
                entry["actor_id"],
                query,
                tuple(rel),
                top_k,
                completion,
                stable_case_uuid(kind, cid),
            )
        )
    if ALLOWED_KINDS - {c.kind for c in cases}:
        raise DatasetInvalid("dataset must cover every required case kind")

    return Dataset(
        dataset_id,
        compute_dataset_sha256(*raw_files),
        tuple(cases),
        chunk_tenant,
        actor_tenant,
        actor_capabilities,
    )
