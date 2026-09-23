"""Pluggable description-provider interface for PyCodeCommenter.

This module is the shared boundary between two paths that both end up
filling the same "free-text description" slot in a generated docstring:

- The deterministic default (:class:`NullDescriptionProvider`), which is
  the tool's entire behavior unless a caller explicitly opts into AI
  drafting -- it always declines, and generation falls back to leaving the
  description slot empty.
- The opt-in, AI-assisted path (:class:`~PyCodeCommenter.remote_provider.
  RemoteDescriptionProvider`), which drafts real semantic descriptions
  ("the discounted price after applying rate") that no amount of AST
  pattern-matching can reach, by calling a hosted backend service. This
  package itself never calls an AI model directly -- see remote_provider.py
  and the `pycodecommenter-ai-backend` project for why.

A provider is only ever consulted when a caller explicitly constructs
``PyCodeCommenter(description_provider=...)``; the default constructor and
every CLI command that doesn't pass ``--ai-draft`` never pass one, so this
path is entirely inert unless a caller explicitly opts in.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ParameterFact:
    """One parameter's already-extracted AST facts.

    Attributes:
        name (str): The parameter's display name (as it appears in Args:).
        type_hint (str): The statically inferred type, or ``"any"``.
        default (Optional[str]): The default value's source representation,
            or ``None`` if the parameter has no default.
    """

    name: str
    type_hint: str
    default: Optional[str] = None


@dataclass(frozen=True)
class FunctionContext:
    """Everything the AST already knows about one function, gathered into a
    single value so a description provider drafts from real facts about
    what the code does -- never from the function's name alone.

    Attributes:
        name (str): The function's name.
        parameters (List[ParameterFact]): Its parameters, in signature order.
        return_type (str): The statically inferred return (or yield) type.
        is_generator (bool): Whether the function's own body yields.
        raised_exceptions (List[str]): Exception class names its own body
            raises (see ``commenter.py``'s ``_get_raised_exceptions``).
        source (str): The function's own source text, def line through its
            last body statement.
    """

    name: str
    parameters: List[ParameterFact]
    return_type: str
    is_generator: bool
    raised_exceptions: List[str]
    source: str


@dataclass(frozen=True)
class DraftSlots:
    """The parts of one docstring a provider is asked to draft: only parts
    that would otherwise be a TODO marker or say nothing beyond the type."""

    summary: bool = False
    description: bool = False
    params: Tuple[str, ...] = ()
    returns: bool = False
    raises: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.summary
            or self.description
            or self.params
            or self.returns
            or self.raises
        )


@dataclass(frozen=True)
class KnownText:
    """Docstring text already settled for the function (the author's words
    or facts read off the code), given to the provider for consistency --
    never for it to rewrite."""

    params: Dict[str, str] = field(default_factory=dict)
    returns: Optional[str] = None
    raises: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocstringDraft:
    """A provider's answer. Any part may be missing; unrequested parts are
    ignored, and every value is checked again before it's written."""

    summary: Optional[str] = None
    description: Optional[str] = None
    params: Dict[str, str] = field(default_factory=dict)
    returns: Optional[str] = None
    raises: Dict[str, str] = field(default_factory=dict)


class DraftingStopped(Exception):
    """The provider can't draft anything more in this run -- for example the
    daily allowance is spent. Unlike an ordinary failure (which only skips
    one function), this ends drafting for the rest of the run.

    Attributes:
        reason (str): A machine-readable reason, e.g.
            ``"user_daily_limit_reached"``.
        message (str): A human-readable explanation to show the user.
    """

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


class DescriptionProvider(ABC):
    """A source of drafted docstring text.

    The generator calls :meth:`draft_docstring` once per function that has
    gaps. Implementations override that, or -- for providers written before
    it existed -- only :meth:`draft_function_description`, which the
    default :meth:`draft_docstring` uses for the description paragraph.

    Every method fails closed: returning nothing (or raising) leaves the
    gaps as they are. Never retry into a fabricated answer on error,
    timeout, or a low-confidence result -- declining is always the correct
    response to uncertainty here.
    """

    def draft_function_description(self, context: FunctionContext) -> Optional[str]:
        """Return a drafted description paragraph, or ``None`` to decline.

        Args:
            context (FunctionContext): The function's AST-derived facts.

        Returns:
            Optional[str]: A drafted description, or ``None``.
        """
        return None

    def draft_docstring(
        self, context: FunctionContext, known: KnownText, slots: DraftSlots
    ) -> DocstringDraft:
        """Drafts the requested parts of one function's docstring.

        Args:
            context (FunctionContext): The function's AST-derived facts.
            known (KnownText): Text already settled, for consistency.
            slots (DraftSlots): The parts to draft.

        Returns:
            DocstringDraft: Whatever could be drafted; may be empty.

        Raises:
            DraftingStopped: Drafting can't continue for the rest of the run.
        """
        if not slots.description:
            return DocstringDraft()
        return DocstringDraft(description=self.draft_function_description(context))


class SwitchOnStop(DescriptionProvider):
    """Wraps a provider and, the first time it stops (for example, the free
    daily allowance is spent), asks for a replacement -- typically the
    user's own API key -- and carries on with it from the same function.

    The replacement is asked for once per run. If none is given, the
    original stop propagates and drafting ends for the run as usual.

    Attributes:
        on_stop (Callable[[DraftingStopped], Optional[DescriptionProvider]]):
            Called with the reason drafting stopped; returns the provider to
            continue with, or ``None`` to stop.
    """

    def __init__(
        self,
        primary: DescriptionProvider,
        on_stop: Callable[[DraftingStopped], Optional[DescriptionProvider]],
    ):
        self._active = primary
        self._switched = False
        self.on_stop = on_stop
        # Why drafting ended for the run, once it has.
        self.stopped: Optional[DraftingStopped] = None

    @property
    def active(self) -> DescriptionProvider:
        """The provider currently doing the drafting."""
        return self._active

    def draft_docstring(
        self, context: FunctionContext, known: KnownText, slots: DraftSlots
    ) -> DocstringDraft:
        try:
            return self._active.draft_docstring(context, known, slots)
        except DraftingStopped as stopped:
            if self._switched:
                self.stopped = stopped
                raise
            self._switched = True
            replacement = self.on_stop(stopped)
            if replacement is None:
                self.stopped = stopped
                raise
            self._active = replacement
            return self.draft_docstring(context, known, slots)


class NullDescriptionProvider(DescriptionProvider):
    """The default provider: always declines.

    This preserves the tool's deterministic behavior -- a caller who never
    passes a ``description_provider`` gets a ``NullDescriptionProvider`` and
    sees no difference from a build with no AI drafting at all.
    """

    def draft_function_description(self, context: FunctionContext) -> Optional[str]:
        return None


__all__ = [
    "ParameterFact",
    "FunctionContext",
    "DraftSlots",
    "KnownText",
    "DocstringDraft",
    "DraftingStopped",
    "DescriptionProvider",
    "SwitchOnStop",
    "NullDescriptionProvider",
]
