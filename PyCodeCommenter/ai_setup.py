"""Setting up AI drafting for the CLI: which provider, which key, consent,
and what to tell the user before and after the run.

Keys are read from each provider's own environment variable, or asked for
(hidden) when running interactively -- never read from or written to a
project file, where they would end up in version control.
"""

import getpass
import os
import sys
from typing import List, Optional

try:
    from .consent import HOSTED, ensure_consent
    from .description_provider import (
        DescriptionProvider,
        DraftingStopped,
        SwitchOnStop,
    )
    from .direct_providers import (
        PROVIDERS,
        ProviderUnavailable,
        install_command,
        make_provider,
        sdk_installed,
    )
    from .draft_limits import count_draft_requests
    from .progress import Progress
    from .remote_provider import DEFAULT_BACKEND_URL, RemoteDescriptionProvider
except ImportError:
    from consent import HOSTED, ensure_consent
    from description_provider import DescriptionProvider, DraftingStopped, SwitchOnStop
    from direct_providers import (
        PROVIDERS,
        ProviderUnavailable,
        install_command,
        make_provider,
        sdk_installed,
    )
    from draft_limits import count_draft_requests
    from progress import Progress
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
    progress: Optional[Progress] = None,
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
        progress (Optional[Progress]): The live status line. Its provider
            name is set here, rate-limit waits are shown on it, and it is
            cleared before any prompt.

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
        remote = RemoteDescriptionProvider(
            backend_url=backend_url,
            on_wait=progress.waiting if progress else None,
        )
        return _with_progress(
            SwitchOnStop(remote, _clearing(progress, on_stop)), progress
        )

    provider = direct_provider(provider_name, model, base_url, assume_consent)
    if progress is not None:
        provider.on_wait = progress.waiting
    return _with_progress(SwitchOnStop(provider, _no_replacement), progress)


def preflight(
    targets: List[str], limit: Optional[int], ask: bool, include_module_docstrings: bool
) -> bool:
    """Says how many requests an AI run over a directory would make, and
    (when asked to) whether to go ahead. Nothing is sent to find out.

    Args:
        targets (List[str]): The files the run would process.
        limit (Optional[int]): ``--max-drafts``, if given.
        ask (bool): Ask for a yes before going on (an interactive run
            that has not passed the consent flag).
        include_module_docstrings (bool): As for the real run.

    Returns:
        bool: ``True`` to go ahead, ``False`` if the user said no.
    """
    counts = count_draft_requests(targets, include_module_docstrings)
    if counts.requests == 0:
        return True
    files = f"{counts.files} file{'' if counts.files == 1 else 's'}"
    things = (
        "function or class has a gap"
        if counts.requests == 1
        else "functions and classes have gaps"
    )
    cap = (
        f"; at most {limit} will be sent (--max-drafts {limit})"
        if limit is not None and limit < counts.requests
        else ""
    )
    status(
        f"AI drafting: {files}, {counts.requests} {things} to draft "
        f"(one request each){cap}."
    )
    if not ask:
        return True
    if _ask("Continue? [y/N]: ").lower() in ("y", "yes"):
        return True
    status("Nothing was sent.")
    return False


def provider_label(provider: SwitchOnStop) -> str:
    """A short name for the provider drafting right now, for the status
    line: ``hosted``, or the vendor and model."""
    active = provider.active
    if isinstance(active, RemoteDescriptionProvider):
        return "hosted"
    label = getattr(active, "label", "")
    model = getattr(active, "model", "")
    return ", ".join(part for part in (label, model) if part)


def _with_progress(provider: SwitchOnStop, progress: Optional[Progress]):
    if progress is not None:
        progress.provider_label = lambda: provider_label(provider)
    return provider


def _clearing(progress: Optional[Progress], on_stop):
    """Wraps a hand-off so the status line is gone before it prompts."""
    if progress is None:
        return on_stop

    def clear_then_ask(stopped: DraftingStopped):
        progress.clear()
        return on_stop(stopped)

    return clear_then_ask


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
    # First, before consent or a key is asked for: a missing SDK would
    # otherwise only show up after the user had done both.
    _require_sdk(provider_name)
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
    service stops, and builds that provider if so. If the chosen provider
    can't be used (its SDK is missing, consent is declined, there is no
    key), says why and asks again, until one works or the user skips.

    Args:
        stopped (DraftingStopped): Why the hosted service stopped.

    Returns:
        Optional[DescriptionProvider]: The replacement, or ``None`` to stop
            drafting (the remaining gaps stay as TODO markers).
    """
    status(f"\n{stopped.message}")
    while True:
        try:
            choice = _ask(
                "Continue with your own API key? Provider "
                f"[{'/'.join(PROVIDERS)}/skip]: "
            ).lower()
        except EOFError:
            return None
        if choice not in PROVIDERS:
            return None
        try:
            return _direct_provider_from_answers(choice)
        except AISetupError as e:
            status(f"Can't continue with {PROVIDERS[choice].label}: {e}")
        except EOFError:
            return None


def _direct_provider_from_answers(choice: str) -> DescriptionProvider:
    """Asks for what the chosen provider still needs and builds it."""
    model = None
    if PROVIDERS[choice].default_model is None:
        model = _ask("Model name: ") or None
    base_url = None
    if choice == "openai-compatible":
        base_url = _ask("API base URL: ") or None
    return direct_provider(choice, model, base_url)


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


def _require_sdk(provider_name: str) -> None:
    if not sdk_installed(provider_name):
        raise AISetupError(
            f"The {PROVIDERS[provider_name].label} provider needs its SDK, "
            "which is not installed for this Python. Install it with:\n"
            f"  {install_command(provider_name)}\n"
            "then run again, or pick another provider with --ai-provider."
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
