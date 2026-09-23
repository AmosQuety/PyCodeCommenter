"""Rule‑based parameter description inference for PyCodeCommenter.

This module provides a single public function :func:`infer_description` that attempts to
produce a concise, Google‑style description for a function parameter without contacting
any external services. The implementation is deliberately lightweight and uses a set of
heuristics based on the parameter name, type hint, default value, the surrounding
function name, and sibling parameters.

The function is pure and deterministic – it can be safely imported from the core
package and used during docstring generation.
"""

from __future__ import annotations

import re
from typing import List, Optional

# Content that isn't extracted from the AST or a hand-written docstring is
# a guess about what something means, not a fact about it. Guesses are marked with
# this instead of being dressed up as a finished sentence -- and the text
# deliberately reuses "TODO", a placeholder validator.py's own
# check_content_quality() already blacklists, so generated output that still
# has unresolved guesses in it visibly fails validation.
GUESS_MARKER = "TODO(pycodecommenter): describe"

# Text drafted by an opt-in AI description provider (see
# description_provider.py) is never presented as an equal, finished fact
# alongside deterministic, AST-grounded content -- it carries this marker
# permanently in the generated text itself, not just at generation time, so
# anyone reading the file later (not just whoever ran the tool) can tell the
# difference. validator.py's check_content_quality() recognizes this marker
# as its own category, distinct from both "documented" and the GUESS_MARKER
# placeholder above, so an AI draft can never be silently laundered into
# either "done" or "still a TODO" in a validate/coverage report.
AI_DRAFT_MARKER = "(AI-drafted, unreviewed)"

_COUNT_WORDS = frozenset({"count", "num", "number"})


def humanize_identifier(name: str) -> str:
    """Strip leading/trailing underscores and collapse any remaining run of
    underscores to a single space.

    Unlike a naive ``name.replace('_', ' ')``, this handles dunder methods
    (``__init__`` -> ``init``, not ``"  init  "`` with stray leading/
    trailing spaces) and names with multiple consecutive underscores.

    Args:
        name (str): The identifier to humanize.

    Returns:
        str: The identifier with underscores replaced by spaces.

    >>> humanize_identifier('__init__')
    'init'
    >>> humanize_identifier('file_path')
    'file path'
    """
    return re.sub(r"_+", " ", name.strip("_"))


def _human_readable(name: str) -> str:
    """Convert ``snake_case`` or ``camelCase`` identifiers to a readable phrase.

    Args:
        name (str): The identifier to convert.

    Returns:
        str: A lowercase, space-separated readable phrase.

    >>> _human_readable('file_path')
    'file path'
    >>> _human_readable('maxRetries')
    'max retries'
    """
    # Replace underscores with spaces (dunder-safe) and split camel case boundaries.
    name = humanize_identifier(name)
    # Insert spaces before capital letters that follow a lowercase letter.
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return name.lower()


def _name_ending_in(lowered: str, *suffixes: str) -> Optional[str]:
    """If ``lowered`` is exactly one of ``suffixes`` or ends with
    ``_<suffix>``, return the human-readable prefix before the suffix
    (``""`` when there is no prefix, i.e. the name is the bare suffix
    itself). Returns ``None`` when nothing matches, so callers can
    distinguish "matched, no prefix" from "didn't match".

    Args:
        lowered (str): The already-lowercased parameter name to check.
        *suffixes (str): One or more bare suffixes to match against (e.g.
            ``"id"``, or ``"index", "idx"`` for two spellings of one concept).

    Returns:
        Optional[str]: The human-readable prefix, or ``None`` if no suffix matched.

    >>> _name_ending_in('customer_id', 'id')
    'customer'
    >>> _name_ending_in('id', 'id')
    ''
    >>> _name_ending_in('price', 'id') is None
    True
    """
    for suffix in suffixes:
        if lowered == suffix:
            return ""
        if lowered.endswith("_" + suffix):
            return _human_readable(lowered[: -(len(suffix) + 1)])
    return None


# Parameter names with no further name/type signal beyond the bare word
# itself -- each phrase here is deliberately as concrete as the equivalent
# type-only fallback (e.g. "Mapping of keys to values" for a bare dict), not
# vaguer, per the rule that a new name pattern only ships when it beats what
# the existing fallback would already say.
_STATIC_NAME_DESCRIPTIONS = {
    "config": "Configuration settings",
    "configuration": "Configuration settings",
    "settings": "Configuration settings",
    "options": "Available options",
    "result": "The computed result",
    "output": "The produced output",
}


def _infer_from_name(param_name: str) -> Optional[str]:
    """Return a description based purely on the parameter name, if a known
    pattern matches.

    Args:
        param_name (str): The parameter name to match against known patterns.

    Returns:
        Optional[str]: A description if a name pattern matched, otherwise None.

    >>> _infer_from_name('customer_id')
    'Unique identifier for the customer'
    >>> _infer_from_name('id')
    'Unique identifier'
    >>> _infer_from_name('customer_name')
    "The customer's name"
    >>> _infer_from_name('cache_key')
    'Key identifying the cache'
    >>> _infer_from_name('row_index')
    'Index of the row'
    >>> _infer_from_name('result')
    'The computed result'
    >>> _infer_from_name('config_path')
    'Path to the config'
    """
    lowered = param_name.lower()
    if lowered in {"path", "file_path", "dir_path", "directory"} or lowered.endswith(
        "_path"
    ):
        return f"Path to the {lowered.replace('_path', '').replace('path', '').strip()}"
    if "url" in lowered:
        return "URL for the resource"
    if (
        lowered.startswith("is_")
        or lowered.startswith("has_")
        or lowered.startswith("can_")
    ):
        # Boolean flag – convert to a question‑style description.
        base = _human_readable(param_name[3:])
        return f"Flag indicating whether {base}"
    # Whole words only: a substring match turned "discount" into
    # "Number of dis" and "country" into "Number of try".
    words = _human_readable(param_name).split()
    if _COUNT_WORDS.intersection(words):
        counted = [w for w in words if w not in _COUNT_WORDS and w != "of"]
        if counted:
            return f"Number of {' '.join(counted)}"
    if lowered in {"timeout", "delay"}:
        return "Timeout in seconds"
    if lowered in {"verbose", "debug"}:
        return "Enable verbose output"

    prefix = _name_ending_in(lowered, "id")
    if prefix is not None:
        return f"Unique identifier for the {prefix}" if prefix else "Unique identifier"

    prefix = _name_ending_in(lowered, "name")
    if prefix is not None:
        return f"The {prefix}'s name" if prefix else "The name"

    prefix = _name_ending_in(lowered, "key")
    if prefix is not None:
        return f"Key identifying the {prefix}" if prefix else "Lookup key"

    prefix = _name_ending_in(lowered, "index", "idx")
    if prefix is not None:
        return f"Index of the {prefix}" if prefix else "Index position"

    if lowered in _STATIC_NAME_DESCRIPTIONS:
        return _STATIC_NAME_DESCRIPTIONS[lowered]

    return None


def _infer_from_type(type_hint: Optional[str]) -> Optional[str]:
    """Return a description based on the provided type hint, if helpful.

    Args:
        type_hint (Optional[str]): The parameter's inferred type hint, if any.

    Returns:
        Optional[str]: A description based on the type, otherwise None.
    """
    if not type_hint:
        return None
    t = type_hint.lower()
    if t in {"int", "float", "decimal"}:
        return f"{t} value"
    if t == "bool":
        return "Boolean flag"
    if t == "str":
        return "String value"
    if t.startswith("list"):
        return "List of items"
    if t.startswith("dict"):
        return "Mapping of keys to values"
    return None


def _infer_from_default(default_value: Optional[str]) -> Optional[str]:
    """Create a short hint based on the default value, when available.

    Args:
        default_value (Optional[str]): The parameter's default value, if any.

    Returns:
        Optional[str]: A short hint based on the default, otherwise None.
    """
    if default_value is None:
        return None
    # Common literal defaults.
    lowered = default_value.lower()
    if lowered in {"true", "false"}:
        return f"Default is {lowered}"
    if lowered.isdigit():
        return f"Default is {default_value}"
    if re.match(r"^[\"\'][^\"\']*[\"\']$", default_value):
        # It's a quoted string literal.
        return f"Default is {default_value}"
    return None


def infer_description(
    *,
    param_name: str,
    type_hint: Optional[str] = None,
    default_value: Optional[str] = None,
    function_name: str | None = None,
    sibling_params: List[str] | None = None,
) -> str:
    """Generate a concise description for a function parameter.

    The heuristic order is:
    1. **Static name patterns** – e.g., ``*_path`` or ``url``.
    2. **Provided type hint** – ``int`` → "int value".
    3. **Default value hint** – adds "Default is …" when appropriate.
    4. **Fallback** – none of the above matched, so this returns
       :data:`GUESS_MARKER` instead of fabricating a sentence.

    Parameters
    ----------
    param_name:
        The raw parameter identifier as it appears in the function signature.
    type_hint:
        Optional string representation of the inferred type (e.g. ``"int"``).
    default_value:
        Optional string representation of the default value (as returned by
        ``repr``). ``None`` indicates the parameter has no default.
    function_name:
        Name of the enclosing function – used for the generic fallback.
    sibling_params:
        List of other parameter names in the same function – currently unused but
        kept for future extensions (e.g., detecting mutually exclusive flags).

    Returns
    -------
    str
        A human‑readable description suitable for a Google‑style ``Args`` block.
    """
    # 1. Name‑based heuristics.
    name_desc = _infer_from_name(param_name)
    if name_desc:
        return name_desc.rstrip(".") + "."

    # 2. Type‑based heuristics.
    type_desc = _infer_from_type(type_hint)
    if type_desc:
        # If we also have a default hint, append it.
        default_desc = _infer_from_default(default_value)
        if default_desc:
            return f"{type_desc}. {default_desc}."
        return f"{type_desc}."

    # 3. Default‑value only heuristics.
    default_desc = _infer_from_default(default_value)
    if default_desc:
        return f"{default_desc}."

    # 4. Generic fallback. Nothing above matched, so there's no real signal
    # to describe this parameter from -- anything written here would be a
    # guess dressed up as prose, so it's marked instead.
    return GUESS_MARKER


__all__ = [
    "infer_description",
    "humanize_identifier",
    "GUESS_MARKER",
    "AI_DRAFT_MARKER",
]
