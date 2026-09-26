"""One-time, versioned consent before any code is sent to an AI service.

Consent is recorded per destination: the hosted AI-drafting service, or a
provider the user calls directly with their own key (``"openai"``,
``"anthropic"``, ...). Agreeing to send code to one never implies agreeing
to send it anywhere else.

Per-user/per-machine, deliberately outside any project directory: this is a
decision about the person running the tool, not about any one codebase they
run it against. Stored at ``~/.pycodecommenter/consent.json`` as
``{"hosted_ai_consent_version": N, "direct_ai_consent_versions":
{"openai": N}}``.

Each notice carries its own version number. If what gets sent, or what a
destination does with it, ever materially changes, bump that constant -- a
stored consent for an old version no longer counts, so the notice is shown
again rather than silently carrying old consent forward onto new terms.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOSTED = "hosted"

# Bump if what's sent to the hosted backend, or what it does with it,
# materially changes. (2: class outlines are sent too, comments included,
# and code that looks like it holds a secret is left out.)
CONSENT_NOTICE_VERSION = 2

# Bump if what's sent to a directly-called provider materially changes.
DIRECT_CONSENT_NOTICE_VERSION = 2

# What is sent, in plain words, shared by every notice: the whole source of
# each function that has gaps and an outline of each such class, comments
# included, minus anything that looks like a secret.
_WHAT_IS_SENT = (
    "the source code of your functions and an outline of your classes, "
    "comments included"
)
_SECRETS_NOTE = (
    "Code that looks like it holds a key, password or token is left out, but "
    "check that your comments contain no secrets."
)

NOTICE = (
    f"PyCodeCommenter is about to send {_WHAT_IS_SENT}, to a hosted service "
    "(run by the PyCodeCommenter maintainer) and then to Google's Gemini API, "
    "to draft docstrings. "
    f"{_SECRETS_NOTE} No source code is stored beyond the time it takes to "
    "process each request.\n"
    "Continue? [y/N] "
)


def notice_for(destination: str = HOSTED) -> str:
    """The consent notice for a destination.

    Args:
        destination (str): ``"hosted"`` or a provider name.

    Returns:
        str: The notice text, ending in a yes/no question.
    """
    if destination == HOSTED:
        return NOTICE
    try:
        from .direct_providers import PROVIDERS
    except ImportError:
        from direct_providers import PROVIDERS
    label = PROVIDERS[destination].label if destination in PROVIDERS else destination
    return (
        f"PyCodeCommenter is about to send {_WHAT_IS_SENT}, to {label}, "
        "using your API key, to draft docstrings. "
        f"{_SECRETS_NOTE} PyCodeCommenter's own service is not involved; "
        f"{label}'s terms and data policy for your account apply.\n"
        "Continue? [y/N] "
    )


def _consent_file_path() -> Path:
    return Path.home() / ".pycodecommenter" / "consent.json"


def _read() -> dict:
    path = _consent_file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def has_given_consent(destination: str = HOSTED) -> bool:
    """Whether valid, current-version consent is on file for a destination.

    Args:
        destination (str): ``"hosted"`` or a provider name.

    Returns:
        bool: ``True`` only if the recorded version matches the current
            notice's. A missing, unreadable, or stale-version file all
            return ``False`` -- consent is never assumed.
    """
    data = _read()
    if destination == HOSTED:
        return data.get("hosted_ai_consent_version") == CONSENT_NOTICE_VERSION
    direct = data.get("direct_ai_consent_versions")
    if not isinstance(direct, dict):
        return False
    return direct.get(destination) == DIRECT_CONSENT_NOTICE_VERSION


def record_consent(destination: str = HOSTED) -> None:
    """Records current-version consent for a destination, keeping any
    consent already recorded for others.

    Args:
        destination (str): ``"hosted"`` or a provider name.
    """
    data = _read()
    if destination == HOSTED:
        data["hosted_ai_consent_version"] = CONSENT_NOTICE_VERSION
    else:
        direct = data.get("direct_ai_consent_versions")
        direct = direct if isinstance(direct, dict) else {}
        direct[destination] = DIRECT_CONSENT_NOTICE_VERSION
        data["direct_ai_consent_versions"] = direct
    path = _consent_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


def ensure_consent(assume_yes: bool, destination: str = HOSTED) -> bool:
    """Ensures consent is on file before any code is sent, prompting
    interactively if needed.

    Args:
        assume_yes (bool): Skip the interactive prompt and record consent
            immediately -- for non-interactive/CI use via an explicit CLI
            flag. Still only takes effect if consent isn't already on file.
        destination (str): ``"hosted"`` or a provider name.

    Returns:
        bool: ``True`` if consent is (now or already) on file. ``False``
            means the user declined and no code may be sent there.
    """
    if has_given_consent(destination):
        return True
    if assume_yes:
        record_consent(destination)
        return True

    # stderr: stdout may be carrying generated code (see ai_setup.status).
    print(notice_for(destination), end="", file=sys.stderr)
    answer = input().strip().lower()
    if answer == "y":
        record_consent(destination)
        return True
    return False


__all__ = [
    "CONSENT_NOTICE_VERSION",
    "DIRECT_CONSENT_NOTICE_VERSION",
    "HOSTED",
    "NOTICE",
    "notice_for",
    "has_given_consent",
    "record_consent",
    "ensure_consent",
]
