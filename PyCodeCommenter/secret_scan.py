"""A conservative check for source that looks like it holds a secret.

The whole source of a function (comments included) is sent to an AI service
for drafting, so a credential pasted into it would be sent too. This flags
the shapes that are almost never anything else -- well-known key formats,
private-key headers, URLs with an embedded password, and a literal assigned
to a secret-named variable -- so that function is kept out of the request.
It is a safety net, not a scanner: it errs towards withholding, and a
withheld function only keeps the deterministic docstring.
"""

import re

# Whole-token shapes of well-known credentials.
_KEY_SHAPES = re.compile(
    "|".join(
        [
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
            r"\bAIza[0-9A-Za-z_\-]{35,}",
            r"\bsk-[A-Za-z0-9_\-]{20,}",
            r"\bgh[pousr]_[A-Za-z0-9]{36,}",
            r"\bgithub_pat_[A-Za-z0-9_]{22,}",
            r"\bxox[abprs]-[A-Za-z0-9\-]{10,}",
            r"\beyJ[\w\-]{10,}\.eyJ[\w\-]{10,}\.[\w\-]{10,}",
            # scheme://user:password@host
            r"\b[a-z][a-z0-9+.\-]*://[^\s/:@'\"]+:[^\s/@'\"]+@",
        ]
    )
)

# A secret-named variable, attribute or dict key assigned a literal of
# eight or more characters with no spaces (a value, not a sentence). Allows
# an annotation: ``DB_PASSWORD: str = "..."``.
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b[\w.]*(?:password|passwd|secret|api[_\-]?key|token|private[_\-]?key)"
    r"\w*[\"']?\s*(?::\s*[\w\[\]., |]+)?\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
)


def looks_like_secret(source: str) -> bool:
    """Whether source text looks like it contains a credential.

    Args:
        source (str): Code, comments included.

    Returns:
        bool: ``True`` if it should not be sent anywhere.
    """
    return bool(_KEY_SHAPES.search(source) or _SECRET_ASSIGNMENT.search(source))


__all__ = ["looks_like_secret"]
