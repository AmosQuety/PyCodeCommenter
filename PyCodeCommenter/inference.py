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


def _human_readable(name: str) -> str:
    """Convert ``snake_case`` or ``camelCase`` identifiers to a readable phrase.

    >>> _human_readable('file_path')
    'file path'
    >>> _human_readable('maxRetries')
    'max retries'
    """
    # Replace underscores with spaces and split camel case boundaries.
    name = name.replace('_', ' ')
    # Insert spaces before capital letters that follow a lowercase letter.
    name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    return name.lower()


def _infer_from_name(param_name: str) -> Optional[str]:
    """Return a description based purely on the parameter name, if a known pattern matches."""
    lowered = param_name.lower()
    if lowered in {"path", "file_path", "dir_path", "directory"} or lowered.endswith("_path"):
        return f"Path to the {lowered.replace('_path', '').replace('path', '').strip()}"
    if "url" in lowered:
        return "URL for the resource"
    if lowered.startswith("is_") or lowered.startswith("has_") or lowered.startswith("can_"):
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
    """Return a description based on the provided type hint, if helpful."""
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
    """Create a short hint based on the default value, when available."""
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
    4. **Fallback** – a generic "{Param} of the {function}" sentence.

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
        return name_desc.rstrip('.') + '.'

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

    # 4. Generic fallback.
    func_part = f" of the {function_name.replace('_', ' ')}" if function_name else ""
    readable = _human_readable(param_name)
    return f"{readable.capitalize()}{func_part}."


__all__ = ["infer_description"]
