"""Unit tests for the worker dispatch state machine (task 3.1 RED).

Locks the DESIGN.md dispatch table as a pure seam (dispatch_action,
poll_until_ready) plus the job-level behavior of each state: ready+object
processes; fresh-unready polls then defers with the typed DispatchNotReady;
stale-unready and missing rows ACK as no-ops; ready+missing object becomes
failed/source_missing; and the settings timeline satisfies wait < freshness
< sweep_age (30s/5s/100ms/5min defaults).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from raguard_api.documents.contracts import (
    EMBEDDING_DIMENSION,
    FakeEmbedder,
    FakeObjectStore,
    FakeParser,
)
from raguard_worker.jobs import (
    DispatchNotReady,
    DocumentState,
    NewChunk,
    dispatch_action,
    ingest_document,
    is_fresh,
    poll_until_ready,
)
from raguard_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)


def state(
    *,
    ready: bool = True,
    status: str = "pending",
    created_at: datetime | None = None,
    failed_reason: str | None = None,
) -> DocumentState:
    return DocumentState(
        document_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="notes.md",
        status=status,
        failure_reason=failed_reason,
        dispatch_ready=ready,
        storage_key=f"{uuid.uuid4()}/notes.md",
        # Call-time now: module-level constants age past the 30s freshness
        # window when the full suite runs long, flipping fresh rows to stale.
        created_at=created_at or datetime.now(UTC),
    )


class FakeClaim:
    """In-memory DocumentClaim recording every commit for behavioral asserts."""

    def __init__(self, document_state: DocumentState | None) -> None:
        self.state = document_state
        self.indexed_calls: list[list[NewChunk]] = []
        self.failed_calls: list[str] = []
        self.closed = False

    async def commit_indexed(self, chunks) -> None:
        self.indexed_calls.append(list(chunks))

    async def commit_failed(self, reason: str) -> None:
        self.failed_calls.append(reason)

    async def close(self) -> None:
        self.closed = True


class FakeDispatchStore:
    """In-memory DispatchStore; fetch returns states[i] (last repeats)."""

    def __init__(self, states: list[DocumentState | None], claim: FakeClaim | None) -> None:
        self._states = states
        self.claim = claim
        self.fetch_count = 0
        self.lock_calls: list[uuid.UUID] = []

    async def fetch(self, document_id: uuid.UUID) -> DocumentState | None:
        index = min(self.fetch_count, len(self._states) - 1)
        self.fetch_count += 1
        return self._states[index]

    async def lock_for_process(self, document_id: uuid.UUID) -> FakeClaim | None:
        self.lock_calls.append(document_id)
        return self.claim


def ctx(*, claim: FakeClaim | None = None, states: list[DocumentState | None] | None = None):
    store = FakeDispatchStore(
        states if states is not None else [claim.state if claim else None], claim
    )
    return {
        "settings": WorkerSettings(dispatch_wait_seconds=0.05, dispatch_poll_interval_seconds=0.01),
        "store": store,
        "object_store": FakeObjectStore(),
        "parser": FakeParser(),
        "embedder": FakeEmbedder(),
        "chunker": lambda text: text.splitlines(),
        "job_try": 1,
    }


async def test_dispatch_action_maps_every_design_state() -> None:
    ready = state(ready=True)
    fresh_unready = state(ready=False)
    stale_unready = state(ready=False, created_at=NOW - timedelta(seconds=400))
    failed = state(ready=True, status="failed", failed_reason="malformed")

    assert dispatch_action(ready, now=NOW, freshness_seconds=30.0) == "process"
    assert dispatch_action(fresh_unready, now=NOW, freshness_seconds=30.0) == "poll"
    assert dispatch_action(stale_unready, now=NOW, freshness_seconds=30.0) == "ack"
    assert dispatch_action(None, now=NOW, freshness_seconds=30.0) == "ack"
    assert dispatch_action(failed, now=NOW, freshness_seconds=30.0) == "ack"


async def test_is_fresh_uses_the_freshness_window_boundary() -> None:
    assert is_fresh(NOW - timedelta(seconds=29), now=NOW, freshness_seconds=30.0)
    assert is_fresh(NOW - timedelta(seconds=30), now=NOW, freshness_seconds=30.0)
    assert not is_fresh(NOW - timedelta(seconds=31), now=NOW, freshness_seconds=30.0)


async def test_settings_defaults_satisfy_wait_freshness_sweep_timeline() -> None:
    settings = WorkerSettings()
    assert settings.dispatch_wait_seconds == 5.0
    assert settings.dispatch_freshness_seconds == 30.0
    assert settings.dispatch_poll_interval_seconds == 0.1
    assert settings.sweep_age_seconds == 300.0
    timeline = (
        settings.dispatch_wait_seconds,
        settings.dispatch_freshness_seconds,
        settings.sweep_age_seconds,
    )
    assert timeline[0] < timeline[1] < timeline[2]


async def test_settings_reject_wait_not_below_freshness() -> None:
    with pytest.raises(ValueError):
        WorkerSettings(dispatch_wait_seconds=30.0, dispatch_freshness_seconds=5.0)


async def test_settings_reject_freshness_not_below_sweep_age() -> None:
    with pytest.raises(ValueError):
        WorkerSettings(dispatch_freshness_seconds=400.0, sweep_age_seconds=300.0)


async def test_poll_until_ready_raises_dispatch_not_ready_after_bounded_wait() -> None:
    unready = state(ready=False)
    store = FakeDispatchStore([unready], None)

    with pytest.raises(DispatchNotReady) as excinfo:
        await poll_until_ready(
            store,
            unready.document_id,
            wait_seconds=0.05,
            poll_interval_seconds=0.01,
            freshness_seconds=30.0,
        )

    assert excinfo.value.defer_score == 50  # retry_after = wait_seconds
    assert store.fetch_count >= 2  # polled, did not decide from the first read


async def test_poll_until_ready_returns_the_ready_row_once_committed() -> None:
    unready, ready = state(ready=False), state(ready=True)
    store = FakeDispatchStore([unready, unready, ready], None)

    result = await poll_until_ready(
        store,
        ready.document_id,
        wait_seconds=1.0,
        poll_interval_seconds=0.01,
        freshness_seconds=30.0,
    )

    assert result is ready
    assert store.fetch_count == 3


async def test_poll_until_ready_acks_when_row_turns_stale() -> None:
    stale = state(ready=False, created_at=NOW - timedelta(seconds=400))
    store = FakeDispatchStore([state(ready=False), stale], None)

    result = await poll_until_ready(
        store,
        stale.document_id,
        wait_seconds=1.0,
        poll_interval_seconds=0.01,
        freshness_seconds=30.0,
    )

    assert result is None


async def test_ready_row_with_object_is_locked_parsed_chunked_embedded_and_committed() -> None:
    document_state = state(ready=True)
    claim = FakeClaim(document_state)
    environment = ctx(claim=claim)
    environment["object_store"].put(document_state.storage_key, b"line one\nline two")

    await ingest_document(environment, str(document_state.document_id))

    assert environment["store"].lock_calls == [document_state.document_id]
    parts = ["line one", "line two"]
    expected = [
        NewChunk(part, vector)
        for part, vector in zip(parts, FakeEmbedder().embed(parts), strict=True)
    ]
    assert claim.indexed_calls == [expected]
    assert len(expected[0].embedding) == EMBEDDING_DIMENSION
    assert claim.failed_calls == []
    assert claim.closed


async def test_fresh_unready_row_defers_with_typed_dispatch_not_ready() -> None:
    document_state = state(ready=False)
    claim = FakeClaim(document_state)
    environment = ctx(claim=claim)

    with pytest.raises(DispatchNotReady):
        await ingest_document(environment, str(document_state.document_id))

    assert environment["store"].lock_calls == []
    assert claim.indexed_calls == [] and claim.failed_calls == []


async def test_stale_unready_row_acks_without_processing() -> None:
    document_state = state(ready=False, created_at=NOW - timedelta(seconds=400))
    claim = FakeClaim(document_state)
    environment = ctx(claim=claim)

    assert await ingest_document(environment, str(document_state.document_id)) is None

    assert environment["store"].lock_calls == []
    assert claim.indexed_calls == [] and claim.failed_calls == []


async def test_missing_row_acks_without_touching_anything() -> None:
    environment = ctx(claim=None, states=[None])

    assert await ingest_document(environment, str(uuid.uuid4())) is None

    assert environment["store"].lock_calls == []
    assert environment["object_store"].put_keys == []


async def test_ready_row_with_missing_object_becomes_failed_source_missing() -> None:
    document_state = state(ready=True)  # object never put into the store
    claim = FakeClaim(document_state)
    environment = ctx(claim=claim)

    assert await ingest_document(environment, str(document_state.document_id)) is None

    assert claim.failed_calls == ["source_missing"]
    assert claim.indexed_calls == []
    assert claim.closed
