"""Object-storage adapter: boto3 S3 (MinIO locally) behind the ObjectStore protocol (task 2.2).

Object keys are always tenant-prefixed ``{tenant_id}/{document_id}/{basename}``
so the object namespace is tenant-scoped exactly like the database rows
(design: tenant/document/basename). The boto3 client stays injectable so tests
substitute a fake; ``create_s3_client`` builds the real MinIO-compatible client
from settings (lazy boto3 import keeps the module cheap for the worker).
"""

import uuid
from typing import Any


def document_object_key(*, tenant_id: uuid.UUID, document_id: uuid.UUID, basename: str) -> str:
    """Tenant-prefixed object key: ``{tenant_id}/{document_id}/{basename}``."""
    return f"{tenant_id}/{document_id}/{basename}"


class S3ObjectStore:
    """ObjectStore adapter over a boto3 S3 client (MinIO-compatible endpoint)."""

    def __init__(self, client: Any, *, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


def create_s3_client(settings) -> Any:
    """Build a boto3 S3 client pointed at the configured object store."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.object_store_endpoint_url,
        aws_access_key_id=settings.object_store_access_key or None,
        aws_secret_access_key=settings.object_store_secret_key or None,
        region_name=settings.object_store_region,
    )
