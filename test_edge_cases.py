import os
import unittest
import logging
import sys
# Add parent directory to path to allow importing from PyCodeCommenter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from PyCodeCommenter import PyCodeCommenter
except ImportError:
    from commenter import PyCodeCommenter

# Disable logging for tests to keep output clean
logging.disable(logging.CRITICAL)

class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.commenter = PyCodeCommenter()

    def test_empty_string(self):
        """Test with an empty string."""
        self.commenter.from_string("")
        docstrings = self.commenter.generate_docstrings()
        self.assertEqual(docstrings, [])
        self.assertEqual(self.commenter.get_patched_code(), "")

    def test_syntax_error(self):
        """Test with a syntax error in the code."""
        code = "def invalid_syntax(:"
        self.commenter.from_string(code)
        docstrings = self.commenter.generate_docstrings()
        self.assertEqual(docstrings, [])
        self.assertEqual(self.commenter.get_patched_code(), code)

    def test_unicode_handling(self):
        """Test with Unicode characters in function names and strings."""
        code = """def 🚀_function(name="世界"):
    return f"Hello {name} 🚀"
"""
        self.commenter.from_string(code)
        patched = self.commenter.get_patched_code()
        self.assertIn('Args:', patched)
        self.assertIn('Returns:', patched)
        self.assertIn('世界', patched)
        self.assertIn('🚀', patched)

    def test_large_file(self):
        """Test with a large number of functions and lines."""
        functions = []
        for i in range(200):
            functions.append(f"def func_{i}(a: int, b: int) -> int:\n    return a + b + {i}")
        
        large_code = "\n\n".join(functions)
        self.commenter.from_string(large_code)
        docstrings = self.commenter.generate_docstrings()
        self.assertEqual(len(docstrings), 200)
        
        patched = self.commenter.get_patched_code()
        self.assertIn("func_199", patched)
        self.assertIn("Args:", patched)

if __name__ == "__main__":
    unittest.main()
