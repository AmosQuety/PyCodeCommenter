"""Tests for RemoteDescriptionProvider -- the HTTP client that talks to the
hosted AI-drafting backend. No real network calls: the urllib layer is
monkeypatched, the same discipline the Gemini client's own tests follow in
the separate pycodecommenter-ai-backend repo.
"""

import json
import urllib.error

import pytest

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


# ---------------------------------------------------------------------------
# /v2: structured drafting, the daily allowance, and limits
# ---------------------------------------------------------------------------

import io  # noqa: E402
from email.message import Message  # noqa: E402

from PyCodeCommenter.description_provider import (  # noqa: E402
    DraftingStopped,
    DraftSlots,
    KnownText,
)

SLOTS = DraftSlots(summary=True, params=("price",), returns=True)
KNOWN = KnownText(params={"rate": "Discount rate."})


class _FakeV2Response(_FakeHTTPResponse):
    def __init__(self, body: dict, remaining="24", limit="25"):
        super().__init__(body)
        self.headers = {"X-AI-Drafts-Remaining": remaining, "X-AI-Drafts-Limit": limit}


def _http_error(code: int, body: dict, retry_after: str = "30"):
    headers = Message()
    headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://example.test/v2/draft-docstring",
        code=code,
        msg="error",
        hdrs=headers,
        fp=io.BytesIO(json.dumps(body).encode()),
    )


def test_draft_docstring_posts_slots_and_known_text_to_v2(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return _FakeV2Response(
            {
                "summary": "Apply a discount.",
                "description": None,
                "params": {"price": "Original price."},
                "returns": "The discounted price.",
                "raises": {},
            }
        )

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )

    draft = provider.draft_docstring(make_context(), KNOWN, SLOTS)

    assert captured["url"] == "https://example.test/v2/draft-docstring"
    assert captured["body"]["slots"] == {
        "summary": True,
        "description": False,
        "params": ["price"],
        "returns": True,
        "raises": [],
    }
    assert captured["body"]["known"]["params"] == {"rate": "Discount rate."}
    assert draft.summary == "Apply a discount."
    assert draft.params == {"price": "Original price."}
    assert draft.returns == "The discounted price."
    assert provider.drafts_remaining == 24
    assert provider.drafts_limit == 25


def test_non_string_values_in_the_reply_are_ignored(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen",
        lambda request, timeout: _FakeV2Response(
            {"summary": 7, "params": {"price": ["x"]}, "returns": None, "raises": "x"}
        ),
    )

    draft = provider.draft_docstring(make_context(), KNOWN, SLOTS)

    assert draft.summary is None
    assert draft.params == {}
    assert draft.raises == {}


@pytest.mark.parametrize("reason", ["user_daily_limit_reached", "daily_cap_reached"])
def test_spent_allowance_stops_drafting_with_the_services_message(monkeypatch, reason):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    calls = []

    def limit_reached(request, timeout):
        calls.append(1)
        raise _http_error(429, {"error": reason, "message": "Use your own key."})

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", limit_reached
    )

    with pytest.raises(DraftingStopped) as first:
        provider.draft_docstring(make_context(), KNOWN, SLOTS)
    with pytest.raises(DraftingStopped):
        provider.draft_docstring(make_context(), KNOWN, SLOTS)

    assert first.value.reason == reason
    assert "Use your own key." in first.value.message
    assert len(calls) == 1  # no further requests once stopped
    assert provider.drafts_remaining == 0 or reason == "daily_cap_reached"


def test_per_minute_rate_limit_waits_once_then_retries(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    slept = []
    responses = iter(
        [
            _http_error(429, {"error": "rate_limited"}, retry_after="7"),
            _FakeV2Response({"summary": "Apply a discount."}),
        ]
    )

    def fake_urlopen(request, timeout):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )
    monkeypatch.setattr("PyCodeCommenter.remote_provider.time.sleep", slept.append)

    draft = provider.draft_docstring(make_context(), KNOWN, SLOTS)

    assert slept == [7]
    assert draft.summary == "Apply a discount."


def test_rate_limit_wait_is_capped(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    slept = []

    def always_limited(request, timeout):
        raise _http_error(429, {"error": "rate_limited"}, retry_after="3600")

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", always_limited
    )
    monkeypatch.setattr("PyCodeCommenter.remote_provider.time.sleep", slept.append)

    draft = provider.draft_docstring(make_context(), KNOWN, SLOTS)

    assert slept == [RemoteDescriptionProvider.MAX_RATE_LIMIT_WAIT_S]
    assert draft.summary is None


def test_older_backend_without_v2_falls_back_to_v1_description(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        if request.full_url.endswith("/v2/draft-docstring"):
            raise _http_error(404, {})
        return _FakeHTTPResponse({"description": "Applies a discount."})

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )

    draft = provider.draft_docstring(
        make_context(), KNOWN, DraftSlots(description=True, summary=True)
    )

    assert draft.description == "Applies a discount."
    assert urls[-1] == "https://example.test/v1/draft-description"


def test_network_failure_returns_an_empty_draft(monkeypatch):
    provider = RemoteDescriptionProvider(backend_url="https://example.test")

    def fail(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr("PyCodeCommenter.remote_provider.urllib.request.urlopen", fail)

    draft = provider.draft_docstring(make_context(), KNOWN, SLOTS)

    assert draft.summary is None and draft.params == {}
