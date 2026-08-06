"""Application settings from environment (task 2.5).

Field names map to uppercase environment variables (JWT_SECRET,
SESSION_COOKIE_SECURE, ALLOWED_ORIGINS as JSON, ...). ``jwt_secret`` has no
default: production must fail fast when the signing key is unset.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "raguard"
    jwt_audience: str = "raguard-api"
    jwt_expiry_minutes: int = 15
    session_cookie_name: str = "raguard_session"
    session_cookie_path: str = "/api"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    allowed_origins: list[str] = ["http://localhost:5173"]
    object_store_endpoint_url: str = "http://127.0.0.1:9000"
    object_store_bucket: str = "raguard-documents"
    object_store_access_key: str = ""
    object_store_secret_key: str = ""
    object_store_region: str = "us-east-1"
    job_queue_redis_url: str = "redis://127.0.0.1:6379/0"
    job_queue_function_name: str = "ingest_document"
    max_upload_bytes: int = 20 * 1024 * 1024

    model_config = {"extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
