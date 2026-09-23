"""AI providers called directly with the user's own API key.

The hosted service needs no key but has a daily allowance; these let a user
keep drafting with their own Gemini, OpenAI, Anthropic, DeepSeek, or any
OpenAI-compatible key. Each uses the provider's official Python SDK,
installed as an optional extra (``pip install "pycodecommenter[openai]"``),
so the default install stays free of AI dependencies. The SDK is imported
only when its provider is chosen.

Every provider fails closed like the rest of the drafting path: a rejected
key or exhausted quota stops drafting for the run (``DraftingStopped``);
any other error leaves that one function's gaps as they are.
"""

import logging
import sys
from dataclasses import dataclass
from typing import Any, Optional

try:
    from .ai_drafting import (
        build_prompt,
        json_schema,
        json_schema_with_length_caps,
        parse_reply,
    )
    from .description_provider import (
        DescriptionProvider,
        DocstringDraft,
        DraftingStopped,
        DraftSlots,
        FunctionContext,
        KnownText,
    )
except (ImportError, ValueError):
    from ai_drafting import (
        build_prompt,
        json_schema,
        json_schema_with_length_caps,
        parse_reply,
    )
    from description_provider import (
        DescriptionProvider,
        DocstringDraft,
        DraftingStopped,
        DraftSlots,
        FunctionContext,
        KnownText,
    )

logger = logging.getLogger(__name__)

# Enough for a handful of one-sentence parts, with room for a model that
# thinks before answering.
_MAX_OUTPUT_TOKENS = 4096


class ProviderUnavailable(Exception):
    """A provider can't be used as configured (its SDK isn't installed, or a
    required setting is missing). The message says how to fix it."""


@dataclass(frozen=True)
class ProviderSpec:
    """How to use one provider.

    Attributes:
        label (str): The provider's name, for messages.
        env_var (str): The environment variable holding the API key.
        default_model (Optional[str]): Used unless ``--ai-model`` overrides
            it; ``None`` where there's no sensible default.
        extra (str): The pip extra that installs the provider's SDK.
        base_url (Optional[str]): The API endpoint, for OpenAI-compatible
            providers other than OpenAI itself.
    """

    label: str
    env_var: str
    default_model: Optional[str]
    extra: str
    base_url: Optional[str] = None


# Default models were chosen for reliability on short structured replies,
# not recency: in live testing (2026-09) gemini-3.8-flash was repeatedly
# overloaded while gemini-2.5-flash answered every request. Users can
# always choose another with --ai-model.
PROVIDERS = {
    "gemini": ProviderSpec("Gemini", "GEMINI_API_KEY", "gemini-2.5-flash", "gemini"),
    "openai": ProviderSpec("OpenAI", "OPENAI_API_KEY", "gpt-6-astra", "openai"),
    "anthropic": ProviderSpec(
        "Anthropic", "ANTHROPIC_API_KEY", "claude-opus-5", "anthropic"
    ),
    "deepseek": ProviderSpec(
        "DeepSeek",
        "DEEPSEEK_API_KEY",
        "deepseek-flash",
        "openai",
        base_url="https://api.deepseek.com",
    ),
    "openai-compatible": ProviderSpec(
        "OpenAI-compatible", "OPENAI_COMPATIBLE_API_KEY", None, "openai"
    ),
}


def make_provider(
    name: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Any = None,
) -> "DirectProvider":
    """Builds a provider by name.

    Args:
        name (str): A key of :data:`PROVIDERS`.
        api_key (str): The user's API key for that provider.
        model (Optional[str]): Overrides the provider's default model.
        base_url (Optional[str]): Overrides the API endpoint (required for
            ``openai-compatible``).
        client (Any): A ready-made SDK client, for tests.

    Returns:
        DirectProvider: The provider.

    Raises:
        ValueError: A required setting is missing.
        ProviderUnavailable: The provider's SDK isn't installed.
    """
    spec = PROVIDERS[name]
    chosen_model = model or spec.default_model
    if not chosen_model:
        raise ValueError(f"The {spec.label} provider needs a model: pass --ai-model.")
    if name == "gemini":
        return GeminiProvider(api_key, chosen_model, client)
    if name == "openai":
        return OpenAIProvider(api_key, chosen_model, client)
    if name == "anthropic":
        return AnthropicProvider(api_key, chosen_model, client)
    endpoint = base_url or spec.base_url
    if not endpoint:
        raise ValueError(
            f"The {spec.label} provider needs an endpoint: pass --ai-base-url."
        )
    return OpenAICompatibleProvider(
        api_key, chosen_model, endpoint, client, label=spec.label, env_var=spec.env_var
    )


class DirectProvider(DescriptionProvider):
    """Shared request/response handling; subclasses make the actual call.

    Attributes:
        model (str): The model every request uses.
    """

    label = "AI provider"
    env_var = ""
    extra = ""
    # The PROVIDERS entry whose default model applies when none is given.
    provider_name = ""

    def __init__(self, api_key: str, model: Optional[str] = None, client: Any = None):
        self.model = model or PROVIDERS[self.provider_name].default_model
        self._client = client if client is not None else self._create_client(api_key)

    def draft_docstring(
        self, context: FunctionContext, known: KnownText, slots: DraftSlots
    ) -> DocstringDraft:
        """Drafts the requested parts with one call to the provider.

        Raises:
            DraftingStopped: The key was rejected or its quota is exhausted.
        """
        prompt = build_prompt(context, known, slots)
        try:
            return parse_reply(self._complete(prompt, slots))
        except Exception as e:
            self._raise_if_run_should_stop(e)
            logger.warning(f"{self.label} request failed for {context.name}: {e}")
            return DocstringDraft()

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        """Makes the call and returns the reply text."""
        raise NotImplementedError

    def _create_client(self, api_key: str) -> Any:
        raise NotImplementedError

    def _missing_sdk(self) -> ProviderUnavailable:
        needs_newer_python = sys.version_info < (3, 10)
        return ProviderUnavailable(
            f"The {self.label} provider needs its SDK: "
            f'pip install "pycodecommenter[{self.extra}]"'
            + (" (requires Python 3.10 or newer)" if needs_newer_python else "")
        )

    def _raise_if_run_should_stop(self, error: Exception) -> None:
        """A rejected key or exhausted quota won't fix itself mid-run, so it
        stops drafting rather than failing once per function."""
        status = _status_of(error)
        if status in (401, 403) or (status == 400 and "API_KEY_INVALID" in str(error)):
            raise DraftingStopped(
                "invalid_api_key",
                f"{self.label} rejected the API key. Check {self.env_var}.",
            ) from error
        if status == 429:
            raise DraftingStopped(
                "rate_limited",
                f"{self.label} is rate-limiting this key or its quota is used up. "
                "Try again later.",
            ) from error


class AnthropicProvider(DirectProvider):
    """Claude, through the official ``anthropic`` SDK."""

    provider_name = "anthropic"

    label = "Anthropic"
    env_var = "ANTHROPIC_API_KEY"
    extra = "anthropic"

    # `effort` is rejected by Claude Haiku 4.5 and older models; the
    # server-side refusal fallback is documented for Claude Opus 5.
    _EFFORT_MODELS = (
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
    )
    _FALLBACK_MODELS = ("claude-opus-5",)
    _FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def _create_client(self, api_key: str) -> Any:
        try:
            import anthropic
        except ImportError:
            raise self._missing_sdk()
        return anthropic.Anthropic(api_key=api_key)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        output_config: dict = {
            "format": {"type": "json_schema", "schema": json_schema(slots)}
        }
        extra: dict = {}
        if self.model.startswith(self._EFFORT_MODELS):
            # A short, grounded description is a simple task.
            output_config["effort"] = "low"
        if self.model.startswith(self._FALLBACK_MODELS):
            # Re-runs a request declined by a safety classifier on
            # Anthropic's recommended fallback model instead of failing.
            extra = {"betas": [self._FALLBACK_BETA], "fallbacks": "default"}
        response = self._client.beta.messages.create(
            model=self.model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            output_config=output_config,
            messages=[{"role": "user", "content": prompt}],
            **extra,
        )
        if response.stop_reason == "refusal":
            return ""
        return next((b.text for b in response.content if b.type == "text"), "")


class OpenAIProvider(DirectProvider):
    """OpenAI, through the official ``openai`` SDK's Responses API."""

    provider_name = "openai"

    label = "OpenAI"
    env_var = "OPENAI_API_KEY"
    extra = "openai"

    def _create_client(self, api_key: str) -> Any:
        try:
            import openai
        except ImportError:
            raise self._missing_sdk()
        return openai.OpenAI(api_key=api_key)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        response = self._client.responses.create(
            model=self.model,
            input=prompt,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "docstring_draft",
                    "strict": True,
                    "schema": json_schema(slots),
                }
            },
        )
        return response.output_text or ""


class OpenAICompatibleProvider(DirectProvider):
    """Any API that follows OpenAI's Chat Completions format (DeepSeek,
    Mistral, Groq, a local Ollama server, ...), through the ``openai`` SDK.

    Uses JSON-object mode, which such APIs support more widely than strict
    JSON Schema; the expected keys are spelled out in the prompt instead.
    """

    extra = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        client: Any = None,
        label: str = "OpenAI-compatible",
        env_var: str = "OPENAI_COMPATIBLE_API_KEY",
    ):
        self.label = label
        self.env_var = env_var
        self._base_url = base_url
        super().__init__(api_key, model, client)

    def _create_client(self, api_key: str) -> Any:
        try:
            import openai
        except ImportError:
            raise self._missing_sdk()
        return openai.OpenAI(api_key=api_key, base_url=self._base_url)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        import json

        instructions = (
            f"{prompt}\n\nReply with a JSON object matching this schema:\n"
            f"{json.dumps(json_schema(slots))}"
        )
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": instructions}],
            response_format={"type": "json_object"},
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
        return response.choices[0].message.content or ""


class GeminiProvider(DirectProvider):
    """Gemini, through the official ``google-genai`` SDK."""

    provider_name = "gemini"

    label = "Gemini"
    env_var = "GEMINI_API_KEY"
    extra = "gemini"

    def _create_client(self, api_key: str) -> Any:
        try:
            from google import genai
        except ImportError:
            raise self._missing_sdk()
        # Unlike the OpenAI and Anthropic SDKs, google-genai doesn't retry
        # transient errors by default; Gemini models are often briefly
        # overloaded (HTTP 503).
        retry = {"attempts": 3, "http_status_codes": [500, 502, 503, 504]}
        return genai.Client(api_key=api_key, http_options={"retry_options": retry})

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": json_schema_with_length_caps(slots),
                "temperature": 0.2,
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
                # No tools are passed; this also silences the SDK's warning.
                "automatic_function_calling": {"disable": True},
            },
        )
        return response.text or ""


def _status_of(error: Exception) -> Optional[int]:
    """The HTTP status of an SDK error: ``status_code`` on the Anthropic and
    OpenAI SDKs, ``code`` on google-genai."""
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


__all__ = [
    "PROVIDERS",
    "ProviderSpec",
    "ProviderUnavailable",
    "DirectProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "OpenAICompatibleProvider",
    "GeminiProvider",
    "make_provider",
]
