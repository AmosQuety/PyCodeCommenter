import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from PyCodeCommenter import PyCodeCommenter
except ImportError:
    from commenter import PyCodeCommenter

class TestBackwardsCompatibility(unittest.TestCase):
    """Ensures that the v2.0 API remains compatible with basic v1.x usage."""
    
    def test_basic_generation(self):
        code = """def add(a, b):
    return a + b
"""
        commenter = PyCodeCommenter().from_string(code)
        docstrings = commenter.generate_docstrings()
        
        self.assertTrue(len(docstrings) > 0)
        self.assertIn("Args:", docstrings[0])
        self.assertIn("Returns:", docstrings[0])
        
    def test_patched_code_insertion(self):
        code = """def multiply(x: int, y: int) -> int:
    return x * y
"""
        commenter = PyCodeCommenter().from_string(code)
        patched = commenter.get_patched_code()
        
        self.assertIn('"""Multiply.', patched)
        self.assertIn('Args:', patched)
        self.assertIn('Returns:', patched)
        self.assertIn('return x * y', patched)

if __name__ == "__main__":
    unittest.main()
