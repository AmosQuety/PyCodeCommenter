import ast
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

def test_multiline_signature_docstring_placement(commenter):
    """Regression test for the 'multi-line signature corruption' item in
    Future Work/Vulnerabilties.md (Question 2, first CRITICAL issue).

    The audit claims get_patched_code() inserts the docstring using
    node.body[0].lineno, and that for a multi-line signature this lands
    inside the signature's continuation lines rather than after it -
    corrupting the file. This does not reproduce: Python's ast module
    resolves body[0].lineno to wherever the first real statement actually
    is, regardless of signature length (verified directly against the
    audit's own example, including a trailing comment on an argument
    line). This test locks in the current, correct behavior as a
    regression safety net.
    """
    code = (
        "def very_long_function_name(\n"
        "    argument_one: str,\n"
        "    argument_two: int,     # <-- lineno of body[0] is THIS line\n"
        "    argument_three: bool,\n"
        ") -> dict:\n"
        "    return {}\n"
    )
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    # Must remain syntactically valid; a corrupted signature would raise
    # SyntaxError here.
    tree = ast.parse(patched)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert func.name == "very_long_function_name"
    assert [a.arg for a in func.args.args] == [
        "argument_one", "argument_two", "argument_three",
    ]

    # Docstring must be the first body statement, and the original body
    # statement must survive intact right after it - not swallowed,
    # duplicated, or shifted into the signature.
    assert ast.get_docstring(func) is not None
    real_stmts = func.body[1:]
    assert len(real_stmts) == 1
    assert ast.unparse(real_stmts[0]) == "return {}"

def test_multi_function_no_line_shift_corruption(commenter):
    """Regression test for the 'line-shift insertion bug' item in
    Future Work/Vulnerabilties.md (Question 2, second CRITICAL issue).

    The audit claims that when get_patched_code() applies multiple
    insertions/replacements to the same file, line-number arithmetic on
    the mutable lines[] list can cause an edit to land on the wrong line.
    This does not reproduce: dumping the raw (start, end, content) changes
    computed for a file mixing insertions, existing-docstring replacements,
    multi-line signatures, and nested classes shows every change lands on a
    distinct, correctly source-ordered line, and reverse-order processing
    (as used here) is the standard-correct technique for this exact
    problem. This test locks in the current, correct behavior as a
    regression safety net by verifying each function's real body statement
    survives unchanged and un-shifted after patching.
    """
    code = '''def a(x, y):
    """Old doc for a."""
    return x

def b(
    x,
    y) -> int:
    return x + y

class Outer:
    """Old outer doc."""

    def m1(self, x):
        return x

    class Inner:
        def m2(
            self,
            val: int,
        ):
            """Old inner doc that is way too short."""
            return val

def c(x, y, z):
    return x

def d(
    a,
    b,
    c,
):
    """Existing docstring for d that will be regenerated because it is bad."""
    return a
'''
    commenter.from_string(code)
    patched = commenter.get_patched_code()

    # Must remain syntactically valid; a line-shift bug would typically
    # produce a SyntaxError or misplace a statement inside another scope.
    tree = ast.parse(patched)

    def first_real_stmt(node):
        body = node.body
        if body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]
        return ast.unparse(body[0]) if body else None

    functions = {}

    class _Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            functions[node.name] = first_real_stmt(node)
            self.generic_visit(node)

    _Collector().visit(tree)

    assert functions == {
        "a": "return x",
        "b": "return x + y",
        "m1": "return x",
        "m2": "return val",
        "c": "return x",
        "d": "return a",
    }
