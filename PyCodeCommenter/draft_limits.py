"""Knowing what an AI run will cost before it starts, and capping it.

An ``--ai-draft`` run makes one request per function or class with gaps, and
running it in the wrong directory spends the hosted allowance (or the user's
own money) on files nobody meant to draft. :func:`count_draft_requests` says
how many requests a run would make without asking any provider, and
:class:`DraftBudget` caps how many it may make (``--max-drafts``).
"""

import logging
from dataclasses import dataclass
from typing import Iterable

try:
    from .commenter import PyCodeCommenter
    from .description_provider import (
        ClassDraft,
        DescriptionProvider,
        DocstringDraft,
    )
except (ImportError, ValueError):
    from commenter import PyCodeCommenter
    from description_provider import ClassDraft, DescriptionProvider, DocstringDraft

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Preflight:
    """What a run would send.

    Attributes:
        files (int): Files that would be processed.
        files_with_gaps (int): Files with at least one gap to draft.
        requests (int): Functions and classes with gaps: one request each.
    """

    files: int
    files_with_gaps: int
    requests: int


class _Counter(DescriptionProvider):
    """Counts the requests a run would make and answers nothing, so counting
    uses the generator's own rules for what is a gap."""

    def __init__(self):
        self.requests = 0

    def draft_docstring(self, context, known, slots) -> DocstringDraft:
        self.requests += 1
        return DocstringDraft()

    def draft_class_docstring(self, context, known, slots) -> ClassDraft:
        self.requests += 1
        return ClassDraft()


def count_draft_requests(
    targets: Iterable[str], include_module_docstrings: bool = False
) -> Preflight:
    """Counts the requests an AI run over these files would make.

    Nothing is sent and nothing is written: the files are generated in
    memory with a provider that only counts. A file that does not parse is
    left out of the count (the real run reports it).

    Args:
        targets (Iterable[str]): The Python files the run would process.
        include_module_docstrings (bool): As for the real run.

    Returns:
        Preflight: The counts.
    """
    files = files_with_gaps = requests = 0
    for target in targets:
        files += 1
        counter = _Counter()
        try:
            commenter = PyCodeCommenter(
                description_provider=counter,
                include_module_docstrings=include_module_docstrings,
            ).from_file(target)
            if not commenter.parsed_code:
                continue
            commenter.get_patched_code()
        except Exception as e:
            logger.warning(f"Could not count drafts for {target}: {e}")
            continue
        requests += counter.requests
        files_with_gaps += bool(counter.requests)
    return Preflight(files, files_with_gaps, requests)


class DraftBudget:
    """A cap on how many AI requests a whole run may make, shared by every
    file. Once a request is refused the budget is *spent*.

    Attributes:
        limit (int): The most requests allowed.
        used (int): Requests granted so far.
        spent (bool): A request was refused because the limit was reached.
    """

    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("A draft limit must be at least 1")
        self.limit = limit
        self.used = 0
        self.spent = False

    def take(self) -> bool:
        """Claims one request; ``False`` (and the budget is spent) if the
        limit has been reached."""
        if self.used >= self.limit:
            self.spent = True
            return False
        self.used += 1
        return True


__all__ = ["DraftBudget", "Preflight", "count_draft_requests"]
