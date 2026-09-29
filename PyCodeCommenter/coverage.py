"""
Documentation coverage analysis module for PyCodeCommenter.

This module provides tools for analyzing documentation coverage across Python
files and projects. It calculates metrics for function and class documentation
and generates coverage reports.

Classes:
    FileCoverage: Coverage statistics for a single file
    ProjectCoverage: Coverage statistics for entire project
    CoverageAnalyzer: Analyzes documentation coverage for files or projects
"""

# coverage.py

import ast
import os
import logging
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, field

try:
    from .inference import AI_DRAFT_MARKER, GUESS_MARKER
except (ImportError, ValueError):
    from inference import AI_DRAFT_MARKER, GUESS_MARKER

# Configure logging
logger = logging.getLogger(__name__)

# Mirrors cli.py's _path_is_excluded / DEFAULT_DIRECTORY_EXCLUDES. Duplicated
# rather than imported: cli.py imports from this module, so importing the
# other way would be a circular import. Includes the same
# vendored-dependency/build-output directories cli.py excludes, plus
# 'tests'/'test_' - coverage-specific, since coverage measures documentation
# of source code, not test code.
DEFAULT_COVERAGE_EXCLUDES = [
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    ".tox",
    ".nox",
    "__pypackages__",
    "site-packages",
    "build",
    "dist",
    ".eggs",
    ".egg-info",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "tests",
    "test_",
]


def _path_is_excluded(py_file: Path, patterns) -> bool:
    """Say whether a path matches an exclusion pattern.

    A path component that exactly equals a pattern matches. A dot-prefixed
    pattern (such as ``.egg-info``) also matches a component it is a suffix
    of, and an underscore-suffixed pattern (such as ``test_``, pytest's file
    naming convention) matches a component it is a prefix of. See cli.py's
    ``_path_is_excluded`` for the equivalent used by generate and validate.

    Args:
        py_file (Path): The file's path, relative to the analysed directory.
        patterns (Iterable[str]): The exclusion patterns.

    Returns:
        bool: ``True`` if the file should be skipped.
    """
    parts = py_file.parts
    for pattern in patterns:
        for part in parts:
            if part == pattern:
                return True
            if pattern.startswith(".") and part.endswith(pattern):
                return True
            if pattern.endswith("_") and part.startswith(pattern):
                return True
    return False


@dataclass
class FileCoverage:
    """Coverage statistics for a single file.

    Attributes:
        path (str): The file's path.
        total_functions (int): Functions and methods found.
        documented_functions (int): Those with a docstring.
        total_classes (int): Classes found.
        documented_classes (int): Those with a docstring.
    """

    path: str
    total_functions: int = 0
    documented_functions: int = 0
    total_classes: int = 0
    documented_classes: int = 0

    @property
    def coverage_percentage(self) -> float:
        """Get the share of functions and classes that are documented.

        Returns:
            float: A percentage from 0 to 100; 0.0 for a file with no functions
            or classes.
        """
        total = self.total_functions + self.total_classes
        documented = self.documented_functions + self.documented_classes
        return (documented / total * 100) if total > 0 else 0.0


@dataclass
class ProjectCoverage:
    """Coverage statistics for a whole project.

    Attributes:
        files (Dict[str, FileCoverage]): Each analysed file's coverage, by
            path.
        strict (bool): Whether placeholder and unreviewed AI text was
            excluded from the count.
    """

    files: Dict[str, FileCoverage] = field(default_factory=dict)
    strict: bool = False

    @property
    def total_coverage(self) -> float:
        """Get the share of documented functions and classes across all files.

        Returns:
            float: A percentage from 0 to 100; 0.0 if there are none.
        """
        total_items = sum(
            f.total_functions + f.total_classes for f in self.files.values()
        )
        documented = sum(
            f.documented_functions + f.documented_classes for f in self.files.values()
        )
        return (documented / total_items * 100) if total_items > 0 else 0.0

    def print_report(self):
        """Print the coverage report to standard output."""
        print("\n" + "=" * 80)
        print("DOCUMENTATION COVERAGE REPORT" + (" (STRICT)" if self.strict else ""))
        if self.strict:
            print(STRICT_NOTE)
        print("=" * 80)

        for path, coverage in sorted(self.files.items()):
            status = "[OK]" if coverage.coverage_percentage == 100 else "[!!]"
            # Shorten path for display
            display_path = os.path.basename(path)
            print(f"{status} {display_path:50} {coverage.coverage_percentage:5.1f}%")

        print("-" * 80)
        print(f"{'TOTAL':52} {self.total_coverage:5.1f}%")
        print("=" * 80)

    def to_json(self) -> dict:
        """Export the coverage as a JSON-serialisable dict.

        Returns:
            dict: The total, and per file the percentage and the
            ``documented/total`` counts of functions and classes. Has
            ``"strict": True`` when strict counting was used.
        """
        exported = {
            "total_coverage": self.total_coverage,
            "files": {
                path: {
                    "coverage": cov.coverage_percentage,
                    "functions": f"{cov.documented_functions}/{cov.total_functions}",
                    "classes": f"{cov.documented_classes}/{cov.total_classes}",
                }
                for path, cov in self.files.items()
            },
        }
        if self.strict:
            exported["strict"] = True
        return exported


def shields_badge_dict(percentage: float, label: str = "docs coverage") -> dict:
    """Build a shields.io endpoint-badge dict for a coverage percentage.

    See https://shields.io/badges/endpoint-badge for the schema.

    Args:
        percentage (float): Coverage percentage, 0-100.
        label (str): Badge label text. (default: 'docs coverage')

    Returns:
        dict: A shields.io endpoint-badge schema dict.
    """
    if percentage >= 90:
        color = "brightgreen"
    elif percentage >= 75:
        color = "green"
    elif percentage >= 50:
        color = "yellow"
    else:
        color = "red"
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{percentage:.0f}%",
        "color": color,
    }


STRICT_NOTE = (
    "Strict: a docstring with a TODO(pycodecommenter) placeholder or an "
    "unreviewed AI-drafted line does not count."
)


class CoverageAnalyzer:
    """Analyze documentation coverage for files or projects.

    By default a function or class counts as documented if it has a
    non-empty docstring: a presence metric. With ``strict=True`` a docstring
    that still holds a ``TODO(pycodecommenter)`` placeholder or an
    unreviewed AI-drafted line does not count, so a project of generated
    stubs does not read as 100%.

    Attributes:
        strict (bool): Whether placeholder and unreviewed AI text is
            excluded from the count.
    """

    def __init__(self, strict: bool = False):
        """Choose how documented is counted.

        Args:
            strict (bool): Do not count docstrings that still hold a placeholder
                or an unreviewed AI-drafted line.
        """
        self.strict = strict

    def _is_documented(self, node: ast.AST) -> bool:
        """Say whether a function or class counts as documented.

        Args:
            node (ast.AST): A function or class definition.

        Returns:
            bool: ``True`` if it has a non-empty docstring (and, in strict mode,
            no placeholder or unreviewed AI-drafted marker).
        """
        docstring = ast.get_docstring(node)
        if not docstring:
            return False
        if self.strict:
            return GUESS_MARKER not in docstring and AI_DRAFT_MARKER not in docstring
        return True

    def analyze_file(self, file_path: str) -> FileCoverage:
        """Analyze a single Python file.

        Args:
            file_path (str): Path to the file.

        Returns:
            FileCoverage: The counts of documented and total functions and
            classes, including nested and async ones.

        Raises:
            SyntaxError: If the file does not parse.
            OSError: If the file can't be read.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

        tree = ast.parse(code)
        coverage = FileCoverage(path=file_path)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                coverage.total_functions += 1
                if self._is_documented(node):
                    coverage.documented_functions += 1
            elif isinstance(node, ast.ClassDef):
                coverage.total_classes += 1
                if self._is_documented(node):
                    coverage.documented_classes += 1

        return coverage

    def analyze_directory(
        self, directory: str, exclude_patterns: List[str] = None
    ) -> ProjectCoverage:
        """Analyze all Python files in a directory.

        Files that can't be read or parsed are logged and left out. Only the part
        of a path inside ``directory`` is matched against the exclusions.

        Args:
            directory (str): Path to the directory.
            exclude_patterns (List[str]): Patterns to skip in addition to
                ``DEFAULT_COVERAGE_EXCLUDES``.

        Returns:
            ProjectCoverage: The coverage of every analysed file.
        """
        patterns = list(DEFAULT_COVERAGE_EXCLUDES) + list(exclude_patterns or [])
        project = ProjectCoverage(strict=self.strict)

        root = Path(directory)
        for py_file in root.rglob("*.py"):
            # Only the path *inside* the analysed directory is matched: a
            # project that lives under, say, ~/work/build/ must still count.
            if _path_is_excluded(py_file.relative_to(root), patterns):
                continue

            try:
                coverage = self.analyze_file(str(py_file))
                project.files[str(py_file)] = coverage
            except (IOError, OSError) as e:
                logger.error(f"Error reading {py_file}: {e}")
            except (SyntaxError, ValueError) as e:
                logger.error(f"Error parsing {py_file}: {e}")
            except UnicodeDecodeError as e:
                logger.error(f"Encoding error in {py_file}: {e}")

        return project
