"""A function docstring as structured parts, each tagged with where its text
came from, and the one place that renders it as Google-style text.

Separating the parts from the text lets later steps work on the structure
-- asking an AI provider to fill only the gaps, counting what was extracted
versus left for a human -- without re-parsing a finished string.
"""

from dataclasses import dataclass, field
from typing import List, Optional

try:
    from .inference import AI_DRAFT_MARKER
except (ImportError, ValueError):
    from inference import AI_DRAFT_MARKER


class Origin:
    """Where a part's text came from.

    AUTHOR: written by a person (kept as-is).
    FACT: stated by the code itself (a type, a condition, a known pattern).
    WEAK: generated from the type alone -- true, but says little.
    GUESS: nothing to go on; the text is the guess marker.
    AI: drafted by an AI provider and not yet reviewed.
    """

    AUTHOR = "author"
    FACT = "fact"
    WEAK = "weak"
    GUESS = "guess"
    AI = "ai"


@dataclass
class DocPart:
    """One piece of docstring text and its origin."""

    text: str
    origin: str

    @classmethod
    def ai_draft(cls, text: str) -> "DocPart":
        """Make a part holding AI-drafted text, carrying the AI-drafted marker.

        The marker stays until a person accepts the line in ``review``.

        Args:
            text (str): The drafted text.

        Returns:
            DocPart: The part, with origin ``Origin.AI``.
        """
        return cls(f"{text} {AI_DRAFT_MARKER}", Origin.AI)

    @property
    def needs_drafting(self) -> bool:
        """Say whether an AI provider may replace this part's text.

        Returns:
            bool: ``True`` for a guess or a weak (type-only) part.
        """
        return self.origin in (Origin.GUESS, Origin.WEAK)


@dataclass
class ArgEntry:
    """One Args: line.

    Attributes:
        name (str): The name as shown in Args, with ``*`` or ``**`` for variadics.
        display_type (str): The type shown in parentheses.
        part (DocPart): The description and where it came from.
        default (Optional[str]): The default value as written in code, or ``None``.
    """

    name: str
    display_type: str
    part: DocPart
    default: Optional[str] = None


@dataclass
class ReturnsEntry:
    """The Returns:/Yields: section. ``display_type`` is ``None`` for the
    bare ``None.`` form used when nothing is returned.

    Attributes:
        label (str): ``"Returns"`` or ``"Yields"``.
        display_type (Optional[str]): The type, or ``None`` for the bare ``None.`` form.
        part (DocPart): The description and where it came from.
    """

    label: str
    display_type: Optional[str]
    part: DocPart


@dataclass
class RaisesEntry:
    """One Raises: line.

    Attributes:
        name (str): The exception class name.
        part (DocPart): When it is raised, and where that text came from.
    """

    name: str
    part: DocPart


@dataclass
class FunctionDoc:
    """Every part of one function's docstring.

    Attributes:
        summary (DocPart): The one-line summary.
        description (Optional[DocPart]): The description paragraph, if any.
        args (List[ArgEntry]): One entry per parameter.
        returns (Optional[ReturnsEntry]): The Returns or Yields entry, if any.
        raises (List[RaisesEntry]): One entry per exception raised.
        dropped (int): Author-written Args entries removed because the
            parameter no longer exists; not rendered, only counted for the run
            summary.
    """

    summary: DocPart
    description: Optional[DocPart] = None
    args: List[ArgEntry] = field(default_factory=list)
    returns: Optional[ReturnsEntry] = None
    raises: List[RaisesEntry] = field(default_factory=list)
    # Author-written Args: entries dropped because the parameter no longer
    # exists; not rendered, only counted for the run summary.
    dropped: int = 0

    def parts(self) -> List[DocPart]:
        """List every part of the docstring, in document order.

        Returns:
            List[DocPart]: The summary, description, argument, return and raise
            parts that are present.
        """
        found = [self.summary]
        if self.description is not None:
            found.append(self.description)
        found += [arg.part for arg in self.args]
        if self.returns is not None:
            found.append(self.returns.part)
        found += [entry.part for entry in self.raises]
        return found


def render_function_doc(doc: FunctionDoc) -> str:
    """Renders a function docstring, including its triple quotes.

    Args:
        doc (FunctionDoc): The parts to render.

    Returns:
        str: The Google-style docstring literal.
    """
    text = f'"""{doc.summary.text}\n\n'
    if doc.description is not None and doc.description.text:
        text += f"{doc.description.text}\n\n"

    text += "Args:\n"
    text += "".join(_render_arg(arg) for arg in doc.args) or "    None.\n"

    if doc.returns is not None:
        text += _render_returns(doc.returns)

    if doc.raises:
        text += "\nRaises:\n"
        text += "".join(f"    {e.name}: {e.part.text}\n" for e in doc.raises)

    return text + '"""'


def needs_closing_period(text: str) -> bool:
    """Say whether an argument description needs a period added.

    The AI marker closes the sentence; a period after it would be added again
    on every regeneration.

    Args:
        text (str): The description text.

    Returns:
        bool: ``True`` unless the text already ends in ``.``, ``!``, ``?`` or
        the AI-drafted marker.
    """
    return not text.endswith((".", "!", "?", AI_DRAFT_MARKER))


def _render_arg(arg: ArgEntry) -> str:
    """Render one Args line, with its default when there is one.

    Args:
        arg (ArgEntry): The argument to render.

    Returns:
        str: The indented line, ending in a newline.
    """
    line = f"    {arg.name} ({arg.display_type}): {arg.part.text}"
    if needs_closing_period(arg.part.text):
        line += "."
    if arg.default is not None:
        line += f" (default: {arg.default})"
    return line + "\n"


def _render_returns(returns: ReturnsEntry) -> str:
    """Render the Returns or Yields section.

    Args:
        returns (ReturnsEntry): The entry to render.

    Returns:
        str: The section, preceded by a blank line. Without a type it is just
        the label and the text (the ``None.`` form).
    """
    if returns.display_type is None:
        return f"\n{returns.label}:\n    {returns.part.text}\n"
    return f"\n{returns.label}:\n    {returns.display_type}: {returns.part.text}\n"


@dataclass
class AttributeEntry:
    """One class attribute. ``display_type`` is ``None`` for an author's
    entry that declared no type.

    Attributes:
        name (str): The attribute's name.
        display_type (Optional[str]): The type, or ``None`` if the author declared none.
        text (str): The description.
        origin (str): Where the text came from (see ``Origin``).
    """

    name: str
    display_type: Optional[str]
    text: str
    origin: str = Origin.AUTHOR


@dataclass
class ClassDoc:
    """Every part of one class's docstring.

    Attributes:
        summary (str): The first line.
        summary_origin (str): Where the summary came from (see ``Origin``).
        description (Optional[str]): Further paragraphs, if any.
        attributes (List[AttributeEntry]): Attributes, in document order.
        methods (str): An author's own Google-style ``Methods:`` section
            body, kept verbatim (never generated).
    """

    summary: str
    description: Optional[str] = None
    attributes: List[AttributeEntry] = field(default_factory=list)
    methods: str = ""
    summary_origin: str = Origin.AUTHOR


def render_class_doc(doc: ClassDoc) -> str:
    """Renders a Google-style class docstring, including its triple quotes.

    Args:
        doc (ClassDoc): The parts to render.

    Returns:
        str: The docstring literal.
    """
    if not doc.attributes and not doc.methods:
        # Nothing after the summary/description: no trailing blank line.
        if not doc.description:
            return f'"""{doc.summary}"""'
        return f'"""{doc.summary}\n\n{doc.description}\n"""'
    text = f'"""{doc.summary}\n\n'
    if doc.description:
        text += f"{doc.description}\n\n"
    if doc.attributes:
        text += "Attributes:\n"
        for attribute in doc.attributes:
            type_part = f" ({attribute.display_type})" if attribute.display_type else ""
            text += f"    {attribute.name}{type_part}: {attribute.text}\n"
    if doc.methods:
        text += "\nMethods:\n" + doc.methods + "\n"
    return text + '"""'
