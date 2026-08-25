import pytest

try:
    from PyCodeCommenter import PyCodeCommenter
except ImportError:
    from commenter import PyCodeCommenter

from PyCodeCommenter.validator import DocstringValidator, Severity


def test_missing_docstring():
    code_missing = """\
def add(a, b):
    return a + b\
"""
    validator = DocstringValidator(code_string=code_missing)
    report = validator.validate_all()
    # Expect at least one error for missing docstring
    assert any(issue.severity == Severity.ERROR for issue in report.issues)


def test_signature_mismatch():
    code_mismatch = """\
def multiply(x, y):
    '''Multiply two numbers.
    
    Args:
        x (int): First number
        z (int): Wrong parameter name!
    
    Returns:
        int: Product
    '''
    return x * y\
"""
    validator = DocstringValidator(code_string=code_mismatch)
    report = validator.validate_all()
    # Should contain an error for the mismatched parameter 'z'
    assert any(
        issue.category == "signature" and "z" in issue.message
        for issue in report.issues
    )


def test_order_mismatch():
    code_order = """\
def subtract(a, b):
    '''Subtract.
    
    Args:
        b (int): Second
        a (int): First
    '''
    return a - b\
"""
    validator = DocstringValidator(code_string=code_order)
    report = validator.validate_all()
    # Should contain an error for the parameter order
    assert any(
        issue.category == "signature" and "order" in issue.message.lower()
        for issue in report.issues
    )
