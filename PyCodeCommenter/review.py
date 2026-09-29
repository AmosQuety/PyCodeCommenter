"""Finding what needs a person's attention after generation, and applying
their decisions: AI-drafted lines (accept, edit, skip), TODO gaps (fill,
skip), and comments a docstring now repeats (remove only on an explicit
yes).

Every change is to a single docstring line, except removing an approved
comment block. :func:`verify_review` checks the result still parses and
that no code changed before anything is saved.
"""

import ast
import re
import sys
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

try:
    from .comment_docs import comment_block_text, leading_comment_block
    from .docstring_parser import DocstringParser
    from .inference import AI_DRAFT_MARKER, GUESS_MARKER
except (ImportError, ValueError):
    from comment_docs import comment_block_text, leading_comment_block
    from docstring_parser import DocstringParser
    from inference import AI_DRAFT_MARKER, GUESS_MARKER

AI = "ai"
TODO = "todo"
COMMENT = "comment"

# The whole guess phrase as rendered on an argument, return or raise line.
_GUESS_PHRASE = re.compile(re.escape(GUESS_MARKER) + r"(?: when this is raised)?\.?")
_OPENING_QUOTES = re.compile(r"^(\s*[rRuU]{0,2}(?:\"\"\"|'''))")
_GOOGLE_SECTION = re.compile(r"^\s*(Args|Returns|Yields|Raises|Attributes):\s*$")
_GOOGLE_LABEL = re.compile(r"^(\s*\S.*?:\s)")
_SPHINX_LABEL = re.compile(r"^(\s*:[^:]+:\s)")
_FORBIDDEN_IN_TEXT = ('"""', "'''", "\\")


class ReviewError(Exception):
    """A reviewed file failed its safety check and was not saved."""


@dataclass(frozen=True)
class ReviewItem:
    """One thing to review.

    Attributes:
        kind (str): ``"ai"``, ``"todo"`` or ``"comment"``.
        line (int): Its (first) line, 1-based.
        end_line (int): Its last line (differs only for a comment block).
        definition (str): The function or class it belongs to (``""`` for the
            module docstring).
        text (str): What to show: the drafted text, the gap's line, or the
            comment text.
        keep_before (str): For an AI line, everything before the drafted text
            (indent, opening quotes, entry label); kept on edit.
        keep_after (str): For an AI line, everything after the marker (for
            example a ``(default: 3)`` note); kept on accept and edit.
        docstring_line (int): First line of the docstring holding the item (0
            for a comment, which lies outside it).
        docstring_end (int): Last line of that docstring.
    """

    kind: str
    line: int
    end_line: int
    definition: str
    text: str
    keep_before: str = ""
    keep_after: str = ""
    docstring_line: int = 0
    docstring_end: int = 0


def is_interactive() -> bool:
    """Say whether a person is at the terminal to answer questions.

    Returns:
        bool: ``True`` if standard input is a terminal.
    """
    return sys.stdin.isatty()


def text_problem(text: str) -> Optional[str]:
    """Say why typed text can't go into a docstring.

    Args:
        text (str): The text a person typed.

    Returns:
        Optional[str]: A sentence describing the problem (empty text, triple
        quotes, backslashes), or ``None`` if the text is acceptable.
    """
    if not text.strip():
        return "The text can't be empty."
    if any(fragment in text for fragment in _FORBIDDEN_IN_TEXT):
        return "The text can't contain triple quotes or backslashes."
    return None


def find_review_items(source: str) -> List[ReviewItem]:
    """Find everything in a file that needs review, in file order.

    Args:
        source (str): The file's text.

    Returns:
        List[ReviewItem]: AI-drafted lines, gap markers, and comments that
        the docstring below them now repeats.

    Raises:
        SyntaxError: If ``source`` does not parse.
    """
    lines = _split_lines(source)
    tree = ast.parse(source)
    items: List[ReviewItem] = []
    for node in [tree] + [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]:
        docstring = ast.get_docstring(node)
        if docstring is None:
            continue
        name = getattr(node, "name", "")
        literal = node.body[0].value
        style = DocstringParser(docstring).get_info()["style"]
        items += _docstring_items(lines, literal, name, style)
        if name:
            items += _repeated_comment(lines, node, docstring)
    return sorted(items, key=lambda item: item.line)


def apply_review(source: str, decisions: List[Tuple[ReviewItem, tuple]]) -> str:
    """Apply decisions to a file's text.

    Args:
        source (str): The file's text, as :func:`find_review_items` saw it.
        decisions (List[Tuple[ReviewItem, tuple]]): Each item with its
            ``(action, text)`` decision. The action is ``"accept"``,
            ``"edit"``, ``"fill"`` or ``"remove"``; ``text`` is the new text
            for an edit or fill and is otherwise unused.

    Returns:
        str: The new text, with the file's own line endings.
    """
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = _split_lines(source)
    removals = []
    for item, (action, text) in decisions:
        index = item.line - 1
        if action == "accept":
            lines[index] = item.keep_before + item.text + item.keep_after
        elif action == "edit":
            lines[index] = item.keep_before + _sentence(text) + item.keep_after
        elif action == "fill":
            lines[index] = _GUESS_PHRASE.sub(
                lambda _: _sentence(text), lines[index], count=1
            )
        elif action == "remove":
            removals.append(item)
    # Removing lines shifts the ones below, so it goes last, bottom-up.
    for item in sorted(removals, key=lambda i: i.line, reverse=True):
        del lines[item.line - 1 : item.end_line]
    return newline.join(lines)


def verify_review(original: str, result: str) -> None:
    """Check a reviewed file before it's saved.

    Args:
        original (str): The file's text before the review.
        result (str): The text the decisions produced.

    Raises:
        ReviewError: The result doesn't parse, or its code (anything but
            docstrings and comments) differs from the original's.
    """
    try:
        changed = _code_only(original) != _code_only(result)
    except SyntaxError as e:
        raise ReviewError(f"the result would not be valid Python ({e})") from e
    if changed:
        raise ReviewError("the result would change code, not just docstrings")


def _docstring_items(
    lines: List[str], literal: ast.Constant, name: str, style: str
) -> List[ReviewItem]:
    """Find the AI-drafted lines and gap markers inside one docstring.

    Args:
        lines (List[str]): The file's lines.
        literal (ast.Constant): The docstring's string node.
        name (str): The function or class the docstring belongs to.
        style (str): The docstring's style, as ``DocstringParser`` names it.

    Returns:
        List[ReviewItem]: One item per marked line, each carrying the
        docstring's first and last line.
    """
    items = []
    in_section = False
    for number in range(literal.lineno, literal.end_lineno + 1):
        line = lines[number - 1]
        in_section = in_section or bool(_GOOGLE_SECTION.match(line))
        if AI_DRAFT_MARKER in line:
            first = number == literal.lineno
            items.append(_ai_item(line, number, name, style, first, in_section))
        elif GUESS_MARKER in line:
            items.append(ReviewItem(TODO, number, number, name, line.strip()))
    return [
        replace(item, docstring_line=literal.lineno, docstring_end=literal.end_lineno)
        for item in items
    ]


def _ai_item(line, number, name, style, first_line, in_section) -> ReviewItem:
    """Split an AI-drafted line into what's kept and the drafted text.

    Args:
        line (str): The docstring line holding the marker.
        number (int): Its line number, 1-based.
        name (str): The function or class the docstring belongs to.
        style (str): The docstring's style.
        first_line (bool): The line is the docstring's first, so it starts
            with the opening quotes.
        in_section (bool): The line is inside an Args, Returns or similar
            section.

    Returns:
        ReviewItem: The item, with ``keep_before`` and ``keep_after`` set.
    """
    at = line.index(AI_DRAFT_MARKER)
    head, after = line[:at].rstrip(" "), line[at + len(AI_DRAFT_MARKER) :]
    before = ""
    opening = _OPENING_QUOTES.match(head) if first_line else None
    if opening:
        before = opening.group(1)
    else:
        label = _entry_label(head, style, in_section)
        before = label.group(1) if label else head[: len(head) - len(head.lstrip())]
    return ReviewItem(AI, number, number, name, head[len(before) :], before, after)


def _entry_label(head: str, style: str, in_section: bool):
    """Match the label an entry starts with, such as ``x (int): `` or ``:param x: ``.

    NumPy descriptions and prose paragraphs have none.

    Args:
        head (str): The line's text before the marker.
        style (str): The docstring's style.
        in_section (bool): The line is inside a Google-style section.

    Returns:
        Optional[re.Match]: The match (group 1 is the label), or ``None`` when
        the line has no label.
    """
    if style == "sphinx":
        return _SPHINX_LABEL.match(head)
    if style == "google" and in_section:
        return _GOOGLE_LABEL.match(head)
    return None


def _repeated_comment(lines: List[str], node: ast.AST, docstring: str) -> list:
    """Find the comment block above a definition that its docstring repeats.

    That is the case when the docstring was taken from the comment.

    Args:
        lines (List[str]): The file's lines.
        node (ast.AST): The function or class.
        docstring (str): Its docstring text.

    Returns:
        list: A list with one comment item, or an empty list.
    """
    found = leading_comment_block(lines, node)
    comment = comment_block_text(found[2]) if found else None
    if not comment:
        return []
    info = DocstringParser(docstring).get_info()
    written = " ".join(p for p in (info["summary"], info["description"]) if p)
    if _normalized(written) != _normalized(comment):
        return []
    return [ReviewItem(COMMENT, found[0], found[1], node.name, comment)]


def _normalized(text: str) -> str:
    """Collapse all whitespace to single spaces, for comparing text.

    Args:
        text (str): Any text.

    Returns:
        str: The words of ``text`` separated by single spaces.
    """
    return " ".join(text.split())


def _sentence(text: str) -> str:
    """Collapse whitespace and end the text with sentence punctuation.

    Args:
        text (str): Text a person typed.

    Returns:
        str: The text on one line, with a period added unless it already
        ends in ``.``, ``!`` or ``?``.
    """
    text = " ".join(text.split())
    return text if text.endswith((".", "!", "?")) else text + "."


def _split_lines(source: str) -> List[str]:
    """Split source into lines, whatever its line endings.

    Args:
        source (str): The file's text.

    Returns:
        List[str]: The lines, without line endings.
    """
    return source.replace("\r\n", "\n").split("\n")


def _code_only(source: str) -> str:
    """Dump the file's code without its docstrings, for comparison.

    Comments are not in the AST, so they do not count either.

    Args:
        source (str): The file's text.

    Returns:
        str: A dump of the syntax tree with docstrings removed.

    Raises:
        SyntaxError: If ``source`` does not parse.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


__all__ = [
    "ReviewError",
    "ReviewItem",
    "apply_review",
    "find_review_items",
    "is_interactive",
    "text_problem",
    "verify_review",
]
