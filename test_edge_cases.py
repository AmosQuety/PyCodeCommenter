import os
import sys
import pytest
import logging

# Add parent directory to path to allow importing from PyCodeCommenter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from PyCodeCommenter import PyCodeCommenter
except ImportError:
    from commenter import PyCodeCommenter

logging.disable(logging.CRITICAL)

@pytest.fixture
def commenter():
    return PyCodeCommenter()

def test_empty_string(commenter):
    """Test with an empty string."""
    commenter.from_string("")
    docstrings = commenter.generate_docstrings()
    assert docstrings == []
    assert commenter.get_patched_code() == ""

def test_syntax_error(commenter):
    """Test with a syntax error in the code."""
    code = "def invalid_syntax(:"
    commenter.from_string(code)
    docstrings = commenter.generate_docstrings()
    assert docstrings == []
    assert commenter.get_patched_code() == code

def test_unicode_handling(commenter):
    """Test with Unicode characters in function names and strings."""
    code = """def 世界_function(name="世界"):
    return f"Hello {name} 🚀"
"""
    commenter.from_string(code)
    patched = commenter.get_patched_code()
    assert 'Args:' in patched
    assert 'Returns:' in patched
    assert '世界' in patched
    assert '🚀' in patched

def test_large_file(commenter):
    """Test with a large number of functions and lines."""
    functions = []
    for i in range(200):
        functions.append(f"def func_{i}(a: int, b: int) -> int:\n    return a + b + {i}")
    large_code = "\n\n".join(functions)
    commenter.from_string(large_code)
    docstrings = commenter.generate_docstrings()
    assert len(docstrings) == 200
    patched = commenter.get_patched_code()
    assert "func_199" in patched
    assert "Args:" in patched
