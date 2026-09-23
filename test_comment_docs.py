"""A `#` comment block written directly above an undocumented function or
class is the author's own description of it: it becomes the docstring, the
comment itself is left in place (the tool never deletes user code), and it
counts as author text, so AI drafting doesn't overwrite it.
"""

import logging

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.comment_docs import comment_block_text
from PyCodeCommenter.description_provider import DescriptionProvider, DocstringDraft

logging.disable(logging.CRITICAL)


def generate(code, provider=None):
    return (
        PyCodeCommenter(description_provider=provider)
        .from_string(code)
        .get_patched_code()
    )


def docstring_of(patched, name):
    return patched.split(f"def {name}", 1)[1].split('"""', 2)[1]


TOTAL_DUE = """# Calculate what the customer owes after VAT and any discount.
# Discount is a flat amount, not a percentage.
def total_due(amount, discount=0):
    return amount * 1.18 - discount
"""


def test_comment_block_becomes_summary_and_description():
    doc = docstring_of(generate(TOTAL_DUE), "total_due")

    assert doc.startswith(
        "Calculate what the customer owes after VAT and any discount.\n\n"
        "    Discount is a flat amount, not a percentage."
    )


def test_the_comment_itself_is_left_in_place():
    patched = generate(TOTAL_DUE)

    assert patched.startswith(
        "# Calculate what the customer owes after VAT and any discount.\n"
        "# Discount is a flat amount, not a percentage.\n"
        "def total_due"
    )


def test_comment_above_decorators_is_used():
    code = "# Cache the parsed config.\n@lru_cache\ndef config():\n    return {}\n"

    assert docstring_of(generate(code), "config").startswith("Cache the parsed config.")


def test_comment_for_a_class_and_a_method():
    code = (
        "# Stores invoices in memory.\n"
        "class Repo:\n"
        "    # Look an invoice up by id.\n"
        "    def get(self, invoice_id):\n"
        "        return None\n"
    )
    patched = generate(code)

    assert '"""Stores invoices in memory.' in patched
    assert '"""Look an invoice up by id.' in patched


def test_existing_docstring_wins_over_the_comment():
    code = '# Old note.\ndef f():\n    """Real docstring."""\n'

    doc = docstring_of(generate(code), "f")

    assert doc.startswith("Real docstring.")
    assert "Old note" not in doc


def test_ai_is_not_asked_to_redo_a_summary_taken_from_a_comment():
    requests = []

    class Recorder(DescriptionProvider):
        def draft_docstring(self, context, known, slots):
            requests.append(slots)
            return DocstringDraft()

    generate(TOTAL_DUE, Recorder())

    [slots] = requests
    assert slots.summary is False and slots.description is False
    assert slots.params == ("amount", "discount")  # still gaps


def test_regeneration_is_idempotent():
    once = generate(TOTAL_DUE)

    assert generate(once) == once


def test_comment_use_is_recorded_for_the_run_report():
    commenter = PyCodeCommenter().from_string(TOTAL_DUE)
    commenter.get_patched_code()

    assert [
        (c.name, c.first_line, c.last_line) for c in commenter.comment_docstrings
    ] == [("total_due", 1, 2)]


# ---------------------------------------------------------------------------
# What is not a description
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        # A blank line separates the comment from the function.
        "# Unrelated note.\n\ndef f():\n    return 1\n",
        # A trailing comment on the line above belongs to that line.
        "x = 1  # the answer\ndef f():\n    return 1\n",
        # A comment directly after code isn't a standalone block.
        "x = 1\n# About x, really.\ndef f():\n    return 1\n",
    ],
)
def test_comments_not_attached_to_the_function_are_ignored(code):
    assert '"""F.' in generate(code)


@pytest.mark.parametrize(
    "lines, expected",
    [
        (["# TODO: speed this up", "# Sum the totals."], "Sum the totals."),
        (["# noqa: E501", "# Sum the totals."], "Sum the totals."),
        (["# type: ignore", "# pylint: disable=foo", "# pragma: no cover"], None),
        # A banner labels a section of the file, not the function below it.
        (["# ---------------", "# Sum the totals.", "# ==="], None),
        (
            ["# 1. Baseline: typed params.", "# More detail."],
            "1. Baseline: typed params.\n\nMore detail.",
        ),
        (["# result = compute(x)", "# return result"], None),
        (["# Deprecated"], "Deprecated"),
        (["#", "# Sum the totals.", "#"], "Sum the totals."),
    ],
)
def test_block_filtering(lines, expected):
    assert comment_block_text(lines) == expected


def test_paragraphs_in_a_comment_block_are_kept():
    text = comment_block_text(["# First part.", "#", "# Second part."])

    assert text == "First part.\n\nSecond part."
