"""Rendering docstrings in the style an author already uses.

New docstrings are Google style (``function_doc``). An existing NumPy- or
Sphinx-style docstring is regenerated in its own style, so filling a gap
never converts someone's documentation to a different convention. All
three styles render the same parts (``FunctionDoc``/``ClassDoc``), so
nothing about *what* is documented depends on the style.

In NumPy and Sphinx style, an empty parameter list and a function that
returns nothing get no section at all: neither convention has an
equivalent of Google's ``Args: None.`` / ``Returns: None.``.
"""

from typing import List

try:
    from .function_doc import (
        ClassDoc,
        FunctionDoc,
        needs_closing_period,
        render_class_doc,
        render_function_doc,
    )
except (ImportError, ValueError):
    from function_doc import (
        ClassDoc,
        FunctionDoc,
        needs_closing_period,
        render_class_doc,
        render_function_doc,
    )

GOOGLE = "google"
NUMPY = "numpy"
SPHINX = "sphinx"


def render_function(doc: FunctionDoc, style: str = GOOGLE) -> str:
    """Renders a function docstring in the given style.

    Args:
        doc (FunctionDoc): The parts to render.
        style (str): ``"google"``, ``"numpy"`` or ``"sphinx"``.

    Returns:
        str: The docstring literal, including its triple quotes.
    """
    if style == NUMPY:
        return _assemble(doc.summary.text, _description(doc), _numpy_function(doc))
    if style == SPHINX:
        return _assemble(doc.summary.text, _description(doc), _sphinx_function(doc))
    return render_function_doc(doc)


def render_class(doc: ClassDoc, style: str = GOOGLE) -> str:
    """Renders a class docstring in the given style.

    Args:
        doc (ClassDoc): The parts to render.
        style (str): ``"google"``, ``"numpy"`` or ``"sphinx"``.

    Returns:
        str: The docstring literal, including its triple quotes.
    """
    if style == NUMPY:
        return _assemble(doc.summary, doc.description, _numpy_class(doc))
    if style == SPHINX:
        return _assemble(doc.summary, doc.description, _sphinx_class(doc))
    return render_class_doc(doc)


def _description(doc: FunctionDoc):
    return doc.description.text if doc.description and doc.description.text else None


def _assemble(summary: str, description, sections: List[str]) -> str:
    """Summary, optional description, then sections separated by blank lines."""
    head = summary if not description else f"{summary}\n\n{description}"
    if not sections:
        return f'"""{head}"""' if not description else f'"""{head}\n"""'
    return f'"""{head}\n\n' + "\n".join(sections) + '"""'


def _sentence(text: str) -> str:
    return text + "." if needs_closing_period(text) else text


# ---------------------------------------------------------------------------
# NumPy
# ---------------------------------------------------------------------------


def _numpy_section(title: str, entries: List[str]) -> str:
    return f"{title}\n{'-' * len(title)}\n" + "".join(entries)


def _numpy_function(doc: FunctionDoc) -> List[str]:
    sections = []
    if doc.args:
        entries = []
        for arg in doc.args:
            optional = ", optional" if arg.default is not None else ""
            default = f" (default: {arg.default})" if arg.default is not None else ""
            entries.append(
                f"{arg.name} : {arg.display_type}{optional}\n"
                f"    {_sentence(arg.part.text)}{default}\n"
            )
        sections.append(_numpy_section("Parameters", entries))
    if doc.returns is not None and doc.returns.display_type is not None:
        sections.append(
            _numpy_section(
                doc.returns.label,
                [f"{doc.returns.display_type}\n    {doc.returns.part.text}\n"],
            )
        )
    if doc.raises:
        sections.append(
            _numpy_section(
                "Raises", [f"{e.name}\n    {e.part.text}\n" for e in doc.raises]
            )
        )
    return sections


def _numpy_class(doc: ClassDoc) -> List[str]:
    if not doc.attributes:
        return []
    entries = [
        (f"{a.name} : {a.display_type}\n" if a.display_type else f"{a.name}\n")
        + f"    {a.text}\n"
        for a in doc.attributes
    ]
    return [_numpy_section("Attributes", entries)]


# ---------------------------------------------------------------------------
# Sphinx
# ---------------------------------------------------------------------------


def _sphinx_function(doc: FunctionDoc) -> List[str]:
    fields = []
    for arg in doc.args:
        default = f" (default: {arg.default})" if arg.default is not None else ""
        fields.append(f":param {arg.name}: {_sentence(arg.part.text)}{default}\n")
        fields.append(f":type {arg.name}: {arg.display_type}\n")
    returns = doc.returns
    if returns is not None and returns.display_type is not None:
        is_yield = returns.label == "Yields"
        fields.append(f":{'yields' if is_yield else 'returns'}: {returns.part.text}\n")
        fields.append(f":{'ytype' if is_yield else 'rtype'}: {returns.display_type}\n")
    fields += [f":raises {e.name}: {e.part.text}\n" for e in doc.raises]
    return ["".join(fields)] if fields else []


def _sphinx_class(doc: ClassDoc) -> List[str]:
    fields = []
    for a in doc.attributes:
        fields.append(f":ivar {a.name}: {a.text}\n")
        if a.display_type:
            fields.append(f":vartype {a.name}: {a.display_type}\n")
    return ["".join(fields)] if fields else []


__all__ = ["GOOGLE", "NUMPY", "SPHINX", "render_function", "render_class"]
