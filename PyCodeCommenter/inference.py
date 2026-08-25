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

# Content that isn't extracted from the AST, a hand-written docstring, or a
# deliberate per-function override in parameter_descriptions.py is a guess
# about what something means, not a fact about it. Guesses are marked with
# this instead of being dressed up as a finished sentence -- and the text
# deliberately reuses "TODO", a placeholder validator.py's own
# check_content_quality() already blacklists, so generated output that still
# has unresolved guesses in it visibly fails validation.
GUESS_MARKER = "TODO(pycodecommenter): describe"


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


def _infer_from_name(param_name: str) -> Optional[str]:
    """Return a description based purely on the parameter name, if a known pattern matches.

    Args:
        param_name (str): The parameter name to match against known patterns.

    Returns:
        Optional[str]: A description if a name pattern matched, otherwise None.
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
    if "count" in lowered or "num" in lowered or "number" in lowered:
        base = _human_readable(param_name)
        return f"Number of {base.replace('count', '').replace('num', '').replace('number', '').strip()}"
    if lowered in {"timeout", "delay"}:
        return f"Timeout in seconds"
    if lowered in {"verbose", "debug"}:
        return f"Enable verbose output"
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


__all__ = ["infer_description", "humanize_identifier", "GUESS_MARKER"]
