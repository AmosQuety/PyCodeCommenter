"""Setting up AI drafting for the CLI: which provider, which key, consent,
and what to tell the user before and after the run.

Keys are read from each provider's own environment variable, or asked for
(hidden) when running interactively -- never read from or written to a
project file, where they would end up in version control.
"""

import getpass
import os
import sys
from typing import Optional

try:
    from .consent import HOSTED, ensure_consent
    from .description_provider import (
        DescriptionProvider,
        DraftingStopped,
        SwitchOnStop,
    )
    from .direct_providers import PROVIDERS, ProviderUnavailable, make_provider
    from .remote_provider import DEFAULT_BACKEND_URL, RemoteDescriptionProvider
except ImportError:
    from consent import HOSTED, ensure_consent
    from description_provider import DescriptionProvider, DraftingStopped, SwitchOnStop
    from direct_providers import PROVIDERS, ProviderUnavailable, make_provider
    from remote_provider import DEFAULT_BACKEND_URL, RemoteDescriptionProvider

AI_PROVIDER_CHOICES = [HOSTED] + list(PROVIDERS)


class AISetupError(Exception):
    """AI drafting can't start as configured; the message says why and how
    to fix it."""


def status(*args, **kwargs) -> None:
    """Prints a status message or prompt to stderr. Stdout may be carrying
    the patched code (``generate`` with no output flag), and a prompt there
    would be invisible once redirected, leaving the run waiting silently."""
    print(*args, file=sys.stderr, **kwargs)


def is_interactive() -> bool:
    """Whether a person is at the terminal to answer questions."""
    return sys.stdin.isatty()


def build_ai_provider(
    provider_name: str,
    model: Optional[str],
    base_url: Optional[str],
    backend_url: str = DEFAULT_BACKEND_URL,
    assume_consent: bool = False,
) -> SwitchOnStop:
    """Builds the provider for a run and tells the user which one it is.

    With the hosted service, running out of free drafts mid-run offers to
    continue with the user's own key (interactive runs only).

    Args:
        provider_name (str): ``"hosted"`` or a key of ``PROVIDERS``.
        model (Optional[str]): Overrides the provider's default model.
        base_url (Optional[str]): API endpoint for ``openai-compatible``.
        backend_url (str): The hosted service's address.
        assume_consent (bool): Record consent without asking (CI use).

    Returns:
        SwitchOnStop: The provider, wrapped for the limit-reached hand-off.

    Raises:
        AISetupError: Consent was declined, no key is available, or the
            provider can't be used as configured.
    """
    if provider_name == HOSTED:
        _require_consent(HOSTED, assume_consent)
        status(
            "AI drafting: PyCodeCommenter's hosted service (free, with a daily "
            "limit). To use your own key instead, pass --ai-provider "
            f"{{{','.join(PROVIDERS)}}}."
        )
        on_stop = offer_own_key if is_interactive() else _no_replacement
        return SwitchOnStop(RemoteDescriptionProvider(backend_url=backend_url), on_stop)

    provider = direct_provider(provider_name, model, base_url, assume_consent)
    return SwitchOnStop(provider, _no_replacement)


def direct_provider(
    provider_name: str,
    model: Optional[str],
    base_url: Optional[str],
    assume_consent: bool = False,
) -> DescriptionProvider:
    """Builds a provider that uses the user's own key.

    Args:
        provider_name (str): A key of ``PROVIDERS``.
        model (Optional[str]): Overrides the provider's default model.
        base_url (Optional[str]): API endpoint for ``openai-compatible``.
        assume_consent (bool): Record consent without asking (CI use).

    Returns:
        DescriptionProvider: The provider.

    Raises:
        AISetupError: Consent was declined, no key is available, or the
            provider can't be used as configured.
    """
    spec = PROVIDERS[provider_name]
    _require_consent(provider_name, assume_consent)
    api_key = _api_key_for(provider_name)
    try:
        provider = make_provider(provider_name, api_key, model=model, base_url=base_url)
    except (ValueError, ProviderUnavailable) as e:
        raise AISetupError(str(e)) from e
    status(
        f"AI drafting: {spec.label}, model {provider.model} "
        "(choose another with --ai-model)."
    )
    return provider


def offer_own_key(stopped: DraftingStopped) -> Optional[DescriptionProvider]:
    """Asks whether to continue with the user's own key after the hosted
    service stops, and builds that provider if so.

    Args:
        stopped (DraftingStopped): Why the hosted service stopped.

    Returns:
        Optional[DescriptionProvider]: The replacement, or ``None`` to stop
            drafting (the remaining gaps stay as TODO markers).
    """
    status(f"\n{stopped.message}")
    choice = _ask(
        "Continue with your own API key? Provider " f"[{'/'.join(PROVIDERS)}/skip]: "
    ).lower()
    if choice not in PROVIDERS:
        return None
    model = None
    if PROVIDERS[choice].default_model is None:
        model = _ask("Model name: ") or None
    base_url = None
    if choice == "openai-compatible":
        base_url = _ask("API base URL: ") or None
    try:
        return direct_provider(choice, model, base_url)
    except AISetupError as e:
        status(f"Can't continue with {PROVIDERS[choice].label}: {e}")
        return None


def report_ai_outcome(provider: SwitchOnStop) -> None:
    """Tells the user how drafting ended: the hosted allowance left, or why
    drafting stopped and how to carry on.

    Args:
        provider (SwitchOnStop): The run's provider.
    """
    stopped = provider.stopped
    active = provider.active
    if stopped is not None:
        status(f"\nAI drafting stopped: {stopped.message}")
        status("Functions after that point keep their TODO markers.")
        if isinstance(active, RemoteDescriptionProvider):
            status(
                "To keep going now, use your own key: --ai-provider gemini "
                "(reads GEMINI_API_KEY), or openai / anthropic / deepseek."
            )
        return
    if (
        isinstance(active, RemoteDescriptionProvider)
        and active.drafts_remaining is not None
    ):
        status(
            f"\nHosted AI drafts left today: {active.drafts_remaining} of "
            f"{active.drafts_limit}."
        )


def _require_consent(destination: str, assume_consent: bool) -> None:
    if not ensure_consent(assume_yes=assume_consent, destination=destination):
        raise AISetupError(
            "AI drafting needs your consent to send source code. " "No code was sent."
        )


def _api_key_for(provider_name: str) -> str:
    """The provider's key from its environment variable, or asked for."""
    spec = PROVIDERS[provider_name]
    key = os.environ.get(spec.env_var, "").strip()
    if key:
        return key
    if is_interactive():
        key = getpass.getpass(f"{spec.label} API key (input hidden): ").strip()
        if key:
            return key
    raise AISetupError(
        f"No {spec.label} API key. Set the {spec.env_var} environment variable."
    )


def _ask(question: str) -> str:
    status(question, end="")
    return input().strip()


def _no_replacement(stopped: DraftingStopped) -> None:
    return None


__all__ = [
    "AI_PROVIDER_CHOICES",
    "AISetupError",
    "build_ai_provider",
    "direct_provider",
    "offer_own_key",
    "report_ai_outcome",
]
