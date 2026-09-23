"""Which parts of a function docstring to ask an AI provider for, and how its
answer is checked and applied.

Only gaps are ever requested: parts that would be a TODO marker, or that
say nothing beyond the type (see ``function_doc.Origin``). Author text and
facts read off the code are sent as context, never for rewriting. Every
drafted value passes :func:`clean_slot_text` before it is written -- the
hosted backend applies the same rules, but a provider's answer is never
trusted to be safe to put inside a docstring.
"""

import json
import re
from typing import Any, Dict, Optional

try:
    from .description_provider import (
        DocstringDraft,
        DraftSlots,
        FunctionContext,
        KnownText,
    )
    from .function_doc import DocPart, FunctionDoc, Origin
except (ImportError, ValueError):
    from description_provider import (
        DocstringDraft,
        DraftSlots,
        FunctionContext,
        KnownText,
    )
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


# ---------------------------------------------------------------------------
# Prompt, schema and reply parsing for providers called directly with the
# user's own key. The hosted backend keeps its own copy of the prompt (it
# deliberately doesn't depend on this package); keep the two in step.
# ---------------------------------------------------------------------------


def build_prompt(context: FunctionContext, known: KnownText, slots: DraftSlots) -> str:
    """Builds the drafting prompt for one function.

    Args:
        context (FunctionContext): The function's AST-derived facts,
            including its source (comments and all).
        known (KnownText): Text already settled, for consistency.
        slots (DraftSlots): The parts to draft.

    Returns:
        str: The prompt text.
    """
    params = (
        ", ".join(
            f"{p.name}: {p.type_hint}" + (f" = {p.default}" if p.default else "")
            for p in context.parameters
        )
        or "none"
    )
    kind = "generator function" if context.is_generator else "function"
    return "\n".join(
        [
            "You are documenting Python source code for its Google-style docstring.",
            "Fill in only the requested parts, grounded strictly in the code shown",
            "(its comments included). Reply with a JSON object only.",
            "Rules:",
            "- One plain sentence per part; name code with `backticks`,"
            " no other markdown.",
            "- Say what something means or is for, not its type"
            " (the type is already shown).",
            "- Use null for any part the code does not make clear. Never guess.",
            f"- summary: an imperative phrase under {MAX_SUMMARY_CHARS} characters.",
            "- description: extra detail beyond the summary, or null.",
            "- raises entries: when the exception is raised.",
            "",
            f"This is a {kind} named `{context.name}`.",
            f"Parameters: {params}.",
            f"Return type: {context.return_type}.",
            _known_lines(known),
            f"Requested JSON keys: {_requested_text(slots)}.",
            "",
            "Source:",
            context.source,
        ]
    )


def _known_lines(known: KnownText) -> str:
    lines = [f"- param `{n}`: {t}" for n, t in known.params.items()]
    if known.returns:
        lines.append(f"- returns: {known.returns}")
    lines += [f"- raises `{n}`: {t}" for n, t in known.raises.items()]
    if not lines:
        return "Already documented: nothing."
    return "Already documented (stay consistent, don't repeat):\n" + "\n".join(lines)


def _requested_text(slots: DraftSlots) -> str:
    parts = [name for name in ("summary", "description") if getattr(slots, name)]
    if slots.params:
        parts.append("params " + ", ".join(slots.params))
    if slots.returns:
        parts.append("returns")
    if slots.raises:
        parts.append("raises " + ", ".join(slots.raises))
    return "; ".join(parts)


def json_schema(slots: DraftSlots) -> dict:
    """A strict JSON Schema for the reply, covering exactly the requested
    parts: every key required, no extra keys, each value a string or null.

    Args:
        slots (DraftSlots): The parts to draft.

    Returns:
        dict: The schema.
    """
    return _schema(slots, lambda max_chars: {"type": "string"})


def json_schema_with_length_caps(slots: DraftSlots) -> dict:
    """:func:`json_schema` plus ``maxLength`` on every string, for providers
    that support it. Observed on Gemini: without a cap, a model in JSON mode
    can ramble in one field until the output budget cuts the reply off.

    Args:
        slots (DraftSlots): The parts to draft.

    Returns:
        dict: The schema.
    """
    return _schema(slots, lambda max_chars: {"type": "string", "maxLength": max_chars})


def _schema(slots: DraftSlots, string_type) -> dict:
    def text(max_chars: int) -> dict:
        return {"anyOf": [string_type(max_chars), {"type": "null"}]}

    def named(names: tuple) -> dict:
        return {
            "type": "object",
            "properties": {name: text(MAX_SLOT_CHARS) for name in names},
            "required": list(names),
            "additionalProperties": False,
        }

    properties: dict = {}
    if slots.summary:
        properties["summary"] = text(MAX_SUMMARY_CHARS)
    if slots.description:
        properties["description"] = text(MAX_SLOT_CHARS)
    if slots.params:
        properties["params"] = named(slots.params)
    if slots.returns:
        properties["returns"] = text(MAX_SLOT_CHARS)
    if slots.raises:
        properties["raises"] = named(slots.raises)
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def parse_reply(raw: str) -> DocstringDraft:
    """Parses a provider's JSON reply into a draft, tolerating a surrounding
    Markdown code fence. Anything malformed yields an empty draft.

    Args:
        raw (str): The provider's reply text.

    Returns:
        DocstringDraft: The draft; values are checked again before writing.
    """
    text = (raw or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except ValueError:
        return DocstringDraft()
    return (
        draft_from_payload(payload) if isinstance(payload, dict) else DocstringDraft()
    )


def draft_from_payload(payload: Dict[str, Any]) -> DocstringDraft:
    """Keeps only string values of the expected shape from a parsed reply.

    Args:
        payload (Dict[str, Any]): The parsed reply.

    Returns:
        DocstringDraft: The draft; values are checked again before writing.
    """
    return DocstringDraft(
        summary=_str_or_none(payload.get("summary")),
        description=_str_or_none(payload.get("description")),
        params=_str_map(payload.get("params")),
        returns=_str_or_none(payload.get("returns")),
        raises=_str_map(payload.get("raises")),
    )


def _str_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _str_map(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}
