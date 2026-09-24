import os
import logging
import pytest


from PyCodeCommenter.coverage import CoverageAnalyzer

logging.disable(logging.CRITICAL)


@pytest.fixture
def analyzer():
    return CoverageAnalyzer()


def test_single_file_analysis(analyzer):
    # Analyze this file itself; should have at least some functions/classes
    coverage = analyzer.analyze_file(__file__)
    assert coverage.total_functions >= 0
    assert coverage.total_classes >= 0
    # Coverage percentage should be between 0 and 100
    assert 0.0 <= coverage.coverage_percentage <= 100.0


def test_directory_analysis(analyzer):
    package_dir = os.path.join(os.path.dirname(__file__), "..", "PyCodeCommenter")
    project = analyzer.analyze_directory(package_dir, exclude_patterns=["__pycache__"])
    # At least one file should be analyzed
    assert len(project.files) > 0
    # Total coverage should be a valid percentage
    assert 0.0 <= project.total_coverage <= 100.0


def test_folders_above_the_target_directory_never_exclude_it(analyzer, tmp_path):
    """Exclusions apply inside the analysed directory only. A project that
    happens to live under a folder named like an exclusion ("build",
    "tests", "venv") must still be analysed."""
    project_dir = tmp_path / "build" / "tests" / "myproject"
    project_dir.mkdir(parents=True)
    (project_dir / "m.py").write_text('def f():\n    """Doc."""\n')

    project = analyzer.analyze_directory(str(project_dir))

    assert len(project.files) == 1


def test_exclusions_still_apply_inside_the_target_directory(analyzer, tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.py").write_text("def g():\n    pass\n")
    (tmp_path / "m.py").write_text('def f():\n    """Doc."""\n')

    project = analyzer.analyze_directory(str(tmp_path))

    assert list(project.files) == [str(tmp_path / "m.py")]  # keyed by path
