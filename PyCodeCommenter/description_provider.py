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

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


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


class DescriptionProvider(ABC):
    """A source of free-text function descriptions.

    The deterministic default and the remote AI-backed implementation share
    this one interface and one call site (``commenter.py``'s
    ``_draft_description_via_provider``) -- so an AI provider is a drop-in,
    not a fork of the generation path.
    """

    @abstractmethod
    def draft_function_description(self, context: FunctionContext) -> Optional[str]:
        """Return a drafted description, or ``None`` to decline.

        The call site treats ``None`` and a raised exception identically:
        both fail closed to today's behavior (an empty description slot).
        Implementations should never retry into a fabricated answer on
        error, timeout, or a low-confidence result -- declining is always
        the correct response to uncertainty here.

        Args:
            context (FunctionContext): The function's AST-derived facts.

        Returns:
            Optional[str]: A drafted description, or ``None``.
        """
        raise NotImplementedError


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
    "DescriptionProvider",
    "NullDescriptionProvider",
]
