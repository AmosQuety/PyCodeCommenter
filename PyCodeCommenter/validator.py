"""
Docstring validation module for PyCodeCommenter.

This module provides comprehensive validation of Python docstrings against actual
code signatures. It checks for signature mismatches, type consistency, exception
documentation, return documentation, format compliance, and content quality.

Classes:
    Severity: Enum for issue severity levels (ERROR, WARNING, INFO)
    ValidationIssue: Represents a single documentation issue
    ValidationStats: Statistics from validation run
    ValidationReport: Container for validation results with reporting capabilities
    DocstringValidator: Main validator class for checking documentation quality
"""

import ast
import re
import logging
from typing import List, Dict, Optional, Set, Any, Union
from dataclasses import dataclass, field
from enum import Enum

try:
    from .docstring_parser import DocstringParser
    from .param_utils import get_all_parameters, exclude_self_cls
except (ImportError, ValueError):
    from docstring_parser import DocstringParser
    from param_utils import get_all_parameters, exclude_self_cls

logger = logging.getLogger(__name__)


def _get_decorators(func_node: Any) -> set:
    """Return the set of simple decorator names on an AST function node.

    Handles both plain decorators (``@property``) and attribute decorators
    (``@name.setter``, ``@name.deleter``).

    Args:
        func_node (Any): An ast.FunctionDef or ast.AsyncFunctionDef node.

    Returns:
        set: Set of decorator name strings found on the node.
    """
    names = set()
    for d in func_node.decorator_list:
        if isinstance(d, ast.Name):
            names.add(d.id)
        elif isinstance(d, ast.Attribute):
            # e.g. @myprop.setter → attr is "setter"
            names.add(d.attr)
    return names


def _has_raises_section(docstring: str) -> bool:
    """Return True if *docstring* contains any recognised Raises section.

    Recognised patterns:

    * ``Raises:`` — Google style (already worked before)
    * ``Raises\\n`` / ``Raises\\r\\n`` — bare header variant
    * ``:raises `` — Sphinx style (trailing space avoids false matches
      on substrings like ``:raisesome``)

    Args:
        docstring (str): The raw docstring text to inspect.

    Returns:
        bool: True if a Raises section is present in any recognised style.
    """
    return bool(
        re.search(r"Raises:", docstring)
        or re.search(r"Raises\r?\n", docstring)
        or re.search(r":raises ", docstring)
    )


class Severity(Enum):
    ERROR = "error"  # Must fix (missing required docs)
    WARNING = "warning"  # Should fix (inconsistencies)
    INFO = "info"  # Nice to have (style issues)


@dataclass
class ValidationIssue:
    """Represents a single documentation issue."""

    severity: Severity
    category: str  # "signature", "types", "exceptions", "format", "quality"
    location: str  # "file.py:line:function_name"
    message: str
    suggestion: Optional[str] = None  # How to fix it

    def __str__(self):
        return f"[{self.severity.value.upper()}] {self.location}: {self.message}"


@dataclass
class ValidationStats:
    """Statistics from validation run."""

    total_functions: int = 0
    total_classes: int = 0
    documented_functions: int = 0
    documented_classes: int = 0
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    info: int = 0

    @property
    def infos(self) -> int:
        """Deprecated alias for ``info``, kept for backward compatibility."""
        return self.info

    @infos.setter
    def infos(self, value: int) -> None:
        self.info = value

    @property
    def coverage_percentage(self) -> float:
        total = self.total_functions + self.total_classes
        documented = self.documented_functions + self.documented_classes
        return (documented / total * 100) if total > 0 else 0.0


class ValidationReport:
    """Container for validation results with reporting capabilities."""

    def __init__(self):
        self.issues: List[ValidationIssue] = []
        self.stats = ValidationStats()
        self.file_path: Optional[str] = None

    def add_issue(self, issue: ValidationIssue):
        """Add an issue and update stats."""
        self.issues.append(issue)
        self.stats.total_issues += 1
        if issue.severity == Severity.ERROR:
            self.stats.errors += 1
        elif issue.severity == Severity.WARNING:
            self.stats.warnings += 1
        else:
            self.stats.info += 1

    def print_summary(self):
        """Print human-readable summary to console."""
        print("\n" + "=" * 60)
        print("VALIDATION REPORT")
        print("=" * 60)
        print(f"File: {self.file_path or 'N/A'}")
        print(f"Coverage: {self.stats.coverage_percentage:.1f}%")
        print(f"Total Issues: {self.stats.total_issues}")
        print(f"  - Errors: {self.stats.errors}")
        print(f"  - Warnings: {self.stats.warnings}")
        print(f"  - Info: {self.stats.info}")

        if self.issues:
            print("\nISSUES:")
            for issue in self.issues:
                print(f"\n{issue}")
                if issue.suggestion:
                    print(f"  → Suggestion: {issue.suggestion}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export.

        The returned shape is:

        .. code-block:: json

            {
              "file": "<path>",
              "stats": {
                "total": 0,
                "errors": 0,
                "warnings": 0,
                "info": 0,
                "coverage_percentage": 0.0
              },
              "issues": [
                {
                  "line": 0,
                  "severity": "ERROR|WARNING|INFO",
                  "check": "<category>",
                  "message": "<message>"
                }
              ]
            }

        Returns:
            dict: Spec-compliant dictionary representation of this report.
        """

        def _parse_line(location: str) -> int:
            """Extract line number from 'file:line:func' location string."""
            parts = location.split(":")
            # location format: "<file>:<line>:<func>"
            # The file part may contain a drive letter on Windows (e.g. C:),
            # so iterate from the end to find the first numeric part.
            for part in reversed(parts):
                if part.isdigit():
                    return int(part)
            return 0

        return {
            "file": self.file_path,
            "stats": {
                "total": self.stats.total_issues,
                "errors": self.stats.errors,
                "warnings": self.stats.warnings,
                "info": self.stats.info,
                "coverage_percentage": round(self.stats.coverage_percentage, 2),
            },
            "issues": [
                {
                    "line": _parse_line(issue.location),
                    "severity": issue.severity.value.upper(),
                    "check": issue.category,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }

    def to_markdown(self) -> str:
        """Generate markdown report."""
        md = f"# Validation Report\n\n"
        md += f"**File:** {self.file_path or 'N/A'}\n\n"
        md += f"## Summary\n\n"
        md += f"- **Coverage:** {self.stats.coverage_percentage:.1f}%\n"
        md += f"- **Total Issues:** {self.stats.total_issues}\n"
        md += f"  - Errors: {self.stats.errors}\n"
        md += f"  - Warnings: {self.stats.warnings}\n"
        md += f"  - Info: {self.stats.info}\n\n"

        if self.issues:
            md += f"## Issues\n\n"
            for issue in self.issues:
                md += f"### {issue.severity.value.upper()}: {issue.message}\n\n"
                md += f"- **Location:** `{issue.location}`\n"
                md += f"- **Category:** {issue.category}\n"
                if issue.suggestion:
                    md += f"- **Suggestion:** {issue.suggestion}\n"
                md += "\n"

        return md


class DocstringValidator:
    """Main validator class for checking documentation quality."""

    def __init__(
        self, code_string: Optional[str] = None, file_path: Optional[str] = None
    ):
        """
        Initializes the validator.

        Args:
            code_string (Optional[str]): The code to validate as a string.
            file_path (Optional[str]): The path to the file to validate.
        """
        self.code = code_string
        self.file_path = file_path
        self.parsed_code = None

        try:
            if code_string:
                self.parsed_code = ast.parse(code_string)
            elif file_path:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.code = f.read()
                self.parsed_code = ast.parse(self.code)
        except (FileNotFoundError, IOError) as e:
            logger.error(f"Error reading file {file_path}: {e}")
        except SyntaxError as e:
            logger.error(f"Syntax error in code: {e}")

    def validate_all(self) -> ValidationReport:
        """Run all validation checks and return comprehensive report."""
        report = ValidationReport()
        report.file_path = self.file_path

        if not self.parsed_code:
            return report

        # Traverse AST and validate each function/class
        for node in ast.walk(self.parsed_code):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._validate_function(node, report)
                report.stats.total_functions += 1
            elif isinstance(node, ast.ClassDef):
                self._validate_class(node, report)
                report.stats.total_classes += 1

        return report

    def _validate_function(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        report: ValidationReport,
    ) -> None:
        """
        Validate a single function.

        Decorator-aware: ``@property`` setters and deleters skip the return
        documentation check (they write to a property but never return a
        meaningful value, so the check would produce a false positive).
        ``@classmethod`` and ``@staticmethod`` are already handled correctly
        by the signature-match heuristic and need no special casing here.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node to validate.
            report (ValidationReport): The report to add issues to.
        """
        docstring = ast.get_docstring(func_node)
        location = f"{self.file_path or 'code'}:{func_node.lineno}:{func_node.name}"

        # Inspect decorators once for all downstream checks.
        decorators = _get_decorators(func_node)
        # A setter or deleter is decorated with @<prop>.setter / @<prop>.deleter.
        # _get_decorators returns the *attr* part, so we check for "setter"/"deleter".
        is_setter_or_deleter = bool(decorators & {"setter", "deleter"})

        # Check if documented
        if not docstring:
            report.add_issue(
                ValidationIssue(
                    severity=Severity.ERROR,
                    category="missing",
                    location=location,
                    message=f"Function '{func_node.name}' has no docstring",
                    suggestion="Add a docstring with at minimum a summary line",
                )
            )
            return

        report.stats.documented_functions += 1

        # Run all checks
        issues = []
        issues.extend(self.check_signature_match(func_node, docstring, location))
        issues.extend(self.check_type_consistency(func_node, docstring, location))
        issues.extend(
            self.check_exception_documentation(func_node, docstring, location)
        )
        # Setters and deleters assign to a property — they do not have a
        # meaningful return value, so skip the return-doc check to avoid
        # false-positive warnings.
        if not is_setter_or_deleter:
            issues.extend(
                self.check_return_documentation(func_node, docstring, location)
            )
        issues.extend(self.check_format_compliance(docstring, location))
        issues.extend(self.check_content_quality(docstring, location))

        for issue in issues:
            report.add_issue(issue)

    def _validate_class(
        self, class_node: ast.ClassDef, report: ValidationReport
    ) -> None:
        """
        Validate a single class.

        Args:
            class_node (ast.ClassDef): The class node to validate.
            report (ValidationReport): The report to add issues to.
        """
        docstring = ast.get_docstring(class_node)
        location = f"{self.file_path or 'code'}:{class_node.lineno}:{class_node.name}"

        if not docstring:
            report.add_issue(
                ValidationIssue(
                    severity=Severity.ERROR,
                    category="missing",
                    location=location,
                    message=f"Class '{class_node.name}' has no docstring",
                    suggestion="Add a class docstring describing its purpose",
                )
            )
            return

        report.stats.documented_classes += 1

    def check_signature_match(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        docstring: str,
        location: str,
    ) -> List[ValidationIssue]:
        """
        Verify all function parameters are documented and vice versa.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            docstring (str): The docstring to check.
            location (str): The location string for issues.

        Returns:
            List[ValidationIssue]: List of issues found.
        """
        issues = []
        parser = DocstringParser(docstring)
        doc_params = list(parser.params.keys())

        # Actual arguments from AST. get_all_parameters() covers
        # positional-only, positional-or-keyword, *args, keyword-only, and
        # **kwargs -- not just func_node.args.args -- so a signature using
        # any of those is no longer invisible to this check.
        all_params = get_all_parameters(func_node)

        # Handle self/cls for methods
        # Simple heuristic: if it's inside a ClassDef (but we don't have parent info easily here without extra logic)
        # Better: check if first arg is self/cls and it's likely a method
        is_method = (
            bool(all_params)
            and all_params[0].kind == "positional"
            and all_params[0].arg.arg in ("self", "cls")
        )
        actual_params = [p.display_name for p in exclude_self_cls(all_params)]

        actual_set = set(actual_params)
        doc_set = set(doc_params)

        # Missing parameters in docstring
        missing = actual_set - doc_set
        for p in missing:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    category="signature",
                    location=location,
                    message=f"Parameter '{p}' is not documented in docstring",
                    suggestion=f"Add '{p}' to the Args section",
                )
            )

        # Extra parameters in docstring
        extra = doc_set - actual_set
        for p in extra:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    category="signature",
                    location=location,
                    message=f"Parameter '{p}' is documented but not in function signature",
                    suggestion=f"Remove '{p}' from docstring or update function signature",
                )
            )

        # Order mismatch
        # Only check if the sets are the same and non-empty
        if not missing and not extra and actual_params and doc_params:
            if actual_params != doc_params:
                issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        category="signature",
                        location=location,
                        message="Parameter order mismatch between signature and docstring",
                        suggestion=f"Reorder docstring params to match: {', '.join(actual_params)}",
                    )
                )

        # Self/cls incorrectly documented
        for p in doc_params:
            if p in ("self", "cls"):
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        category="signature",
                        location=location,
                        message=f"'{p}' should not be documented in docstring",
                        suggestion=f"Remove '{p}' from Args section",
                    )
                )

        return issues

    def check_type_consistency(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        docstring: str,
        location: str,
    ) -> List[ValidationIssue]:
        """
        Verify type hints match docstring type documentation.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            docstring (str): The docstring to check.
            location (str): The location string for issues.

        Returns:
            List[ValidationIssue]: List of issues found.
        """
        issues = []
        parser = DocstringParser(docstring)

        # Check return type consistency
        if func_node.returns:
            return_type_hint = (
                ast.unparse(func_node.returns)
                if hasattr(ast, "unparse")
                else str(func_node.returns)
            )
            if not parser.returns:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        category="types",
                        location=location,
                        message=f"Function has return type hint '{return_type_hint}' but no Returns section in docstring",
                        suggestion="Add a Returns section documenting the return value",
                    )
                )

        # Check parameter type hints vs docstring
        for param in exclude_self_cls(get_all_parameters(func_node)):
            if param.arg.annotation and param.display_name not in parser.params:
                type_hint = (
                    ast.unparse(param.arg.annotation)
                    if hasattr(ast, "unparse")
                    else str(param.arg.annotation)
                )
                issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        category="types",
                        location=location,
                        message=f"Parameter '{param.display_name}' has type hint '{type_hint}' but is not documented",
                        suggestion=f"Document '{param.display_name}' in the Args section",
                    )
                )

        return issues

    def check_exception_documentation(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        docstring: str,
        location: str,
    ) -> List[ValidationIssue]:
        """
        Verify all raised exceptions are documented.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            docstring (str): The docstring to check.
            location (str): The location string for issues.

        Returns:
            List[ValidationIssue]: List of issues found.
        """
        issues = []
        parser = DocstringParser(docstring)

        # Find all raise statements in function body
        raised_exceptions = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Raise):
                if node.exc:
                    # Extract exception name
                    if isinstance(node.exc, ast.Name):
                        raised_exceptions.add(node.exc.id)
                    elif isinstance(node.exc, ast.Call) and isinstance(
                        node.exc.func, ast.Name
                    ):
                        raised_exceptions.add(node.exc.func.id)

        # Check if docstring has Raises section (Google or Sphinx style)
        has_raises_section = _has_raises_section(docstring)

        if raised_exceptions and not has_raises_section:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    category="exceptions",
                    location=location,
                    message=f"Function raises exceptions {raised_exceptions} but has no Raises section",
                    suggestion="Add a Raises section documenting the exceptions",
                )
            )

        return issues

    def check_return_documentation(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        docstring: str,
        location: str,
    ) -> List[ValidationIssue]:
        """
        Validate return value documentation.

        Args:
            func_node (Union[ast.FunctionDef, ast.AsyncFunctionDef]): The function node.
            docstring (str): The docstring to check.
            location (str): The location string for issues.

        Returns:
            List[ValidationIssue]: List of issues found.
        """
        issues = []
        parser = DocstringParser(docstring)

        # Find all return statements
        has_return_value = False
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value is not None:
                has_return_value = True
                break

        # Check consistency
        if has_return_value and not parser.returns:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    category="returns",
                    location=location,
                    message="Function returns a value but has no Returns section in docstring",
                    suggestion="Add a Returns section documenting the return value",
                )
            )
        elif not has_return_value and parser.returns and func_node.name != "__init__":
            issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    category="returns",
                    location=location,
                    message="Function has Returns section but doesn't return a value",
                    suggestion="Remove the Returns section or add a return statement",
                )
            )

        return issues

    def check_format_compliance(
        self, docstring: str, location: str
    ) -> List[ValidationIssue]:
        """
        Validate docstring follows Google-style format.

        Args:
            docstring (str): The docstring to check.
            location (str): The location string for issues.

        Returns:
            List[ValidationIssue]: List of issues found.
        """
        issues = []

        # Check for summary line
        lines = docstring.strip().splitlines()
        if not lines:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    category="format",
                    location=location,
                    message="Docstring is empty",
                    suggestion="Add at least a summary line",
                )
            )
            return issues

        summary = lines[0].strip()
        if not summary:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    category="format",
                    location=location,
                    message="Docstring missing summary line",
                    suggestion="Add a summary line as the first line of the docstring",
                )
            )

        # Check for proper section headers (Google style)
        valid_sections = [
            "Args:",
            "Returns:",
            "Raises:",
            "Yields:",
            "Attributes:",
            "Example:",
            "Examples:",
            "Note:",
            "Notes:",
        ]
        for line in lines:
            stripped = line.strip()
            if stripped.endswith(":") and stripped not in valid_sections:
                # Check if it looks like a section header
                if stripped[0].isupper() and len(stripped.split()) == 1:
                    issues.append(
                        ValidationIssue(
                            severity=Severity.INFO,
                            category="format",
                            location=location,
                            message=f"Non-standard section header '{stripped}' found",
                            suggestion=f"Use standard Google-style sections: {', '.join(valid_sections)}",
                        )
                    )

        return issues

    def check_content_quality(
        self, docstring: str, location: str
    ) -> List[ValidationIssue]:
        """
        Check for low-quality documentation content.

        Args:
            docstring (str): The docstring to check.
            location (str): The location string for issues.

        Returns:
            List[ValidationIssue]: List of issues found.
        """
        issues = []
        parser = DocstringParser(docstring)

        # Check for placeholder text
        placeholders = [
            "TODO",
            "FIXME",
            "XXX",
            "HACK",
            "Description of",
            "TBD",
            "To be determined",
        ]
        for placeholder in placeholders:
            if placeholder.lower() in docstring.lower():
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        category="quality",
                        location=location,
                        message=f"Placeholder text '{placeholder}' found in docstring",
                        suggestion="Replace placeholder with actual documentation",
                    )
                )

        # Check summary length
        if parser.summary and len(parser.summary) < 10:
            issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    category="quality",
                    location=location,
                    message=f"Summary line is very short ({len(parser.summary)} chars)",
                    suggestion="Provide a more descriptive summary (at least 10 characters)",
                )
            )

        # Check for duplicate parameter descriptions
        if len(parser.params) > 1:
            descriptions = list(parser.params.values())
            if len(descriptions) != len(set(descriptions)):
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        category="quality",
                        location=location,
                        message="Multiple parameters have identical descriptions",
                        suggestion="Provide unique descriptions for each parameter",
                    )
                )

        # Check if summary and description are identical
        if (
            parser.summary
            and parser.description
            and parser.summary.strip() == parser.description.strip()
        ):
            issues.append(
                ValidationIssue(
                    severity=Severity.INFO,
                    category="quality",
                    location=location,
                    message="Summary and description are identical",
                    suggestion="Either remove the description or expand it with more details",
                )
            )

        return issues
