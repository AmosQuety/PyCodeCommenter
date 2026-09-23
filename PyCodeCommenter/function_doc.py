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
        """A part holding AI-drafted text, carrying the permanent marker."""
        return cls(f"{text} {AI_DRAFT_MARKER}", Origin.AI)

    @property
    def needs_drafting(self) -> bool:
        """Whether an AI provider may replace this part's text."""
        return self.origin in (Origin.GUESS, Origin.WEAK)


@dataclass
class ArgEntry:
    """One Args: line."""

    name: str
    display_type: str
    part: DocPart
    default: Optional[str] = None


@dataclass
class ReturnsEntry:
    """The Returns:/Yields: section. ``display_type`` is ``None`` for the
    bare ``None.`` form used when nothing is returned."""

    label: str
    display_type: Optional[str]
    part: DocPart


@dataclass
class RaisesEntry:
    """One Raises: line."""

    name: str
    part: DocPart


@dataclass
class FunctionDoc:
    """Every part of one function's docstring."""

    summary: DocPart
    description: Optional[DocPart] = None
    args: List[ArgEntry] = field(default_factory=list)
    returns: Optional[ReturnsEntry] = None
    raises: List[RaisesEntry] = field(default_factory=list)

    def parts(self) -> List[DocPart]:
        """Every part, in document order."""
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
    """Whether an argument description needs a period added. The AI marker
    closes the sentence; a period after it would be added again on every
    regeneration."""
    return not text.endswith((".", "!", "?", AI_DRAFT_MARKER))


def _render_arg(arg: ArgEntry) -> str:
    line = f"    {arg.name} ({arg.display_type}): {arg.part.text}"
    if needs_closing_period(arg.part.text):
        line += "."
    if arg.default is not None:
        line += f" (default: {arg.default})"
    return line + "\n"


def _render_returns(returns: ReturnsEntry) -> str:
    if returns.display_type is None:
        return f"\n{returns.label}:\n    {returns.part.text}\n"
    return f"\n{returns.label}:\n    {returns.display_type}: {returns.part.text}\n"


@dataclass
class AttributeEntry:
    """One class attribute. ``display_type`` is ``None`` for an author's
    entry that declared no type."""

    name: str
    display_type: Optional[str]
    text: str


@dataclass
class ClassDoc:
    """Every part of one class's docstring.

    Attributes:
        summary (str): The first line.
        description (Optional[str]): Further paragraphs, if any.
        attributes (List[AttributeEntry]): Attributes, in document order.
        methods (str): An author's own Google-style ``Methods:`` section
            body, kept verbatim (never generated).
    """

    summary: str
    description: Optional[str] = None
    attributes: List[AttributeEntry] = field(default_factory=list)
    methods: str = ""


def render_class_doc(doc: ClassDoc) -> str:
    """Renders a Google-style class docstring, including its triple quotes.

    Args:
        doc (ClassDoc): The parts to render.

    Returns:
        str: The docstring literal.
    """
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
