"""Opt-in strictness for coverage and validate: a stub full of
`TODO(pycodecommenter)` placeholders, or of unreviewed AI drafts, is not
finished documentation. Defaults are unchanged: coverage stays a presence
metric and validate only fails on ERROR-level issues."""

import json
import sys

import pytest

from PyCodeCommenter.cli import main
from PyCodeCommenter.coverage import CoverageAnalyzer

TODO_DOC = '''def stub(x):
    """Do the thing.

    Args:
        x (Any): TODO(pycodecommenter): describe

    Returns:
        Any: TODO(pycodecommenter): describe
    """
    return x
'''
AI_DOC = '''def drafted(x):
    """Do the other thing. (AI-drafted, unreviewed)

    Args:
        x (Any): The input. (AI-drafted, unreviewed)

    Returns:
        Any: The output. (AI-drafted, unreviewed)
    """
    return x
'''
REAL_DOC = '''def real(x):
    """Do a real thing.

    Args:
        x (Any): The input.

    Returns:
        Any: The output.
    """
    return x
'''
TODO_CLASS = '''class Box:
    """Box class.

    Attributes:
        size (int): TODO(pycodecommenter): describe
    """
'''


@pytest.fixture
def source(tmp_path):
    def write(name, text):
        path = tmp_path / name
        path.write_text(text)
        return str(path)

    return write


def run(args, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pycodecommenter", *args])
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# coverage --strict
# ---------------------------------------------------------------------------


def test_default_coverage_counts_placeholders_as_documented(source):
    path = source("m.py", REAL_DOC + "\n\n" + TODO_DOC + "\n\n" + AI_DOC)

    assert CoverageAnalyzer().analyze_file(path).coverage_percentage == 100.0


def test_strict_coverage_counts_only_finished_docstrings(source):
    path = source("m.py", REAL_DOC + "\n\n" + TODO_DOC + "\n\n" + AI_DOC)

    coverage = CoverageAnalyzer(strict=True).analyze_file(path)

    assert coverage.documented_functions == 1
    assert coverage.total_functions == 3
    assert round(coverage.coverage_percentage, 1) == 33.3


def test_strict_coverage_applies_to_classes_too(source):
    path = source("m.py", TODO_CLASS)

    coverage = CoverageAnalyzer(strict=True).analyze_file(path)

    assert (coverage.documented_classes, coverage.total_classes) == (0, 1)


def test_a_missing_docstring_is_undocumented_either_way(source):
    path = source("m.py", "def bare():\n    pass\n")

    assert CoverageAnalyzer(strict=True).analyze_file(path).documented_functions == 0


def test_strict_directory_coverage(tmp_path, source):
    source("a.py", REAL_DOC)
    source("b.py", TODO_DOC)

    project = CoverageAnalyzer(strict=True).analyze_directory(str(tmp_path))

    assert project.total_coverage == 50.0


def test_the_cli_fails_below_a_threshold_only_when_strict(source, monkeypatch, capsys):
    path = source("m.py", TODO_DOC)

    relaxed, _, _ = run(["coverage", path, "--fail-below", "80"], monkeypatch, capsys)
    strict, _, err = run(
        ["coverage", path, "--strict", "--fail-below", "80"], monkeypatch, capsys
    )

    assert relaxed == 0
    assert strict == 1
    assert "0.0%" in err


def test_strict_is_stated_in_the_output(source, monkeypatch, capsys):
    path = source("m.py", TODO_DOC)

    _, text_out, _ = run(["coverage", path, "--strict"], monkeypatch, capsys)
    _, json_out, _ = run(
        ["coverage", path, "--strict", "--output-format", "json"], monkeypatch, capsys
    )

    assert "strict" in text_out.lower()
    assert json.loads(json_out)["strict"] is True


def test_default_json_output_is_unchanged(source, monkeypatch, capsys):
    path = source("m.py", TODO_DOC)

    _, out, _ = run(["coverage", path, "--output-format", "json"], monkeypatch, capsys)

    assert "strict" not in json.loads(out)


# ---------------------------------------------------------------------------
# validate --fail-on-todo / --fail-on-ai-draft
# ---------------------------------------------------------------------------


def test_validate_passes_by_default_with_only_warnings(source, monkeypatch, capsys):
    path = source("m.py", TODO_DOC + "\n\n" + AI_DOC)

    code, _, _ = run(["validate", path], monkeypatch, capsys)

    assert code == 0


def test_fail_on_todo_fails_when_a_placeholder_is_left(source, monkeypatch, capsys):
    path = source("m.py", TODO_DOC)

    code, _, err = run(["validate", path, "--fail-on-todo"], monkeypatch, capsys)

    assert code == 1
    assert "--fail-on-todo" in err


def test_fail_on_todo_passes_a_finished_file(source, monkeypatch, capsys):
    path = source("m.py", REAL_DOC)

    code, _, _ = run(["validate", path, "--fail-on-todo"], monkeypatch, capsys)

    assert code == 0


def test_fail_on_todo_ignores_unreviewed_ai_drafts(source, monkeypatch, capsys):
    path = source("m.py", AI_DOC)

    code, _, _ = run(["validate", path, "--fail-on-todo"], monkeypatch, capsys)

    assert code == 0


def test_fail_on_ai_draft_fails_on_unreviewed_drafts(source, monkeypatch, capsys):
    path = source("m.py", AI_DOC)

    code, _, err = run(["validate", path, "--fail-on-ai-draft"], monkeypatch, capsys)

    assert code == 1
    assert "--fail-on-ai-draft" in err


def test_fail_on_ai_draft_ignores_todo_placeholders(source, monkeypatch, capsys):
    path = source("m.py", TODO_DOC)

    code, _, _ = run(["validate", path, "--fail-on-ai-draft"], monkeypatch, capsys)

    assert code == 0


def test_both_flags_together_fail_on_either(source, monkeypatch, capsys):
    only_todo = source("a.py", TODO_DOC)
    only_ai = source("b.py", AI_DOC)
    flags = ["--fail-on-todo", "--fail-on-ai-draft"]

    assert run(["validate", only_todo, *flags], monkeypatch, capsys)[0] == 1
    assert run(["validate", only_ai, *flags], monkeypatch, capsys)[0] == 1


def test_directory_validation_fails_if_any_file_has_a_placeholder(
    tmp_path, source, monkeypatch, capsys
):
    source("a.py", REAL_DOC)
    source("b.py", TODO_DOC)

    code, _, err = run(
        ["validate", str(tmp_path), "--fail-on-todo"], monkeypatch, capsys
    )

    assert code == 1


def test_json_output_stays_valid_json_when_the_flag_fails_the_run(
    source, monkeypatch, capsys
):
    path = source("m.py", TODO_DOC)

    code, out, _ = run(
        ["validate", path, "--fail-on-todo", "--output-format", "json"],
        monkeypatch,
        capsys,
    )

    assert code == 1
    assert isinstance(json.loads(out), dict)
