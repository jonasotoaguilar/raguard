"""Unit tests for the OpenAI chat completer (task 3.1 RED): bounded adapter.

The completer must build the OpenAI client lazily with ``max_retries=0`` and
the shared timeout, forward the bounded completion parameters, accept
truncated output, retry only timeout/connection/429/5xx failures at most
``retries`` times with bounded exponential waits, and surface exhausted or
non-retryable failures as a typed, detail-free error.
"""

import types

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from raguard_api.chat.contracts import ChatCompleter, CompletionPrompt
from raguard_api.chat.providers.openai import (
    CompletionError,
    OpenAICompleter,
    create_openai_client,
)

pytestmark = pytest.mark.unit


def _prompt() -> CompletionPrompt:
    return CompletionPrompt(system_prompt="sys", user_prompt="usr")


def _response(text: str = "answer", reason: str = "stop"):
    return types.SimpleNamespace(output_text=text, finish_reason=reason)


def _status_response(status: int) -> httpx.Response:
    return httpx.Response(
        status, request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )


class _ResponsesAPI:
    def __init__(self, responses, errors):
        self.responses = list(responses)
        self.errors = list(errors)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return self.responses.pop(0)


class _FakeClient:
    def __init__(self, responses=(), errors=()):
        self.responses = _ResponsesAPI(responses, errors)


def _completer(client=None, **overrides):
    kwargs = dict(
        api_key="sk-test",
        model="gpt-4o-mini",
        max_output_tokens=500,
        timeout_seconds=30.0,
        retries=2,
        client=client,
    )
    kwargs.update(overrides)
    return OpenAICompleter(**kwargs)


def test_complete_forwards_prompt_and_bounds():
    client = _FakeClient(responses=[_response("grounded")])
    completer = _completer(client=client, model="custom-model", max_output_tokens=800)

    assert isinstance(completer, ChatCompleter)
    assert completer.complete(_prompt()) == "grounded"

    call = client.responses.calls[0]
    assert call["model"] == "custom-model"
    assert call["max_output_tokens"] == 800
    assert call["input"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_client_is_built_lazily_through_injectable_factory():
    calls: list[tuple] = []

    def factory(*, api_key, timeout_seconds):
        calls.append((api_key, timeout_seconds))
        return _FakeClient(responses=[_response("ok")])

    completer = _completer(client_factory=factory, api_key="sk-lazy", timeout_seconds=9.0)
    assert calls == []  # construction never touches the provider

    assert completer.complete(_prompt()) == "ok"
    assert calls == [("sk-lazy", 9.0)]


def test_factory_disables_sdk_retries_and_bounds_timeout():
    client = create_openai_client(api_key="sk-test", timeout_seconds=7.0)

    assert client.max_retries == 0
    assert client.timeout == 7.0


def test_truncated_output_is_accepted():
    completer = _completer(client=_FakeClient(responses=[_response("truncated", reason="length")]))

    assert completer.complete(_prompt()) == "truncated"


@pytest.mark.parametrize(
    "error",
    [
        APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
        APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
        RateLimitError("slow down", response=_status_response(429), body=None),
        InternalServerError("boom", response=_status_response(500), body=None),
    ],
)
def test_transient_failures_retry_then_succeed(error):
    sleeps: list[float] = []

    def sleep_fn(delay):
        sleeps.append(delay)

    client = _FakeClient(responses=[_response("recovered")], errors=[error])
    completer = _completer(client=client, retries=1, sleep_fn=sleep_fn)

    assert completer.complete(_prompt()) == "recovered"
    assert len(client.responses.calls) == 2
    assert sleeps == [0.25]


def test_exhausted_retries_raise_typed_error_without_detail():
    sleeps: list[float] = []
    errors = [RateLimitError("quota sk-test", response=_status_response(429), body=None)] * 3
    client = _FakeClient(errors=errors)

    with pytest.raises(CompletionError, match="completion provider failed") as exc_info:
        _completer(client=client, retries=2, sleep_fn=sleeps.append).complete(_prompt())

    assert len(client.responses.calls) == 3
    assert sleeps == [0.25, 0.5]
    assert "quota" not in str(exc_info.value)


def test_non_retryable_provider_errors_fail_immediately():
    sleeps: list[float] = []
    errors = [BadRequestError("invalid model", response=_status_response(400), body=None)]
    client = _FakeClient(errors=errors)

    with pytest.raises(CompletionError):
        _completer(client=client, retries=2, sleep_fn=sleeps.append).complete(_prompt())

    assert len(client.responses.calls) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("kwarg", "value"),
    [
        ("max_output_tokens", 0),
        ("max_output_tokens", 2001),
        ("retries", -1),
        ("retries", 3),
        ("timeout_seconds", 0.0),
    ],
)
def test_construction_rejects_invalid_bounds(kwarg, value):
    with pytest.raises(ValueError):
        _completer(**{kwarg: value})
