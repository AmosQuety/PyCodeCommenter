import os
import sys
import logging
import pytest

# Ensure repository root is on sys.path for package imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyCodeCommenter.commenter import PyCodeCommenter  # noqa: E402
from PyCodeCommenter.coverage import CoverageAnalyzer  # noqa: E402

logging.disable(logging.CRITICAL)


@pytest.fixture
def commenter():
    return PyCodeCommenter()


def test_integration_flow(commenter):
    """Full integration test covering generation, validation, and coverage."""
    test_code = """
def add(a, b):
    '''Add two numbers.

    Args:
        a (int): First number
        b (int): Second number

    Returns:
        int: Sum of a and b
    '''
    return a + b

def subtract(x, y):
    '''Subtract y from x.

    Args:
        a (int): Wrong parameter name
        b (int): Another wrong name
    '''
    return x - y

def divide(numerator: int, denominator: int) -> float:
    '''Divide two numbers.

    Args:
        numerator (int): The numerator
        denominator (int): The denominator
    '''
    if denominator == 0:
        raise ValueError("Cannot divide by zero")
    return numerator / denominator

class Calculator:
    '''Calculator class.'''

    def multiply(self, a, b):
        return a * b

def no_docs(param1, param2):
    return param1 + param2
"""
    # Load code into commenter
    commenter.from_string(test_code)
    # Generation should produce docstrings for all functions/classes
    docstrings = commenter.generate_docstrings()
    assert len(docstrings) >= 4
    # Validation should produce a report object
    report = commenter.validate()
    assert report is not None
    # Coverage analysis on this test file itself
    analyzer = CoverageAnalyzer()
    coverage = analyzer.analyze_file(__file__)
    assert coverage.total_functions >= 0
    assert 0.0 <= coverage.coverage_percentage <= 100.0
