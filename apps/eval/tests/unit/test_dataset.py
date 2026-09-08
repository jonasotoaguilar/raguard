"""Tests for the PR3 dataset contract (task 2.1).

A valid dataset starts scoring; bad schema, duplicate ids, unsupported or
missing kinds, secret-like keys or content, and oversized queries raise
DatasetInvalid (exit 3) with no verdict.
"""

from __future__ import annotations

import hashlib
import json
import struct
import uuid
from pathlib import Path

import pytest
from raguard_eval.dataset import (
    FILES_IN_HASH_ORDER,
    QUERY_MAX_CHARS,
    compute_dataset_sha256,
    load_dataset,
    stable_case_uuid,
)
from raguard_eval.errors import DatasetInvalid

KINDS = ["relevant", "neutral", "cross-tenant", "capability-denied", "adversarial"]


def _manifest() -> dict:
    return {"schema_version": 1, "dataset_id": "mvp-v1", "draft_precision_at_10": 0.70}


def _corpus() -> dict:
    return {
        "tenants": [{"id": "t-a"}, {"id": "t-b"}],
        "documents": [{"id": "d-1", "tenant_id": "t-a"}, {"id": "d-2", "tenant_id": "t-b"}],
        "chunks": [
            {"id": "c-1", "tenant_id": "t-a", "document_id": "d-1", "content": "alpha bravo"},
            {"id": "c-2", "tenant_id": "t-a", "document_id": "d-1", "content": "charlie delta"},
            {"id": "c-3", "tenant_id": "t-b", "document_id": "d-2", "content": "echo foxtrot"},
        ],
    }


def _actors() -> dict:
    return {
        "actors": [
            {"id": "actor-a", "tenant_id": "t-a", "capabilities": ["chat.use"]},
            {"id": "actor-b", "tenant_id": "t-b", "capabilities": []},
        ]
    }


def _case(cid: str, kind: str) -> dict:
    rel = {"relevant": ["c-1"], "adversarial": ["c-1"], "cross-tenant": ["c-3"]}.get(kind, [])
    return {
        "id": cid,
        "kind": kind,
        "actor_id": "actor-b" if kind == "capability-denied" else "actor-a",
        "query": f"query for {cid}",
        "relevant_chunk_ids": rel,
    }


def _parts() -> tuple[dict, dict, dict, list[dict]]:
    return _manifest(), _corpus(), _actors(), [_case(f"case-{k}", k) for k in KINDS]


def _write_dataset(root: Path, manifest: dict, corpus: dict, actors: dict, rows: list) -> Path:
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "corpus.json").write_text(json.dumps(corpus))
    (root / "actors.json").write_text(json.dumps(actors))
    (root / "cases.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return root


def _assert_invalid(root: Path) -> None:
    with pytest.raises(DatasetInvalid) as excinfo:
        load_dataset(root)
    assert excinfo.value.exit_code == 3
    assert not hasattr(excinfo.value, "verdict")


def test_valid_dataset_starts(tmp_path: Path) -> None:
    ds = load_dataset(_write_dataset(tmp_path, *_parts()))
    assert ds.dataset_id == "mvp-v1"
    assert sorted(c.kind for c in ds.cases) == sorted(KINDS)
    raw = [(tmp_path / name).read_bytes() for name in FILES_IN_HASH_ORDER]
    assert ds.dataset_sha256 == compute_dataset_sha256(*raw)
    assert not hasattr(ds, "verdict")


def test_stable_case_uuid_is_uuid5() -> None:
    first = stable_case_uuid("relevant", "case-relevant")
    assert first.version == 5
    assert first == stable_case_uuid("relevant", "case-relevant")
    assert first == uuid.uuid5(uuid.NAMESPACE_URL, "raguard.eval.mvp-v1:relevant:case-relevant")
    assert stable_case_uuid("neutral", "case-relevant") != first


def test_sha256_uses_length_prefix_and_order() -> None:
    parts = [b"m", b"cc", b"a", b"cases\n"]
    framed = b"".join(struct.pack(">Q", len(p)) + p for p in parts)
    assert compute_dataset_sha256(*parts) == hashlib.sha256(framed).hexdigest()
    swapped = compute_dataset_sha256(parts[1], parts[0], parts[2], parts[3])
    assert compute_dataset_sha256(*parts) != swapped


def test_production_parses_with_json_loads_only() -> None:
    root = Path(__file__).resolve().parents[4]
    src = (root / "apps" / "eval" / "src" / "raguard_eval" / "dataset.py").read_text()
    assert "json.loads" in src
    for banned in ("import yaml", "import pickle", "pickle.", "marshal", "exec(", "eval("):
        assert banned not in src


@pytest.mark.parametrize(
    "variant",
    [
        "schema",
        "dupes",
        "kind",
        "missing",
        "secret-key",
        "secret-value",
        "oversize",
        "documents-str",
        "documents-dict",
        "chunks-str",
        "chunks-dict",
    ],
)
def test_invalid_datasets_exit3(tmp_path: Path, variant: str) -> None:
    manifest, corpus, actors, rows = _parts()
    if variant == "schema":
        manifest["schema_version"] = 99
    elif variant == "dupes":
        rows[1] = _case("case-relevant", "neutral")
    elif variant == "kind":
        rows[0]["kind"] = "live-semantic"
    elif variant == "missing":
        del rows[1:]
    elif variant == "secret-key":
        corpus["chunks"][0]["api_key"] = "sk-test-1"
    elif variant == "secret-value":
        corpus["chunks"][0]["content"] = "-----BEGIN RSA PRIVATE KEY-----\nx"
    elif variant == "oversize":
        rows[0]["query"] = "q" * (QUERY_MAX_CHARS + 1)
    else:
        field, shape = variant.split("-")
        corpus[field] = "bad" if shape == "str" else {"id": "bad"}
    _assert_invalid(_write_dataset(tmp_path, manifest, corpus, actors, rows))
