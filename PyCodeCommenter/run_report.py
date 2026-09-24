"""What a generate run did, for the summary printed at the end of it.

Counted from the tagged parts the generator builds (see
``function_doc.Origin``), not by searching the output text, so the numbers
are exact. Facts and AI-drafted lines count only in docstrings this run
wrote or changed; gaps count everywhere, since they are what's left to do.
"""

from dataclasses import dataclass, fields
from typing import List

try:
    from .function_doc import ClassDoc, FunctionDoc, Origin
    from .inference import GUESS_MARKER
except (ImportError, ValueError):
    from function_doc import ClassDoc, FunctionDoc, Origin
    from inference import GUESS_MARKER

# Facts too routine to be worth counting: a constructor's fixed summary, and
# "returns nothing".
_ROUTINE_FACTS = ("Initialize the class.", "None.")


@dataclass
class GenerationReport:
    """Counts for one file, or (after :meth:`merge`) a whole run.

    Attributes:
        files (int): Files processed.
        new (int): Docstrings written where there were none.
        updated (int): Existing docstrings that changed.
        unchanged (int): Existing docstrings left exactly as they were.
        facts (int): Parts stated from the code itself (raise conditions,
            boolean return conditions, name-based descriptions).
        ai_lines (int): Lines drafted by AI in this run.
        todos (int): Gaps left as the guess marker.
        from_comments (int): Docstrings taken from the comment above them.
    """

    files: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    facts: int = 0
    ai_lines: int = 0
    todos: int = 0
    from_comments: int = 0

    def record_function(self, doc: FunctionDoc, outcome: str) -> None:
        """Counts one function's docstring.

        Args:
            doc (FunctionDoc): Its parts.
            outcome (str): ``"new"``, ``"updated"`` or ``"unchanged"``.
        """
        self._record_outcome(outcome)
        parts = doc.parts()
        self.todos += sum(p.origin == Origin.GUESS for p in parts)
        if outcome == "unchanged":
            return
        self.ai_lines += sum(p.origin == Origin.AI for p in parts)
        self.facts += sum(
            p.origin == Origin.FACT and p.text not in _ROUTINE_FACTS for p in parts
        )

    def record_class(self, doc: ClassDoc, outcome: str) -> None:
        """Counts one class's docstring.

        Args:
            doc (ClassDoc): Its parts.
            outcome (str): ``"new"``, ``"updated"`` or ``"unchanged"``.
        """
        self._record_outcome(outcome)
        self.todos += sum(GUESS_MARKER in a.text for a in doc.attributes)

    def merge(self, other: "GenerationReport") -> None:
        """Adds another report's counts to this one."""
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    def summary_lines(self, preview: bool, ai_used: bool) -> List[str]:
        """The summary, in plain words, with a suggested next step.

        Args:
            preview (bool): The run only showed changes (``--dry-run``), so
                the wording says what *would* be written.
            ai_used (bool): ``--ai-draft`` was on for this run.

        Returns:
            List[str]: The lines to print.
        """
        if not (self.new or self.updated or self.unchanged):
            return ["Summary: no functions or classes found."]
        would = "would be " if preview else ""
        head = [f"{_count(self.new, 'docstring')} {would}written"]
        if self.updated:
            head.append(f"{self.updated} {would}updated (your text kept)")
        if self.unchanged:
            head.append(f"{self.unchanged} already complete")
        lines = ["Summary: " + ", ".join(head) + "."]
        if self.facts:
            lines.append(
                f"  {_count(self.facts, 'detail')} taken straight from the code"
            )
        if self.ai_lines:
            lines.append(
                f"  {_count(self.ai_lines, 'line')} drafted by AI, "
                'marked "(AI-drafted, unreviewed)"'
            )
        if self.from_comments:
            noun = "docstring" if self.from_comments == 1 else "docstrings"
            where = (
                "the comment above it (comment"
                if self.from_comments == 1
                else ("the comments above them (comments")
            )
            lines.append(
                f"  {self.from_comments} {noun} taken from {where} left in place)"
            )
        if self.todos:
            lines.append(
                f'  {_count(self.todos, "gap")} left as "TODO(pycodecommenter)" '
                "for you to fill"
            )
        lines.append("Next: " + self._next_step(ai_used))
        return lines

    def _next_step(self, ai_used: bool) -> str:
        if self.ai_lines:
            return (
                'review the AI-drafted lines (search for "AI-drafted, '
                'unreviewed"), then run `pycodecommenter validate`.'
            )
        if self.todos and not ai_used:
            return (
                "fill in the gaps, or add --ai-draft to have them drafted; then "
                "run `pycodecommenter validate`."
            )
        return "run `pycodecommenter validate` to keep the docstrings accurate."

    def _record_outcome(self, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


__all__ = ["GenerationReport"]
