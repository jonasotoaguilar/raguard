"""Tests for the PR4 report contract (task 3.2, RED).

Deterministic case-id ordering; frozen allowlisted fields only; secret and
environment values never serialized.
"""

from __future__ import annotations

import json

import pytest
from raguard_eval.report import FAILURE_REASONS, build_report


def _report(**overrides):  # type: ignore[no-untyped-def]
    params = {
        "dataset_id": "mvp-v1",
        "dataset_sha256": "0" * 64,
        "settings": {"k": 10},
        "thresholds": {"draft_precision_at_10": 0.70},
        "aggregates": {"precision_at_10": 0.5},
        "cases": [{"id": "b"}, {"id": "a"}],
        "failure_reasons": [],
        "verdict": "pass",
    }
    params.update(overrides)
    return build_report(**params)  # type: ignore[arg-type]


def test_cases_sorted_by_id() -> None:
    assert [c["id"] for c in _report()["cases"]] == ["a", "b"]


def test_allowlisted_fields_and_secret_exclusion() -> None:
    report = _report(
        settings={"k": 10, "database_url": "postgres://secret", "jwt_secret": "s"},
        thresholds={"draft_precision_at_10": 0.70, "model": "gpt-x"},
    )
    assert set(report) == {
        "schema_version",
        "proof_scope",
        "dataset_id",
        "dataset_sha256",
        "settings",
        "thresholds",
        "aggregates",
        "cases",
        "failure_reasons",
        "verdict",
    }
    assert report["thresholds"] == {"draft_precision_at_10": 0.70, "fail_under_precision": None}
    blob = json.dumps(report)
    assert "postgres://secret" not in blob and "gpt-x" not in blob


def test_unknown_failure_reason_rejected() -> None:
    assert "tenant_leak" in FAILURE_REASONS
    with pytest.raises(ValueError):
        _report(failure_reasons=["live-model-refusal"])


def test_full_settings_allowlist_passes_through() -> None:
    report = _report(
        settings={
            "k": 10,
            "rrf_k": 60,
            "retrieval_candidates": 50,
            "retrieval_ef_search": 64,
            "retrieval_semantic_max_distance": 0.9,
            "actor_email": "actor@example.com",
            "env": {"HOME": "/root"},
        }
    )
    assert report["settings"] == {
        "k": 10,
        "rrf_k": 60,
        "retrieval_candidates": 50,
        "retrieval_ef_search": 64,
        "retrieval_semantic_max_distance": 0.9,
    }
    assert "actor@example.com" not in json.dumps(report)


def test_unknown_verdict_rejected() -> None:
    with pytest.raises(ValueError):
        _report(verdict="warn")


def test_nested_forbidden_keys_and_secret_values_sanitized() -> None:
    report = _report(
        aggregates={
            "precision_at_10": 0.5,
            "nested": {"database_url": "postgres://secret", "jwt_secret": "s"},
            "note": "postgres://internal-db/eval",
        },
        cases=[
            {
                "id": "a",
                "actor_email": "actor@example.com",
                "env": {"HOME": "/root"},
                "nested": {"provider_key": "sk-abcdefgh12345678", "model": "gpt-x"},
                "contact": "actor@example.com",
            }
        ],
    )
    blob = json.dumps(report)
    assert "postgres://" not in blob
    assert "actor@example.com" not in blob
    assert "sk-abcdefgh12345678" not in blob
    assert "gpt-x" not in blob
    assert report["aggregates"].get("precision_at_10") == 0.5


def test_allowed_position_sensitive_values_fail_closed() -> None:
    with pytest.raises(ValueError):
        _report(dataset_id="actor@example.com")
    with pytest.raises(ValueError):
        _report(dataset_sha256="postgres://internal-db/eval")
    report = _report(
        settings={"k": "postgres://internal-db/eval"},
        thresholds={"draft_precision_at_10": "sk-abcdefgh12345678"},
    )
    blob = json.dumps(report)
    assert "postgres://" not in blob and "sk-abcdefgh12345678" not in blob
    assert report["settings"] == {}
    assert report["thresholds"] == {"draft_precision_at_10": None, "fail_under_precision": None}
    assert _report()["settings"] == {"k": 10}
