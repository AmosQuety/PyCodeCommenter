"""Which parts of a function docstring to ask an AI provider for, and how its
answer is checked and applied.

Only gaps are ever requested: parts that would be a TODO marker, or that
say nothing beyond the type (see ``function_doc.Origin``). Author text and
facts read off the code are sent as context, never for rewriting. Every
drafted value passes :func:`clean_slot_text` before it is written -- the
hosted backend applies the same rules, but a provider's answer is never
trusted to be safe to put inside a docstring.
"""

import re
from typing import Any, Optional

try:
    from .description_provider import DocstringDraft, DraftSlots, KnownText
    from .function_doc import DocPart, FunctionDoc, Origin
except (ImportError, ValueError):
    from description_provider import DocstringDraft, DraftSlots, KnownText
    from function_doc import DocPart, FunctionDoc, Origin

MAX_SLOT_CHARS = 300
MAX_SUMMARY_CHARS = 80

# Text that must never be written into a docstring: it would end the string
# early, start an escape sequence, or pass a placeholder off as an answer.
_FORBIDDEN_FRAGMENTS = ('"""', "'''", "\\", "TODO", "AI-drafted")

# Parts whose text an AI draft may replace.
_REPLACEABLE = (Origin.GUESS, Origin.WEAK)


def slots_for(doc: FunctionDoc) -> DraftSlots:
    """The gaps in a function's docstring.

    A description is only requested for a docstring being written from
    scratch (its summary is derived from the name): an author who wrote a
    summary without a description chose not to have one.

    Args:
        doc (FunctionDoc): The function's docstring parts.

    Returns:
        DraftSlots: The parts worth drafting; empty if there are none.
    """
    fresh = doc.summary.origin == Origin.WEAK
    return DraftSlots(
        summary=fresh,
        description=fresh and doc.description is None,
        params=tuple(a.name for a in doc.args if a.part.origin in _REPLACEABLE),
        returns=doc.returns is not None and doc.returns.part.origin in _REPLACEABLE,
        raises=tuple(e.name for e in doc.raises if e.part.origin in _REPLACEABLE),
    )


def known_text(doc: FunctionDoc) -> KnownText:
    """The settled text a provider should stay consistent with.

    Args:
        doc (FunctionDoc): The function's docstring parts.

    Returns:
        KnownText: Author text and facts, by part.
    """
    settled = (Origin.AUTHOR, Origin.FACT)
    returns = doc.returns
    return KnownText(
        params={a.name: a.part.text for a in doc.args if a.part.origin in settled},
        returns=(
            returns.part.text
            if returns is not None and returns.part.origin in settled
            else None
        ),
        raises={e.name: e.part.text for e in doc.raises if e.part.origin in settled},
    )


def apply_draft(doc: FunctionDoc, draft: DocstringDraft, slots: DraftSlots) -> int:
    """Writes a provider's answer into the requested gaps, labelling each.

    Unrequested parts, unknown names, and values that fail
    :func:`clean_slot_text` are ignored, leaving that gap as it was.

    Args:
        doc (FunctionDoc): The docstring parts, updated in place.
        draft (DocstringDraft): The provider's answer.
        slots (DraftSlots): What was requested.

    Returns:
        int: How many parts were filled.
    """
    filled = 0
    if slots.summary:
        filled += _fill(
            doc, "summary", clean_slot_text(draft.summary, MAX_SUMMARY_CHARS)
        )
    if slots.description:
        description = clean_slot_text(draft.description)
        if description and not _same_text(description, doc.summary.text):
            doc.description = DocPart.ai_draft(description)
            filled += 1
    filled += _fill_named(doc.args, slots.params, draft.params)
    if slots.returns and doc.returns is not None:
        text = clean_slot_text(draft.returns)
        if text:
            doc.returns.part = DocPart.ai_draft(text)
            filled += 1
    filled += _fill_named(doc.raises, slots.raises, draft.raises)
    return filled


def _fill(doc: FunctionDoc, attribute: str, text: Optional[str]) -> int:
    if not text:
        return 0
    setattr(doc, attribute, DocPart.ai_draft(text))
    return 1


def _fill_named(entries: list, requested: tuple, drafted: Any) -> int:
    """Fills Args:/Raises: entries by name, for requested names only."""
    if not isinstance(drafted, dict):
        return 0
    filled = 0
    for entry in entries:
        text = (
            clean_slot_text(drafted.get(entry.name))
            if entry.name in requested
            else None
        )
        if text:
            entry.part = DocPart.ai_draft(text)
            filled += 1
    return filled


def _same_text(a: str, b: str) -> bool:
    return a.lower().rstrip(".") == b.lower().rstrip(".")


def clean_slot_text(value: Any, max_chars: int = MAX_SLOT_CHARS) -> Optional[str]:
    """Normalises one drafted value, or declines it.

    Whitespace is collapsed to single spaces (a docstring line must stay one
    line) and a final period is added if missing.

    Args:
        value (Any): The raw value from the provider.
        max_chars (int): The longest acceptable text.

    Returns:
        Optional[str]: The cleaned sentence, or ``None`` to decline.
    """
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text or any(fragment in text for fragment in _FORBIDDEN_FRAGMENTS):
        return None
    if not text.endswith((".", "!", "?")):
        text += "."
    return text if len(text) <= max_chars else None
