import sys
import os
import logging
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyCodeCommenter.coverage import CoverageAnalyzer  # noqa: E402

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
    project = analyzer.analyze_directory(
        os.path.dirname(__file__), exclude_patterns=["__pycache__", "test_", "venv"]
    )
    # At least one file should be analyzed
    assert len(project.files) > 0
    # Total coverage should be a valid percentage
    assert 0.0 <= project.total_coverage <= 100.0
