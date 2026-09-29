"""A compact view of a class's source for an AI provider.

Sending a whole class would be costly and mostly irrelevant: what explains
a class and its attributes is its header, class-level fields, how
``__init__`` sets things up, and what the other methods are called and take.
So the outline keeps those, and reduces every other method to its signature.
"""

import ast
import copy
from typing import List

# A generous cap: a class this large is summarised by its shape anyway.
MAX_OUTLINE_CHARS = 6000


def outline_source(class_node: ast.ClassDef, code: str) -> str:
    """Build the outline of one class.

    Args:
        class_node (ast.ClassDef): The class.
        code (str): The source text ``class_node`` was parsed from.

    Returns:
        str: The class header, its class-level statements, ``__init__`` in
        full and the other methods as signatures, cut at
        ``MAX_OUTLINE_CHARS``.
    """
    bases = [ast.unparse(base) for base in class_node.bases + class_node.keywords]
    header = f"class {class_node.name}" + (f"({', '.join(bases)})" if bases else "")
    lines: List[str] = [header + ":"]
    for item in class_node.body:
        text = _outline_item(item, code)
        if text:
            lines.append(text)
    outline = "\n".join(lines)
    if len(outline) > MAX_OUTLINE_CHARS:
        outline = outline[:MAX_OUTLINE_CHARS].rstrip() + "\n    # ... (cut)"
    return outline


def _outline_item(item: ast.stmt, code: str) -> str:
    """Outline one statement of a class body.

    Keeps ``__init__`` and class-level assignments as written, reduces every
    other method to its signature, and drops everything else (docstrings,
    nested classes, other statements).

    Args:
        item (ast.stmt): A statement from the class body.
        code (str): The source text the class was parsed from.

    Returns:
        str: The indented outline text, or an empty string if the statement
        is left out.
    """
    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if item.name == "__init__":
            return _indent_first_line(ast.get_source_segment(code, item) or "")
        return _signature_only(item)
    if isinstance(item, (ast.Assign, ast.AnnAssign)):
        return _indent_first_line(ast.get_source_segment(code, item) or "")
    return ""


def _signature_only(function: ast.stmt) -> str:
    """Show a function's decorators and signature with its body elided.

    Args:
        function (ast.stmt): The function definition.

    Returns:
        str: The definition with ``...`` as its body, indented one level.
    """
    stub = copy.copy(function)
    stub.body = [ast.Expr(ast.Constant(...))]
    lines = ast.unparse(stub).replace(":\n    ...", ": ...").split("\n")
    return "\n".join("    " + line for line in lines)


def _indent_first_line(text: str) -> str:
    """Indent the first line of a source segment by one level.

    ``ast.get_source_segment`` drops the first line's indent but keeps the
    others' own, so only the first line needs re-indenting.

    Args:
        text (str): A source segment.

    Returns:
        str: The text with four spaces in front, or ``text`` itself if empty.
    """
    # get_source_segment drops the first line's indent but keeps the rest
    # of the lines' own, so only the first needs re-indenting.
    return "    " + text if text else text
