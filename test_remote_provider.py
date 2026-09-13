"""Tests for RemoteDescriptionProvider -- the HTTP client that talks to the
hosted AI-drafting backend. No real network calls: the urllib layer is
monkeypatched, matching the discipline test_gemini_provider.py (the direct-
Gemini provider's own tests) already used.
"""

import json
import urllib.error

from PyCodeCommenter.description_provider import FunctionContext, ParameterFact
from PyCodeCommenter.remote_provider import RemoteDescriptionProvider


def make_context(**overrides) -> FunctionContext:
    defaults = dict(
        name="calculate_discount",
        parameters=[
            ParameterFact(name="price", type_hint="float"),
            ParameterFact(name="rate", type_hint="float", default="0.1"),
        ],
        return_type="float",
        is_generator=False,
        raised_exceptions=[],
        source=(
            "def calculate_discount(price, rate=0.1):\n    return price * (1 - rate)"
        ),
    )
    defaults.update(overrides)
    return FunctionContext(**defaults)


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_successful_draft_returns_trimmed_description(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse({"description": "  A function.  "}),
    )

    result = provider.draft_function_description(make_context())

    assert result == "A function."


def test_decline_response_returns_none(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen",
        lambda request, timeout: _FakeHTTPResponse({"description": None}),
    )

    assert provider.draft_function_description(make_context()) is None


def test_429_returns_none_without_raising(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")

    def raise_429(request, timeout):
        raise urllib.error.HTTPError(
            url="https://example.test/v1/draft-description",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", raise_429
    )

    assert provider.draft_function_description(make_context()) is None


def test_timeout_returns_none_without_raising(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")

    def raise_timeout(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", raise_timeout
    )

    assert provider.draft_function_description(make_context()) is None


def test_malformed_json_response_returns_none(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")

    class _BadResponse:
        def read(self):
            return b"not json"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen",
        lambda request, timeout: _BadResponse(),
    )

    assert provider.draft_function_description(make_context()) is None


def test_request_payload_matches_the_wire_contract(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse({"description": "ok."})

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )

    provider.draft_function_description(make_context())

    assert captured["url"] == "https://example.test/v1/draft-description"
    assert captured["body"]["name"] == "calculate_discount"
    assert captured["body"]["parameters"] == [
        {"name": "price", "type_hint": "float", "default": None},
        {"name": "rate", "type_hint": "float", "default": "0.1"},
    ]
    assert captured["body"]["return_type"] == "float"
    assert captured["timeout"] == 90.0


def test_backend_url_trailing_slash_is_normalized(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test/")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return _FakeHTTPResponse({"description": "ok."})

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )

    provider.draft_function_description(make_context())

    assert captured["url"] == "https://example.test/v1/draft-description"
