"""The tutorial in docs/getting-started.md shows real output; keep it real.

The test runs the tutorial's commands on the tutorial's file and compares
the result with what the page prints.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parent.parent / "docs" / "getting-started.md"
ROOT = PAGE.parent.parent


def _fences(language: str):
    text = PAGE.read_text(encoding="utf-8")
    return re.findall(rf"```{language}\n(.*?)```", text, re.DOTALL)


def _tutorial_files():
    sources = [f for f in _fences("python") if "def discounted_price" in f]
    assert len(sources) == 2, "expected the starting file and the generated file"
    return sources


def _run(workdir, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "PyCodeCommenter.cli", *arguments],
        cwd=workdir,
        env={"PYTHONPATH": str(ROOT), "PATH": ""},
        capture_output=True,
        text=True,
    )


@pytest.fixture
def tutorial_dir(tmp_path):
    start, _ = _tutorial_files()
    (tmp_path / "pricing.py").write_text(start, encoding="utf-8")
    return tmp_path


def test_generate_writes_the_docstrings_the_tutorial_shows(tutorial_dir):
    _, expected = _tutorial_files()
    result = _run(tutorial_dir, "generate", "pricing.py", "--inplace")
    assert result.returncode == 0, result.stderr
    assert (tutorial_dir / "pricing.py").read_text(encoding="utf-8") == expected


def test_the_summary_lines_shown_are_the_ones_printed(tutorial_dir):
    result = _run(tutorial_dir, "generate", "pricing.py", "--dry-run")
    page = PAGE.read_text(encoding="utf-8")
    for line in result.stderr.splitlines():
        if line.strip():
            assert line in page


def test_coverage_and_validate_output_match_the_page(tutorial_dir):
    page = PAGE.read_text(encoding="utf-8")
    assert (
        "Coverage for pricing.py: 0.0%"
        in _run(tutorial_dir, "coverage", "pricing.py").stdout
    )
    _run(tutorial_dir, "generate", "pricing.py", "--inplace")
    review = _run(tutorial_dir, "review", "pricing.py", "--list").stdout
    for line in review.splitlines():
        if line.strip():
            assert line in page
    assert "gap" in review
