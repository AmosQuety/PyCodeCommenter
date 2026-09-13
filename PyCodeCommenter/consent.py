"""One-time, versioned consent before any code is sent to the hosted
AI-drafting backend.

Per-user/per-machine, deliberately outside any project directory: this is a
decision about the person running the tool, not about any one codebase they
run it against. Stored at ``~/.pycodecommenter/consent.json`` as
``{"hosted_ai_consent_version": N}``.

The notice text carries its own version number (:data:`CONSENT_NOTICE_
VERSION`). If what gets sent or logged server-side ever materially changes,
bump that constant -- a stored consent for an old version no longer
satisfies :func:`has_given_consent`, so the notice is shown again rather
than silently carrying old consent forward onto different terms.
"""

from __future__ import annotations

import json
from pathlib import Path

# Bump this if what's sent to the backend, or what the backend does with
# it, ever materially changes -- a mismatch between a stored consent's
# version and this one means the notice must be shown again.
CONSENT_NOTICE_VERSION = 1

NOTICE = (
    "PyCodeCommenter is about to send this function's source code to a "
    "hosted service (run by the PyCodeCommenter maintainer) and then to "
    "Google's Gemini API, to draft a description. No source code is "
    "stored beyond the time it takes to process each request.\n"
    "Continue? [y/N] "
)


def _consent_file_path() -> Path:
    return Path.home() / ".pycodecommenter" / "consent.json"


def has_given_consent() -> bool:
    """Whether valid, current-version consent is already on file.

    Returns:
        bool: ``True`` if a consent file exists and its recorded version
            matches :data:`CONSENT_NOTICE_VERSION`. A missing, unreadable,
            or stale-version file all correctly return ``False`` -- consent
            is never assumed.
    """
    path = _consent_file_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("hosted_ai_consent_version") == CONSENT_NOTICE_VERSION


def record_consent() -> None:
    """Writes the current consent version to disk."""
    path = _consent_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"hosted_ai_consent_version": CONSENT_NOTICE_VERSION}) + "\n",
        encoding="utf-8",
    )


def ensure_consent(assume_yes: bool) -> bool:
    """Ensures consent is on file before any code reaches the hosted
    backend, prompting interactively if needed.

    Args:
        assume_yes (bool): Skip the interactive prompt and record consent
            immediately -- for non-interactive/CI use via an explicit CLI
            flag. Still only takes effect if consent isn't already on file;
            this never re-shows a notice that's already been agreed to.

    Returns:
        bool: ``True`` if consent is (now or already) on file. ``False``
            means the user declined and the caller must not send any code
            to the hosted backend.
    """
    if has_given_consent():
        return True
    if assume_yes:
        record_consent()
        return True

    print(NOTICE, end="")
    answer = input().strip().lower()
    if answer == "y":
        record_consent()
        return True
    return False


__all__ = [
    "CONSENT_NOTICE_VERSION",
    "NOTICE",
    "has_given_consent",
    "record_consent",
    "ensure_consent",
]
