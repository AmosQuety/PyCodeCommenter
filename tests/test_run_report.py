"""The end-of-run summary: what a generate run did, counted from the parts
it built, and printed to stderr so it never mixes with code on stdout."""

import logging
import sys

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.cli import main
from PyCodeCommenter.description_provider import DescriptionProvider, DocstringDraft
from PyCodeCommenter.run_report import GenerationReport

logging.disable(logging.CRITICAL)

CODE = '''# Add two numbers.
def add(a, b):
    return a + b


def check(x: int) -> bool:
    if x < 0:
        raise ValueError(x)
    return x > 10


def done():
    """Already documented.

    Args:
        None.

    Returns:
        None.
    """
'''


def report_for(code, provider=None):
    commenter = PyCodeCommenter(description_provider=provider).from_string(code)
    commenter.get_patched_code()
    return commenter.report


def test_counts_new_updated_and_unchanged_docstrings():
    report = report_for(CODE)

    assert report.new == 2
    assert report.updated == 0
    assert report.unchanged == 1


def test_counts_facts_gaps_and_comment_docstrings():
    report = report_for(CODE)

    # check: the raise condition and the bool return. (x's "int value." is
    # type-only filler, which is weak, not a fact.)
    assert report.facts == 2
    assert report.todos == 3  # a, b and add's return
    assert report.from_comments == 1
    assert report.ai_lines == 0


def test_counts_ai_drafted_lines():
    class Drafts(DescriptionProvider):
        def draft_docstring(self, context, known, slots):
            return DocstringDraft(params={"a": "First.", "b": "Second."})

    report = report_for(CODE, Drafts())

    assert report.ai_lines == 2
    assert report.todos == 1


def test_counts_are_reset_for_each_run():
    commenter = PyCodeCommenter().from_string(CODE)
    commenter.get_patched_code()
    commenter.get_patched_code()

    assert commenter.report.new == 2


def test_reports_add_up_across_files():
    total = GenerationReport()
    total.merge(report_for(CODE))
    total.merge(report_for(CODE))

    assert total.new == 4 and total.todos == 6 and total.files == 2


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------


def test_summary_states_each_count_in_plain_words():
    text = "\n".join(report_for(CODE).summary_lines(preview=False, ai_used=False))

    assert "2 docstrings written, 1 already complete" in text
    assert "2 details taken straight from the code" in text
    assert "1 docstring taken from the comment above it (comment left in place)" in text
    assert '3 gaps left as "TODO(pycodecommenter)"' in text
    assert "--ai-draft" in text  # gaps left and AI not used: say how to fill them


def test_preview_wording_and_ai_review_hint():
    class Drafts(DescriptionProvider):
        def draft_docstring(self, context, known, slots):
            return DocstringDraft(params={"a": "First."})

    text = "\n".join(
        report_for(CODE, Drafts()).summary_lines(preview=True, ai_used=True)
    )

    assert "would be written" in text
    assert '1 line drafted by AI, marked "(AI-drafted, unreviewed)"' in text
    assert "review" in text.lower()


def test_nothing_found():
    lines = GenerationReport().summary_lines(preview=False, ai_used=False)

    assert lines == ["Summary: no functions or classes found."]


# ---------------------------------------------------------------------------
# CLI: the summary goes to stderr, code to stdout
# ---------------------------------------------------------------------------


def run_cli(args, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pycodecommenter"] + args)
    try:
        main()
    except SystemExit:
        pass
    return capsys.readouterr()


def test_summary_is_printed_to_stderr_and_stdout_stays_pure_code(
    tmp_path, monkeypatch, capsys
):
    target = tmp_path / "m.py"
    target.write_text(CODE)

    captured = run_cli(["generate", str(target)], monkeypatch, capsys)

    assert "Summary:" in captured.err
    assert "Summary:" not in captured.out
    compile(captured.out, "m.py", "exec")  # stdout is exactly the patched code


@pytest.mark.parametrize("mode", [["--dry-run"], ["--inplace"]])
def test_summary_follows_other_output_modes(tmp_path, monkeypatch, capsys, mode):
    target = tmp_path / "m.py"
    target.write_text(CODE)

    captured = run_cli(["generate", str(target), *mode], monkeypatch, capsys)

    assert "Summary:" in captured.err


# ---------------------------------------------------------------------------
# Why gaps are left after AI drafting
# ---------------------------------------------------------------------------

from PyCodeCommenter.description_provider import (  # noqa: E402
    ClassDraft,
    DraftingStopped,
)

THREE = """def one(a):
    return a


def two(b):
    return b


def three(c):
    return c
"""

CLASS_ONE = """class Box:
    def __init__(self, size):
        self.size = size
"""


class Scripted(DescriptionProvider):
    """Answers each request from a list: a draft, or an error to raise."""

    def __init__(self, answers):
        self.answers = iter(answers)

    def _next(self):
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def draft_docstring(self, context, known, slots):
        return self._next()

    def draft_class_docstring(self, context, known, slots):
        return self._next()


def filled(name):
    return DocstringDraft(
        summary=f"Do {name}.",
        params={"a": "The value.", "b": "The value.", "c": "The value."},
        returns="The result.",
    )


def drafted_report(code, answers):
    return report_for(code, Scripted(answers))


def test_every_request_that_was_answered_is_counted_with_nothing_left_over():
    report = drafted_report(THREE, [filled("one"), filled("two"), filled("three")])

    assert (report.ai_requests, report.ai_failed, report.ai_not_tried) == (3, 0, 0)
    assert report.ai_declined == 0


def test_gaps_the_model_declined_are_counted_and_worded():
    report = drafted_report(THREE, [DocstringDraft()] * 3)

    assert report.ai_declined > 0 and report.ai_failed == 0
    text = "\n".join(report.summary_lines(preview=False, ai_used=True))
    assert "declined" in text


def test_a_failed_request_is_not_counted_as_a_decline():
    report = drafted_report(
        THREE, [DocstringDraft(failed=True), filled("two"), filled("three")]
    )

    assert report.ai_failed == 1
    assert report.ai_declined == 0
    text = "\n".join(report.summary_lines(preview=False, ai_used=True))
    assert "1 request failed" in text


def test_a_provider_that_raises_counts_as_a_failed_request():
    report = drafted_report(
        THREE, [RuntimeError("boom"), filled("two"), filled("three")]
    )

    assert report.ai_failed == 1 and report.ai_requests == 3


def test_functions_after_a_stop_are_counted_as_not_tried():
    stop = DraftingStopped("user_daily_limit_reached", "Daily limit reached.")

    report = drafted_report(THREE, [filled("one"), stop])

    assert report.ai_requests == 1  # only the first got an answer
    assert report.ai_not_tried == 2  # the one that hit the limit, and the last
    text = "\n".join(report.summary_lines(preview=False, ai_used=True))
    assert "2 functions or classes not tried" in text


def test_class_requests_are_counted_the_same_way():
    failed = drafted_report(CLASS_ONE, [ClassDraft(failed=True), filled("__init__")])
    declined = drafted_report(CLASS_ONE, [ClassDraft(), filled("__init__")])

    assert failed.ai_failed == 1
    assert declined.ai_declined > 0 and declined.ai_failed == 0


def test_no_ai_numbers_appear_without_a_provider():
    report = report_for(THREE)

    assert (
        report.ai_requests,
        report.ai_declined,
        report.ai_failed,
        report.ai_not_tried,
    ) == (0, 0, 0, 0)
    text = "\n".join(report.summary_lines(preview=False, ai_used=False))
    assert "declined" not in text and "failed" not in text


def test_a_fully_drafted_run_adds_no_problem_lines():
    report = drafted_report(THREE, [filled("one"), filled("two"), filled("three")])

    text = "\n".join(report.summary_lines(preview=False, ai_used=True))
    assert "declined" not in text and "failed" not in text and "not tried" not in text


def test_the_new_counts_add_up_across_files():
    first = drafted_report(THREE, [DocstringDraft(failed=True)] * 3)
    second = drafted_report(THREE, [DocstringDraft(failed=True)] * 3)

    total = GenerationReport()
    total.merge(first)
    total.merge(second)

    assert total.ai_failed == 6
