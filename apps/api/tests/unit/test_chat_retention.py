"""Unit tests for chat history retention/purge (G3, test-first RED).

Covers: ``chat_retention_days`` defaults/bounds, the ``retention_days <= 0``
no-op, the ``updated_at`` cutoff computation, and the no-content-logging
invariant. Expiration selection against real rows is covered by
``apps/api/tests/integration/test_chat_retention.py`` (CI).
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from raguard_api.config import Settings

pytestmark = pytest.mark.unit

JWT_SECRET = "a" * 32


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret=JWT_SECRET, **overrides)


def test_chat_retention_default_is_zero_disabled():
    assert _settings().chat_retention_days == 0


def test_chat_retention_days_is_environment_configurable(monkeypatch):
    monkeypatch.setenv("CHAT_RETENTION_DAYS", "30")
    assert _settings().chat_retention_days == 30


@pytest.mark.parametrize("value", [-1, -30, 3651, 100_000])
def test_startup_rejects_out_of_range_retention_days(value):
    with pytest.raises(ValueError, match="chat_retention_days"):
        _settings(chat_retention_days=value)


@pytest.mark.parametrize("value", [0, 1, 30, 3650])
def test_retention_bounds_are_inclusive(value):
    assert _settings(chat_retention_days=value).chat_retention_days == value


def test_cutoff_subtracts_retention_days():
    from raguard_api.chat.retention import cutoff_for_retention

    now = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
    assert cutoff_for_retention(30, now=now) == now - timedelta(days=30)


async def test_nonpositive_retention_is_noop_without_touching_db():
    from raguard_api.chat import retention as retention_module

    calls: list = []

    def _factory():
        calls.append(1)
        raise AssertionError("session_factory must not be used when disabled")

    assert await retention_module.purge_expired_conversations(_factory, 0) == 0
    assert await retention_module.purge_expired_conversations(_factory, -5) == 0
    assert calls == []


async def test_purge_logs_summary_without_message_content(caplog):
    from raguard_api.chat import retention as retention_module

    class _FakeResult:
        def scalars(self):
            class _S:
                def all(self):
                    return []

            return _S()

        def rowcount(self):
            return 0

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt, *args, **kwargs):
            return _FakeResult()

        def begin(self):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _begin():
                yield

            return _begin()

    def _factory():
        return _FakeSession()

    secret_content = "super-secret-message-body-never-log-this"
    with caplog.at_level(logging.INFO, logger="raguard_api.chat.retention"):
        count = await retention_module.purge_expired_conversations(_factory, 30)
    assert count == 0
    for record in caplog.records:
        assert secret_content not in record.getMessage()
        assert secret_content not in str(record.args)
