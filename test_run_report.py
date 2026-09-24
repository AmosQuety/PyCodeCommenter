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
