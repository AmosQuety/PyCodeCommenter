import os
import sys
import pytest
import logging

# Ensure repository root is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from PyCodeCommenter import PyCodeCommenter
except ImportError:
    from commenter import PyCodeCommenter

logging.disable(logging.CRITICAL)

@pytest.fixture
def commenter():
    return PyCodeCommenter()

def test_basic_generation(commenter):
    """Ensures that the v2.0 API remains compatible with basic v1.x usage."""
    code = """def add(a, b):
    return a + b"""
    commenter.from_string(code)
    docstrings = commenter.generate_docstrings()
    assert len(docstrings) > 0
    assert "Args:" in docstrings[0]
    assert "Returns:" in docstrings[0]

def test_patched_code_insertion(commenter):
    code = """def multiply(x: int, y: int) -> int:
    return x * y"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    # verify that documentation was inserted correctly
    assert "Multiply" in patched
    assert "Args:" in patched
    assert "Returns:" in patched
    assert "return x * y" in patched
