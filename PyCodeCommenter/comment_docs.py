"""Finding the `#` comment block an author wrote directly above a function
or class, and turning it into docstring text.

Such a block is the author's own description, so it's used as their
docstring text (never as a guess). The comment itself is left in place:
the tool never deletes user code. Lines that aren't description -- notes
(`TODO`), tool directives (`noqa`, `type:`), commented-out code -- are
skipped, and a banner (a block with a separator line such as `# -----`)
isn't used at all: it labels a section of the file, not one function.
"""

import ast
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Tool directives and file markers, not prose.
_DIRECTIVE = re.compile(
    r"^(noqa|type:|pylint:|pragma|fmt:|mypy:|isort:|flake8:|ruff:|pyright:"
    r"|black:|-\*-|!|coding[:=])",
    re.IGNORECASE,
)
# Notes to the author, not a description of the code.
_NOTE = re.compile(r"^(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)
# Divider lines such as "# ----------".
_SEPARATOR = re.compile(r"^[-=*#~_+.]{3,}$")
# A first sentence followed by more text starting with a capital letter.
# The sentence can't end right after a digit, so a numbered heading
# ("1. Baseline: ...") isn't split after "1.".
_FIRST_SENTENCE = re.compile(r"^(.+?[^\d\s][.!?])\s+(?=[A-Z])(.*)$", re.DOTALL)


@dataclass(frozen=True)
class CommentDocstring:
    """A docstring taken from the comment block above a definition.

    Attributes:
        name (str): The function or class name.
        first_line (int): The comment block's first line (1-based).
        last_line (int): Its last line.
    """

    name: str
    first_line: int
    last_line: int


def leading_comment_block(
    lines: List[str], node: ast.AST
) -> Optional[Tuple[int, int, List[str]]]:
    """The comment block directly above a definition, if it has one.

    The block must end on the line right above the definition (or its
    first decorator), be indented like it, and stand on its own: the line
    before it is blank, opens the enclosing block (ends with ``:``), or is
    the start of the file. That keeps a comment about the preceding code
    from being taken as a description of this definition.

    Args:
        lines (List[str]): The source, one entry per line.
        node (ast.AST): A function or class definition.

    Returns:
        Optional[Tuple[int, int, List[str]]]: The block's first and last
            line numbers (1-based) and its lines, or ``None``.
    """
    decorators = getattr(node, "decorator_list", [])
    start = min([d.lineno for d in decorators] + [node.lineno])
    index = start - 2
    block: List[str] = []
    while index >= 0 and _is_comment_at(lines[index], node.col_offset):
        block.insert(0, lines[index].strip())
        index -= 1
    if not block:
        return None
    above = lines[index].rstrip() if index >= 0 else ""
    if above.strip() and not above.endswith(":"):
        return None
    return index + 2, start - 1, block


def comment_block_text(lines: List[str]) -> Optional[str]:
    """Docstring text from comment lines: the first sentence as the summary,
    the rest as the description, with blank ``#`` lines as paragraph breaks.
    A banner (any separator line) yields nothing.

    Args:
        lines (List[str]): The comment lines, each starting with ``#``.

    Returns:
        Optional[str]: The text, or ``None`` if no line is description.
    """
    texts = [line.lstrip("#").strip() for line in lines]
    if any(_SEPARATOR.match(text) for text in texts):
        return None
    paragraphs: List[List[str]] = [[]]
    for text in texts:
        if not text:
            paragraphs.append([])
        elif not _is_non_description(text):
            paragraphs[-1].append(text)
    joined = [" ".join(p) for p in paragraphs if p]
    if not joined:
        return None
    first = _FIRST_SENTENCE.match(joined[0])
    if first:
        joined[0:1] = [first.group(1), first.group(2)]
    return "\n\n".join(joined)


def _is_comment_at(line: str, column: int) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("#") and len(line) - len(stripped) == column


def _is_non_description(text: str) -> bool:
    return bool(_DIRECTIVE.match(text) or _NOTE.match(text) or _looks_like_code(text))


def _looks_like_code(text: str) -> bool:
    """Whether a comment line is commented-out code: it parses as Python and
    is more than a lone word or literal (``# Deprecated`` is prose)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    if len(tree.body) != 1:
        return True
    statement = tree.body[0]
    return not (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, (ast.Name, ast.Constant))
    )


__all__ = ["CommentDocstring", "comment_block_text", "leading_comment_block"]
