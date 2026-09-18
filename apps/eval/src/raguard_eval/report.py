"""Deterministic allowlisted evaluation report.

Only frozen top-level, settings, and threshold fields are serialized, and
``aggregates``/``cases`` mappings are recursively sanitized, so DB URLs,
JWT/provider secrets, models, actor emails, and environment values can never
leak into ``eval/reports/``. Cases are sorted by id; unknown failure reasons
and verdicts fail closed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

SCHEMA_VERSION = 1
PROOF_SCOPE = "offline-synthetic"

TOP_LEVEL_FIELDS = (
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
)
SETTINGS_FIELDS = (
    "k",
    "rrf_k",
    "retrieval_candidates",
    "retrieval_ef_search",
    "retrieval_semantic_max_distance",
)
THRESHOLD_FIELDS = ("draft_precision_at_10", "fail_under_precision")
FAILURE_REASONS = frozenset(
    {
        "tenant_leak",
        "unauthorized_execution",
        "citation_out_of_set",
        "malformed_citation_accepted",
        "prompt_boundary_violation",
        "precision_below_threshold",
    }
)
VERDICTS = ("pass", "fail")

_FORBIDDEN_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "database_url",
    "database-url",
    "db_url",
    "jwt",
    "provider",
    "model",
    "actor_email",
    "email",
    "env",
)
_SECRET_VALUE_RE = re.compile(
    r"postgres(?:ql)?://|-----BEGIN[^-]*PRIVATE KEY-----|sk-[A-Za-z0-9_-]{8,}"
    r"|AKIA[0-9A-Z]{16}|(?:ghp|gsk|xox[bpas])[_-][A-Za-z0-9-]+"
)
_EMAIL_VALUE_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _is_forbidden_key(key: object) -> bool:
    lowered = str(key).lower()
    return any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS)


def _is_forbidden_value(value: object) -> bool:
    return isinstance(value, str) and bool(
        _EMAIL_VALUE_RE.search(value) or _SECRET_VALUE_RE.search(value)
    )


def _sanitize(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _sanitize(value)
            for key, value in node.items()
            if not _is_forbidden_key(key) and not _is_forbidden_value(value)
        }
    if isinstance(node, list):
        return [_sanitize(value) for value in node if not _is_forbidden_value(value)]
    return node


def build_report(
    *,
    dataset_id: str,
    dataset_sha256: str,
    settings: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
    aggregates: dict[str, Any] | None = None,
    cases: Sequence[dict[str, Any]] = (),
    failure_reasons: Sequence[str] = (),
    verdict: str,
) -> dict[str, Any]:
    """Build the frozen-shape report dict; unknown fields never pass through."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict: {verdict!r}")
    unknown = [reason for reason in failure_reasons if reason not in FAILURE_REASONS]
    if unknown:
        raise ValueError(f"unknown failure reasons: {unknown!r}")
    selected = thresholds or {}
    ordered = sorted(cases, key=lambda case: case["id"])
    if _is_forbidden_value(dataset_id) or _is_forbidden_value(dataset_sha256):
        raise ValueError("sensitive dataset identifier")
    return {
        "schema_version": SCHEMA_VERSION,
        "proof_scope": PROOF_SCOPE,
        "dataset_id": dataset_id,
        "dataset_sha256": dataset_sha256,
        "settings": {
            key: settings[key]
            for key in SETTINGS_FIELDS
            if key in settings and not _is_forbidden_value(settings[key])
        },
        "thresholds": {
            key: (None if _is_forbidden_value(selected.get(key)) else selected.get(key))
            for key in THRESHOLD_FIELDS
        },
        "aggregates": _sanitize(dict(aggregates or {})),
        "cases": [_sanitize(dict(case)) for case in ordered],
        "failure_reasons": list(failure_reasons),
        "verdict": verdict,
    }
