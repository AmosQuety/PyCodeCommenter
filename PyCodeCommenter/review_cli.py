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
    """The user asked to stop; decisions made so far are still saved."""


def run_review(files: List[str], list_only: bool) -> None:
    """Reviews files interactively, or lists what needs review.

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
    """Asks about each item; raises QuitReview (carrying the decisions so
    far) if the user quits.

    For a function with several AI-drafted lines the whole docstring is
    shown first and one answer can accept all of that function's AI lines
    (only those: gaps and comments are still asked one by one).
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
    """Indexes of the undecided AI lines of ``items[index]``'s docstring,
    from that item on. Empty unless the item is itself an AI line."""
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
    print(f"\nThe docstring of {item.definition or 'the module'}():")
    for line in lines[item.docstring_line - 1 : item.docstring_end]:
        print(f"  | {line}")


def _choose(kind: str, waiting_in_function: int = 0) -> str:
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
    while True:
        text = _ask("New text: ")
        problem = review.text_problem(text)
        if problem is None:
            return text
        print(f"  {problem} Try again.")


def _save(path: str, source: str, decisions) -> None:
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
    return f"in {item.definition}(): " if item.definition else ""


def _ask(prompt: str) -> str:
    print(prompt, end="")
    return input().strip()


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


__all__ = ["run_review"]
