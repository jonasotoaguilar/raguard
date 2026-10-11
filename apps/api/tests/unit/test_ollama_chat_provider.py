"""Unit tests for the Ollama chat completer (ODD-2 RED): bounded local adapter.

The completer must satisfy the ``ChatCompleter`` protocol over the native
Ollama ``POST /api/chat`` contract: static system/user messages, explicit
``stream: false``, bounded ``options.num_predict``, lazy bounded client,
success parsing of ``message.content``, detail-free ``CompletionError`` on
malformed responses, and retries only for timeout/connection/429/5xx.
"""

import httpx
import pytest
from raguard_api.chat.contracts import ChatCompleter, CompletionPrompt
from raguard_api.chat.providers.ollama import OllamaCompleter
from raguard_api.chat.providers.openai import CompletionError

pytestmark = pytest.mark.unit


def _prompt() -> CompletionPrompt:
    return CompletionPrompt(system_prompt="sys", user_prompt="usr")


def _chat_payload(text: str = "answer") -> dict:
    return {"model": "qwen3:1.7b", "message": {"role": "assistant", "content": text}}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses=(), errors=()):
        self._responses = list(responses)
        self._errors = list(errors)
        self.posts: list[dict] = []

    def post(self, path, *, json):
        self.posts.append({"path": path, "json": dict(json)})
        if self._errors:
            raise self._errors.pop(0)
        return self._responses.pop(0)


def _completer(client=None, **overrides):
    kwargs = dict(
        base_url="http://127.0.0.1:11434",
        model="qwen3:1.7b",
        max_output_tokens=500,
        timeout_seconds=30.0,
        retries=2,
        client=client,
    )
    kwargs.update(overrides)
    return OllamaCompleter(**kwargs)


def _timeout() -> httpx.TimeoutException:
    return httpx.TimeoutException("timed out")


def _connection() -> httpx.ConnectError:
    return httpx.ConnectError("refused")


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://ollama:11434/api/chat")
    return httpx.HTTPStatusError(
        "error", request=request, response=httpx.Response(status, request=request)
    )


def test_complete_posts_native_chat_contract_with_stream_false():
    client = _FakeClient(responses=[_FakeResponse(_chat_payload("grounded"))])
    completer = _completer(client=client, model="custom-model", max_output_tokens=800)

    assert isinstance(completer, ChatCompleter)
    assert completer.complete(_prompt()) == "grounded"

    assert client.posts == [
        {
            "path": "/api/chat",
            "json": {
                "model": "custom-model",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "usr"},
                ],
                "stream": False,
                "options": {"num_predict": 800},
            },
        }
    ]


def test_client_is_built_lazily_through_injectable_factory():
    calls: list[tuple] = []

    def factory(*, base_url, timeout_seconds):
        calls.append((base_url, timeout_seconds))
        return _FakeClient(responses=[_FakeResponse(_chat_payload("ok"))])

    completer = _completer(
        client_factory=factory, base_url="http://ollama:11434", timeout_seconds=9.0
    )
    assert calls == []  # construction never touches the provider

    assert completer.complete(_prompt()) == "ok"
    assert calls == [("http://ollama:11434", 9.0)]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": {}},
        {"message": {"content": 42}},
        {"message": "not-a-dict"},
        ["not-a-dict"],
    ],
)
def test_malformed_response_raises_typed_error_without_retry(payload):
    sleeps: list[float] = []
    client = _FakeClient(responses=[_FakeResponse(payload)])

    with pytest.raises(CompletionError, match="completion provider failed"):
        _completer(client=client, sleep_fn=sleeps.append).complete(_prompt())

    assert len(client.posts) == 1
    assert sleeps == []


@pytest.mark.parametrize("error", [_timeout(), _connection()])
def test_transient_transport_failures_retry_then_succeed(error):
    sleeps: list[float] = []
    client = _FakeClient(responses=[_FakeResponse(_chat_payload("recovered"))], errors=[error])

    result = _completer(client=client, retries=1, sleep_fn=sleeps.append).complete(_prompt())

    assert result == "recovered"
    assert len(client.posts) == 2
    assert sleeps == [0.25]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_statuses_retry_then_succeed(status):
    sleeps: list[float] = []
    client = _FakeClient(responses=[_FakeResponse(_chat_payload("recovered"))])
    real_post = client.post
    calls = {"count": 0}

    def flaky_post(path, *, json):
        calls["count"] += 1
        if calls["count"] == 1:
            raise _status_error(status)
        return real_post(path, json=json)

    client.post = flaky_post

    result = _completer(client=client, retries=1, sleep_fn=sleeps.append).complete(_prompt())

    assert result == "recovered"
    assert calls["count"] == 2
    assert sleeps == [0.25]


@pytest.mark.parametrize("status", [400, 401, 404])
def test_non_retryable_statuses_fail_immediately(status):
    sleeps: list[float] = []

    def always_fails(path, *, json):
        raise _status_error(status)

    client = _FakeClient(responses=[])
    client.post = always_fails

    with pytest.raises(CompletionError, match="completion provider failed"):
        _completer(client=client, retries=2, sleep_fn=sleeps.append).complete(_prompt())

    assert sleeps == []


def test_exhausted_retries_raise_typed_error_without_detail():
    sleeps: list[float] = []
    client = _FakeClient(errors=[_timeout(), _timeout(), _timeout()])

    with pytest.raises(CompletionError, match="completion provider failed") as exc_info:
        _completer(client=client, retries=2, sleep_fn=sleeps.append).complete(_prompt())

    assert len(client.posts) == 3
    assert sleeps == [0.25, 0.5]
    assert "timed out" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("kwarg", "value"),
    [
        ("max_output_tokens", 0),
        ("max_output_tokens", 2001),
        ("retries", -1),
        ("retries", 3),
        ("timeout_seconds", 0.0),
        ("model", "   "),
        ("base_url", "ftp://host"),
    ],
)
def test_construction_rejects_invalid_bounds(kwarg, value):
    with pytest.raises(ValueError):
        _completer(**{kwarg: value})
