"""Unit tests for the upload helpers and compensation retries (task 2.5).

Characterization + behavior tests for the router's pure validation boundary
(safe basename, size/type/extension/signature bounds) and the bounded jittered
object-delete retry that backs the compensation paths: transient failures
recover, retries are bounded, and exhaustion is reported instead of raising —
so no path leaves an unlogged orphan.
"""

import types
import uuid

import pytest
import raguard_api.documents.router as router_module
from raguard_api.documents.router import (
    _delete_object_with_retries,
    _remove_object,
    safe_basename,
    validate_upload,
)
from raguard_api.errors import ValidationError

pytestmark = pytest.mark.unit

MAX_BYTES = 1000


class FailingDeleteStore:
    """Store whose delete fails the first ``failures`` calls."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.delete_calls: list[str] = []

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        if self.failures:
            self.failures -= 1
            raise OSError("s3 unreachable")


def _no_jitter(monkeypatch):
    monkeypatch.setattr(router_module, "_COMPENSATION_MAX_JITTER", 0)


async def test_delete_object_with_retries_recovers_after_transient_failures(monkeypatch):
    _no_jitter(monkeypatch)
    store = FailingDeleteStore(failures=2)

    assert await _delete_object_with_retries(store, "tenant/doc/x.pdf", attempts=3) is True
    assert store.delete_calls == ["tenant/doc/x.pdf"] * 3


async def test_delete_object_with_retries_is_bounded_and_reports_exhaustion(monkeypatch):
    _no_jitter(monkeypatch)
    store = FailingDeleteStore(failures=99)

    assert await _delete_object_with_retries(store, "tenant/doc/x.pdf", attempts=3) is False
    assert len(store.delete_calls) == 3  # bounded: never more than attempts


async def test_delete_object_with_retries_succeeds_on_first_attempt(monkeypatch):
    _no_jitter(monkeypatch)
    store = FailingDeleteStore(failures=0)

    assert await _delete_object_with_retries(store, "tenant/doc/x.pdf", attempts=3) is True
    assert store.delete_calls == ["tenant/doc/x.pdf"]


async def test_remove_object_reports_exhaustion_without_raising(monkeypatch):
    _no_jitter(monkeypatch)
    document = types.SimpleNamespace(id=uuid.uuid4(), storage_key="tenant/doc/x.pdf")
    messages: list[str] = []
    monkeypatch.setattr(
        router_module.logger, "error", lambda *args, **_kwargs: messages.append(str(args[0]))
    )

    await _remove_object(FailingDeleteStore(failures=99), document)

    assert any("cleanup exhausted" in message for message in messages)


def test_safe_basename_strips_client_supplied_paths():
    assert safe_basename("../evil.pdf") == "evil.pdf"
    assert safe_basename("C:\\fake\\dir\\notes.md") == "notes.md"
    assert safe_basename("report.pdf") == "report.pdf"


def test_safe_basename_rejects_empty_or_dot_names():
    for bad in (None, "", ".", ".."):
        with pytest.raises(ValidationError):
            safe_basename(bad)


def test_validate_upload_rejects_each_bound_violation():
    cases = [
        # size over bound
        dict(content_type="application/pdf", filename="a.pdf", data=b"%PDF" * 100, max_bytes=10),
        # type not allowlisted
        dict(
            content_type="application/octet-stream",
            filename="a.pdf",
            data=b"%PDF",
            max_bytes=MAX_BYTES,
        ),
        # extension not allowlisted
        dict(content_type="application/pdf", filename="a.txt", data=b"%PDF", max_bytes=MAX_BYTES),
        # pdf without the %PDF- signature
        dict(content_type="application/pdf", filename="a.pdf", data=b"nope", max_bytes=MAX_BYTES),
    ]
    for kwargs in cases:
        with pytest.raises(ValidationError):
            validate_upload(**kwargs)


def test_validate_upload_accepts_pdf_and_markdown_within_bounds():
    assert (
        validate_upload(
            content_type="application/pdf", filename="a.pdf", data=b"%PDF-1.4", max_bytes=MAX_BYTES
        )
        == "a.pdf"
    )
    assert (
        validate_upload(
            content_type="text/markdown", filename="b.md", data=b"# t", max_bytes=MAX_BYTES
        )
        == "b.md"
    )
