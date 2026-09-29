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

import importlib.util
import logging
import shlex
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

try:
    from .ai_drafting import (
        build_class_prompt,
        build_prompt,
        json_schema,
        json_schema_with_length_caps,
        parse_reply,
    )
    from .description_provider import (
        ClassContext,
        ClassDraft,
        ClassSlots,
        DescriptionProvider,
        DocstringDraft,
        DraftingStopped,
        DraftSlots,
        FunctionContext,
        KnownText,
    )
except (ImportError, ValueError):
    from ai_drafting import (
        build_class_prompt,
        build_prompt,
        json_schema,
        json_schema_with_length_caps,
        parse_reply,
    )
    from description_provider import (
        ClassContext,
        ClassDraft,
        ClassSlots,
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
    """A provider can't be used as configured.

    Raised when its SDK isn't installed or a required setting is missing. The
    message says how to fix it.
    """


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


# Default models. Model names change often, so a default is only a starting
# point: users can always choose another with --ai-model. Gemini also has a
# fallback chain (see GEMINI_FALLBACK_MODELS) that is used only when the user
# did not choose a model.
PROVIDERS = {
    "gemini": ProviderSpec("Gemini", "GEMINI_API_KEY", "gemini-3.8-flash", "gemini"),
    "openai": ProviderSpec("OpenAI", "OPENAI_API_KEY", "gpt-6-astra", "openai"),
    "anthropic": ProviderSpec(
        "Anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-5-5", "anthropic"
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


# Tried in order when the default Gemini model is unavailable to the key (for
# example Google limits access to an older model, or a new one is overloaded
# after the SDK's own retries). The 2.5 model comes last: Google restricts it
# to keys that have used it before, so it is a last resort, not a first choice.
GEMINI_FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash")

# HTTP statuses that mean "this model can't serve the request", as opposed to
# a bad key (401/403/400 invalid key) or a rate limit (429), which are
# handled elsewhere.
_MODEL_UNAVAILABLE_STATUSES = frozenset({404, 500, 502, 503, 504})

# The module each pip extra installs; its presence means the SDK is there.
_SDK_MODULES = {
    "gemini": "google.genai",
    "openai": "openai",
    "anthropic": "anthropic",
}


def sdk_installed(name: str) -> bool:
    """Say whether a provider's SDK can be imported here, without importing it.

    Args:
        name (str): A key of :data:`PROVIDERS`.

    Returns:
        bool: ``True`` if the SDK is installed.
    """
    module = _SDK_MODULES[PROVIDERS[name].extra]
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        # find_spec raises when a parent package ("google") is missing.
        return False


def install_command(name: str) -> str:
    """Give the command that installs a provider's SDK into this Python.

    The tool prints the command for the user to copy; it never runs it.

    Args:
        name (str): A key of :data:`PROVIDERS`.

    Returns:
        str: For example ``/path/to/python -m pip install
        "pycodecommenter[gemini]"``.
    """
    extra = PROVIDERS[name].extra
    return f'{shlex.quote(sys.executable)} -m pip install "pycodecommenter[{extra}]"'


def make_provider(
    name: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Any = None,
) -> "DirectProvider":
    """Build a provider by name.

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
        ValueError: If no model is known for the provider, or an
            OpenAI-compatible provider has no endpoint.
        ProviderUnavailable: If the provider's SDK isn't installed and no
            ``client`` was given.
    """
    spec = PROVIDERS[name]
    chosen_model = model or spec.default_model
    if not chosen_model:
        raise ValueError(f"The {spec.label} provider needs a model: pass --ai-model.")
    if name == "gemini":
        # Pass the user's own choice, not the default: only an unchosen model
        # gets the fallback chain.
        return GeminiProvider(api_key, model, client)
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
    """Shared request and response handling; subclasses make the actual call.

    Subclasses set the class attributes below and implement
    :meth:`_create_client` and :meth:`_complete`.

    Attributes:
        label (str): The provider's name, for messages.
        env_var (str): The environment variable holding the API key.
        extra (str): The pip extra that installs the provider's SDK.
        provider_name (str): The :data:`PROVIDERS` entry whose default model
            applies when none is given.
        on_wait (Optional[Callable[[float], None]]): Told the seconds about to
            be waited out for a rate limit, so the wait can be shown. Set by
            whoever runs the provider (see ``ai_setup``).
        model (Optional[str]): The model every request uses.
        _client (Any): The SDK client requests go through.
    """

    label = "AI provider"
    env_var = ""
    extra = ""
    # The PROVIDERS entry whose default model applies when none is given.
    provider_name = ""
    # Told the seconds about to be waited out for a rate limit, so the wait
    # can be shown; set by whoever runs the provider (see ai_setup).
    on_wait: Optional[Callable[[float], None]] = None

    def __init__(self, api_key: str, model: Optional[str] = None, client: Any = None):
        """Create the provider and its SDK client.

        Args:
            api_key (str): The user's API key.
            model (Optional[str]): The model to use; the provider's default when
                omitted.
            client (Any): A ready-made SDK client, for tests. When omitted the
                provider creates its own.

        Raises:
            ProviderUnavailable: If the SDK isn't installed and no ``client``
                was given.
        """
        self.model = model or PROVIDERS[self.provider_name].default_model
        self._client = client if client is not None else self._create_client(api_key)

    def draft_docstring(
        self, context: FunctionContext, known: KnownText, slots: DraftSlots
    ) -> DocstringDraft:
        """Draft the requested parts of a function docstring with one call.

        Args:
            context (FunctionContext): The function's source and facts.
            known (KnownText): Text already settled, sent as context.
            slots (DraftSlots): Which parts to draft.

        Returns:
            DocstringDraft: The drafted parts. ``failed`` is set if the request
            failed for this function.

        Raises:
            DraftingStopped: The key was rejected or its quota is exhausted.
        """
        return self._draft(build_prompt(context, known, slots), slots, context.name)

    def draft_class_docstring(
        self, context: ClassContext, known: Dict[str, str], slots: ClassSlots
    ) -> ClassDraft:
        """Draft a class's summary and attributes with one call.

        The attributes travel as the reply's ``params``, so the function schema
        and parser are reused.

        Args:
            context (ClassContext): The class outline and facts.
            known (Dict[str, str]): Text already settled, sent as context.
            slots (ClassSlots): Which parts to draft.

        Returns:
            ClassDraft: The drafted parts. ``failed`` is set if the request
            failed for this class.

        Raises:
            DraftingStopped: The key was rejected or its quota is exhausted.
        """
        as_function = DraftSlots(summary=slots.summary, params=slots.attributes)
        draft = self._draft(
            build_class_prompt(context, known, slots), as_function, context.name
        )
        return ClassDraft(
            summary=draft.summary, attributes=draft.params, failed=draft.failed
        )

    def _draft(self, prompt: str, slots: DraftSlots, name: str) -> DocstringDraft:
        """Send a prompt and parse the reply, with one retry after a rate limit.

        A 429 is waited out and tried once more. An error that should end the run
        raises; any other error is logged and gives a draft marked ``failed``, so
        that one function keeps its gaps.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the reply should contain.
            name (str): The function or class name, for the log message.

        Returns:
            DocstringDraft: The parsed reply, or a failed draft.

        Raises:
            DraftingStopped: If the key is rejected or the quota is spent.
        """
        for attempt in range(2):
            try:
                return parse_reply(self._complete(prompt, slots))
            except Exception as e:
                if attempt == 0 and _status_of(e) == 429:
                    self._wait_out_rate_limit(e)
                    continue
                self._raise_if_run_should_stop(e)
                logger.warning(f"{self.label} request failed for {name}: {e}")
                return DocstringDraft(failed=True)
        return DocstringDraft(failed=True)

    def _wait_out_rate_limit(self, error: Exception) -> None:
        """Wait once for a 429 to clear before the run is given up on.

        A per-minute limit usually clears; a spent quota fails again and stops
        the run through :meth:`_raise_if_run_should_stop`.

        Args:
            error (Exception): The rate-limit error, read for its Retry-After.
        """
        seconds = _retry_after_seconds(error)
        if self.on_wait is not None:
            self.on_wait(seconds)
        _wait(seconds)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        """Make the provider call and return the reply text.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the reply should contain.

        Returns:
            str: The model's reply, expected to be JSON.

        Raises:
            NotImplementedError: Always; subclasses override it.
        """
        raise NotImplementedError

    def _create_client(self, api_key: str) -> Any:
        """Create the provider's SDK client.

        Args:
            api_key (str): The user's API key.

        Returns:
            Any: The SDK client.

        Raises:
            NotImplementedError: Always; subclasses override it.
        """
        raise NotImplementedError

    def _missing_sdk(self) -> ProviderUnavailable:
        """Build the error that says how to install this provider's SDK.

        Returns:
            ProviderUnavailable: The error, ready to raise.
        """
        return ProviderUnavailable(
            f"The {self.label} provider needs its SDK: "
            f'pip install "pycodecommenter[{self.extra}]"'
        )

    def _raise_if_run_should_stop(self, error: Exception) -> None:
        """Stop the run for an error that will not fix itself.

        A rejected key or exhausted quota would fail for every function, so it
        stops drafting instead of failing once per function. Any other error
        returns normally.

        Args:
            error (Exception): The error the provider call raised.

        Raises:
            DraftingStopped: For HTTP 401 or 403, a 400 reporting an invalid Gemini
                key, or a 429.
        """
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
    """Claude, through the official ``anthropic`` SDK.

    Requests use structured JSON output. Models that accept it are asked for
    low reasoning effort, and Opus 5 models are sent with the server-side
    refusal fallback.
    """

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
        """Create an ``anthropic.Anthropic`` client.

        Args:
            api_key (str): The user's Anthropic API key.

        Returns:
            Any: The SDK client.

        Raises:
            ProviderUnavailable: If the ``anthropic`` SDK isn't installed.
        """
        try:
            import anthropic
        except ImportError:
            raise self._missing_sdk()
        return anthropic.Anthropic(api_key=api_key)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        """Ask for a structured JSON reply through the Messages API.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the JSON schema should require.

        Returns:
            str: The first text block of the reply, or an empty string when the
            model refused or returned no text.
        """
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
        """Create an ``openai.OpenAI`` client.

        Args:
            api_key (str): The user's OpenAI API key.

        Returns:
            Any: The SDK client.

        Raises:
            ProviderUnavailable: If the ``openai`` SDK isn't installed.
        """
        try:
            import openai
        except ImportError:
            raise self._missing_sdk()
        return openai.OpenAI(api_key=api_key)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        """Ask for a strict JSON-schema reply through the Responses API.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the JSON schema should require.

        Returns:
            str: The reply text, or an empty string if there is none.
        """
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
    """Any API that follows OpenAI's Chat Completions format, through ``openai``.

    That covers DeepSeek, Mistral, Groq, a local Ollama server and similar.
    It uses JSON-object mode, which such APIs support more widely than strict
    JSON Schema; the expected keys are spelled out in the prompt instead.

    Attributes:
        label (str): The provider's name, for messages.
        env_var (str): The environment variable holding the API key.
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
        """Create the provider for one endpoint.

        Args:
            api_key (str): The user's API key for the endpoint.
            model (str): The model to use.
            base_url (str): The endpoint's base URL.
            client (Any): A ready-made SDK client, for tests.
            label (str): The provider's name, for messages.
            env_var (str): The environment variable holding the key, named in the
                "key rejected" message.

        Raises:
            ProviderUnavailable: If the ``openai`` SDK isn't installed and no
                ``client`` was given.
        """
        self.label = label
        self.env_var = env_var
        self._base_url = base_url
        super().__init__(api_key, model, client)

    def _create_client(self, api_key: str) -> Any:
        """Create an ``openai.OpenAI`` client pointed at the configured endpoint.

        Args:
            api_key (str): The user's API key for the endpoint.

        Returns:
            Any: The SDK client.

        Raises:
            ProviderUnavailable: If the ``openai`` SDK isn't installed.
        """
        try:
            import openai
        except ImportError:
            raise self._missing_sdk()
        return openai.OpenAI(api_key=api_key, base_url=self._base_url)

    def _complete(self, prompt: str, slots: DraftSlots) -> str:
        """Ask for a JSON-object reply through Chat Completions.

        The schema is appended to the prompt as text, since JSON-object mode does
        not enforce one.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the schema should require.

        Returns:
            str: The message content, or an empty string if there is none.
        """
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
    """Gemini, through the official ``google-genai`` SDK.

    When no model is chosen, the default is tried first and, if Google says
    it can't serve the request, the models in ``GEMINI_FALLBACK_MODELS`` in
    turn. A model the user chose is never swapped for another.
    """

    provider_name = "gemini"

    label = "Gemini"
    env_var = "GEMINI_API_KEY"
    extra = "gemini"

    def __init__(self, api_key: str, model: Optional[str] = None, client: Any = None):
        """Create the provider, with a fallback chain if no model is chosen.

        Args:
            api_key (str): The user's Gemini API key.
            model (Optional[str]): The model to use. When omitted, the default
                is used and the fallback models stand ready behind it.
            client (Any): A ready-made SDK client, for tests.

        Raises:
            ProviderUnavailable: If the SDK isn't installed and no ``client``
                was given.
        """
        super().__init__(api_key, model, client)
        self._fallback_models = list(GEMINI_FALLBACK_MODELS) if model is None else []

    def _create_client(self, api_key: str) -> Any:
        """Create a ``genai.Client`` that retries transient server errors.

        Args:
            api_key (str): The user's Gemini API key.

        Returns:
            Any: The SDK client.

        Raises:
            ProviderUnavailable: If the ``google-genai`` SDK isn't installed.
        """
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
        """Ask for a JSON reply, moving to a fallback model if need be.

        A model that can't serve the request (not found or no access, or still
        failing after the SDK's retries) is replaced, for the rest of the run,
        by the next fallback model. Any other error is raised as it is.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the schema should require.

        Returns:
            str: The reply text, or an empty string if there is none.
        """
        while True:
            try:
                return self._generate(prompt, slots)
            except Exception as error:
                if (
                    not self._fallback_models
                    or _status_of(error) not in _MODEL_UNAVAILABLE_STATUSES
                ):
                    raise
                following = self._fallback_models.pop(0)
                logger.warning(
                    f"Gemini model {self.model} is unavailable ({error}); "
                    f"trying {following}"
                )
                self.model = following

    def _generate(self, prompt: str, slots: DraftSlots) -> str:
        """Make one Gemini call with the current model.

        Args:
            prompt (str): The full prompt.
            slots (DraftSlots): Which parts the schema should require.

        Returns:
            str: The reply text, or an empty string if there is none.
        """
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


# How long a rate limit is waited out once: the server's Retry-After when it
# gives one, kept within these bounds.
_DEFAULT_RATE_LIMIT_WAIT_S = 20
_MAX_RATE_LIMIT_WAIT_S = 60


def _wait(seconds: float) -> None:
    """Sleep for a number of seconds.

    Kept as its own function so tests can replace it.

    Args:
        seconds (float): How long to sleep.
    """
    time.sleep(seconds)


def _retry_after_seconds(error: Exception) -> int:
    """Read how long to wait from an SDK error's ``Retry-After`` header.

    Args:
        error (Exception): The rate-limit error.

    Returns:
        int: The header value limited to 1-60 seconds, or a default of 20
        when the error carries no usable header (google-genai errors carry
        none).
    """
    headers = getattr(getattr(error, "response", None), "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_RATE_LIMIT_WAIT_S
    return max(1, min(seconds, _MAX_RATE_LIMIT_WAIT_S))


def _status_of(error: Exception) -> Optional[int]:
    """Read the HTTP status from an SDK error.

    Args:
        error (Exception): The error raised by an SDK call.

    Returns:
        Optional[int]: ``status_code`` on the Anthropic and OpenAI SDKs,
        ``code`` on google-genai, or ``None`` if the error has neither.
    """
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
