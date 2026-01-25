"""
PyCodeCommenter - Automatic Python docstring generation and validation.

A comprehensive tool for generating, validating, and maintaining Google-style
docstrings for Python code with coverage analysis and CI/CD integration.
"""

from .commenter import PyCodeCommenter
from .validator import DocstringValidator, ValidationReport, ValidationIssue, Severity
from .coverage import CoverageAnalyzer, FileCoverage, ProjectCoverage
from .type_analyzer import TypeAnalyzer
from .docstring_parser import DocstringParser

__version__ = "2.0.3"
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
