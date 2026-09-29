"""The interactive `pycodecommenter review` session.

Goes through each file's review items (see ``review.py``), asks what to do
with each, and saves a file only after its result passes the safety check.
Without a terminal -- or with ``--list`` -- it lists the items and changes
nothing.
"""

from pathlib import Path
from typing import List, Set, Tuple

try:
    from . import review
    from .review import AI, COMMENT, TODO, ReviewItem
except (ImportError, ValueError):
    import review
    from review import AI, COMMENT, TODO, ReviewItem

_PROMPTS = {
    AI: (
        "[a]ccept, [e]dit, [s]kip, [q]uit: ",
        {"a": "accept", "e": "edit", "s": "skip"},
    ),
    TODO: ("[f]ill, [s]kip, [q]uit: ", {"f": "fill", "s": "skip"}),
    COMMENT: (
        "Remove this comment now that the docstring says the same? [y/N/q]: ",
        {"y": "remove", "n": "skip", "": "skip"},
    ),
}
_LABELS = {AI: "AI-drafted", TODO: "gap", COMMENT: "repeated comment"}


class QuitReview(Exception):
    """The user asked to stop; decisions made so far are still saved.

    The decisions made before quitting travel in ``args[0]``.
    """


def run_review(files: List[str], list_only: bool) -> None:
    """Review files interactively, or list what needs review.

    Files with nothing to review are skipped. Without a terminal, or with
    ``list_only``, the items are printed and no file is changed. Otherwise each
    file is saved (if anything changed) before the next one is asked about, so
    quitting keeps the decisions already made.

    Args:
        files (List[str]): The Python files to review.
        list_only (bool): List items without asking anything (also the
            behaviour when there is no terminal).
    """
    found = [(path, _read(path)) for path in files]
    found = [(path, source, review.find_review_items(source)) for path, source in found]
    found = [entry for entry in found if entry[2]]
    if not found:
        where = ", ".join(files) if len(files) < 4 else f"{len(files)} files"
        print(f"Nothing to review in {where}.")
        return
    if list_only or not review.is_interactive():
        _list(found)
        return
    for path, source, items in found:
        try:
            decisions = _ask_about(path, source, items)
            stopped = False
        except QuitReview as quit_now:
            decisions, stopped = quit_now.args[0], True
        _save(path, source, decisions)
        if stopped:
            return


def _list(found) -> None:
    """Print one line per review item and a summary count.

    Args:
        found: ``(path, source, items)`` tuples for the files that have items.
    """
    counts = {AI: 0, TODO: 0, COMMENT: 0}
    for path, _, items in found:
        for item in items:
            counts[item.kind] += 1
            print(
                f"{path}:{item.line}  {_LABELS[item.kind]}  {_where(item)}{item.text}"
            )
    parts = [
        _plural(counts[AI], "AI-drafted line"),
        _plural(counts[TODO], "gap"),
        _plural(counts[COMMENT], "repeated comment"),
    ]
    print(
        f"\n{', '.join(parts)} to review in {_plural(len(found), 'file')}. "
        "Run `pycodecommenter review` in a terminal to go through them."
    )


def _ask_about(
    path: str, source: str, items: List[ReviewItem]
) -> List[Tuple[ReviewItem, tuple]]:
    """Ask what to do about each item in one file.

    For a function with several AI-drafted lines the whole docstring is
    shown first and one answer can accept all of that function's AI lines
    (only those: gaps and comments are still asked one by one).

    Args:
        path (str): Path of the file, used in the prompts.
        source (str): The file's text.
        items (List[ReviewItem]): The file's review items, in source order.

    Returns:
        List[Tuple[ReviewItem, tuple]]: Each answered item with its
        ``(action, text)`` decision.

    Raises:
        QuitReview: If the user quits; carries the decisions made so far.
    """
    print(f"\n{path}: {_plural(len(items), 'item')} to review")
    lines = source.replace("\r\n", "\n").split("\n")
    decisions: List[Tuple[ReviewItem, tuple]] = []
    accepted_together: Set[int] = set()
    shown: Set[int] = set()
    for index, item in enumerate(items):
        if index in accepted_together:
            continue
        waiting = _ai_items_waiting(items, index, accepted_together)
        if len(waiting) > 1 and item.docstring_line not in shown:
            shown.add(item.docstring_line)
            _show_docstring(lines, item)
        print(f"\n{path}:{item.line} {_where(item)}")
        print(f"  {_LABELS[item.kind]}: {item.text}")
        action = _choose(item.kind, len(waiting))
        if action == "quit":
            raise QuitReview(decisions)
        if action == "accept_all":
            decisions += [(items[j], ("accept", None)) for j in waiting]
            accepted_together.update(waiting)
            continue
        text = _ask_text() if action in ("edit", "fill") else None
        decisions.append((item, (action, text)))
    return decisions


def _ai_items_waiting(items, index: int, decided: Set[int]) -> List[int]:
    """Find the undecided AI lines of one item's docstring, from that item on.

    Args:
        items: The file's review items.
        index (int): Position of the item being asked about.
        decided (Set[int]): Positions already accepted together.

    Returns:
        List[int]: Positions of the undecided AI lines sharing the item's
        docstring. Empty unless the item is itself an AI line.
    """
    item = items[index]
    if item.kind != AI:
        return []
    return [
        j
        for j in range(index, len(items))
        if items[j].kind == AI
        and items[j].docstring_line == item.docstring_line
        and j not in decided
    ]


def _show_docstring(lines: List[str], item: ReviewItem) -> None:
    """Print the docstring an item belongs to, so the user sees the context.

    Args:
        lines (List[str]): The file's lines.
        item (ReviewItem): An item inside the docstring to show.
    """
    print(f"\nThe docstring of {item.definition or 'the module'}():")
    for line in lines[item.docstring_line - 1 : item.docstring_end]:
        print(f"  | {line}")


def _choose(kind: str, waiting_in_function: int = 0) -> str:
    """Ask until the user gives a valid answer for this kind of item.

    Args:
        kind (str): The item kind: AI, gap or repeated comment.
        waiting_in_function (int): How many undecided AI lines the function's
            docstring has. When more than one, a capital ``A`` accepts them all.

    Returns:
        str: The action: accept, accept_all, edit, fill, remove, skip or quit.
    """
    prompt, choices = _PROMPTS[kind]
    if waiting_in_function > 1:
        prompt = (
            f"[a]ccept, [A]ccept all {waiting_in_function} AI-drafted lines "
            "in this function, [e]dit, [s]kip, [q]uit: "
        )
    while True:
        answer = _ask(prompt)
        if answer == "A" and waiting_in_function > 1:
            return "accept_all"
        answer = answer.lower()
        if answer == "q":
            return "quit"
        if answer in choices:
            return choices[answer]


def _ask_text() -> str:
    """Ask for replacement text until it passes the safety check.

    Returns:
        str: Text that ``review.text_problem`` finds no fault with.
    """
    while True:
        text = _ask("New text: ")
        problem = review.text_problem(text)
        if problem is None:
            return text
        print(f"  {problem} Try again.")


def _save(path: str, source: str, decisions) -> None:
    """Apply the decisions to a file, if the result passes the safety check.

    The file is written only when at least one decision changes something and
    ``review.verify_review`` confirms that only docstrings and comments
    differ. Otherwise the file is left as it was and the reason is printed.

    Args:
        path (str): The file to write.
        source (str): The file's original text.
        decisions: ``(item, (action, text))`` pairs; skips are ignored.
    """
    changes = [d for d in decisions if d[1][0] != "skip"]
    if not changes:
        return
    result = review.apply_review(source, changes)
    try:
        review.verify_review(source, result)
    except review.ReviewError as e:
        print(f"Not saved {path}: {e}. Your file is unchanged.")
        return
    Path(path).write_text(result, encoding="utf-8", newline="")
    tally = _tally(changes)
    print(f"\nSaved {path}: {tally}.")


def _tally(changes) -> str:
    """Summarise the decisions, for example ``2 accepted, 1 edited``.

    Args:
        changes: ``(item, (action, text))`` pairs, none of them skips.

    Returns:
        str: Counts per action, in the order the actions first appear.
    """
    names = {
        "accept": "accepted",
        "edit": "edited",
        "fill": "filled",
        "remove": "removed",
    }
    counts: dict = {}
    for _, (action, _) in changes:
        counts[names[action]] = counts.get(names[action], 0) + 1
    return ", ".join(f"{n} {verb}" for verb, n in counts.items())


def _where(item: ReviewItem) -> str:
    """Name the function an item is in, for use in a prompt.

    Args:
        item (ReviewItem): The item.

    Returns:
        str: ``in name(): ``, or an empty string for a module-level item.
    """
    return f"in {item.definition}(): " if item.definition else ""


def _ask(prompt: str) -> str:
    """Show a prompt and read one line from the user.

    Args:
        prompt (str): The text to show, without a trailing newline.

    Returns:
        str: The answer with surrounding whitespace removed.
    """
    print(prompt, end="")
    return input().strip()


def _read(path: str) -> str:
    """Read a file as UTF-8 without translating line endings.

    Args:
        path (str): The file to read.

    Returns:
        str: The file's text, exactly as stored.
    """
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _plural(n: int, noun: str) -> str:
    """Format a count with its noun, adding ``s`` unless the count is one.

    Args:
        n (int): The count.
        noun (str): The singular noun.

    Returns:
        str: For example ``1 gap`` or ``3 gaps``.
    """
    return f"{n} {noun}{'' if n == 1 else 's'}"


__all__ = ["run_review"]
