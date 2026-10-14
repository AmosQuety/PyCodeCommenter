"""
PyCodeCommenter - Automatic Python docstring generation and validation.

A comprehensive tool for generating, validating, and maintaining Google-style
docstrings for Python code with coverage analysis and CI/CD integration.
"""

from .commenter import PyCodeCommenter
from .coverage import CoverageAnalyzer, FileCoverage, ProjectCoverage
from .docstring_parser import DocstringParser
from .type_analyzer import TypeAnalyzer
from .validator import DocstringValidator, Severity, ValidationIssue, ValidationReport

__version__ = "2.6.1"


__all__ = [
    "PyCodeCommenter",
    "DocstringValidator",
    "ValidationReport",
    "ValidationIssue",
    "Severity",
    "CoverageAnalyzer",
    "FileCoverage",
    "ProjectCoverage",
    "TypeAnalyzer",
    "DocstringParser",
]
