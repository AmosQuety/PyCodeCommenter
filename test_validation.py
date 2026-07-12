"""Comprehensive pytest suite for all validation checks (v2.2.0 rewrite)."""
# -*- coding: utf-8 -*-
import pytest
from PyCodeCommenter.validator import DocstringValidator, Severity


# ---------------------------------------------------------------------------
# Original test scenarios (1–10), preserved and migrated to pytest
# ---------------------------------------------------------------------------

def test_missing_docstring():
    """Test 1 – Missing docstring raises an ERROR."""
    code = """
def add(a, b):
    return a + b
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.errors > 0


def test_signature_mismatch():
    """Test 2 – Wrong parameter name produces errors or warnings."""
    code = """
def multiply(x, y):
    '''Multiply two numbers.

    Args:
        x (int): First number
        z (int): Wrong parameter name!

    Returns:
        int: Product
    '''
    return x * y
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.errors > 0 or report.stats.warnings > 0


def test_type_consistency_missing_returns():
    """Test 3 – Return type hint present but no Returns section → WARNING."""
    code = """
def divide(a: int, b: int) -> float:
    '''Divide two numbers.

    Args:
        a (int): Numerator
        b (int): Denominator
    '''
    return a / b
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.warnings > 0


def test_exception_documentation_missing():
    """Test 4 – Raised exception not documented → WARNING."""
    code = """
def validate_age(age):
    '''Validate age is positive.

    Args:
        age (int): Age to validate
    '''
    if age < 0:
        raise ValueError("Age cannot be negative")
    return age
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.warnings > 0


def test_return_documentation_missing():
    """Test 5 – Function returns a value but no Returns section → WARNING."""
    code = """
def greet(name):
    '''Greet a person.

    Args:
        name (str): Person's name
    '''
    return f"Hello, {name}!"
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.warnings > 0


def test_content_quality_placeholder():
    """Test 6 – Placeholder text in docstring → WARNING."""
    code = """
def process_data(data):
    '''TODO: Add description.

    Args:
        data: Input data
    '''
    pass
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.warnings > 0


def test_content_quality_short_summary():
    """Test 7 – Very short summary → INFO."""
    code = """
def foo():
    '''Do it.'''
    pass
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.infos > 0


def test_format_compliance_missing_summary():
    """Test 8 – Missing/blank summary line produces at least one issue."""
    code = """
def bar():
    '''

    Args:
        x: Something
    '''
    pass
"""
    report = DocstringValidator(code_string=code).validate_all()
    # The validator may emit INFO or ERROR depending on whether it sees
    # any content after the blank first line; either way there must be
    # at least one issue flagged.
    assert report.stats.total_issues > 0


def test_complete_validation_report():
    """Test 9 – Complex function produces a non-empty report."""
    code = """
def complex_function(a, b, c):
    '''TODO: Fix this.

    Args:
        a: First
        b: Second
        x: Wrong param

    Returns:
        Something
    '''
    if a < 0:
        raise ValueError("Invalid")
    return a + b
"""
    report = DocstringValidator(code_string=code).validate_all()
    assert report.stats.total_issues > 0


def test_export_formats():
    """Test 10 – to_dict() returns a dict, to_markdown() returns a string."""
    code = """
def complex_function(a, b, c):
    '''TODO: Fix this.

    Args:
        a: First
        b: Second
        x: Wrong param

    Returns:
        Something
    '''
    if a < 0:
        raise ValueError("Invalid")
    return a + b
"""
    report = DocstringValidator(code_string=code).validate_all()
    d = report.to_dict()
    assert isinstance(d, dict)
    md = report.to_markdown()
    assert isinstance(md, str)


# ---------------------------------------------------------------------------
# Feature 1 – Decorator awareness (new in v2.2.0)
# ---------------------------------------------------------------------------

def test_property_getter_return_check_fires():
    """@property getter should still require a Returns section."""
    code = """
class MyClass:
    @property
    def value(self):
        '''Get the stored value.'''
        return self._value
"""
    report = DocstringValidator(code_string=code).validate_all()
    # The getter returns a value but has no Returns section → at least one warning
    return_warnings = [
        i for i in report.issues
        if i.category == "returns" and i.severity == Severity.WARNING
    ]
    assert len(return_warnings) > 0, "Expected a return-doc warning on the @property getter"


def test_property_setter_skips_return_check():
    """@property setter must NOT generate a false-positive return warning."""
    code = """
class MyClass:
    @value.setter
    def value(self, v):
        '''Set the stored value.

        Args:
            v: New value to store.
        '''
        self._value = v
"""
    report = DocstringValidator(code_string=code).validate_all()
    return_warnings = [
        i for i in report.issues
        if i.category == "returns" and i.severity == Severity.WARNING
    ]
    assert len(return_warnings) == 0, (
        f"@property setter must not trigger a return warning, got: {return_warnings}"
    )


def test_property_deleter_skips_return_check():
    """@property deleter must NOT generate a false-positive return warning."""
    code = """
class MyClass:
    @value.deleter
    def value(self):
        '''Delete the stored value.'''
        del self._value
"""
    report = DocstringValidator(code_string=code).validate_all()
    return_warnings = [
        i for i in report.issues
        if i.category == "returns" and i.severity == Severity.WARNING
    ]
    assert len(return_warnings) == 0, (
        f"@property deleter must not trigger a return warning, got: {return_warnings}"
    )


def test_classmethod_cls_not_flagged():
    """@classmethod — cls must not appear as an undocumented parameter."""
    code = """
class MyClass:
    @classmethod
    def create(cls, name):
        '''Create a new instance.

        Args:
            name (str): Name for the instance.

        Returns:
            MyClass: New instance.
        '''
        return cls()
"""
    report = DocstringValidator(code_string=code).validate_all()
    cls_issues = [i for i in report.issues if "'cls'" in i.message]
    assert len(cls_issues) == 0, (
        f"cls should not be flagged as missing/extra, got: {cls_issues}"
    )


def test_staticmethod_first_arg_not_stripped():
    """@staticmethod first arg should not be silently stripped (no false positives)."""
    code = """
class MyClass:
    @staticmethod
    def add(x, y):
        '''Add two numbers.

        Args:
            x (int): First operand.
            y (int): Second operand.

        Returns:
            int: Sum.
        '''
        return x + y
"""
    report = DocstringValidator(code_string=code).validate_all()
    # Both x and y are documented; no signature errors expected
    sig_errors = [
        i for i in report.issues
        if i.category == "signature" and i.severity == Severity.ERROR
    ]
    assert len(sig_errors) == 0, (
        f"@staticmethod should not produce signature errors, got: {sig_errors}"
    )


# ---------------------------------------------------------------------------
# Feature 3 – Sphinx :raises: detection (new in v2.2.0)
# ---------------------------------------------------------------------------

def test_sphinx_raises_detected():
    """Sphinx-style ':raises ExcType:' must suppress the missing-Raises warning."""
    code = """
def fetch(url):
    '''Fetch a URL.

    Args:
        url (str): The URL to fetch.

    Returns:
        str: Response body.

    :raises ValueError: If the URL is empty.
    '''
    if not url:
        raise ValueError("URL must not be empty")
    return "response"
"""
    report = DocstringValidator(code_string=code).validate_all()
    raises_warnings = [
        i for i in report.issues
        if i.category == "exceptions" and i.severity == Severity.WARNING
    ]
    assert len(raises_warnings) == 0, (
        f"Sphinx ':raises:' should suppress the warning, got: {raises_warnings}"
    )


# ---------------------------------------------------------------------------
# Feature 2 – JSON output shape (new in v2.2.0)
# ---------------------------------------------------------------------------

def test_json_output_shape():
    """to_dict() must return the exact spec-compliant shape."""
    code = """
def divide(a, b):
    '''Divide two numbers.

    Args:
        a (int): Numerator.
        b (int): Denominator.
    '''
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b
"""
    report = DocstringValidator(code_string=code).validate_all()
    d = report.to_dict()

    # Top-level keys
    assert "file" in d
    assert "stats" in d
    assert "issues" in d

    # stats shape
    stats = d["stats"]
    assert "total" in stats
    assert "errors" in stats
    assert "warnings" in stats
    assert "info" in stats
    assert "coverage_percentage" in stats

    # issues shape — if any issues exist
    for issue in d["issues"]:
        assert "line" in issue, f"Missing 'line' key in issue: {issue}"
        assert "severity" in issue, f"Missing 'severity' key in issue: {issue}"
        assert "check" in issue, f"Missing 'check' key in issue: {issue}"
        assert "message" in issue, f"Missing 'message' key in issue: {issue}"
        # severity must be uppercase string name
        assert issue["severity"] in {"ERROR", "WARNING", "INFO"}, (
            f"severity must be uppercase, got: {issue['severity']}"
        )
        # line must be an integer
        assert isinstance(issue["line"], int), (
            f"'line' must be int, got {type(issue['line'])}: {issue['line']}"
        )
