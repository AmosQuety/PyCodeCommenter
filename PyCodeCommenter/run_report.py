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
except (ImportError, ValueError):
    from function_doc import ClassDoc, FunctionDoc, Origin

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
        ai_requests (int): Requests that reached a provider (answered or
            failed), one per function or class with gaps.
        ai_declined (int): Requested parts the AI answered with nothing.
        ai_failed (int): Requests that failed (network or service error).
        ai_not_tried (int): Functions and classes with gaps that were never
            asked because drafting had stopped (for example a spent limit).
        ai_withheld (int): Functions and classes not sent to the AI because
            their source looks like it holds a secret.
        dropped_entries (int): Author-written Args entries removed because
            their parameter is no longer in the signature.
    """

    files: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    facts: int = 0
    ai_lines: int = 0
    todos: int = 0
    from_comments: int = 0
    ai_requests: int = 0
    ai_declined: int = 0
    ai_failed: int = 0
    ai_not_tried: int = 0
    ai_withheld: int = 0
    dropped_entries: int = 0

    def record_function(self, doc: FunctionDoc, outcome: str) -> None:
        """Count one function's docstring.

        Gaps are counted whatever the outcome; facts and AI-drafted lines only
        when the docstring was written or changed in this run.

        Args:
            doc (FunctionDoc): Its parts.
            outcome (str): ``"new"``, ``"updated"`` or ``"unchanged"``.
        """
        self._record_outcome(outcome)
        self.dropped_entries += doc.dropped
        parts = doc.parts()
        self.todos += sum(p.origin == Origin.GUESS for p in parts)
        if outcome == "unchanged":
            return
        self.ai_lines += sum(p.origin == Origin.AI for p in parts)
        self.facts += sum(
            p.origin == Origin.FACT and p.text not in _ROUTINE_FACTS for p in parts
        )

    def record_class(self, doc: ClassDoc, outcome: str) -> None:
        """Count one class's docstring.

        Args:
            doc (ClassDoc): Its parts.
            outcome (str): ``"new"``, ``"updated"`` or ``"unchanged"``.
        """
        self._record_outcome(outcome)
        origins = [a.origin for a in doc.attributes] + [doc.summary_origin]
        self.todos += sum(origin == Origin.GUESS for origin in origins)
        if outcome != "unchanged":
            self.ai_lines += sum(origin == Origin.AI for origin in origins)

    def record_draft(self, declined: int, failed: bool) -> None:
        """Count one AI request and how it ended.

        Args:
            declined (int): Requested parts the answer left unfilled.
            failed (bool): The request itself failed; nothing was answered.
        """
        self.ai_requests += 1
        if failed:
            self.ai_failed += 1
        else:
            self.ai_declined += declined

    def record_withheld(self) -> None:
        """Count a function or class kept out of AI drafting as a suspected secret.

        Its source looked like it holds a secret, so it was not sent.
        """
        self.ai_withheld += 1

    def record_not_tried(self) -> None:
        """Count a function or class whose gaps were not asked about.

        Drafting had stopped, for example because a limit was spent.
        """
        self.ai_not_tried += 1

    def merge(self, other: "GenerationReport") -> None:
        """Add another report's counts to this one.

        Args:
            other (GenerationReport): The report to add; it is not changed.
        """
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    def summary_lines(self, preview: bool, ai_used: bool) -> List[str]:
        """Write the summary in plain words, with a suggested next step.

        Args:
            preview (bool): The run only showed changes (``--dry-run``), so the
                wording says what *would* be written.
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
        if self.dropped_entries:
            plural = self.dropped_entries != 1
            verb = "would be" if preview else ("were" if plural else "was")
            lines.append(
                f"  {self.dropped_entries} documented "
                f"{'arguments' if plural else 'argument'} no longer in the "
                f"signature {verb} removed from the docstrings"
            )
        lines += self._ai_problem_lines()
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

    def _ai_problem_lines(self) -> List[str]:
        """Explain why AI drafting left gaps, so "gaps left" is not a mystery.

        Returns:
            List[str]: One line for each of declined parts, failed requests,
            withheld sources and untried requests that is not zero.
        """
        lines = []
        if self.ai_declined:
            lines.append(
                f"  {_count(self.ai_declined, 'part')} the AI declined to write "
                "(the code did not make them clear); they keep their earlier text"
            )
        if self.ai_failed:
            noun = "request" if self.ai_failed == 1 else "requests"
            lines.append(
                f"  {self.ai_failed} {noun} failed (network or service error); "
                "those gaps are unchanged"
            )
        if self.ai_withheld:
            noun = (
                "function or class" if self.ai_withheld == 1 else "functions or classes"
            )
            lines.append(
                f"  {self.ai_withheld} {noun} not sent to the AI because the source "
                "looks like it holds a secret (key, password or token)"
            )
        if self.ai_not_tried:
            noun = (
                "function or class"
                if self.ai_not_tried == 1
                else "functions or classes"
            )
            lines.append(
                f"  {self.ai_not_tried} {noun} not tried because drafting stopped"
            )
        return lines

    def _next_step(self, ai_used: bool) -> str:
        """Suggest what to do after this run.

        Args:
            ai_used (bool): ``--ai-draft`` was on for this run.

        Returns:
            str: The suggestion, which depends on whether there are AI-drafted
            lines, gaps or comment-derived docstrings to deal with.
        """
        if self.ai_lines:
            return (
                "go through the AI-drafted lines with `pycodecommenter review` "
                "(accept, edit or skip each), then run `pycodecommenter validate`."
            )
        if self.todos and not ai_used:
            return (
                "fill the gaps with `pycodecommenter review`, or add --ai-draft "
                "to have them drafted; then run `pycodecommenter validate`."
            )
        if self.from_comments:
            return (
                "`pycodecommenter review` offers to remove comments the new "
                "docstrings now repeat; then run `pycodecommenter validate`."
            )
        return "run `pycodecommenter validate` to keep the docstrings accurate."

    def _record_outcome(self, outcome: str) -> None:
        """Add one to the count named by the outcome.

        Args:
            outcome (str): ``"new"``, ``"updated"`` or ``"unchanged"``.
        """
        setattr(self, outcome, getattr(self, outcome) + 1)


def _count(number: int, noun: str) -> str:
    """Format a count with its noun, adding ``s`` unless the count is one.

    Args:
        number (int): The count.
        noun (str): The singular noun.

    Returns:
        str: For example ``1 gap`` or ``3 gaps``.
    """
    return f"{number} {noun}{'' if number == 1 else 's'}"


__all__ = ["GenerationReport"]
