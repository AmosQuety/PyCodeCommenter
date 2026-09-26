"""Knowing what an AI run will cost before it starts, and capping it:
the pre-flight count (`--ai-draft` on a directory), its confirmation, and
`--max-drafts`. Nothing here sends code anywhere: providers are fakes."""

import logging
import sys

import pytest

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.cli import main
from PyCodeCommenter.description_provider import (
    ClassDraft,
    DescriptionProvider,
    DocstringDraft,
    SwitchOnStop,
)
from PyCodeCommenter.draft_limits import DraftBudget, count_draft_requests

logging.disable(logging.CRITICAL)

FUNCTIONS = "def one(a):\n    return a\n\n\ndef two(b):\n    return b\n"
CLASS_AND_FUNCTION = (
    "class Box:\n    def __init__(self, size):\n        self.size = size\n\n\n"
    "def go(x):\n    return x\n"
)
COMPLETE = '''def done():
    """Already documented.

    Args:
        None.

    Returns:
        None.
    """
'''


class Recording(DescriptionProvider):
    """Counts requests; answers nothing."""

    def __init__(self):
        self.requests = 0

    def draft_docstring(self, context, known, slots):
        self.requests += 1
        return DocstringDraft()

    def draft_class_docstring(self, context, known, slots):
        self.requests += 1
        return ClassDraft()


def write(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source)
    return str(path)


# ---------------------------------------------------------------------------
# The pre-flight count
# ---------------------------------------------------------------------------


def test_counts_one_request_per_function_or_class_with_gaps(tmp_path):
    targets = [
        write(tmp_path, "a.py", FUNCTIONS),
        write(tmp_path, "b.py", CLASS_AND_FUNCTION),
        write(tmp_path, "c.py", COMPLETE),
    ]

    result = count_draft_requests(targets)

    assert result.files == 3
    # a: two functions; b: the class, its __init__ and a function
    assert result.requests == 2 + 3
    assert result.files_with_gaps == 2


def test_a_file_that_does_not_parse_is_skipped_not_fatal(tmp_path):
    targets = [
        write(tmp_path, "bad.py", "def (:\n"),
        write(tmp_path, "a.py", FUNCTIONS),
    ]

    result = count_draft_requests(targets)

    assert result.requests == 2


def test_counting_needs_no_provider_and_writes_nothing(tmp_path):
    path = write(tmp_path, "a.py", FUNCTIONS)

    count_draft_requests([path])

    assert (tmp_path / "a.py").read_text() == FUNCTIONS


def test_no_targets_means_nothing_to_draft():
    assert count_draft_requests([]).requests == 0


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------


def report_for(sources, budget):
    provider = Recording()
    reports = []
    for source in sources:
        commenter = PyCodeCommenter(description_provider=provider, budget=budget)
        commenter.from_string(source).get_patched_code()
        reports.append(commenter.report)
    return provider, reports


def test_a_budget_stops_requests_at_its_limit_across_files():
    budget = DraftBudget(limit=3)

    provider, reports = report_for([FUNCTIONS, FUNCTIONS], budget)

    assert provider.requests == 3
    assert budget.spent is True
    assert sum(r.ai_not_tried for r in reports) == 1  # the fourth function


def test_a_budget_larger_than_the_work_is_never_spent():
    budget = DraftBudget(limit=10)

    provider, _ = report_for([FUNCTIONS], budget)

    assert provider.requests == 2
    assert budget.spent is False
    assert budget.used == 2


def test_classes_and_functions_draw_on_the_same_budget():
    budget = DraftBudget(limit=1)

    provider, reports = report_for([CLASS_AND_FUNCTION], budget)

    assert provider.requests == 1


def test_a_limit_below_one_is_rejected():
    with pytest.raises(ValueError):
        DraftBudget(limit=0)


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text(FUNCTIONS)
    (tmp_path / "b.py").write_text(CLASS_AND_FUNCTION)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def provider(monkeypatch):
    recording = Recording()
    monkeypatch.setattr(
        "PyCodeCommenter.cli.build_ai_provider",
        lambda *a, **k: SwitchOnStop(recording, lambda stopped: None),
    )
    return recording


def run(args, monkeypatch, capsys, answers=None, interactive=True):
    replies = iter(answers or [])
    monkeypatch.setattr("builtins.input", lambda: next(replies))
    monkeypatch.setattr("PyCodeCommenter.cli.is_interactive", lambda: interactive)
    monkeypatch.setattr(sys, "argv", ["pycodecommenter", "generate", *args])
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_pre_flight_line_says_how_many_files_and_requests(
    project, provider, monkeypatch, capsys
):
    _, _, err = run(
        [".", "--ai-draft", "--dry-run"], monkeypatch, capsys, answers=["y"]
    )

    assert "2 files" in err and "5 functions and classes" in err
    assert "one request each" in err


def test_a_directory_run_asks_before_sending_and_no_stops_it(
    project, provider, monkeypatch, capsys
):
    code, _, err = run(
        [".", "--ai-draft", "--dry-run"], monkeypatch, capsys, answers=["n"]
    )

    assert code == 1
    assert provider.requests == 0
    assert "Nothing was sent" in err


def test_the_default_answer_is_no(project, provider, monkeypatch, capsys):
    code, _, _ = run(
        [".", "--ai-draft", "--dry-run"], monkeypatch, capsys, answers=[""]
    )

    assert code == 1 and provider.requests == 0


def test_yes_goes_ahead(project, provider, monkeypatch, capsys):
    run([".", "--ai-draft", "--dry-run"], monkeypatch, capsys, answers=["y"])

    assert provider.requests == 5


def test_the_consent_flag_skips_the_question_for_ci(
    project, provider, monkeypatch, capsys
):
    _, _, err = run(
        [".", "--ai-draft", "--dry-run", "--yes-send-code-to-ai"], monkeypatch, capsys
    )

    assert provider.requests == 5
    assert "Continue?" not in err


def test_without_a_terminal_it_prints_the_line_and_carries_on(
    project, provider, monkeypatch, capsys
):
    _, _, err = run(
        [".", "--ai-draft", "--dry-run"], monkeypatch, capsys, interactive=False
    )

    assert provider.requests == 5
    assert "5 functions and classes" in err


def test_a_single_file_is_not_asked_about(project, provider, monkeypatch, capsys):
    _, _, err = run(["a.py", "--ai-draft", "--dry-run"], monkeypatch, capsys)

    assert provider.requests == 2
    assert "Continue?" not in err


def test_a_run_with_nothing_to_draft_asks_nothing(
    tmp_path, provider, monkeypatch, capsys
):
    (tmp_path / "done.py").write_text(COMPLETE)
    monkeypatch.chdir(tmp_path)

    code, _, err = run([".", "--ai-draft", "--dry-run"], monkeypatch, capsys)

    assert "Continue?" not in err and provider.requests == 0


def test_max_drafts_caps_the_requests_and_says_so(
    project, provider, monkeypatch, capsys
):
    _, _, err = run(
        [".", "--ai-draft", "--dry-run", "--max-drafts", "2", "--yes-send-code-to-ai"],
        monkeypatch,
        capsys,
    )

    assert provider.requests == 2
    assert "--max-drafts 2" in err
    assert "not tried" in err


def test_the_preflight_line_mentions_the_cap(project, provider, monkeypatch, capsys):
    _, _, err = run(
        [".", "--ai-draft", "--dry-run", "--max-drafts", "2", "--yes-send-code-to-ai"],
        monkeypatch,
        capsys,
    )

    assert "at most 2 will be sent" in err


@pytest.mark.parametrize("value", ["0", "-3", "many"])
def test_max_drafts_must_be_a_positive_whole_number(
    project, provider, monkeypatch, capsys, value
):
    code, _, err = run([".", "--ai-draft", "--max-drafts", value], monkeypatch, capsys)

    assert code == 2  # argparse's usage error
    assert provider.requests == 0
