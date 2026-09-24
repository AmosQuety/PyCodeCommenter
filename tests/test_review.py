"""`pycodecommenter review`: step through AI-drafted lines, TODO gaps, and
comments a docstring now repeats; accept, edit, fill, or remove -- never
touching code, and never removing a comment without an explicit yes."""

import ast
import sys

from PyCodeCommenter.cli import main
from PyCodeCommenter.review import (
    apply_review,
    find_review_items,
)

MARK = "(AI-drafted, unreviewed)"
TODO = "TODO(pycodecommenter)"

SOURCE = f'''# Add two numbers.
def add(a, b):
    """Add two numbers.

    Args:
        a (Any): The first number. {MARK}
        b (Any): {TODO}: describe. (default: 0)

    Returns:
        Any: The sum. {MARK}
    """
    return a + b


def check(x):
    """Check x. {MARK}

    Raises:
        ValueError: {TODO}: describe when this is raised.
    """
    raise ValueError(x)
'''


def kinds(items):
    return [(i.kind, i.line) for i in items]


# ---------------------------------------------------------------------------
# Finding items
# ---------------------------------------------------------------------------


def test_finds_ai_lines_todos_and_repeated_comments_in_file_order():
    items = find_review_items(SOURCE)

    assert kinds(items) == [
        ("comment", 1),
        ("ai", 6),
        ("todo", 7),
        ("ai", 10),
        ("ai", 16),
        ("todo", 19),
    ]
    assert items[1].definition == "add"
    assert items[1].text == "The first number."


def test_comment_that_differs_from_the_docstring_is_not_offered():
    code = '# Something else.\ndef f():\n    """Real docstring."""\n'

    assert find_review_items(code) == []


def test_text_outside_docstrings_is_ignored():
    code = f'x = "{MARK}"  # {TODO}: describe\n'

    assert find_review_items(code) == []


# ---------------------------------------------------------------------------
# Applying decisions
# ---------------------------------------------------------------------------


def test_accept_removes_only_the_label():
    items = find_review_items(SOURCE)
    result = apply_review(SOURCE, [(items[1], ("accept", None))])

    assert "        a (Any): The first number.\n" in result


def test_edit_replaces_the_text_and_keeps_the_entry_and_default():
    source = SOURCE.replace(
        "The first number. " + MARK, "The first number. " + MARK + " (default: 1)"
    )
    items = find_review_items(source)
    result = apply_review(source, [(items[1], ("edit", "Left operand."))])

    assert "        a (Any): Left operand. (default: 1)\n" in result


def test_edit_of_a_summary_keeps_the_opening_quotes():
    items = find_review_items(SOURCE)
    check_summary = items[4]
    result = apply_review(SOURCE, [(check_summary, ("edit", "Validate x"))])

    assert '    """Validate x.\n' in result


def test_fill_replaces_the_todo_including_its_raises_wording():
    items = find_review_items(SOURCE)
    result = apply_review(
        SOURCE,
        [(items[2], ("fill", "Right operand")), (items[5], ("fill", "Always."))],
    )

    assert "        b (Any): Right operand. (default: 0)\n" in result
    assert "        ValueError: Always.\n" in result
    assert TODO not in result


def test_remove_comment_deletes_only_those_lines():
    items = find_review_items(SOURCE)
    result = apply_review(SOURCE, [(items[0], ("remove", None))])

    assert result.startswith("def add(a, b):\n")
    ast.parse(result)


def test_skip_changes_nothing():
    items = find_review_items(SOURCE)

    assert apply_review(SOURCE, [(item, ("skip", None)) for item in items]) == SOURCE


def test_every_decision_together_leaves_valid_code_with_the_same_logic():
    items = find_review_items(SOURCE)
    decisions = [
        ("remove", None),
        ("accept", None),
        ("fill", "Right operand"),
        ("edit", "Their sum"),
        ("accept", None),
        ("fill", "Always"),
    ]
    result = apply_review(SOURCE, list(zip(items, decisions)))

    assert MARK not in result and TODO not in result
    compile(result, "m.py", "exec")


def test_crlf_line_endings_are_kept():
    source = SOURCE.replace("\n", "\r\n")
    items = find_review_items(source)
    result = apply_review(source, [(items[1], ("accept", None))])

    assert "\r\n" in result and "\n" not in result.replace("\r\n", "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_review(path, monkeypatch, capsys, answers, interactive=True):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda: next(replies))
    monkeypatch.setattr("PyCodeCommenter.review.is_interactive", lambda: interactive)
    monkeypatch.setattr(sys, "argv", ["pycodecommenter", "review", str(path)])
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code or 0
    return code, capsys.readouterr().out


def test_review_session_applies_answers_and_saves(tmp_path, monkeypatch, capsys):
    target = tmp_path / "m.py"
    target.write_text(SOURCE)

    code, out = run_review(
        target,
        monkeypatch,
        capsys,
        ["y", "a", "f", "Right operand", "e", "Their sum", "a", "s"],
    )

    result = target.read_text()
    assert code == 0
    assert not result.startswith("# Add two numbers.")
    assert "a (Any): The first number.\n" in result
    assert "b (Any): Right operand. (default: 0)" in result
    assert "Any: Their sum.\n" in result
    assert f"ValueError: {TODO}" in result  # skipped
    assert "Saved" in out


def test_comment_removal_defaults_to_no(tmp_path, monkeypatch, capsys):
    target = tmp_path / "m.py"
    target.write_text(SOURCE)

    run_review(target, monkeypatch, capsys, ["", "q"])

    assert target.read_text().startswith("# Add two numbers.")


def test_unsafe_text_is_refused_and_asked_again(tmp_path, monkeypatch, capsys):
    target = tmp_path / "m.py"
    target.write_text(SOURCE)

    _, out = run_review(
        target, monkeypatch, capsys, ["n", "e", 'bad """ text', "Good text", "q"]
    )

    assert "Good text." in target.read_text()
    assert "can't contain" in out


def test_quit_keeps_what_was_decided_so_far(tmp_path, monkeypatch, capsys):
    target = tmp_path / "m.py"
    target.write_text(SOURCE)

    run_review(target, monkeypatch, capsys, ["n", "a", "q"])

    result = target.read_text()
    assert "a (Any): The first number.\n" in result
    assert f"Any: The sum. {MARK}" in result


def test_without_a_terminal_it_only_lists(tmp_path, monkeypatch, capsys):
    target = tmp_path / "m.py"
    target.write_text(SOURCE)

    code, out = run_review(target, monkeypatch, capsys, [], interactive=False)

    assert target.read_text() == SOURCE
    assert "3 AI-drafted lines, 2 gaps, 1 repeated comment" in out
    assert code == 0


def test_nothing_to_review(tmp_path, monkeypatch, capsys):
    target = tmp_path / "m.py"
    target.write_text('def f():\n    """Done."""\n')

    _, out = run_review(target, monkeypatch, capsys, [])

    assert "Nothing to review" in out
