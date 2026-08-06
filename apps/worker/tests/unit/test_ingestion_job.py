"""Unit tests for ingestion-job retries, exhaustion, and idempotency (task 3.2 RED).

Provider calls retry ``provider_attempts`` times with jittered backoff and
honor a bounded 429 Retry-After; retry-budget exhaustion ends in an
allowlisted terminal reason (parse -> malformed, embed -> limit); commits are
one atomic zero-or-all replacement; redelivery of an ``indexed`` row
reprocesses while a ``failed`` row ACKs without adapters or mutation. PR5
adds the observability contract: terminal failures and unhandled stage
failures log a bounded-cardinality alert carrying the document-id
correlation and ``job_try``, while designed deferrals never alert.
Corrective remediation: transient parser/embedder failures at a non-terminal
``job_try`` raise the bounded ``TransientStageFailure`` (an ``arq.worker.Retry``
the worker requeues — arq 0.28 terminal-fails plain exceptions), and only the
terminal ``job_try`` commits the allowlisted reason.
"""

import uuid
from dataclasses import replace

import pytest
from arq.worker import Retry
from conftest import ctx, state
from raguard_api.documents.contracts import FAILURE_REASONS, FakeEmbedder
from raguard_worker.jobs import (
    DispatchNotReady,
    NewChunk,
    ProviderRateLimited,
    TransientStageFailure,
    call_with_retries,
    ingest_document,
)

pytestmark = pytest.mark.unit


class RecordingSleep:
    """Records every backoff delay instead of sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class FailingParser:
    def parse(self, data: bytes) -> str:
        raise RuntimeError("parse failed")


class FailingEmbedder:
    def embed(self, texts) -> list[list[float]]:
        raise RuntimeError("embed failed")


async def test_transient_failures_retry_with_jitter_then_succeed() -> None:
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    sleeper = RecordingSleep()
    result = await call_with_retries(
        flaky, attempts=3, max_jitter=0.05, max_retry_after=5.0, sleep=sleeper
    )

    assert result == "ok"
    assert calls["n"] == 3
    assert len(sleeper.delays) == 2
    assert 0 <= sleeper.delays[0] <= 0.05
    assert 0 <= sleeper.delays[1] <= 0.10  # jitter grows with the attempt


async def test_provider_429_sleeps_the_bounded_retry_after() -> None:
    calls = {"n": 0}

    async def rate_limited_once():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderRateLimited(retry_after=60.0)
        return "ok"

    sleeper = RecordingSleep()
    result = await call_with_retries(
        rate_limited_once, attempts=3, max_jitter=0.05, max_retry_after=5.0, sleep=sleeper
    )

    assert result == "ok"
    assert sleeper.delays == [5.0]  # bounded: min(retry_after, max_retry_after)


async def test_provider_429_honors_a_short_retry_after() -> None:
    calls = {"n": 0}

    async def rate_limited_once():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderRateLimited(retry_after=1.0)
        return "ok"

    sleeper = RecordingSleep()
    await call_with_retries(
        rate_limited_once, attempts=3, max_jitter=0.05, max_retry_after=5.0, sleep=sleeper
    )

    assert sleeper.delays == [1.0]


async def test_retries_exhaust_raise_the_last_error() -> None:
    async def always_fails():
        raise RuntimeError("boom")

    sleeper = RecordingSleep()
    with pytest.raises(RuntimeError, match="boom"):
        await call_with_retries(
            always_fails, attempts=3, max_jitter=0.05, max_retry_after=5.0, sleep=sleeper
        )
    assert len(sleeper.delays) == 2


async def test_parse_exhaustion_on_last_attempt_ends_failed_malformed(claim, env) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["parser"] = FailingParser()
    env["job_try"] = 10  # == settings.max_tries: retry budget spent

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert claim.failed_calls == ["malformed"]
    assert claim.failed_calls[0] in FAILURE_REASONS
    assert claim.indexed_calls == []


async def test_parse_failure_with_retries_left_defers_bounded_retry_without_failed_write(
    claim, env
) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["parser"] = FailingParser()
    env["job_try"] = 1  # Arq retries remain: the job must requeue, not terminal-fail

    with pytest.raises(TransientStageFailure) as excinfo:
        await ingest_document(env, str(claim.state.document_id))

    assert isinstance(excinfo.value, Retry)  # arq 0.28 requeues Retry, fails plain exceptions
    assert excinfo.value.defer_score >= 0  # bounded deferral, not a terminal failure
    assert claim.failed_calls == []
    assert claim.indexed_calls == []
    assert claim.closed  # the row lock is released before the deferral propagates


async def test_embed_failure_with_retries_left_defers_bounded_retry_without_failed_write(
    claim, env
) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["embedder"] = FailingEmbedder()
    env["job_try"] = 1

    with pytest.raises(TransientStageFailure) as excinfo:
        await ingest_document(env, str(claim.state.document_id))

    assert isinstance(excinfo.value, Retry)
    assert claim.failed_calls == []
    assert claim.indexed_calls == []
    assert claim.closed


async def test_transient_429_defers_the_bounded_retry_after(claim, env) -> None:
    class RateLimitedParser:
        def parse(self, data: bytes) -> str:
            raise ProviderRateLimited(retry_after=60.0)

    env["object_store"].put(claim.state.storage_key, b"data")
    env["parser"] = RateLimitedParser()
    env["job_try"] = 1

    with pytest.raises(TransientStageFailure) as excinfo:
        await ingest_document(env, str(claim.state.document_id))

    assert excinfo.value.defer_score == 5000  # bounded: min(60.0, max_retry_after_seconds=5.0)
    assert claim.failed_calls == []
    assert claim.indexed_calls == []


async def test_transient_failure_at_try_nine_still_defers_not_exhausted(claim, env) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["parser"] = FailingParser()
    env["job_try"] = 9  # one attempt remains: still defers, not yet terminal

    with pytest.raises(TransientStageFailure):
        await ingest_document(env, str(claim.state.document_id))

    assert claim.failed_calls == []
    assert claim.indexed_calls == []


async def test_embed_exhaustion_on_last_attempt_ends_failed_limit(claim, env) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["embedder"] = FailingEmbedder()
    env["job_try"] = 10

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert claim.failed_calls == ["limit"]
    assert claim.failed_calls[0] in FAILURE_REASONS
    assert claim.indexed_calls == []


async def test_commit_failure_reraises_without_any_written_failure(
    claim, env, recording_logger
) -> None:
    class ExplodingClaim(type(claim)):
        async def commit_indexed(self, chunks) -> None:
            raise RuntimeError("commit failed")

    env["object_store"].put(claim.state.storage_key, b"data")
    exploding = ExplodingClaim(claim.state)
    env["store"].claim = exploding
    env["logger"] = recording_logger

    with pytest.raises(RuntimeError, match="commit failed"):
        await ingest_document(env, str(claim.state.document_id))

    assert exploding.failed_calls == []
    assert exploding.indexed_calls == []
    assert len(recording_logger.errors) == 1  # genuinely unhandled failures still alert
    assert "job failure alert" in recording_logger.errors[0]
    assert str(claim.state.document_id) in recording_logger.errors[0]
    assert "RuntimeError" in recording_logger.errors[0]
    assert "job_try=1" in recording_logger.errors[0]


async def test_indexed_redelivery_reprocesses_and_replaces_atomically(claim, env) -> None:
    claim.state = replace(claim.state, status="indexed")
    env["object_store"].put(claim.state.storage_key, b"first")

    await ingest_document(env, str(claim.state.document_id))
    assert claim.indexed_calls == [[NewChunk("first", FakeEmbedder().embed(["first"])[0])]]

    env["object_store"].put(claim.state.storage_key, b"second line")
    await ingest_document(env, str(claim.state.document_id))

    assert claim.indexed_calls == [
        [NewChunk("first", FakeEmbedder().embed(["first"])[0])],
        [NewChunk("second line", FakeEmbedder().embed(["second line"])[0])],
    ]
    assert claim.failed_calls == []


async def test_failed_redelivery_acks_without_adapters_or_mutation(claim, env) -> None:
    claim.state = replace(claim.state, status="failed", failure_reason="malformed")
    env["object_store"].put(claim.state.storage_key, b"data")  # object exists

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert env["store"].lock_calls == []
    assert claim.indexed_calls == [] and claim.failed_calls == []


async def test_transient_stage_failure_defers_without_job_failure_alert(
    claim, env, recording_logger
) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["parser"] = FailingParser()
    env["job_try"] = 1  # retries left: the job defers via TransientStageFailure
    env["logger"] = recording_logger

    with pytest.raises(TransientStageFailure):
        await ingest_document(env, str(claim.state.document_id))

    assert recording_logger.errors == []  # designed deferrals are not failures


async def test_fresh_unready_deferral_is_not_logged_as_failure(recording_logger) -> None:
    env = ctx(states=[state(ready=False)])
    env["logger"] = recording_logger

    with pytest.raises(DispatchNotReady):
        await ingest_document(env, str(uuid.uuid4()))

    assert recording_logger.errors == []  # deferrals are designed, not failures


async def test_terminal_parse_exhaustion_logs_alert_with_reason(
    claim, env, recording_logger
) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["parser"] = FailingParser()
    env["job_try"] = 10  # == settings.max_tries: retry budget spent
    env["logger"] = recording_logger

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert claim.failed_calls == ["malformed"]
    assert len(recording_logger.errors) == 1
    assert "job failure alert" in recording_logger.errors[0]
    assert str(claim.state.document_id) in recording_logger.errors[0]
    assert "reason=malformed" in recording_logger.errors[0]
    assert "job_try=10" in recording_logger.errors[0]


async def test_terminal_embed_exhaustion_logs_alert_with_reason(
    claim, env, recording_logger
) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["embedder"] = FailingEmbedder()
    env["job_try"] = 10
    env["logger"] = recording_logger

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert claim.failed_calls == ["limit"]
    assert len(recording_logger.errors) == 1
    assert "reason=limit" in recording_logger.errors[0]
    assert str(claim.state.document_id) in recording_logger.errors[0]


async def test_terminal_chunker_failure_logs_alert_with_reason(
    claim, env, recording_logger
) -> None:
    env["object_store"].put(claim.state.storage_key, b"data")
    env["logger"] = recording_logger

    def broken_chunker(text: str) -> list[str]:
        raise RuntimeError("chunk bound exceeded")

    env["chunker"] = broken_chunker

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert claim.failed_calls == ["malformed"]  # deterministic logic: terminal immediately
    assert len(recording_logger.errors) == 1
    assert "job failure alert" in recording_logger.errors[0]
    assert "reason=malformed" in recording_logger.errors[0]
    assert str(claim.state.document_id) in recording_logger.errors[0]


async def test_source_missing_logs_job_failure_alert(claim, env, recording_logger) -> None:
    env["logger"] = recording_logger  # object deliberately missing

    assert await ingest_document(env, str(claim.state.document_id)) is None

    assert claim.failed_calls == ["source_missing"]
    assert len(recording_logger.errors) == 1
    assert "job failure alert" in recording_logger.errors[0]
    assert "reason=source_missing" in recording_logger.errors[0]


async def test_success_logs_indexed_info_with_correlation(claim, env, recording_logger) -> None:
    env["object_store"].put(claim.state.storage_key, b"# notes\nbody line")
    env["logger"] = recording_logger

    await ingest_document(env, str(claim.state.document_id))

    parts = ["# notes", "body line"]
    vectors = FakeEmbedder().embed(parts)
    assert claim.indexed_calls == [[NewChunk(parts[i], vectors[i]) for i in range(len(parts))]]
    assert len(recording_logger.infos) == 1
    assert "document indexed" in recording_logger.infos[0]
    assert str(claim.state.document_id) in recording_logger.infos[0]
    assert "chunks=2" in recording_logger.infos[0]
    assert recording_logger.errors == []
