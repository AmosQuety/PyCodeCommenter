"""Pluggable description-provider interface for PyCodeCommenter.

This module is the shared boundary between the deterministic generator and
the opt-in AI-drafting paths, which both fill the same free-text slots in a
generated docstring:

- The deterministic default: ``PyCodeCommenter(description_provider=None)``
  never consults a provider, so gaps keep their
  gap markers. :class:`NullDescriptionProvider` is an explicit provider that
  always declines, with the same result.
- The opt-in, AI-assisted paths, which draft descriptions that no amount of
  AST pattern-matching can reach. The generator itself never calls a model:
  a provider does. :class:`~PyCodeCommenter.remote_provider.
  RemoteDescriptionProvider` calls the hosted backend service, and the
  providers in :mod:`PyCodeCommenter.direct_providers` call a vendor's API
  with the user's own key.

A provider is only ever consulted when a caller constructs
``PyCodeCommenter(description_provider=...)``. Every CLI command that
doesn't pass ``--ai-draft`` passes none, so this path is inert unless a
caller opts in.
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
    """Everything the AST knows about one function, gathered into one value.

    A description provider drafts from real facts about what the code does,
    never from the function's name alone.

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
    """The parts of one docstring a provider is asked to draft.

    Only parts that would otherwise be a gap marker, or say nothing beyond
    the type, are requested.

    Attributes:
        summary (bool): Draft the one-line summary.
        description (bool): Draft the description paragraph.
        params (Tuple[str, ...]): Names of the parameters to describe.
        returns (bool): Draft the Returns text.
        raises (Tuple[str, ...]): Names of the exceptions to describe.
    """

    summary: bool = False
    description: bool = False
    params: Tuple[str, ...] = ()
    returns: bool = False
    raises: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        """Say whether nothing is requested.

        Returns:
            bool: ``True`` if no part is to be drafted.
        """
        return not (
            self.summary
            or self.description
            or self.params
            or self.returns
            or self.raises
        )


@dataclass(frozen=True)
class KnownText:
    """Docstring text already settled for the function.

    It is the author's words or facts read off the code, given to the
    provider for consistency and never for it to rewrite.

    Attributes:
        params (Dict[str, str]): Settled parameter text, by name.
        returns (Optional[str]): Settled Returns text, if any.
        raises (Dict[str, str]): Settled exception text, by exception name.
    """

    params: Dict[str, str] = field(default_factory=dict)
    returns: Optional[str] = None
    raises: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocstringDraft:
    """A provider's answer for a function.

    Any part may be missing; unrequested parts are ignored, and every value
    is checked again before it's written.

    Attributes:
        summary (Optional[str]): The drafted one-line summary.
        description (Optional[str]): The drafted description paragraph.
        params (Dict[str, str]): Drafted parameter text, by name.
        returns (Optional[str]): The drafted Returns text.
        raises (Dict[str, str]): Drafted exception text, by exception name.
        failed (bool): The request itself failed, as opposed to the model
            answering with nothing.
    """

    summary: Optional[str] = None
    description: Optional[str] = None
    params: Dict[str, str] = field(default_factory=dict)
    returns: Optional[str] = None
    raises: Dict[str, str] = field(default_factory=dict)
    # True when the request itself failed (network or service error), as
    # opposed to the model answering with nothing: the run summary tells the
    # two apart.
    failed: bool = False


@dataclass(frozen=True)
class ClassContext:
    """What the AST knows about one class, for drafting its docstring.

    Attributes:
        name (str): The class name.
        bases (List[str]): Its base classes, as written.
        attributes (List[ParameterFact]): The attributes the docstring
            lists, with their inferred types (``default`` is unused).
        source (str): An outline of the class: its header, class-level
            statements, ``__init__`` in full, and the other methods as
            signatures only.
    """

    name: str
    bases: List[str]
    attributes: List[ParameterFact]
    source: str


@dataclass(frozen=True)
class ClassSlots:
    """The parts of a class docstring a provider is asked to draft.

    Attributes:
        summary (bool): Draft the one-line summary.
        attributes (Tuple[str, ...]): Names of the attributes to describe.
    """

    summary: bool = False
    attributes: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        """Say whether nothing is requested.

        Returns:
            bool: ``True`` if no part is to be drafted.
        """
        return not (self.summary or self.attributes)


@dataclass(frozen=True)
class ClassDraft:
    """A provider's answer for a class.

    Any part may be missing; every value is checked again before it's
    written.

    Attributes:
        summary (Optional[str]): The drafted one-line summary.
        attributes (Dict[str, str]): Drafted attribute text, by name.
        failed (bool): The request itself failed; see
            :attr:`DocstringDraft.failed`.
    """

    summary: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    failed: bool = False  # see DocstringDraft.failed


class DraftingStopped(Exception):
    """The provider can't draft anything more in this run.

    For example the daily allowance is spent. Unlike an ordinary failure
    (which only skips one function), this ends drafting for the rest of the
    run.

    Attributes:
        reason (str): A machine-readable reason, for example
            ``"user_daily_limit_reached"``.
        message (str): A human-readable explanation to show the user.
    """

    def __init__(self, reason: str, message: str):
        """Create the exception.

        Args:
            reason (str): A machine-readable reason.
            message (str): A human-readable explanation to show the user.
        """
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

    def draft_class_docstring(
        self, context: ClassContext, known: Dict[str, str], slots: ClassSlots
    ) -> ClassDraft:
        """Draft the requested parts of one class's docstring.

        Providers written before class drafting existed inherit this, which
        declines everything: the class keeps its gap markers.

        Args:
            context (ClassContext): The class's AST-derived facts.
            known (Dict[str, str]): Attribute text already settled, by name.
            slots (ClassSlots): The parts to draft.

        Returns:
            ClassDraft: Whatever could be drafted; may be empty.

        Raises:
            DraftingStopped: Drafting can't continue for the rest of the run.
        """
        return ClassDraft()


class SwitchOnStop(DescriptionProvider):
    """Wrap a provider and ask for a replacement the first time it stops.

    When the provider stops (for example, the free daily allowance is spent)
    the replacement, typically the user's own API key, carries on from the
    same function.

    The replacement is asked for once per run. If none is given, the
    original stop propagates and drafting ends for the run as usual.

    Attributes:
        on_stop (Callable[[DraftingStopped], Optional[DescriptionProvider]]):
            Called with the reason drafting stopped; returns the provider to
            continue with, or ``None`` to stop.
        stopped (Optional[DraftingStopped]): Why drafting ended for the run,
            once it has.
        _active (DescriptionProvider): The provider drafting now.
        _switched (bool): Whether the hand-over has already happened.
    """

    def __init__(
        self,
        primary: DescriptionProvider,
        on_stop: Callable[[DraftingStopped], Optional[DescriptionProvider]],
    ):
        """Wrap a provider.

        Args:
            primary (DescriptionProvider): The provider to start with.
            on_stop (Callable[[DraftingStopped], Optional[DescriptionProvider]]):
                Asked for a replacement when ``primary`` stops.
        """
        self._active = primary
        self._switched = False
        self.on_stop = on_stop
        # Why drafting ended for the run, once it has.
        self.stopped: Optional[DraftingStopped] = None

    @property
    def active(self) -> DescriptionProvider:
        """The provider currently doing the drafting.

        Returns:
            DescriptionProvider: The primary provider, or the replacement after
            a hand-over.
        """
        return self._active

    def draft_docstring(
        self, context: FunctionContext, known: KnownText, slots: DraftSlots
    ) -> DocstringDraft:
        """Draft a function's docstring parts with the active provider.

        Args:
            context (FunctionContext): The function's AST-derived facts.
            known (KnownText): Text already settled, for consistency.
            slots (DraftSlots): The parts to draft.

        Returns:
            DocstringDraft: The active provider's draft.

        Raises:
            DraftingStopped: If the provider stops and no replacement is given, or
                the replacement stops too.
        """
        return self._call("draft_docstring", context, known, slots)

    def draft_class_docstring(
        self, context: ClassContext, known: Dict[str, str], slots: ClassSlots
    ) -> ClassDraft:
        """Draft a class's docstring parts with the active provider.

        Args:
            context (ClassContext): The class's AST-derived facts.
            known (Dict[str, str]): Attribute text already settled, by name.
            slots (ClassSlots): The parts to draft.

        Returns:
            ClassDraft: The active provider's draft.

        Raises:
            DraftingStopped: If the provider stops and no replacement is given, or
                the replacement stops too.
        """
        return self._call("draft_class_docstring", context, known, slots)

    def _call(self, method: str, *arguments):
        """Call a method on the active provider, handing over once if it stops.

        On a stop, asks ``on_stop`` for a replacement and repeats the same call
        on it.

        Args:
            method (str): The name of the provider method to call.
            *arguments: The arguments to pass to it.

        Returns:
            Any: What the method returned.

        Raises:
            DraftingStopped: If the provider stops and no replacement is given, or
                the replacement stops too; recorded in ``stopped``.
        """
        try:
            return getattr(self._active, method)(*arguments)
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
            return self._call(method, *arguments)


class NullDescriptionProvider(DescriptionProvider):
    """A provider that always declines.

    Using it gives the same result as passing no provider at all: nothing is
    drafted and every gap keeps its marker.
    """

    def draft_function_description(self, context: FunctionContext) -> Optional[str]:
        """Decline to draft anything.

        Args:
            context (FunctionContext): The function's AST-derived facts (unused).

        Returns:
            Optional[str]: Always ``None``.
        """
        return None


__all__ = [
    "ClassContext",
    "ClassDraft",
    "ClassSlots",
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
