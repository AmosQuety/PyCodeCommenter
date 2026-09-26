"""Bring-your-own-key providers: the shared prompt/schema/parsing, each
provider's call shape against a fake SDK client, error handling, the
limit-reached hand-off, and per-destination consent.

No test here touches the network or needs an SDK installed: every provider
accepts an injected client, and the fakes below mimic only the calls the
providers make.
"""

import json
from types import SimpleNamespace

import pytest

from PyCodeCommenter.ai_drafting import (
    build_prompt,
    json_schema,
    json_schema_with_length_caps,
    parse_reply,
)
from PyCodeCommenter.description_provider import (
    DescriptionProvider,
    DocstringDraft,
    DraftingStopped,
    DraftSlots,
    FunctionContext,
    KnownText,
    ParameterFact,
    SwitchOnStop,
)
from PyCodeCommenter.direct_providers import (
    PROVIDERS,
    AnthropicProvider,
    GeminiProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    ProviderUnavailable,
    make_provider,
)

CONTEXT = FunctionContext(
    name="truncate",
    parameters=[
        ParameterFact("text", "any"),
        ParameterFact("max_length", "any"),
    ],
    return_type="str",
    is_generator=False,
    raised_exceptions=[],
    source=(
        "def truncate(text, max_length):\n"
        "    # Keep room for the ellipsis.\n"
        "    return text[:max_length] + '...'"
    ),
)
KNOWN = KnownText(returns=None)
SLOTS = DraftSlots(summary=True, params=("text", "max_length"), returns=True)
REPLY = {
    "summary": "Shorten text to a maximum length.",
    "description": None,
    "params": {"text": "The text to shorten.", "max_length": "Longest result."},
    "returns": "The shortened text.",
    "raises": {},
}


class StatusError(Exception):
    """Stands in for an SDK's HTTP error: they all expose the status code."""

    def __init__(self, status, message="error"):
        super().__init__(message)
        self.status_code = status


# ---------------------------------------------------------------------------
# Shared prompt, schema and parsing
# ---------------------------------------------------------------------------


def test_prompt_includes_source_comments_and_requested_parts():
    prompt = build_prompt(CONTEXT, KNOWN, SLOTS)

    assert "# Keep room for the ellipsis." in prompt  # comments inform the draft
    assert "truncate" in prompt
    assert "params text, max_length" in prompt
    assert "JSON" in prompt  # required by JSON-object mode providers


def test_schema_is_strict_and_covers_exactly_the_requested_parts():
    schema = json_schema(SLOTS)

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"summary", "params", "returns"}
    params = schema["properties"]["params"]
    assert params["additionalProperties"] is False
    assert set(params["required"]) == {"text", "max_length"}
    assert "maxLength" not in json.dumps(schema)


def test_length_capped_schema_adds_caps_for_providers_that_support_them():
    schema = json_schema_with_length_caps(SLOTS)

    assert schema["properties"]["summary"]["anyOf"][0]["maxLength"] == 80


@pytest.mark.parametrize("raw", ["", "not json", "[1]", '{"summary": 5}'])
def test_unusable_replies_parse_to_an_empty_draft(raw):
    draft = parse_reply(raw)

    assert draft.summary is None and draft.params == {}


def test_reply_wrapped_in_a_code_fence_still_parses():
    draft = parse_reply("```json\n" + json.dumps(REPLY) + "\n```")

    assert draft.summary == "Shorten text to a maximum length."


# ---------------------------------------------------------------------------
# Each provider's call shape
# ---------------------------------------------------------------------------


class FakeAnthropic:
    def __init__(self, reply=REPLY, stop_reason="end_turn", error=None):
        self.calls = []
        self.error = error
        text = SimpleNamespace(type="text", text=json.dumps(reply))
        self.response = SimpleNamespace(stop_reason=stop_reason, content=[text])
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_anthropic_default_is_a_small_model_without_effort_or_fallback_options():
    fake = FakeAnthropic()
    provider = AnthropicProvider(api_key="k", client=fake)

    provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    [call] = fake.calls
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert "effort" not in call["output_config"]
    assert "betas" not in call and "fallbacks" not in call


def test_anthropic_uses_structured_output_low_effort_and_refusal_fallback():
    fake = FakeAnthropic()
    provider = AnthropicProvider(api_key="k", model="claude-opus-5", client=fake)

    draft = provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    [call] = fake.calls
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert draft.summary == "Shorten text to a maximum length."


def test_anthropic_refusal_yields_an_empty_draft():
    fake = FakeAnthropic(stop_reason="refusal")

    draft = AnthropicProvider(api_key="k", client=fake).draft_docstring(
        CONTEXT, KNOWN, SLOTS
    )

    assert draft == DocstringDraft()


def test_openai_uses_strict_json_schema_on_the_responses_api():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(REPLY))

    fake = SimpleNamespace(responses=SimpleNamespace(create=create))
    draft = OpenAIProvider(api_key="k", client=fake).draft_docstring(
        CONTEXT, KNOWN, SLOTS
    )

    [call] = calls
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    assert draft.returns == "The shortened text."


def test_openai_compatible_uses_json_object_mode_on_chat_completions():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=json.dumps(REPLY))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    provider = OpenAICompatibleProvider(
        api_key="k",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        client=fake,
    )

    draft = provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    [call] = calls
    assert call["model"] == "deepseek-flash"
    assert call["response_format"] == {"type": "json_object"}
    assert draft.params["text"] == "The text to shorten."


def test_gemini_asks_for_json_with_length_capped_schema():
    calls = []

    def generate_content(model, contents, config):
        calls.append((model, contents, config))
        return SimpleNamespace(text=json.dumps(REPLY))

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    draft = GeminiProvider(api_key="k", client=fake).draft_docstring(
        CONTEXT, KNOWN, SLOTS
    )

    [(model, _, config)] = calls
    assert config["response_mime_type"] == "application/json"
    assert "maxLength" in json.dumps(config["response_json_schema"])
    assert draft.summary == "Shorten text to a maximum length."


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, reason",
    [(401, "invalid_api_key"), (403, "invalid_api_key"), (429, "rate_limited")],
)
def test_key_and_quota_errors_stop_drafting_for_the_run(status, reason):
    fake = FakeAnthropic(error=StatusError(status))
    provider = AnthropicProvider(api_key="k", client=fake)

    with pytest.raises(DraftingStopped) as stopped:
        provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert stopped.value.reason == reason
    assert "Anthropic" in stopped.value.message


def test_gemini_invalid_key_400_stops_drafting():
    def generate_content(model, contents, config):
        error = Exception("400 INVALID_ARGUMENT API_KEY_INVALID")
        error.code = 400
        raise error

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))

    with pytest.raises(DraftingStopped) as stopped:
        GeminiProvider(api_key="k", client=fake).draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert stopped.value.reason == "invalid_api_key"


def test_other_errors_skip_only_that_function():
    fake = FakeAnthropic(error=StatusError(500))

    draft = AnthropicProvider(api_key="k", client=fake).draft_docstring(
        CONTEXT, KNOWN, SLOTS
    )

    assert draft == DocstringDraft()


# ---------------------------------------------------------------------------
# Choosing a provider
# ---------------------------------------------------------------------------


def test_every_provider_documents_its_key_variable_and_default_model():
    for name, spec in PROVIDERS.items():
        assert spec.env_var, name
        assert spec.label, name
        if name != "openai-compatible":
            assert spec.default_model, name


def test_make_provider_uses_the_default_model_unless_overridden():
    fake = FakeAnthropic()

    default = make_provider("anthropic", api_key="k", client=fake)
    chosen = make_provider("anthropic", api_key="k", model="claude-opus-5", client=fake)

    assert default.model == "claude-haiku-4-5-20251001"
    assert chosen.model == "claude-opus-5"


def test_openai_compatible_requires_a_model_and_base_url():
    with pytest.raises(ValueError, match="--ai-model"):
        make_provider(
            "openai-compatible", api_key="k", base_url="http://x", client=object()
        )
    with pytest.raises(ValueError, match="--ai-base-url"):
        make_provider("openai-compatible", api_key="k", model="m", client=object())


def test_missing_sdk_names_the_extra_to_install(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_anthropic)

    with pytest.raises(ProviderUnavailable, match=r"pycodecommenter\[anthropic\]"):
        make_provider("anthropic", api_key="k")


# ---------------------------------------------------------------------------
# Limit reached: switch to the user's own key mid-run
# ---------------------------------------------------------------------------


class Scripted(DescriptionProvider):
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def draft_docstring(self, context, known, slots):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_switch_on_stop_continues_with_the_replacement_for_the_same_function():
    stopped = DraftingStopped("user_daily_limit_reached", "Used up.")
    replacement = Scripted(DocstringDraft(summary="From my key."))
    offered = []

    def offer(reason):
        offered.append(reason.reason)
        return replacement

    provider = SwitchOnStop(Scripted(stopped), offer)

    first = provider.draft_docstring(CONTEXT, KNOWN, SLOTS)
    second = provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert first.summary == second.summary == "From my key."
    assert offered == ["user_daily_limit_reached"]  # asked once, not per function
    assert replacement.calls == 2


def test_switch_on_stop_declined_stops_the_run():
    stopped = DraftingStopped("user_daily_limit_reached", "Used up.")
    provider = SwitchOnStop(Scripted(stopped), lambda reason: None)

    with pytest.raises(DraftingStopped):
        provider.draft_docstring(CONTEXT, KNOWN, SLOTS)


# ---------------------------------------------------------------------------
# Consent per destination
# ---------------------------------------------------------------------------


@pytest.fixture
def consent_home(tmp_path, monkeypatch):
    import PyCodeCommenter.consent as consent

    monkeypatch.setattr(consent.Path, "home", staticmethod(lambda: tmp_path))
    return consent


def test_consent_is_recorded_per_destination(consent_home):
    consent_home.record_consent("openai")

    assert consent_home.has_given_consent("openai")
    assert not consent_home.has_given_consent("anthropic")
    assert not consent_home.has_given_consent()  # hosted is separate


def test_recording_one_destination_keeps_the_others(consent_home):
    consent_home.record_consent()
    consent_home.record_consent("gemini")

    assert consent_home.has_given_consent()
    assert consent_home.has_given_consent("gemini")


def test_direct_notice_names_the_provider_not_the_hosted_service(consent_home):
    notice = consent_home.notice_for("anthropic")

    assert "Anthropic" in notice
    assert "your API key" in notice
    assert "hosted service" not in notice


# ---------------------------------------------------------------------------
# Class docstrings
# ---------------------------------------------------------------------------

from PyCodeCommenter.ai_drafting import build_class_prompt  # noqa: E402
from PyCodeCommenter.description_provider import (  # noqa: E402
    ClassContext,
    ClassDraft,
    ClassSlots,
)

CLASS_CONTEXT = ClassContext(
    name="Cache",
    bases=["Base"],
    attributes=[ParameterFact("_items", "dict"), ParameterFact("ttl", "int")],
    source=(
        "class Cache(Base):\n"
        "    def __init__(self, ttl: int):\n"
        "        # Entries older than ttl seconds are dropped.\n"
        "        self.ttl = ttl\n"
        "        self._items = {}"
    ),
)
CLASS_SLOTS = ClassSlots(summary=True, attributes=("_items", "ttl"))
CLASS_REPLY = {
    "summary": "Keep recent results for a limited time.",
    "params": {
        "_items": "Cached values by key.",
        "ttl": "Seconds an entry stays valid.",
    },
}


def test_class_prompt_names_the_class_its_attributes_and_the_requested_parts():
    prompt = build_class_prompt(CLASS_CONTEXT, {"a": "Known."}, CLASS_SLOTS)

    assert "class named `Cache`" in prompt
    assert "Base" in prompt
    assert "_items: dict" in prompt and "ttl: int" in prompt
    assert "# Entries older than ttl seconds are dropped." in prompt
    assert "a`: Known." in prompt or "`a`" in prompt
    assert "attributes _items, ttl" in prompt
    assert "JSON" in prompt


def test_class_draft_maps_the_reply_onto_summary_and_attributes():
    fake = FakeAnthropic(reply=CLASS_REPLY)
    provider = AnthropicProvider(api_key="k", client=fake)

    draft = provider.draft_class_docstring(CLASS_CONTEXT, {}, CLASS_SLOTS)

    assert draft == ClassDraft(
        summary="Keep recent results for a limited time.",
        attributes={
            "_items": "Cached values by key.",
            "ttl": "Seconds an entry stays valid.",
        },
    )
    [call] = fake.calls
    schema = call["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"summary", "params"}
    assert set(schema["properties"]["params"]["required"]) == {"_items", "ttl"}


def test_class_draft_of_an_unusable_reply_is_empty():
    fake = FakeAnthropic(reply="not a json object")
    fake.response.content[0].text = "not json"
    provider = AnthropicProvider(api_key="k", client=fake)

    assert (
        provider.draft_class_docstring(CLASS_CONTEXT, {}, CLASS_SLOTS) == ClassDraft()
    )


def test_class_draft_stops_the_run_when_the_key_is_rejected():
    provider = AnthropicProvider(
        api_key="k", client=FakeAnthropic(error=StatusError(401))
    )

    with pytest.raises(DraftingStopped):
        provider.draft_class_docstring(CLASS_CONTEXT, {}, CLASS_SLOTS)


def test_class_draft_survives_an_ordinary_failure_as_an_empty_draft():
    provider = AnthropicProvider(
        api_key="k", client=FakeAnthropic(error=StatusError(500))
    )

    assert (
        provider.draft_class_docstring(CLASS_CONTEXT, {}, CLASS_SLOTS) == ClassDraft()
    )


def test_switch_on_stop_hands_class_drafting_to_the_replacement():
    class Stopped(DescriptionProvider):
        def draft_class_docstring(self, context, known, slots):
            raise DraftingStopped("limit", "Daily limit reached.")

    class Replacement(DescriptionProvider):
        def draft_class_docstring(self, context, known, slots):
            return ClassDraft(summary="From the replacement.")

    provider = SwitchOnStop(Stopped(), lambda stopped: Replacement())

    draft = provider.draft_class_docstring(CLASS_CONTEXT, {}, CLASS_SLOTS)

    assert draft.summary == "From the replacement."
    assert isinstance(provider.active, Replacement)


# ---------------------------------------------------------------------------
# A rate limit is waited out once before the run gives up
# ---------------------------------------------------------------------------


class RateLimited(Exception):
    """An SDK 429, optionally carrying the response's Retry-After."""

    def __init__(self, retry_after=None):
        super().__init__("rate limited")
        self.status_code = 429
        headers = {} if retry_after is None else {"retry-after": str(retry_after)}
        self.response = SimpleNamespace(headers=headers)


class ScriptedAnthropic(FakeAnthropic):
    """Raises each queued error in turn, then answers normally."""

    def __init__(self, errors):
        super().__init__()
        self.errors = list(errors)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        return self.response


@pytest.fixture
def waits(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "PyCodeCommenter.direct_providers._wait",
        lambda seconds: recorded.append(seconds),
    )
    return recorded


def test_one_rate_limit_is_waited_out_and_the_request_retried(waits):
    fake = ScriptedAnthropic([RateLimited(retry_after=7)])
    provider = AnthropicProvider(api_key="k", client=fake)

    draft = provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert waits == [7]
    assert len(fake.calls) == 2
    assert draft.summary == "Shorten text to a maximum length."


def test_a_second_rate_limit_stops_the_run_after_a_single_wait(waits):
    fake = ScriptedAnthropic([RateLimited(retry_after=3), RateLimited(retry_after=3)])
    provider = AnthropicProvider(api_key="k", client=fake)

    with pytest.raises(DraftingStopped) as stopped:
        provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert stopped.value.reason == "rate_limited"
    assert waits == [3]


def test_a_missing_retry_after_uses_a_default_wait(waits):
    provider = AnthropicProvider(api_key="k", client=ScriptedAnthropic([RateLimited()]))

    provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert waits == [20]


@pytest.mark.parametrize("header, expected", [("3600", 60), ("0", 1), ("soon", 20)])
def test_the_wait_is_kept_within_sensible_bounds(waits, header, expected):
    provider = AnthropicProvider(
        api_key="k", client=ScriptedAnthropic([RateLimited(retry_after=header)])
    )

    provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert waits == [expected]


def test_the_wait_is_reported_before_it_starts(waits):
    seen = []
    provider = AnthropicProvider(
        api_key="k", client=ScriptedAnthropic([RateLimited(retry_after=9)])
    )
    provider.on_wait = seen.append

    provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert seen == [9]


def test_other_errors_never_wait(waits):
    provider = AnthropicProvider(
        api_key="k", client=ScriptedAnthropic([StatusError(500)])
    )

    provider.draft_docstring(CONTEXT, KNOWN, SLOTS)

    assert waits == []


def test_class_drafting_waits_out_a_rate_limit_too(waits):
    fake = ScriptedAnthropic([RateLimited(retry_after=4)])
    fake.response.content[0].text = json.dumps(CLASS_REPLY)
    provider = AnthropicProvider(api_key="k", client=fake)

    draft = provider.draft_class_docstring(CLASS_CONTEXT, {}, CLASS_SLOTS)

    assert waits == [4]
    assert draft.summary == "Keep recent results for a limited time."
