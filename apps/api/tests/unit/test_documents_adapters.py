"""Unit tests for the storage and queue adapters (task 2.1 RED).

The real adapters wrap boto3 (S3/MinIO) and Arq (Redis) behind the narrow
ObjectStore/JobQueue protocols from contracts.py. These tests lock the adapter
surface with lightweight fakes standing in for the SDK clients: tenant-prefixed
object keys, deterministic ``ingest:{document_id}`` job ids, exactly-one
enqueue, and an ID-only job payload.
"""

import io
import uuid

import pytest
from raguard_api.documents.contracts import JobQueue, ObjectStore
from raguard_api.documents.queue import ArqJobQueue, _job_id
from raguard_api.documents.storage import S3ObjectStore, document_object_key

pytestmark = pytest.mark.unit

BUCKET = "raguard-documents"


class FakeS3Client:
    """Records boto3 calls; get_object returns a streamed body like boto3."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[tuple[str, str, bytes]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:
        self.put_calls.append((Bucket, Key, Body))
        self.objects[Key] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.delete_calls.append((Bucket, Key))
        self.objects.pop(Key, None)


class FakeRedis:
    """Records Arq enqueue_job calls: function, id-only args, and job id."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], str]] = []

    async def enqueue_job(self, function: str, *args: str, _job_id: str | None = None, **_kwargs):
        self.calls.append((function, args, _job_id))


def test_object_key_is_tenant_prefixed_with_document_and_basename():
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    document_id = uuid.uuid4()

    key_a = document_object_key(tenant_id=tenant_a, document_id=document_id, basename="report.pdf")

    assert key_a == f"{tenant_a}/{document_id}/report.pdf"
    assert (
        document_object_key(tenant_id=tenant_b, document_id=document_id, basename="report.pdf")
        != key_a
    )


def test_s3_put_writes_tenant_key_into_configured_bucket():
    client = FakeS3Client()
    store = S3ObjectStore(client, bucket=BUCKET)
    key = f"{uuid.uuid4()}/{uuid.uuid4()}/notes.md"

    store.put(key, b"# hello")

    assert client.put_calls == [(BUCKET, key, b"# hello")]
    assert store.get(key) == b"# hello"


def test_s3_get_returns_object_bytes_and_missing_raises():
    client = FakeS3Client()
    store = S3ObjectStore(client, bucket=BUCKET)
    key = f"{uuid.uuid4()}/{uuid.uuid4()}/a.pdf"
    store.put(key, b"%PDF-1.4")

    assert store.get(key) == b"%PDF-1.4"
    with pytest.raises(KeyError):
        store.get("missing/object")


def test_s3_delete_removes_the_tenant_prefixed_object():
    client = FakeS3Client()
    store = S3ObjectStore(client, bucket=BUCKET)
    key = f"{uuid.uuid4()}/{uuid.uuid4()}/notes.md"
    store.put(key, b"body")

    store.delete(key)

    assert client.delete_calls == [(BUCKET, key)]
    with pytest.raises(KeyError):
        store.get(key)


def test_job_id_is_deterministic_ingest_document():
    document_id = uuid.uuid4()

    assert _job_id(document_id) == f"ingest:{document_id}"
    assert _job_id(document_id) == _job_id(document_id)  # deterministic
    assert _job_id(uuid.uuid4()) != _job_id(document_id)


def test_arq_enqueue_pushes_exactly_one_id_only_job_with_job_id():
    redis = FakeRedis()
    queue = ArqJobQueue(redis_url="redis://unused", redis=redis)
    document_id = uuid.uuid4()

    queue.enqueue(_job_id(document_id), document_id)

    assert redis.calls == [("ingest_document", (str(document_id),), f"ingest:{document_id}")]


def test_arq_enqueue_two_documents_enqueue_two_distinct_jobs():
    redis = FakeRedis()
    queue = ArqJobQueue(redis_url="redis://unused", redis=redis)
    first, second = uuid.uuid4(), uuid.uuid4()

    queue.enqueue(_job_id(first), first)
    queue.enqueue(_job_id(second), second)

    assert redis.calls == [
        ("ingest_document", (str(first),), f"ingest:{first}"),
        ("ingest_document", (str(second),), f"ingest:{second}"),
    ]


def test_adapters_satisfy_the_narrow_protocols():
    assert isinstance(S3ObjectStore(FakeS3Client(), bucket=BUCKET), ObjectStore)
    assert isinstance(ArqJobQueue(redis_url="redis://unused", redis=FakeRedis()), JobQueue)
